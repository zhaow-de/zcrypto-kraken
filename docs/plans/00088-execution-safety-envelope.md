# The execution safety envelope — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and deploy the chokepoint every future order submission must pass — two-key arming, a latching kill switch, a fail-closed venue gate, and a latching post-restart reduce-only hold — while the engine still submits nothing, and prove each refusal by construction.

**Architecture:** One pure predicate (`ExecutionGate.evaluate`) over four independently-constructible inputs, returning a level plus *every* reason that restricted it. Its inputs are a config flag, three presence-only control files under the engine state dir, and a 30-second-bounded snapshot of Kraken's public `SystemStatus`. The verdict is published as six gauges and recorded in a **new** per-cycle artifact that the Stage-6a gate evaluator provably ignores. Nothing in `cli/engine/cycle.py`'s journal path, `cli/engine/journal.py`'s schema, or `cli/engine/node.py` is modified.

**Tech Stack:** Python 3.14, uv, `prometheus_client`, `urllib.request` (stdlib, matching `cli/ohlc/fetch.py`), Typer CLI, Ansible + Grafana Alloy for delivery.

## Global Constraints

- **Nothing submits an order in this plan.** No `submit_order`, no `order_factory`, no order type is imported or constructed. If a task seems to need one, it is the wrong task.
- **`exec_enabled` keeps its current meaning** ("the exec transport is connected"). It is already `true` in production. Do not repurpose, rename, or re-document it.
- **Default closed, with no exception.** Every unreadable input, exception, timeout, or unrecognised value resolves to level `none`. There must exist no code path from an error to a permissive verdict.
- **`cli/engine/journal.py`, `CycleRecord`, `schema_version`, `validate_record`, `snapshot_content_hash`, `cli/engine/concordance.py` and `cli/engine/node.py` are NOT modified by any task.** The Stage-6a streak (measured 30 days on 2026-08-11 against a bar of 14) rests on them.
- **Control-file semantics are presence-only**: `<engine_state_dir>/exec/armed`, `<engine_state_dir>/exec/kill`, `<engine_state_dir>/exec/restart-hold`. Contents are informational and never parsed for control flow.
- **Metric names verbatim**: `zcrypto_exec_gate_level`, `zcrypto_exec_armed`, `zcrypto_exec_kill_tripped`, `zcrypto_exec_venue_ok`, `zcrypto_exec_last_evaluation_timestamp_seconds`, `zcrypto_exec_restart_hold`. Level encoding `0 = none`, `1 = reduce_only`, `2 = full`.
- **A family is published and admitted in the same change** — both directions of the trap. Nothing published stays out of the keep-list; nothing is admitted that is not published.
- **Existing `zcrypto_engine_*` families are NOT renamed.** They are live series; a rename changes series identity under `increase()`.
- **Operator-visible text carries no internal traceability tokens** (`Phase <N>`, `T<NNNN>`, `iter-<N>`, `spec <NNNNN>`) — per `.claude/rules/operator-facing-text.md`, this binds metric HELP strings, alert summaries, panel titles and `--help` text. `tests/test_internal_terms_not_operator_visible.py` enforces it.
- **Review floor is Fable for every commit** — this branch is the foundation of the live trade path.
- Commit gate is `uv run pre-commit run -a`, run to clean, with hook rewrites re-staged. Never `--no-verify`.

---

## File Structure

| File | Responsibility |
| --- | --- |
| `cli/config.py` | *modify* — add `exec_armed: bool = False` to `EngineConfig` and its validation to `_build_engine` |
| `cli/engine/venue.py` | *create* — `read_system_status()`: the public REST read, fail-closed, `opener=` injectable |
| `cli/engine/execgate.py` | *create* — `GateVerdict`, `ExecutionGate`, the control-file paths, the 30 s snapshot cache |
| `cli/engine/execledger.py` | *create* — the per-cycle execution artifact: schema, write, read |
| `cli/engine/command.py` | *modify* — `_ExecGauges`, sink composition, the restart-hold write, the `exec-status` subcommand |
| `infra/ansible/roles/engine/templates/zcrypto.toml.j2` | *modify* — render `exec_armed = false` |
| `infra/ansible/roles/capture/files/config.alloy` | *modify* — admit the six families to the keep-list |
| `infra/grafana/engine-dashboard.json`, `infra/grafana/alerts.yaml` | *modify* — panels and three rules |
| `infra/runbooks/README.md` | *modify* — one section per alert |
| `tests/test_engine_venue.py`, `tests/test_engine_execgate.py`, `tests/test_engine_execledger.py` | *create* |
| `tests/test_engine_command.py`, `tests/test_config.py`, `tests/test_engine_metrics.py` | *modify* |

---

### Task 1: The `exec_armed` config key and its rendering

**Files:**
- Modify: `cli/config.py` (`EngineConfig`, `_build_engine`)
- Modify: `infra/ansible/roles/engine/templates/zcrypto.toml.j2`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `EngineConfig.exec_armed: bool` (default `False`), read by `ExecutionGate` in Task 3.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_config.py`, matching the file's existing style for engine-table cases:

```python
def test_exec_armed_defaults_to_false_when_absent(tmp_path):
    cfg_path = tmp_path / "zcrypto.toml"
    cfg_path.write_text("[zcrypto.engine]\nexec_enabled = true\n")
    cfg = load_config(cfg_path)
    assert cfg.engine.exec_armed is False
    # The two flags are independent: connecting the transport never arms anything.
    assert cfg.engine.exec_enabled is True


def test_exec_armed_reads_true_when_set(tmp_path):
    cfg_path = tmp_path / "zcrypto.toml"
    cfg_path.write_text("[zcrypto.engine]\nexec_armed = true\n")
    assert load_config(cfg_path).engine.exec_armed is True


def test_exec_armed_rejects_a_non_boolean(tmp_path):
    cfg_path = tmp_path / "zcrypto.toml"
    cfg_path.write_text('[zcrypto.engine]\nexec_armed = "yes"\n')
    with pytest.raises(ConfigError, match="exec_armed"):
        load_config(cfg_path)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_config.py -k exec_armed -v`
Expected: **2 failed, 1 passed** — and the passing one is expected, not a mistake. The first two fail with `AttributeError: 'EngineConfig' object has no attribute 'exec_armed'`. The third **passes before the change**, because `_build_engine`'s unknown-key guard already raises `ConfigError("[zcrypto.engine] … has unknown key(s): exec_armed")`, which satisfies `match="exec_armed"`. That is a genuinely weaker assertion than it looks: it would pass whether or not the boolean validation exists. Tighten it now, before implementing:

```python
    with pytest.raises(ConfigError, match="must be a boolean"):
```

Re-run and confirm all three are red for the right reason.

- [ ] **Step 3: Add the field**

In `cli/config.py`, `EngineConfig` — place it immediately after `exec_enabled` so the two read together:

```python
    exec_enabled: bool = False
    # Whether the engine may SUBMIT. Independent of exec_enabled (which only says the transport is
    # connected) and, on its own, insufficient: arming also requires the arm file on the host, so
    # no single change can arm the live trade path.
    exec_armed: bool = False
```

- [ ] **Step 4: Add the validation**

In `_build_engine`, immediately after the `exec_enabled` block, mirroring it exactly:

```python
    if "exec_armed" in raw:
        value = raw["exec_armed"]
        if not isinstance(value, bool):
            raise ConfigError(f"[{CONFIG_TABLE}.engine].exec_armed in {config_path} must be a boolean")
        overrides["exec_armed"] = value
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/test_config.py -k exec_armed -v`
Expected: 3 passed.

- [ ] **Step 6: Render it in the deployed config, explicitly**

In `infra/ansible/roles/engine/templates/zcrypto.toml.j2`, directly below the `exec_enabled = true` line:

```jinja
exec_enabled = true
# Rendered explicitly rather than omitted so a converge diff shows the value. FALSE is the only
# value that belongs here outside an attended probe window: arming also needs the `exec/armed`
# file on the host, and the resting state is disarmed.
exec_armed = false
```

- [ ] **Step 7: Run the full suite and the commit gate**

Run: `uv run pytest -q` then `uv run pre-commit run -a`
Expected: suite green; gate clean (re-run and re-stage if a hook rewrites).

- [ ] **Step 8: Commit**

```bash
git add cli/config.py tests/test_config.py infra/ansible/roles/engine/templates/zcrypto.toml.j2
git commit -m "feat(engine): add the exec_armed config key, rendered false"
```

---

### Task 2: The venue status reader, fail-closed

**Files:**
- Create: `cli/engine/venue.py`
- Test: `tests/test_engine_venue.py`

**Interfaces:**
- Produces: `VenueStatus(status: str, ok: bool, observed_at: datetime)` and
  `read_system_status(*, now: datetime, opener=urllib.request.urlopen) -> VenueStatus`.
  Never raises. `ok` is `True` only when Kraken reported exactly `"online"`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_engine_venue.py`. The `opener=` seam mirrors `cli/ohlc/fetch.py::fetch_ohlc`, so no test touches the network:

```python
from __future__ import annotations

import io
import json
import urllib.error
from contextlib import contextmanager
from datetime import datetime, timezone

from cli.engine.venue import read_system_status

NOW = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)


def _opener_returning(payload: dict):
    @contextmanager
    def opener(url, timeout=None):
        yield io.BytesIO(json.dumps(payload).encode())

    return opener


def test_online_is_the_only_ok_status():
    st = read_system_status(now=NOW, opener=_opener_returning({"error": [], "result": {"status": "online"}}))
    assert st.ok is True
    assert st.status == "online"
    assert st.observed_at == NOW


def test_maintenance_is_not_ok():
    st = read_system_status(now=NOW, opener=_opener_returning({"error": [], "result": {"status": "maintenance"}}))
    assert st.ok is False
    assert st.status == "maintenance"


def test_cancel_only_is_not_ok():
    st = read_system_status(now=NOW, opener=_opener_returning({"error": [], "result": {"status": "cancel_only"}}))
    assert st.ok is False


def test_an_unknown_status_is_not_ok():
    # Fail closed on a value we have never seen rather than assuming it is benign.
    st = read_system_status(now=NOW, opener=_opener_returning({"error": [], "result": {"status": "wibble"}}))
    assert st.ok is False
    assert st.status == "wibble"


def test_krakens_error_array_is_not_ok_even_on_http_200():
    # Kraken returns HTTP 200 with errors in the body — the trap cli/ohlc/fetch.py documents.
    st = read_system_status(
        now=NOW, opener=_opener_returning({"error": ["EGeneral:Invalid"], "result": {"status": "online"}})
    )
    assert st.ok is False


def test_a_transport_failure_is_not_ok_and_does_not_raise():
    @contextmanager
    def failing(url, timeout=None):
        raise urllib.error.URLError("no route to host")
        yield  # pragma: no cover

    st = read_system_status(now=NOW, opener=failing)
    assert st.ok is False
    assert st.status == "unreachable"


def test_a_malformed_body_is_not_ok_and_does_not_raise():
    @contextmanager
    def garbage(url, timeout=None):
        yield io.BytesIO(b"<html>502 Bad Gateway</html>")

    st = read_system_status(now=NOW, opener=garbage)
    assert st.ok is False
    assert st.status == "unreadable"


def test_a_missing_status_key_is_not_ok():
    st = read_system_status(now=NOW, opener=_opener_returning({"error": [], "result": {}}))
    assert st.ok is False
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_engine_venue.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cli.engine.venue'`.

- [ ] **Step 3: Implement the reader**

Create `cli/engine/venue.py`:

```python
from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime

_BASE_URL = "https://api.kraken.com/0/public/SystemStatus"
_TIMEOUT_SECONDS = 10

# The only value that permits submission. Everything else -- `maintenance`, `cancel_only`,
# `post_only`, an unrecognised string, or no reading at all -- refuses. Kept as an allowlist of
# ONE rather than a denylist of known-bad states: the payload shape for an unobserved outage is
# unknown, and a denylist would silently permit whatever it failed to enumerate.
_OK_STATUS = "online"


@dataclass(frozen=True)
class VenueStatus:
    """One reading of Kraken's venue status. `ok` is the only field control flow may branch on;
    `status` exists so an operator can see WHY, including the two synthetic values below."""

    status: str  # Kraken's own string, or "unreachable" (transport) / "unreadable" (bad body)
    ok: bool
    observed_at: datetime


def read_system_status(*, now: datetime, opener=urllib.request.urlopen) -> VenueStatus:
    """Read Kraken's public SystemStatus. NEVER raises -- every failure becomes `ok=False`.

    That is the whole contract: this feeds a gate whose caller may hold the live trade key, so a
    raising reader would turn an unknown venue state into an unhandled exception at a submission
    site rather than into a refusal. `opener` is injectable for tests, matching `fetch_ohlc`.
    """
    try:
        with opener(_BASE_URL, timeout=_TIMEOUT_SECONDS) as response:
            payload = json.load(response)
    except (urllib.error.URLError, OSError, TimeoutError):
        return VenueStatus(status="unreachable", ok=False, observed_at=now)
    except Exception:  # noqa: BLE001 -- a malformed body must refuse, never propagate
        return VenueStatus(status="unreadable", ok=False, observed_at=now)

    if not isinstance(payload, dict):
        return VenueStatus(status="unreadable", ok=False, observed_at=now)
    if payload.get("error"):
        # Kraken answers HTTP 200 with errors carried in the body.
        return VenueStatus(status="unreadable", ok=False, observed_at=now)
    result = payload.get("result")
    if not isinstance(result, dict):
        return VenueStatus(status="unreadable", ok=False, observed_at=now)
    status = result.get("status")
    if not isinstance(status, str) or not status:
        return VenueStatus(status="unreadable", ok=False, observed_at=now)
    return VenueStatus(status=status, ok=status == _OK_STATUS, observed_at=now)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_engine_venue.py -v`
Expected: 8 passed.

- [ ] **Step 5: Commit**

```bash
git add cli/engine/venue.py tests/test_engine_venue.py
git commit -m "feat(engine): read Kraken's venue status, fail-closed on every failure mode"
```

---

### Task 3: The gate — level, every reason, and the 30-second snapshot bound

**Files:**
- Create: `cli/engine/execgate.py`
- Test: `tests/test_engine_execgate.py`

**Interfaces:**
- Consumes: `EngineConfig.exec_armed` (Task 1); `read_system_status`/`VenueStatus` (Task 2).
- Produces:
  - `GateLevel` — the string constants `NONE = "none"`, `REDUCE_ONLY = "reduce_only"`, `FULL = "full"`, and `LEVEL_CODE: dict[str, int]` mapping them to `0/1/2`.
  - `GateVerdict(level: str, reasons: tuple[str, ...], inputs: dict)`.
  - `exec_dir(state_dir: Path) -> Path`, `ARM_FILE`/`KILL_FILE`/`RESTART_HOLD_FILE` basenames.
  - `ExecutionGate(*, armed_in_config: bool, state_dir: Path, venue_reader=read_system_status, snapshot_max_age_seconds: float = 30.0)` with `evaluate(now: datetime) -> GateVerdict`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_engine_execgate.py`:

```python
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from cli.engine.execgate import ARM_FILE, KILL_FILE, RESTART_HOLD_FILE, ExecutionGate, GateLevel, exec_dir
from cli.engine.venue import VenueStatus

NOW = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)


def _venue(status="online", ok=True):
    def reader(*, now, opener=None):
        return VenueStatus(status=status, ok=ok, observed_at=now)

    return reader


def _all_clear(tmp_path: Path) -> ExecutionGate:
    """Every control file in its permissive state: armed present, no kill, no restart hold."""
    d = exec_dir(tmp_path)
    d.mkdir(parents=True, exist_ok=True)
    (d / ARM_FILE).touch()
    return ExecutionGate(armed_in_config=True, state_dir=tmp_path, venue_reader=_venue())


def test_all_clear_is_full(tmp_path):
    v = _all_clear(tmp_path).evaluate(NOW)
    assert v.level == GateLevel.FULL
    assert v.reasons == ()


def test_config_false_refuses_even_with_the_arm_file(tmp_path):
    d = exec_dir(tmp_path)
    d.mkdir(parents=True)
    (d / ARM_FILE).touch()
    gate = ExecutionGate(armed_in_config=False, state_dir=tmp_path, venue_reader=_venue())
    v = gate.evaluate(NOW)
    assert v.level == GateLevel.NONE
    assert "config_not_armed" in v.reasons


def test_config_true_without_the_arm_file_refuses(tmp_path):
    gate = ExecutionGate(armed_in_config=True, state_dir=tmp_path, venue_reader=_venue())
    v = gate.evaluate(NOW)
    assert v.level == GateLevel.NONE
    assert "arm_file_absent" in v.reasons


def test_the_kill_file_overrides_everything(tmp_path):
    gate = _all_clear(tmp_path)
    (exec_dir(tmp_path) / KILL_FILE).touch()
    v = gate.evaluate(NOW)
    assert v.level == GateLevel.NONE
    assert "kill_switch" in v.reasons


def test_nothing_in_the_gate_clears_the_kill_switch(tmp_path):
    # D7's latch. Evaluating repeatedly must never remove the file or stop honouring it: a kill
    # switch that self-heals is not a kill switch.
    gate = _all_clear(tmp_path)
    (exec_dir(tmp_path) / KILL_FILE).touch()
    for _ in range(5):
        assert gate.evaluate(NOW).level == GateLevel.NONE
    assert (exec_dir(tmp_path) / KILL_FILE).exists()


def test_the_kill_switch_refuses_even_when_every_other_input_is_permissive(tmp_path):
    # The override must not depend on anything else also being wrong.
    gate = _all_clear(tmp_path)
    (exec_dir(tmp_path) / KILL_FILE).touch()
    v = gate.evaluate(NOW)
    assert v.level == GateLevel.NONE
    assert v.reasons == ("kill_switch",)  # the ONLY reason — everything else was fine


def test_the_kill_switch_does_not_SUPPRESS_the_other_reasons(tmp_path):
    """The companion the test above requires, and without it the whole all-reasons property is
    unguarded in the kill quadrant.

    Writing `if kill: return GateVerdict(NONE, ("kill_switch",), {})` is the NATURAL way to
    express "kill overrides everything", and it passes every other kill test here -- including
    the one directly above, whose asserted tuple is exactly what that early return produces. The
    multi-reason test cannot catch it either, because it sets no kill file. So this is the only
    test standing between the spec's D3 and an implementation that reports one reason and sends
    the operator to remove the kill file, only to be refused again by the arm file they were
    never told about.
    """
    (exec_dir(tmp_path)).mkdir(parents=True)
    (exec_dir(tmp_path) / KILL_FILE).touch()
    gate = ExecutionGate(
        armed_in_config=False, state_dir=tmp_path, venue_reader=_venue(status="maintenance", ok=False)
    )
    v = gate.evaluate(NOW)
    assert v.level == GateLevel.NONE
    assert v.reasons == ("kill_switch", "config_not_armed", "arm_file_absent", "venue_not_online")


def test_a_venue_in_maintenance_refuses(tmp_path):
    d = exec_dir(tmp_path)
    d.mkdir(parents=True)
    (d / ARM_FILE).touch()
    gate = ExecutionGate(
        armed_in_config=True, state_dir=tmp_path, venue_reader=_venue(status="maintenance", ok=False)
    )
    v = gate.evaluate(NOW)
    assert v.level == GateLevel.NONE
    assert "venue_not_online" in v.reasons
    assert v.inputs["venue_status"] == "maintenance"


def test_a_raising_venue_reader_refuses_rather_than_propagating(tmp_path):
    d = exec_dir(tmp_path)
    d.mkdir(parents=True)
    (d / ARM_FILE).touch()

    def boom(*, now, opener=None):
        raise RuntimeError("reader blew up")

    gate = ExecutionGate(armed_in_config=True, state_dir=tmp_path, venue_reader=boom)
    v = gate.evaluate(NOW)  # must not raise
    assert v.level == GateLevel.NONE
    assert "venue_not_online" in v.reasons


def test_a_stale_snapshot_is_re_read_and_a_failed_re_read_refuses(tmp_path):
    d = exec_dir(tmp_path)
    d.mkdir(parents=True)
    (d / ARM_FILE).touch()
    calls = {"n": 0}

    def flaky(*, now, opener=None):
        calls["n"] += 1
        if calls["n"] == 1:
            return VenueStatus(status="online", ok=True, observed_at=now)
        return VenueStatus(status="unreachable", ok=False, observed_at=now)

    gate = ExecutionGate(armed_in_config=True, state_dir=tmp_path, venue_reader=flaky)
    assert gate.evaluate(NOW).level == GateLevel.FULL
    # Inside the bound: cached, no second call, still permitted.
    assert gate.evaluate(NOW + timedelta(seconds=29)).level == GateLevel.FULL
    assert calls["n"] == 1
    # Past the bound: re-read, and the re-read fails, so it refuses.
    assert gate.evaluate(NOW + timedelta(seconds=31)).level == GateLevel.NONE
    assert calls["n"] == 2


def test_a_restart_hold_caps_at_reduce_only(tmp_path):
    gate = _all_clear(tmp_path)
    (exec_dir(tmp_path) / RESTART_HOLD_FILE).write_text("2026-08-11T11:59:00Z")
    v = gate.evaluate(NOW)
    assert v.level == GateLevel.REDUCE_ONLY
    assert v.reasons == ("restart_hold",)


def test_every_applicable_reason_is_reported_not_just_the_first(tmp_path):
    # This is the live host's actual resting state: no arm file AND a restart hold. An
    # implementation that returns on the first failing check sends an operator to fix one
    # condition and leaves them still refused.
    (exec_dir(tmp_path)).mkdir(parents=True)
    (exec_dir(tmp_path) / RESTART_HOLD_FILE).touch()
    gate = ExecutionGate(
        armed_in_config=False, state_dir=tmp_path, venue_reader=_venue(status="maintenance", ok=False)
    )
    v = gate.evaluate(NOW)
    assert v.level == GateLevel.NONE
    assert v.reasons == ("config_not_armed", "arm_file_absent", "venue_not_online", "restart_hold")


def test_a_reader_that_RETURNS_garbage_refuses_rather_than_raising(tmp_path):
    # The sibling of the raising-reader case, and the easier one to get wrong: nothing about
    # `None` triggers an except clause, so an unguarded `venue.ok` raises out of evaluate().
    d = exec_dir(tmp_path)
    d.mkdir(parents=True)
    (d / ARM_FILE).touch()
    gate = ExecutionGate(armed_in_config=True, state_dir=tmp_path, venue_reader=lambda *, now: None)
    v = gate.evaluate(NOW)  # must not raise
    assert v.level == GateLevel.NONE
    assert "venue_not_online" in v.reasons


def test_a_missing_exec_dir_refuses_rather_than_raising(tmp_path):
    gate = ExecutionGate(armed_in_config=True, state_dir=tmp_path / "nope", venue_reader=_venue())
    v = gate.evaluate(NOW)
    assert v.level == GateLevel.NONE


def test_inputs_carry_every_value_the_verdict_was_derived_from(tmp_path):
    v = _all_clear(tmp_path).evaluate(NOW)
    assert v.inputs["armed_in_config"] is True
    assert v.inputs["arm_file"] is True
    assert v.inputs["kill_file"] is False
    assert v.inputs["restart_hold"] is False
    assert v.inputs["venue_status"] == "online"
    assert v.inputs["venue_snapshot_age_seconds"] == 0.0
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_engine_execgate.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cli.engine.execgate'`.

- [ ] **Step 3: Implement the gate**

Create `cli/engine/execgate.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from cli.engine.venue import VenueStatus, read_system_status

ARM_FILE = "armed"
KILL_FILE = "kill"
RESTART_HOLD_FILE = "restart-hold"

_EXEC_SUBDIR = "exec"


class GateLevel:
    """What may be submitted right now. Ordered least- to most-permissive."""

    NONE = "none"
    REDUCE_ONLY = "reduce_only"
    FULL = "full"


LEVEL_CODE: dict[str, int] = {GateLevel.NONE: 0, GateLevel.REDUCE_ONLY: 1, GateLevel.FULL: 2}


def exec_dir(state_dir: Path) -> Path:
    """The control-file directory. Presence is the whole protocol -- contents are informational."""
    return Path(state_dir) / _EXEC_SUBDIR


@dataclass(frozen=True)
class GateVerdict:
    """`reasons` is a TUPLE, not a single string, and carries EVERY condition that restricted the
    level -- several routinely apply at once (the disarmed resting state has both an absent arm
    file and a restart hold), and reporting only the first sends an operator to fix one condition
    while still refused. Order is declaration order in `_evaluate`, so output is deterministic."""

    level: str
    reasons: tuple[str, ...]
    inputs: dict = field(default_factory=dict)


class ExecutionGate:
    """The single predicate every submission must pass.

    Cheap and side-effect-free by construction so that callers evaluate it immediately before
    EVERY submission rather than once per cycle: a resting post-only order that later crosses is a
    second submission decision, taken minutes after cycle entry, by which time the arm file, the
    kill file and the venue may all have changed. The only cost is two/three `Path.exists()` calls
    plus a venue read that is cached for `snapshot_max_age_seconds`.
    """

    def __init__(
        self,
        *,
        armed_in_config: bool,
        state_dir: Path,
        venue_reader=read_system_status,
        snapshot_max_age_seconds: float = 30.0,
    ) -> None:
        self._armed_in_config = armed_in_config
        self._dir = exec_dir(state_dir)
        self._venue_reader = venue_reader
        self._max_age = snapshot_max_age_seconds
        self._snapshot: VenueStatus | None = None

    def _present(self, name: str) -> bool:
        # A missing exec dir, a permission error, a broken symlink -- all read as "absent", which
        # is the safe direction for `armed` and, for `kill`, is why the kill file's absence is
        # never load-bearing on its own: the gate still needs both arming keys.
        try:
            return (self._dir / name).exists()
        except OSError:
            return False

    def _venue(self, now: datetime) -> VenueStatus:
        snap = self._snapshot
        if snap is not None and (now - snap.observed_at).total_seconds() <= self._max_age:
            return snap
        try:
            snap = self._venue_reader(now=now)
        except Exception:  # noqa: BLE001 -- a raising reader must refuse, never propagate
            snap = VenueStatus(status="unreachable", ok=False, observed_at=now)
        # A reader that RETURNS garbage is as dangerous as one that raises: `venue.ok` on a None
        # would raise AttributeError out of evaluate(), and at a 00090 submission site an
        # unhandled exception is not a refusal -- it has no safe direction. Validate the type.
        if not isinstance(snap, VenueStatus):
            snap = VenueStatus(status="unreadable", ok=False, observed_at=now)
        self._snapshot = snap
        return snap

    def evaluate(self, now: datetime) -> GateVerdict:
        armed_file = self._present(ARM_FILE)
        kill = self._present(KILL_FILE)
        hold = self._present(RESTART_HOLD_FILE)
        venue = self._venue(now)
        age = max(0.0, (now - venue.observed_at).total_seconds())

        reasons: list[str] = []
        level = GateLevel.FULL

        # Declaration order IS the reported order. Each condition appends independently; none
        # short-circuits, because the caller needs the complete picture.
        if kill:
            reasons.append("kill_switch")
            level = GateLevel.NONE
        if not self._armed_in_config:
            reasons.append("config_not_armed")
            level = GateLevel.NONE
        if not armed_file:
            reasons.append("arm_file_absent")
            level = GateLevel.NONE
        if not venue.ok:
            reasons.append("venue_not_online")
            level = GateLevel.NONE
        if hold:
            reasons.append("restart_hold")
            if level != GateLevel.NONE:
                level = GateLevel.REDUCE_ONLY

        return GateVerdict(
            level=level,
            reasons=tuple(reasons),
            inputs={
                "armed_in_config": self._armed_in_config,
                "arm_file": armed_file,
                "kill_file": kill,
                "restart_hold": hold,
                "venue_status": venue.status,
                "venue_snapshot_age_seconds": age,
            },
        )
```

Note the reason order the tests assert is `config_not_armed, arm_file_absent, venue_not_online, restart_hold` — with `kill_switch` first when present. Match the implementation to the tests, not the prose.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_engine_execgate.py -v`
Expected: all tests in the file pass (count them from the file rather than trusting a number here). If either all-reasons test fails on ordering, fix the ORDER in `evaluate` to match the asserted tuple — **do not relax the assertion to a set or a subset check**: the order is what makes the output deterministic and diffable, and a set assertion would re-open the early-return hole the kill-suppression test exists to close.

- [ ] **Step 5: Commit**

```bash
git add cli/engine/execgate.py tests/test_engine_execgate.py
git commit -m "feat(engine): the execution gate — default closed, every reason reported"
```

---

### Task 4: The restart hold, written at startup and cleared only by a human

**Files:**
- Modify: `cli/engine/command.py` (in `run()`, before the node is built)
- Test: `tests/test_engine_command.py`

**Interfaces:**
- Consumes: `exec_dir`, `RESTART_HOLD_FILE` (Task 3).
- Produces: `write_restart_hold(state_dir: Path, started_at: datetime) -> Path` in `cli/engine/execgate.py`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_engine_execgate.py`:

```python
def test_write_restart_hold_creates_the_marker_and_the_dir(tmp_path):
    from cli.engine.execgate import write_restart_hold

    p = write_restart_hold(tmp_path, NOW)
    assert p.exists()
    assert p.name == RESTART_HOLD_FILE
    assert "2026-08-11T12:00:00" in p.read_text()  # informational only


def test_write_restart_hold_is_idempotent_and_restamps(tmp_path):
    from cli.engine.execgate import write_restart_hold

    write_restart_hold(tmp_path, NOW)
    later = NOW + timedelta(hours=3)
    p = write_restart_hold(tmp_path, later)
    assert "15:00:00" in p.read_text()  # the newest restart owns the marker


def test_nothing_in_the_gate_clears_the_restart_hold(tmp_path):
    # The latch is the point: only a human removes it. Evaluating many times must never clear it.
    gate = _all_clear(tmp_path)
    (exec_dir(tmp_path) / RESTART_HOLD_FILE).touch()
    for _ in range(5):
        assert gate.evaluate(NOW).level == GateLevel.REDUCE_ONLY
    assert (exec_dir(tmp_path) / RESTART_HOLD_FILE).exists()
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_engine_execgate.py -k restart -v`
Expected: FAIL — `ImportError: cannot import name 'write_restart_hold'`.

- [ ] **Step 3: Implement**

Append to `cli/engine/execgate.py`:

```python
def write_restart_hold(state_dir: Path, started_at: datetime) -> Path:
    """Latch `reduce_only` for this process. Written unconditionally on every engine start.

    After a restart -- a converge, the supervision watchdog's `os._exit(1)`, a host reboot -- what
    has NOT been re-established is the engine's belief about what it holds, so holding at
    reduce-only until a human says otherwise is the honest response. Nothing in this module
    removes it; a later spec may add a further PRECONDITION to clearing (e.g. reconciliation
    agrees), never a path that clears it without the human.

    The timestamp is informational: it lets an operator tell which restart the marker belongs to.
    """
    d = exec_dir(state_dir)
    d.mkdir(parents=True, exist_ok=True)
    path = d / RESTART_HOLD_FILE
    path.write_text(started_at.isoformat())
    return path
```

- [ ] **Step 4: Call it at engine startup**

In `cli/engine/command.py`'s `run()`, immediately after the config is resolved and **before** the node is built, add:

```python
    # Every start latches reduce-only. Deliberately unconditional: an engine that has just come
    # up must not be able to widen its own permission.
    write_restart_hold(config.journal_dir.parent, _utc_now())
```

Use the same state-dir root the journal and store share (`journal_dir.parent` is `<engine_state_dir>` on the deployed host, per the role's template) and `run()`'s own local name for the config, which is `config`. Import `write_restart_hold` from `cli.engine.execgate` at the top of the file.

- [ ] **Step 5: Test the WIRING, not just the function**

The function's own tests do not prove `run()` calls it, and the failure mode is silent: passing `config.journal_dir` instead of `config.journal_dir.parent` writes the hold to `<journal>/exec/restart-hold` while the gate reads `<state>/exec/restart-hold`. The hold is then permanently invisible, D6 is disarmed, and **every test above still passes**. Add to `tests/test_engine_command.py`, reusing that file's existing stubbed-node `run()` machinery (the "passable `engine run` environment" fixture):

```python
def test_engine_startup_latches_the_restart_hold(tmp_path, ...):
    # ... set up the passable run environment with journal_dir = tmp_path / "journal"
    # ... invoke run() with the node stubbed so it returns immediately
    assert (tmp_path / "exec" / "restart-hold").exists(), (
        "the hold must land beside the journal, not inside it — a hold the gate cannot see is no hold"
    )
```

- [ ] **Step 6: Run the tests**

Run: `uv run pytest tests/test_engine_execgate.py tests/test_engine_command.py -v`
Expected: all green.

- [ ] **Step 7: Commit**

```bash
git add cli/engine/execgate.py cli/engine/command.py tests/test_engine_execgate.py tests/test_engine_command.py
git commit -m "feat(engine): latch reduce-only on every engine start"
```

---

### Task 5: The execution ledger, and the proof it cannot break the concordance streak

**Files:**
- Create: `cli/engine/execledger.py`
- Test: `tests/test_engine_execledger.py`

**Interfaces:**
- Consumes: `GateVerdict` (Task 3).
- Produces: `write_exec_record(journal_dir: Path, cycle_ts: datetime, verdict: GateVerdict, *, evaluated_at: datetime) -> Path`
  writing `<journal_dir>/<YYYY-MM-DD>/exec-<HH>.json`, and `read_exec_record(path) -> dict`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_engine_execledger.py`:

```python
from __future__ import annotations

import json
from datetime import datetime, timezone

from cli.engine.execgate import GateLevel, GateVerdict
from cli.engine.execledger import EXEC_SCHEMA_VERSION, read_exec_record, write_exec_record

CYCLE_TS = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)


def _verdict():
    return GateVerdict(
        level=GateLevel.NONE,
        reasons=("arm_file_absent", "restart_hold"),
        inputs={"armed_in_config": False, "venue_status": "online"},
    )


def test_the_record_lands_beside_the_cycle_record_and_is_named_for_the_hour(tmp_path):
    p = write_exec_record(tmp_path, CYCLE_TS, _verdict(), evaluated_at=CYCLE_TS)
    assert p == tmp_path / "2026-08-11" / "exec-12.json"
    assert p.exists()


def test_the_record_carries_the_verdict_its_reasons_and_an_empty_submission_list(tmp_path):
    p = write_exec_record(tmp_path, CYCLE_TS, _verdict(), evaluated_at=CYCLE_TS)
    doc = json.loads(p.read_text())
    assert doc["schema_version"] == EXEC_SCHEMA_VERSION
    assert doc["level"] == "none"
    assert doc["reasons"] == ["arm_file_absent", "restart_hold"]
    assert doc["submitted"] == []  # by construction in this spec: nothing can submit
    assert doc["inputs"]["venue_status"] == "online"


def test_round_trips(tmp_path):
    p = write_exec_record(tmp_path, CYCLE_TS, _verdict(), evaluated_at=CYCLE_TS)
    assert read_exec_record(p)["level"] == "none"


def test_exec_records_are_invisible_to_every_journal_glob(tmp_path):
    """The load-bearing invariant of this whole spec, tested where it actually lives.

    `evaluate_gate` takes a list of CycleOutcome objects, NOT a directory -- it never globs at all,
    so testing it directly would prove nothing. The globbing is `cli/engine/command.py`'s
    `_journal_artifacts`, and it derives the hour from `path.stem.rsplit("-", 1)[-1]`: `exec-12`
    yields "12", a perfectly valid boundary. The ONLY thing keeping an exec record out of the
    concordance universe is that every call site globs `cycle-*.json` / `failed-cycle-*.json` and
    our prefix is neither. This test is what keeps that true.

    (There are eight `_journal_artifacts` call sites -- seven in `cli/engine/command.py`, one in
    `cli/engine/soak.py` -- plus `cli/engine/cycle.py`'s own direct `*/cycle-*.json` back-search.
    Verify by grep rather than trusting this count, which rots.)
    """
    from cli.engine.command import _journal_artifacts

    day = tmp_path / "2026-08-11"
    day.mkdir(parents=True)
    for hh in (0, 4, 8, 12, 16, 20):
        (day / f"cycle-{hh:02d}.json").write_text("{}")
        write_exec_record(tmp_path, CYCLE_TS.replace(hour=hh), _verdict(), evaluated_at=CYCLE_TS)

    # Non-vacuity first: the fixture really did write exec records next to the cycle records.
    assert len(list(day.glob("exec-*.json"))) == 6

    records = _journal_artifacts(tmp_path, "*", "cycle-*.json")
    sidecars = _journal_artifacts(tmp_path, "*", "failed-cycle-*.json")
    assert len(records) == 6
    assert sidecars == []
    assert all("exec" not in p.name for _, p in records)


def test_the_exec_prefix_would_be_swept_up_by_a_looser_glob(tmp_path):
    """Guards the reason the test above passes, so a future `*.json` glob fails loudly here
    rather than silently resetting the streak. If this test ever needs changing, the change is a
    decision about the concordance universe -- not a test fix."""
    from cli.engine.command import _journal_artifacts

    day = tmp_path / "2026-08-11"
    day.mkdir(parents=True)
    write_exec_record(tmp_path, CYCLE_TS, _verdict(), evaluated_at=CYCLE_TS)
    swept = _journal_artifacts(tmp_path, "*", "*.json")
    assert len(swept) == 1  # a loose glob DOES pick it up, with a parsed boundary
    assert swept[0][0].hour == 12
```

- [ ] **Step 1b: Write the INTEGRATION test — the one that survives a loosened glob**

The two tests above pin *filename disjointness*. They do **not** pin what the call sites pass: if someone later widens a call site's glob argument to `"*.json"`, both stay green (the names are still disjoint; the loose-glob canary still sweeps). The regression that would actually reset the streak therefore needs a test that drives the **real report path** — `report` → `_evaluate_journal` → the call-site globs → `evaluate_gate` — and compares its output with and without execution records present.

Add to `tests/test_engine_command.py`, building on that file's existing report/gate fixture rather than hand-rolling journal JSON (the record shape is `CycleRecord` schema v1 and must come from `cli/engine/journal.py`'s own constructors):

```python
def test_execution_records_do_not_change_the_gate_report(tmp_path, ...):
    # ... build a journal of complete clean days using the file's existing helper
    before = runner.invoke(app, ["engine", "report", "--journal-dir", str(journal)])
    assert before.exit_code == 0

    for day_dir in sorted(journal.glob("20*-*-*")):
        cycle_ts = ...  # each boundary in that day
        write_exec_record(journal, cycle_ts, _refusing_verdict(), evaluated_at=cycle_ts)
    assert list(journal.glob("*/exec-*.json")), "fixture wrote no exec records — the test is vacuous"

    after = runner.invoke(app, ["engine", "report", "--journal-dir", str(journal)])
    assert after.exit_code == 0
    assert after.stdout == before.stdout, (
        "a refusal to trade changed the concordance report — the streak is no longer immune"
    )
```

**Non-vacuity matters here more than usual**: assert the fixture actually wrote exec records *before* comparing, or a test that writes nothing passes trivially and certifies nothing.

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_engine_execledger.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cli.engine.execledger'`.

- [ ] **Step 3: Implement**

Create `cli/engine/execledger.py`:

```python
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from cli.engine.execgate import GateVerdict

EXEC_SCHEMA_VERSION = 1

# Deliberately NOT `cycle-<HH>.json` and NOT a `failed-cycle-*` sidecar. The Stage-6a streak is
# scored off those two names, and a refusal to trade is not a broken research day -- the cycle
# computed its targets correctly and simply was not permitted to act. Keeping execution outcomes
# in a separate file with a separate prefix makes that structural rather than a matter of care.
_PREFIX = "exec"


def exec_record_path(journal_dir: Path, cycle_ts: datetime) -> Path:
    return Path(journal_dir) / f"{cycle_ts:%Y-%m-%d}" / f"{_PREFIX}-{cycle_ts:%H}.json"


def write_exec_record(
    journal_dir: Path, cycle_ts: datetime, verdict: GateVerdict, *, evaluated_at: datetime
) -> Path:
    path = exec_record_path(journal_dir, cycle_ts)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = {
        "schema_version": EXEC_SCHEMA_VERSION,
        "cycle_ts": cycle_ts.isoformat(),
        "evaluated_at": evaluated_at.isoformat(),
        "level": verdict.level,
        "reasons": list(verdict.reasons),
        "inputs": dict(verdict.inputs),
        # Empty by construction while nothing can submit. The key exists from schema 1 so the
        # first spec that DOES submit adds rows, never a field.
        "submitted": [],
    }
    path.write_text(json.dumps(doc, indent=2, sort_keys=True))
    return path


def read_exec_record(path: Path) -> dict:
    return json.loads(Path(path).read_text())
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/test_engine_execledger.py -v`
Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add cli/engine/execledger.py tests/test_engine_execledger.py
git commit -m "feat(engine): the execution ledger, structurally invisible to the stage gate"
```

---

### Task 6: The six gauges, wired through the existing metrics sink

**Files:**
- Modify: `cli/engine/command.py` (`_ExecGauges`, and the sink installed in `run()`)
- Test: `tests/test_engine_metrics.py`

**Interfaces:**
- Consumes: `ExecutionGate`, `GateVerdict`, `LEVEL_CODE` (Task 3); `write_exec_record` (Task 5).
- Produces: nothing consumed by later tasks in this plan.

**Why the sink and not `run_cycle`:** `cli/engine/cycle.py::set_metrics_sink` already delivers `(CycleResult, completed_at, duration_seconds)` after every cycle's artifact is written, and its exceptions are already isolated and logged. Reusing it means **`cycle.py`, `node.py` and the journal are untouched** — no change to the fenced node tests, no change to the live cycle path. The gate is therefore evaluated at cycle *completion* in this spec; moving evaluation to each submission point is 00090's job and is what the gate's cheap, side-effect-free design exists to allow.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_engine_metrics.py`, following that file's existing registry-inspection style:

```python
def test_exec_gauges_publish_the_verdict(tmp_path):
    from prometheus_client import CollectorRegistry

    from cli.engine.command import _ExecGauges
    from cli.engine.execgate import GateLevel, GateVerdict

    reg = CollectorRegistry()
    g = _ExecGauges(reg)
    g.update(
        GateVerdict(
            level=GateLevel.REDUCE_ONLY,
            reasons=("restart_hold",),
            inputs={
                "armed_in_config": True,
                "arm_file": True,
                "kill_file": False,
                "restart_hold": True,
                "venue_status": "online",
                "venue_snapshot_age_seconds": 4.0,
            },
        )
    )
    assert reg.get_sample_value("zcrypto_exec_gate_level") == 1
    assert reg.get_sample_value("zcrypto_exec_armed") == 1
    assert reg.get_sample_value("zcrypto_exec_kill_tripped") == 0
    assert reg.get_sample_value("zcrypto_exec_restart_hold") == 1
    assert reg.get_sample_value("zcrypto_exec_venue_ok") == 1
    assert reg.get_sample_value("zcrypto_exec_last_evaluation_timestamp_seconds") == NOW.timestamp()


def test_armed_requires_BOTH_keys(tmp_path):
    from prometheus_client import CollectorRegistry

    from cli.engine.command import _ExecGauges
    from cli.engine.execgate import GateLevel, GateVerdict

    for cfg_armed, file_armed in ((True, False), (False, True), (False, False)):
        reg = CollectorRegistry()
        _ExecGauges(reg).update(
            GateVerdict(
                level=GateLevel.NONE,
                reasons=("x",),
                inputs={
                    "armed_in_config": cfg_armed,
                    "arm_file": file_armed,
                    "kill_file": False,
                    "restart_hold": False,
                    "venue_status": "online",
                    "venue_snapshot_age_seconds": 0.0,
                },
            )
        )
        assert reg.get_sample_value("zcrypto_exec_armed") == 0


def test_the_heartbeat_series_is_absent_until_an_evaluation_exists(tmp_path):
    # `_CycleGauges` precedent: an absent series is honest, a published 0 is a claim. Before any
    # venue read, "the snapshot is 0 seconds old" would assert a reading that never happened.
    from prometheus_client import CollectorRegistry

    from cli.engine.command import _ExecGauges

    reg = CollectorRegistry()
    _ExecGauges(reg)  # constructed, never updated
    assert reg.get_sample_value("zcrypto_exec_last_evaluation_timestamp_seconds") is None
    # gate_level seeds at 0 = "nothing may be submitted", which is true of a process that has not
    # evaluated anything yet. The other presence gauges also seed at 0, which is NOT necessarily
    # true — hence the startup evaluation in Step 4b.
    assert reg.get_sample_value("zcrypto_exec_gate_level") == 0
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_engine_metrics.py -k exec -v`
Expected: FAIL — `ImportError: cannot import name '_ExecGauges'`.

- [ ] **Step 3: Implement the gauges**

In `cli/engine/command.py`, beside `_CycleGauges`:

```python
class _ExecGauges:
    """The execution envelope's published state. Built on the SAME registry the exporter serves,
    exactly as `_CycleGauges` is, and updated from the gate's verdict after every cycle.

    `zcrypto_exec_gate_level` is registered EAGERLY and seeded at 0: before anything is evaluated,
    "nothing may be submitted" is the true state, not an unmeasured claim -- the engine really is
    refusing. The other presence gauges are eager for the same reason, and `run()` evaluates once
    at startup so none of them sits at its seeded default: a `kill_tripped` reading 0 while the
    kill file exists is not a stale gauge, it is a false statement about the safety envelope.
    `last_evaluation` is LAZY for `_CycleGauges.cycle_duration`'s reason: a published 0 before any
    evaluation would claim the gate was last read at the Unix epoch, and an absent series is
    honest where a zero is a lie -- which matters doubly here, since the staleness alert reads
    this series and a seeded 0 would page instantly on every fresh process.
    """

    def __init__(self, registry) -> None:
        self._registry = registry
        self.gate_level = Gauge(
            "zcrypto_exec_gate_level",
            "What the engine may submit right now: 0 = nothing, 1 = reducing orders only, 2 = anything.",
            registry=registry,
        )
        self.armed = Gauge(
            "zcrypto_exec_armed",
            "Whether both arming keys are present (the config flag and the arm file on the host).",
            registry=registry,
        )
        self.kill_tripped = Gauge(
            "zcrypto_exec_kill_tripped", "Whether the kill switch file is present.", registry=registry
        )
        self.restart_hold = Gauge(
            "zcrypto_exec_restart_hold",
            "Whether this process is still held at reducing-only after a restart.",
            registry=registry,
        )
        self.venue_ok = Gauge(
            "zcrypto_exec_venue_ok", "Whether the last venue reading said the exchange is online.", registry=registry
        )
        # The envelope's heartbeat, and the ONLY series that can answer "is the gate still being
        # evaluated at all". A snapshot-AGE gauge was rejected: evaluations are hours apart and the
        # snapshot bound is 30 s, so every evaluation re-reads and the age would publish ~0 forever
        # -- a constant wearing a measurement's clothes. Lazy for `_CycleGauges.cycle_duration`'s
        # reason: before the first evaluation there is no timestamp to state.
        self.last_evaluation: Gauge | None = None

    def update(self, verdict, *, evaluated_at) -> None:
        i = verdict.inputs
        self.gate_level.set(LEVEL_CODE[verdict.level])
        self.armed.set(1 if (i["armed_in_config"] and i["arm_file"]) else 0)
        self.kill_tripped.set(1 if i["kill_file"] else 0)
        self.restart_hold.set(1 if i["restart_hold"] else 0)
        self.venue_ok.set(1 if i["venue_status"] == "online" else 0)
        if self.last_evaluation is None:
            self.last_evaluation = Gauge(
                "zcrypto_exec_last_evaluation_timestamp_seconds",
                "Unix timestamp the execution gate was last evaluated.",
                registry=self._registry,
            )
        self.last_evaluation.set(evaluated_at.timestamp())
```

Import `LEVEL_CODE` from `cli.engine.execgate` at the top of the file.

- [ ] **Step 4: Compose it into the installed sink**

In `run()`, where `set_metrics_sink(gauges.update)` is currently installed, build the gate and an exec-aware sink instead. Read the existing installation site first and keep its structure; the shape is:

**Read `run()` before writing this.** The existing `set_metrics_sink(gauges.update)` sits *inside* `if port is not None:` — the metrics opt-in. Composing the exec work into that call site would make the **execution ledger a side effect of telemetry being switched on**: production sets `ZCRYPTO_METRICS_PORT` (verified in `compose.yaml.j2`), but a manual `zcrypto engine run` on the host does not, and would then journal cycles with no execution record and no error. Spec D5 requires the ledger unconditionally, and 00090 extends this same artifact with the list of orders actually submitted — inheriting the coupling would let a misconfigured engine trade with no record of it.

So the sink is installed **unconditionally**, and only the gauge update is conditional on a registry existing. Use `run()`'s own local names (the config local is `config`, not `cfg`):

```python
    # Built regardless of telemetry: the ledger is a forensic artifact, not a metric.
    gate = ExecutionGate(armed_in_config=config.exec_armed, state_dir=config.journal_dir.parent)
    exec_gauges = _ExecGauges(registry) if registry is not None else None

    def _sink(result, completed_at, duration_seconds):
        if cycle_gauges is not None:
            cycle_gauges.update(result, completed_at, duration_seconds)
        verdict = gate.evaluate(completed_at)
        if exec_gauges is not None:
            exec_gauges.update(verdict, evaluated_at=completed_at)
        write_exec_record(config.journal_dir, result.cycle_ts, verdict, evaluated_at=completed_at)

    set_metrics_sink(_sink)
```

This requires hoisting two locals out of the `if port is not None:` block — `registry` (initialise to `None` before it) and the `_CycleGauges` instance (call it `cycle_gauges`, also `None` when telemetry is off) — so the existing behaviour is preserved exactly when the port is unset: no registry, no cycle gauges, no metrics server, and now additionally a sink that still writes the ledger. **Do not change what `_CycleGauges` does or when it is seeded.**

`cycle.py::_update_metrics` already wraps the sink in try/except-and-log, so a failure here can never affect the cycle or its journal artifact — the isolation invariant that file documents. It calls `logger.exception`, so a raising gate evaluation or a failed ledger write surfaces as an ERROR line that the existing `zcrypto-engine-error-logs` rule pages on: the swallow is loud, not silent, and that is load-bearing for this design rather than luck.

- [ ] **Step 4b: Evaluate ONCE at startup, or every latch lies for up to four hours**

The sink fires only at cycle completion — every four hours. Without a startup evaluation, all five eager gauges sit at their seeded `0` from process start until the first completion, and the consequences are not cosmetic:

- After any restart, `zcrypto_exec_restart_hold` reads **0** while the hold file that the *same process just wrote* is present.
- A kill switch engaged across a restart (the supervision watchdog's `os._exit(1)` is a routine path) makes `zcrypto_exec_kill_tripped` drop 1→0, **resolving the alert**, then re-fire hours later. The alert exists because the failure mode is forgetting — a built-in invisibility window is precisely wrong.

So immediately after `set_metrics_sink(_sink)`, add:

```python
    # One evaluation at startup so no latch gauge sits at its seeded default. Inside the same
    # isolation the sink enjoys: telemetry must never be able to stop the engine from starting.
    if exec_gauges is not None:
        try:
            now = _utc_now()
            exec_gauges.update(gate.evaluate(now), evaluated_at=now)
        except Exception:  # noqa: BLE001
            logger.exception("startup execution-gate evaluation failed")
```

This costs one public REST call per process start. It does **not** make the gauges live between cycles — that bound is stated in the spec's bounded claims, made *visible* by the heartbeat gauge, and drilled through `exec-status` instead.

- [ ] **Step 4c: Test the composition, not just the pieces**

`_ExecGauges.update` is tested with hand-built verdicts, but the closure above is the ledger's only production writer and `_update_metrics` swallows its exceptions by design — so a broken composition fails **silently in production**. Using the same stubbed-`run()` fixture as Task 4:

```python
def test_a_completed_cycle_writes_an_exec_record_and_moves_the_gauges(tmp_path, ...):
    # ... run one cycle through the stubbed node
    assert list((tmp_path / "journal").glob("*/exec-*.json")), "the sink never wrote an exec record"
    # and the startup evaluation alone must already have published a truthful restart hold:
    assert registry.get_sample_value("zcrypto_exec_restart_hold") == 1
```

- [ ] **Step 5: Run the tests**

Run: `uv run pytest tests/test_engine_metrics.py tests/test_engine_command.py -v`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add cli/engine/command.py tests/test_engine_metrics.py
git commit -m "feat(engine): publish the execution envelope's state and record it per cycle"
```

---

### Task 7: `zcrypto engine exec-status`

**Files:**
- Modify: `cli/engine/command.py`
- Modify: `README.md` (the `## Usage` section)
- Test: `tests/test_engine_command.py`

**Interfaces:**
- Consumes: `ExecutionGate` (Task 3).

- [ ] **Step 1: Write the failing test**

Add to `tests/test_engine_command.py`, following that file's `CliRunner` style:

```python
def test_exec_status_prints_the_level_and_every_reason(tmp_path, monkeypatch):
    from cli.engine.execgate import exec_dir

    exec_dir(tmp_path).mkdir(parents=True)
    (exec_dir(tmp_path) / "restart-hold").touch()
    # --state-dir makes the config's journal_dir irrelevant here; the venue read is stubbed so no
    # test touches the network. Patch the symbol as imported INTO command.py, not at its source.
    monkeypatch.setattr(
        "cli.engine.command.read_system_status",
        lambda *, now, opener=None: VenueStatus(status="unreachable", ok=False, observed_at=now),
    )
    result = runner.invoke(app, ["engine", "exec-status", "--state-dir", str(tmp_path)])
    assert result.exit_code == 0
    assert "level=none" in result.stdout
    assert "arm_file_absent" in result.stdout
    assert "restart_hold" in result.stdout
```

**Implementer note:** the monkeypatch is deliberate and the alternative was rejected — do **not** add a `--no-venue-check` flag. A flag that skips a safety check is a flag someone eventually passes in production, and this command's whole value is reporting the truth about whether the engine may trade. `ExecutionGate` takes `venue_reader` precisely so tests need no such flag.

The command must therefore accept the injected reader in production code too: have `exec_status` construct `ExecutionGate(..., venue_reader=read_system_status)` explicitly, importing `read_system_status` into `cli/engine/command.py` so the monkeypatch above has a symbol to replace.

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_engine_command.py -k exec_status -v`
Expected: FAIL — no such command.

- [ ] **Step 3: Implement the command**

The Typer app in this module is `engine_app`, not `app`; config is loaded through the file's own `_load_engine_config()` helper so a bad config aborts cleanly instead of printing a traceback; and `venue_reader` is passed **explicitly** — without it the monkeypatch in Step 1 replaces an unused name, the test silently calls `api.kraken.com` for real, and it *still passes* (offline the read returns `unreachable`, online the missing arm file forces `none` anyway, so all three asserted substrings appear either way). A test that passes in both worlds is not a test.

```python
@engine_app.command("exec-status")
def exec_status(
    state_dir: Optional[Path] = typer.Option(None, "--state-dir", help="Engine state directory."),
) -> None:
    """Report whether the engine may submit orders right now, and everything that decided it."""
    config = _load_engine_config()
    root = state_dir if state_dir is not None else config.journal_dir.parent
    gate = ExecutionGate(
        armed_in_config=config.exec_armed,
        state_dir=root,
        venue_reader=read_system_status,  # explicit so tests can substitute it — see Step 1
    )
    verdict = gate.evaluate(_utc_now())
    typer.echo(f"level={verdict.level}")
    typer.echo(f"reasons={','.join(verdict.reasons) or '-'}")
    for key, value in sorted(verdict.inputs.items()):
        typer.echo(f"  {key}={value}")
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/test_engine_command.py -v`
Expected: green.

- [ ] **Step 5: Document it in README `## Usage`**

Add `zcrypto engine exec-status` beside the other engine subcommands, with its `--state-dir` option — required by `.claude/rules/readme-usage.md` in the same change.

- [ ] **Step 6: Run the operator-text guard and the gate**

Run: `uv run pytest tests/test_internal_terms_not_operator_visible.py -v` then `uv run pre-commit run -a`
Expected: green — no `T<NNNN>`/spec serial reached a help string.

- [ ] **Step 7: Commit**

```bash
git add cli/engine/command.py tests/test_engine_command.py README.md
git commit -m "feat(engine): add exec-status, the operator's view of the envelope"
```

---

### Task 8: Delivery — Alloy admission, panels, alert rules, runbook

**Files:**
- Modify: `infra/ansible/roles/capture/files/config.alloy` (the keep-list `regex`)
- Modify: `infra/grafana/engine-dashboard.json` (the `zcrypto-engine` board), `infra/grafana/alerts.yaml`
- Modify: `infra/runbooks/README.md`
- Test: the repo's existing dashboard/alert coverage tests

- [ ] **Step 1: Admit the six families**

Append to the single `regex` in the `write_relabel_config` keep block of `infra/ansible/roles/capture/files/config.alloy` (the engine is scraped there as job `engine_app`):

`|zcrypto_exec_gate_level|zcrypto_exec_armed|zcrypto_exec_kill_tripped|zcrypto_exec_venue_ok|zcrypto_exec_last_evaluation_timestamp_seconds|zcrypto_exec_restart_hold`

- [ ] **Step 2: Verify both directions of the admission trap**

Run: `uv run pytest tests/test_infra_alloy_series.py tests/test_dashboards_cover_metrics.py tests/test_infra_alert_rules.py -v`

`test_infra_alloy_series.py` is the keep-list walker and `test_dashboards_cover_metrics.py` is the panel-coverage walker. Expected: every published `zcrypto_exec_*` name is admitted **and** drawn, and no admitted name is unpublished. If either test does not currently enumerate engine-app families, extend it in this task rather than asserting by eye — an unadmitted family reads as `NoData` forever and the alert rules in Step 4 would never fire.

- [ ] **Step 3: Add panels to the Engine board**

Add a row to `infra/grafana/engine-dashboard.json` (uid `zcrypto-engine`; boards live flat under `infra/grafana/`, there is no `dashboards/` subdirectory): gate level (with the 0/1/2 mapping as value mappings, not a raw number), armed, kill tripped, restart hold, venue ok, and the heartbeat rendered as an age (`time() - zcrypto_exec_last_evaluation_timestamp_seconds`) rather than a raw epoch. Titles carry no internal tokens.

- [ ] **Step 4: Add the two alert rules**

In `infra/grafana/alerts.yaml`. Copy the surrounding rules' full structure (`data:` blocks, `condition`, `folderUID`, `orgId`, `notification_settings`) from an adjacent `zcrypto-engine` rule rather than inventing it — only the parts below are specific to this task:

```yaml
  - uid: zcrypto-engine-exec-armed-too-long
    title: "Engine · order submission has been armed for over six hours"
    # min_over_time == 1 means it was armed for the WHOLE window: a single dip to 0 (a disarm)
    # clears it. `> 0` on an average would fire on a brief, correct probe window.
    #   expr: min_over_time(zcrypto_exec_armed[6h]) == 1
    for: 15m
    annotations:
      summary: "The engine has been armed to submit orders continuously for more than six hours. Arming is expected only inside an attended probe window and is normally removed when it ends, so this most likely means an arm was left on. Deleting the arm file on the engine host disarms it immediately, with no deploy and no restart. This is not itself an incident — several other conditions must also be permissive before anything could be submitted — but an engine left armed removes one of the two keys that are supposed to stand between a mistake and real money. Runbook: infra/runbooks/README.md#zcrypto-engine-exec-armed-too-long"
    labels:
      severity: warning

  - uid: zcrypto-engine-exec-kill-tripped
    title: "Engine · the execution kill switch is engaged"
    #   expr: zcrypto_exec_kill_tripped == 1
    for: 5m
    annotations:
      summary: "The execution kill switch is engaged, so the engine will refuse to submit any order until it is removed. This is a deliberate state and firing does not mean anything is broken — the alert exists because the failure mode is forgetting, not tripping. If the switch was engaged deliberately and the reason still holds, silence this for the expected duration; otherwise remove the kill file on the engine host. Runbook: infra/runbooks/README.md#zcrypto-engine-exec-kill-tripped"
    labels:
      severity: warning

  - uid: zcrypto-engine-exec-not-evaluated
    title: "Engine · the execution safety gate has stopped being evaluated"
    # The rule that catches the one failure nothing else can see: a regression that drops the
    # gate evaluation from the cycle path freezes all six gauges at their last values, cycle
    # telemetry stays healthy, and every dashboard reads green while the envelope is gone.
    # Follows zcrypto-gate-exporter-stale's shape. Threshold = one cycle interval plus slack.
    # noDataState MUST be Alerting: a gate that never published at all is this rule's worst
    # case, not an exemption from it.
    #   expr: time() - zcrypto_exec_last_evaluation_timestamp_seconds   > 17100   (4 h 45 m)
    for: 10m
    annotations:
      summary: "The engine has not evaluated its execution safety gate for more than four and three quarter hours, so every published value describing whether it may trade is frozen at whatever it last read. Nothing else reports this: the cycle metrics can look perfectly healthy while the safety gate is no longer consulted at all, and a stale reading of `disarmed` is indistinguishable from a live one. Check that cycles are still completing, then read the current state directly on the engine host with the exec-status command rather than trusting the dashboard. Runbook: infra/runbooks/README.md#zcrypto-engine-exec-not-evaluated"
    labels:
      severity: warning
```

All three `receiver: metrics`, all carrying `__dashboardUid__: "zcrypto-engine"` and their panel id. The file's evaluators are threshold `gt`/`lt`, so an `== 1` condition is written as `gt 0.5` in the copied `data:` block, and the sibling engine rules' `{host="zcrypto"}` selector is matched. **No internal traceability tokens in any summary** — `tests/test_internal_terms_not_operator_visible.py` enforces this and these three strings are exactly the surface it guards.

- [ ] **Step 5: Write the three runbook sections**

In `infra/runbooks/README.md`, one section per rule with an explicit `<a name=...>` anchor matching the summary's link, and the file's four required parts — what you are seeing / what it means / what to do / **retire when**.

Two things every section must say, because the telemetry cannot: **`reasons` never reaches Grafana and `zcrypto_exec_armed` deliberately conflates its two keys**, so remote dashboards can show *that* the engine is disarmed but never *which* key is missing — the next diagnostic step is always `zcrypto engine exec-status` on the host. And the retire-when for the armed-too-long rule must state that it is *replaced* when the engine begins arming continuously, not silenced.

- [ ] **Step 6: Run the commit gate**

Run: `uv run pre-commit run -a` (yamllint and mdformat both bite here) then `uv run pytest -q`.

- [ ] **Step 7: Commit**

```bash
git add infra/ansible/roles/capture/files/config.alloy infra/grafana/ infra/runbooks/README.md
git commit -m "feat(engine): admit, chart and alert on the execution envelope"
```

---

### Task 9: Mutation probes — prove each guard by removing it

**Files:** none changed if all probes are killed; fixes here otherwise.

- [ ] **Step 1: Run each probe through the repo's harness**

Use `infra/scripts/mutate-probe.sh` (never a hand-rolled mutate-and-restore loop — it refuses a dirty tree, refuses a no-op sed, refuses a probe that fails on unmutated code, and neutralises the stale-`.pyc` trap). One probe per guard:

1. Delete the `if kill:` branch → the kill-switch test must go red.
2. Delete `if not self._armed_in_config:` → the config test must go red.
3. Delete `if not armed_file:` → the arm-file test must go red.
4. Delete `if not venue.ok:` → both venue tests must go red.
5. Delete `if hold:` → the restart-hold tests must go red.
6. Change `_OK_STATUS` to accept `maintenance` → the maintenance test must go red.
7. Change the snapshot bound from `<=` to `>=`, or `30.0` to `3000.0` → the staleness test must go red.
8. Make `evaluate` early-return on the kill branch → **`test_the_kill_switch_does_not_SUPPRESS_the_other_reasons` must go red, and it is the ONLY test that catches this.** `mutate-probe.sh` takes a single sed expression, so express it as one: rewrite the first `reasons.append(` line into an immediate `return GateVerdict(level=GateLevel.NONE, reasons=("kill_switch",), inputs={})`. Do not expect the general multi-reason test to catch it — that test sets no kill file, so the mutated branch never executes for it, and every *other* kill test passes against this mutant (one of them asserts exactly the tuple the mutant returns).
9. Rename the exec record prefix to `cycle-` → the stage-gate-immunity test must go red.
10. Remove the `except Exception` in `read_system_status` → the **malformed-body** test must go red. Not the transport test: `URLError` is still caught by the first `except` clause, so it stays green. Removing the *first* clause instead is a separate probe for the transport case.

- [ ] **Step 2: Record the result honestly**

A probe that survives is a **missing test**, not a nuisance: add the test that kills it, then re-run. Report which probes were killed by which test in the ledger — and if any probe's control and mutation fail at the same assertion, say so rather than counting it as a kill.

- [ ] **Step 3: Commit any test additions**

```bash
git add tests/
git commit -m "test(engine): close the gaps the mutation probes exposed"
```

---

### Task 10: Closeout

**Files:**
- Modify: `docs/iterations-history-phase6.md`
- Modify: `docs/research/14.phase6-decisions.md`
- Modify: `docs/open-topics/T0018-phase6-build-sequence.md` (flip `00088` to landed in the five-spec table)

- [ ] **Step 1: Append the iterations-history entry**

Load the `iteration-closeout` skill and follow it. This is **iter-135**, subject-matter phase 6, so it appends to `docs/iterations-history-phase6.md`. Write it at closeout against the full branch log — not from this plan.

- [ ] **Step 2: Append the decisions-log entries**

`docs/research/14.phase6-decisions.md`, prefixed `[iter-135]`, one paragraph per decision with its options and `(Decision: N)`: the five-spec risk-first decomposition; two-key arming; the separate execution ledger; the venue-status source; the restart-hold clearing policy.

- [ ] **Step 3: No data-catalog change is owed**

This iteration introduces, relocates and retires no dataset. Stated explicitly so the closeout's catalog check is answered rather than skipped.

- [ ] **Step 4: Commit**

```bash
git add docs/
git commit -m "docs(engine): iter-135 closeout — the execution safety envelope"
```

---

## Deployment (after merge, attended — NOT part of task execution)

Ordered, because two hosts are involved and the keep-list must be live before the families arrive:

1. **Capture-host converge** for the `config.alloy` keep-list, with `-e capture_alloy_digest=<currently-running>` — the drift assert refuses otherwise. Config-only, so **no canary bake is owed**.
2. **Engine converge** inside the 4-hourly inter-cycle gap, `-e converge_primary=true`, digest recorded in `docs/reference/fleet-pins.md` first, canary-gated on that digest running as *capture* on `zcrypto-red`.

   ⚠️ **The rendered config and the image must move together — a config-only engine converge here CRASH-LOOPS the live engine.** `_build_engine` rejects unknown keys, so the moment the role renders `exec_armed = false` into `zcrypto.toml` while the host still runs an image whose `EngineConfig` has no such field, every start raises `ConfigError: [zcrypto.engine] … has unknown key(s): exec_armed` — on the host that holds the trade key, taking cycles with it and damaging the streak clock. This matters because the "config-only, pass the currently-running digest" pattern is *correct* for the Alloy step immediately above and is muscle memory on this fleet; it is wrong here, and nothing mechanical refuses it. Pass the new digest.
3. **Grafana push** for the panels and the three rules.
4. **Verify by outcome, by value not presence.** Available within seconds of the restart, from the startup evaluation: `zcrypto_exec_gate_level` reads **0**, `zcrypto_exec_armed` **0**, `zcrypto_exec_restart_hold` **1** — the correct disarmed resting state, and a combination only a real startup evaluation produces (seeded defaults would show `restart_hold` at 0). `(no series)` reads FAIL, never a zero. The sink-written values — the exec record itself — appear after the first post-converge cycle completes, so check those at the next boundary, not immediately.
5. **The live drill, in two parts, because the two paths have different latencies.** The gate: run `zcrypto engine exec-status` on the host, create the kill file, run it again and confirm `kill_switch` appears in the reasons, remove the file, confirm it disappears — seconds, and it proves the gate reads live filesystem state. The publication path: already proven by step 4's startup values. **Do not** plan a 0→1→0 gauge flip as the drill: between cycle completions that gauge does not move, so it would take up to eight hours and would read as a failure long before it read as a pass.
6. Re-measure the active-series budget against the <1k ceiling and record the number.
