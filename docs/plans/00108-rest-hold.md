# `rest-hold` plan mode — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a third plan mode whose order is placed passively, is not cancelled on acknowledgement, and rests for a duration the plan author declares — so the six blocked order-path drills have a subject — and ship the instrument that shows a resting order while it rests.

**Architecture:** One token in `_MODES`, two plan-carried fields validated at the plan wall, and four executor sites rewritten to decide on a *property* rather than on the name `rest-cancel`. One labelled gauge published from the tick the executor already runs, one panel, one alert rule.

**Tech Stack:** Python 3.14, `nautilus_trader 2.0.0rc4.dev20260825`, `prometheus_client`, pytest, Grafana provisioned JSON + `alerts.yaml`.

**Spec:** `docs/specs/00108-rest-hold-plan-mode-design.md`

## Global Constraints

- **Live trade path.** Review floor is **Fable**, per `.claude/rules/spec-plan-locations.md`. The code ships disarmed and reaches the engine only on an attended converge.
- **The defect this plan exists to prevent** (spec preamble): adding `"rest-hold"` to `_MODES` alone gives the new mode full `execute` semantics — joining the touch, repricing, and firing up to `_MAX_IOC_ATTEMPTS` marketable IOCs at the time box. Task 1's first step pins `_MODES` so that miswiring cannot ship green; Task 2 fixes it.
- **`offset_pct` is a PERCENTAGE**: `5.0` means five percent. `_REST_CANCEL_OFFSET = 0.05` is a *fraction*; copying its shape would price an order five hundredths of a percent from the touch, which fills. Every fence below divides by `100.0` at the pricing site and nowhere else.
- **A guard is unproven until the defect it names is constructed and seen to trip**, on a fixture where defect and correct behaviour differ. Every task states the fixture value that makes each assertion bite.
- **Every mutation probe runs against a single named test** (`infra/scripts/mutate-probe.sh --test 'tests/x.py::test_name'`). Never a `-k` filter: a filter's meaning is a function of every test name in the file.
- `uv run pre-commit run -a` clean before each commit; stage by explicit path; `Co-Authored-By:` the actual authoring model; no `Reviewed-by:` from the implementer; never a `Claude-Session:` trailer.
- **Do not build `cancel-on-stop`.** Drill G measures the current shutdown behaviour first; building it here would answer G's question before G runs.

## File Structure

| file | responsibility |
| --- | --- |
| `cli/engine/probeplan.py` | the mode vocabulary, the two new fields, and every refusal that stops a malformed hold at the plan wall |
| `cli/engine/executor.py` | the four mode-dependent branches, the per-intent time box, and the gauge's publish site |
| `cli/engine/command.py` | the gauge's declaration and its setter, beside the existing exec gauges |
| `infra/grafana/engine-dashboard.json` | the panel that makes the gauge visible, and the board's explainer |
| `infra/grafana/alerts.yaml` | the stuck-order rule |
| `infra/runbooks/engine-procedures.md` | the plan shape an operator authors, and the outcome vocabulary they read back |
| `tests/test_engine_executor.py`, `tests/test_engine_probeplan.py`, `tests/test_engine_metrics.py` | the guards |

---

### Task 1: The plan wall — the vocabulary, the fields, and the refusals

**Files:**

- Modify: `cli/engine/probeplan.py`
- Test: `tests/test_engine_probeplan.py`

**Interfaces:**

- Consumes: nothing from later tasks.
- Produces: `ProbeIntent.offset_pct: float | None`, `ProbeIntent.hold_minutes: int | None`, and `_MAX_HOLD_MINUTES = 60`. Task 2 reads both fields off the intent.

- [ ] **Step 1: Write the failing test that pins the vocabulary**

This test is first because its absence is why the whole-mode miswiring would ship green.

```python
def test_the_mode_vocabulary_is_pinned_so_a_new_mode_cannot_arrive_unnoticed():
    """Every mode name is a branch in the executor. A mode added here and nowhere else runs with
    `execute` semantics -- joining the touch and crossing the spread at the time box -- so the
    vocabulary is pinned and widening it is a deliberate, reviewed edit."""
    assert probeplan._MODES == frozenset({"execute", "rest-cancel", "rest-hold"})
```

- [ ] **Step 2: Run it and watch it fail**

Run: `uv run pytest tests/test_engine_probeplan.py::test_the_mode_vocabulary_is_pinned_so_a_new_mode_cannot_arrive_unnoticed -v`
Expected: FAIL — the frozenset lacks `"rest-hold"`.

- [ ] **Step 3: Widen the vocabulary, the key set, and the dataclass**

In `cli/engine/probeplan.py`:

```python
_MODES = frozenset({"execute", "rest-cancel", "rest-hold"})
```

```python
_INTENT_KEYS = frozenset(
    {"symbol", "side", "action", "mode", "notional_eur", "qty", "leverage", "offset_pct", "hold_minutes"}
)
_MAX_HOLD_MINUTES = 60
```

Add to `ProbeIntent`, after `leverage`:

```python
    offset_pct: float | None  # rest-hold only: PERCENT passive of the touch -- 5.0 is five percent
    hold_minutes: int | None  # rest-hold only: how long the order rests, 1.._MAX_HOLD_MINUTES
```

- [ ] **Step 4: Write the failing refusal tests**

Each names the fixture value that makes it bite: a plan that would otherwise parse cleanly, differing only in the field under test.

```python
def test_a_rest_hold_intent_without_both_fields_is_refused():
    """The two fields are what distinguish this mode; an intent missing either has no price and no
    duration, and there is no default that would be safe to invent for a live order."""
    for missing in ("offset_pct", "hold_minutes"):
        raw = _rest_hold_intent()
        del raw[missing]
        with pytest.raises(probeplan.ProbePlanError, match="rest-hold"):
            probeplan._parse_intent(raw)


def test_the_two_fields_are_refused_on_every_other_mode():
    """A hold on an `execute` intent reads as a request the executor will silently ignore."""
    for mode in ("execute", "rest-cancel"):
        raw = _rest_hold_intent() | {"mode": mode}
        with pytest.raises(probeplan.ProbePlanError, match="only on mode 'rest-hold'"):
            probeplan._parse_intent(raw)


@pytest.mark.parametrize("hold", [0, -1, 61, 600])
def test_a_hold_outside_the_cap_is_refused(hold):
    """The cap is what keeps a plan from resting an order indefinitely -- the one bound on this
    mode that does not depend on anything else in the system still working."""
    with pytest.raises(probeplan.ProbePlanError, match="hold_minutes"):
        probeplan._parse_intent(_rest_hold_intent() | {"hold_minutes": hold})


@pytest.mark.parametrize("offset", [0, -1.0])
def test_a_non_positive_offset_is_refused(offset):
    """Zero or negative prices the order at or through the touch, which the post-only submission
    path rejects -- and which would make a mode built never to fill, fill."""
    with pytest.raises(probeplan.ProbePlanError, match="offset_pct"):
        probeplan._parse_intent(_rest_hold_intent() | {"offset_pct": offset})


def test_a_rest_hold_close_is_refused():
    """No drill needs a resting close, and a resting reduce-only order is a different animal that
    should be specified when something wants it."""
    with pytest.raises(probeplan.ProbePlanError, match="action"):
        probeplan._parse_intent(_rest_hold_intent() | {"action": "close"})


def test_a_well_formed_rest_hold_intent_parses():
    """The true positive: without it, a refusal-only suite is satisfied by a parser that refuses
    everything."""
    intent = probeplan._parse_intent(_rest_hold_intent())
    assert (intent.mode, intent.offset_pct, intent.hold_minutes) == ("rest-hold", 5.0, 45)
```

with the fixture helper:

```python
def _rest_hold_intent() -> dict:
    return {
        "symbol": "BTC/EUR",
        "side": "buy",
        "action": "open",
        "mode": "rest-hold",
        "notional_eur": 20.0,
        "offset_pct": 5.0,
        "hold_minutes": 45,
    }
```

- [ ] **Step 5: Run them and watch them fail**

Run: `uv run pytest tests/test_engine_probeplan.py -v -k "rest_hold or offset or hold_minutes"`
Expected: FAIL — the fields are unread, so nothing refuses.

- [ ] **Step 6: Implement the refusals**

In `_parse_intent`, after the `leverage` block and before the `qty` cross-check:

```python
    offset_raw = raw.get("offset_pct")
    hold_raw = raw.get("hold_minutes")
    offset_pct: float | None = None
    hold_minutes: int | None = None
    if mode == "rest-hold":
        if offset_raw is None or hold_raw is None:
            raise ProbePlanError(
                "probe plan intent mode 'rest-hold' requires both offset_pct and hold_minutes, got "
                f"offset_pct={offset_raw!r} hold_minutes={hold_raw!r}"
            )
        if action != "open":
            raise ProbePlanError(f"probe plan intent mode 'rest-hold' requires action == 'open', got {action!r}")
        # PERCENT, not a fraction: 5.0 is five percent. `_REST_CANCEL_OFFSET` is the fraction 0.05,
        # and an intent copying that shape would rest five hundredths of a percent off the touch --
        # which fills, on the one mode built never to.
        offset_pct = _parse_positive_number(offset_raw, "offset_pct")
        if not isinstance(hold_raw, int) or not (1 <= hold_raw <= _MAX_HOLD_MINUTES):
            raise ProbePlanError(
                f"probe plan intent hold_minutes must be an int in [1, {_MAX_HOLD_MINUTES}], got {hold_raw!r}"
            )
        hold_minutes = hold_raw
    elif offset_raw is not None or hold_raw is not None:
        raise ProbePlanError(
            "probe plan intent offset_pct/hold_minutes are legal only on mode 'rest-hold', got "
            f"mode={mode!r} offset_pct={offset_raw!r} hold_minutes={hold_raw!r}"
        )
```

and extend the constructor call:

```python
    return ProbeIntent(
        symbol=symbol, side=side, action=action, mode=mode, notional_eur=notional_eur, qty=qty,
        leverage=leverage, offset_pct=offset_pct, hold_minutes=hold_minutes,
    )
```

**Note, do not "fix":** `isinstance(hold_raw, int)` admits `True`, exactly as the neighbouring `leverage` check does. `hold_minutes: true` parses as a one-minute hold — benign, and matching the house style is worth more here than deviating. Mention it in the report; do not widen it.

- [ ] **Step 7: Run the tests**

Run: `uv run pytest tests/test_engine_probeplan.py -v`
Expected: PASS.

- [ ] **Step 8: Prove the vocabulary guard bites**

Run: `infra/scripts/mutate-probe.sh --file cli/engine/probeplan.py --test 'tests/test_engine_probeplan.py::test_the_mode_vocabulary_is_pinned_so_a_new_mode_cannot_arrive_unnoticed' --mutation 's/"execute", "rest-cancel", "rest-hold"/"execute", "rest-cancel"/'`
Expected: **KILLED**, control proven.

- [ ] **Step 9: Commit**

```bash
git add cli/engine/probeplan.py tests/test_engine_probeplan.py
git commit -m "feat(engine): the rest-hold plan vocabulary and every refusal that stops a bad hold at the wall"
```

---

### Task 2: The executor — four sites that must stop deciding on a name

**Files:**

- Modify: `cli/engine/executor.py`
- Test: `tests/test_engine_executor.py`

**Interfaces:**

- Consumes: `ProbeIntent.offset_pct`, `ProbeIntent.hold_minutes` from Task 1.
- Produces: the terminal outcome string `rest_hold_expired`; `_ActiveIntent.hold_expired: bool`.

- [ ] **Step 1: Write the failing live-money test**

This is the plan's most important test. Its fixture is a quoted book that would let an IOC cross.

```python
def test_a_rest_hold_order_never_crosses_the_spread_when_its_hold_elapses():
    """The mode exists to rest, so the one thing it must never do is what the time box does for
    `execute`: cancel and then cross with a marketable IOC. The defect is a single character --
    `!=` where `==` belongs at the fallback -- and it puts the most aggressive order on the path
    from the intent built least to want it."""
    client, executor = _armed_executor(_plan_with(mode="rest-hold", offset_pct=5.0, hold_minutes=1))
    _tick_through(executor, client, minutes=3, bid=30000.0, ask=30010.0)
    assert len(client.submitted) == 1, "a second order means it fell back and crossed"
    assert client.submitted[0]["post_only"] is True
    assert _outcome_of(executor) == "rest_hold_expired"
```

The biting value is `len(client.submitted)`: under the defect the fallback submits a second, marketable order, and the count moves from 1 to 2. Asserting only the outcome string would pass under the defect, because `_fallback` still terminates.

- [ ] **Step 2: Write the other three failing tests**

```python
def test_a_rest_hold_order_is_not_cancelled_when_the_venue_acknowledges_it():
    """`rest-cancel`'s defining behaviour, inverted. Without this the drills have no subject: an
    order cancelled on the ack leaves no window for any induction to act in."""
    client, executor = _armed_executor(_plan_with(mode="rest-hold", offset_pct=5.0, hold_minutes=45))
    _accept_first_order(executor, client)
    assert "cancel_order" not in _venue_calls(client)
    assert _phase_of(executor) == "resting"


@pytest.mark.parametrize(("side", "expected"), [("buy", 28500.0), ("sell", 31510.0)])
def test_a_rest_hold_order_is_priced_the_declared_percent_passive_of_the_touch(side, expected):
    """5.0 means five percent. The dangerous misreading is the quiet one: an author copying
    `_REST_CANCEL_OFFSET`'s fractional 0.05 would rest five hundredths of a percent off the touch
    and fill. The arithmetic here is `rest-cancel`'s own, with the constant made per-intent."""
    client, executor = _armed_executor(
        _plan_with(mode="rest-hold", offset_pct=5.0, hold_minutes=45, side=side)
    )
    _tick_once(executor, client, bid=30000.0, ask=31600.0)
    assert client.submitted[0]["price"] == pytest.approx(expected)


def test_the_kill_file_revokes_a_resting_rest_hold_order_within_one_tick():
    """Drill E's subject, and the only bound that acts on a resting order while it rests. The path
    is exercised today only against `execute`."""
    client, executor = _armed_executor(_plan_with(mode="rest-hold", offset_pct=5.0, hold_minutes=45))
    _accept_first_order(executor, client)
    _write_kill_file(executor)
    _tick_once(executor, client, bid=30000.0, ask=30010.0)
    assert "cancel_order" in _venue_calls(client)
    assert _outcome_of(executor) != "rest_hold_expired", "a kill is a revoke, never an expiry"


def test_quote_silence_still_revokes_a_resting_rest_hold_order():
    """Drill F2 has no subject without it: 30 s of silence, one cancel attempt, no retry. Exempting
    this mode would delete the drill whose result decides whether re-cancel-on-reconnect is built."""
    client, executor = _armed_executor(_plan_with(mode="rest-hold", offset_pct=5.0, hold_minutes=45))
    _accept_first_order(executor, client)
    _tick_silent(executor, seconds=31)
    assert "cancel_order" in _venue_calls(client)
```

- [ ] **Step 3: Run them and watch them fail for the right reasons**

Run: `uv run pytest tests/test_engine_executor.py -v -k "rest_hold"`
Expected: FAIL. Confirm the pricing test fails with the order priced *at* the touch (30000.0), not with a `TypeError` — a wrong failure means the fixture, not the code, is wrong.

- [ ] **Step 4: Add the expiry flag to `_ActiveIntent`**

Beside `falling_back` (`executor.py:514`):

```python
    hold_expired: bool = False
```

The flag exists because a rest-hold order reaching `_on_cancel_ack` may have got there two ways — its hold elapsed, or the kill file revoked it — and only the first is `rest_hold_expired`. Matching on `revoke_reasons`' text would tie the outcome to a string written for a human.

- [ ] **Step 5: Make the time box per-intent**

At `executor.py:1177`, inside the `_ActiveIntent(...)` construction:

```python
            timebox_at=now + (
                timedelta(minutes=intent.hold_minutes) if intent.mode == "rest-hold" else _TIME_BOX
            ),
```

- [ ] **Step 6: Fix the fallback — the live-money line**

At `executor.py:1108-1113`, replace the `falling_back` assignment:

```python
        if now > active.timebox_at:
            # Only `execute` crosses when its box elapses. Both resting modes exist never to fill,
            # so for them the box cancels and stops there -- the property, not the mode name, is
            # what decides, because a fourth mode added against a name inherits the wrong arm.
            active.cancel_requested = True
            active.falling_back = active.intent.mode == "execute"
            active.hold_expired = active.intent.mode == "rest-hold"
            active.revoke_reasons = ("time box elapsed",)
            self._enter(active, "cancelling")
            self._cancel(active)
```

- [ ] **Step 7: Price the order**

At `executor.py:1236-1239`, replace the `rest-cancel` branch:

```python
        if active.intent.mode == "rest-cancel":
            offset = _REST_CANCEL_OFFSET
        elif active.intent.mode == "rest-hold":
            offset = active.intent.offset_pct / 100.0  # the field is PERCENT; the arithmetic is a fraction
        else:
            return touch
        return touch * (1 - offset) if active.intent.side == "buy" else touch * (1 + offset)
```

**`executor.py:1965` needs no edit.** Its `== "rest-cancel"` test already excludes `rest-hold`, so the order is not cancelled on acknowledgement — which is the whole point. The test in Step 2 is what proves it, and what would catch a later widening.

**The reprice ladder needs no edit either, and must not get one.** Spec D5 says a `rest-hold` order does not follow the touch; that is inherited, not enforced. `_reprice`'s own docstring names its two callers — "the venue's synchronous post-only rejection and its accept-then-cancel" — both *crossing* surfaces, which a passive order never reaches. A wide `offset_pct` cannot cross; a tight one that does is repriced passively and then rests, which is correct. **Do not add a mode check to `_reprice`**: it would be a guard for a door with no caller, and it would break the tight-offset case that A2 needs.

- [ ] **Step 8: Give the expiry its own outcome**

At `executor.py:2050`, after the existing `rest-cancel` branch:

```python
            if active.intent.mode == "rest-hold" and active.hold_expired:
                self._finish_active("rest_hold_expired" if active.filled == 0.0 else "partial", (), active.filled)
                return
```

A rest-hold order revoked by the kill file falls through to `_finish_revoked`, which is correct: it was revoked, not expired.

- [ ] **Step 9: Run the tests**

Run: `uv run pytest tests/test_engine_executor.py -v -k "rest_hold or rest_cancel"`
Expected: PASS, and `rest-cancel`'s existing tests unchanged — particularly the one pinning `order.price == 28500.0` for its 5 % constant.

- [ ] **Step 10: Prove each guard bites**

Each against a single named test:

```bash
# the live-money one: restore the name-based fallback
infra/scripts/mutate-probe.sh --file cli/engine/executor.py \
  --test 'tests/test_engine_executor.py::test_a_rest_hold_order_never_crosses_the_spread_when_its_hold_elapses' \
  --mutation 's/active.falling_back = active.intent.mode == "execute"/active.falling_back = active.intent.mode != "rest-cancel"/'

# the units: treat the percentage as a fraction
infra/scripts/mutate-probe.sh --file cli/engine/executor.py \
  --test 'tests/test_engine_executor.py::test_a_rest_hold_order_is_priced_the_declared_percent_passive_of_the_touch[buy-28500.0]' \
  --mutation 's|offset = active.intent.offset_pct / 100.0|offset = active.intent.offset_pct|'

# cancel-on-ack widened to the new mode
infra/scripts/mutate-probe.sh --file cli/engine/executor.py \
  --test 'tests/test_engine_executor.py::test_a_rest_hold_order_is_not_cancelled_when_the_venue_acknowledges_it' \
  --mutation 's/if active.intent.mode == "rest-cancel":\n                # The drill/if active.intent.mode in ("rest-cancel", "rest-hold"):\n                # The drill/'

# the per-intent box reverted to the constant
infra/scripts/mutate-probe.sh --file cli/engine/executor.py \
  --test 'tests/test_engine_executor.py::test_a_rest_hold_order_never_crosses_the_spread_when_its_hold_elapses' \
  --mutation 's|timedelta(minutes=intent.hold_minutes) if intent.mode == "rest-hold" else _TIME_BOX|_TIME_BOX|'
```

Expected: **KILLED** on each, control proven. Any exit 6 means the sed no-op'd and scored nothing — repoint it rather than record it.

- [ ] **Step 11: Commit**

```bash
git add cli/engine/executor.py tests/test_engine_executor.py
git commit -m "feat(engine): rest-hold rests -- the four mode branches decide on a property, never a name"
```

---

### Task 3: The gauge, its panel, and the board's own explainer

**Files:**

- Modify: `cli/engine/command.py`, `cli/engine/executor.py`, `infra/grafana/engine-dashboard.json`
- Test: `tests/test_engine_metrics.py`

**Interfaces:**

- Consumes: `_ActiveIntent` and the mode from Task 2.
- Produces: `zcrypto_exec_resting_order_age_seconds{mode}`.

- [ ] **Step 1: Write the failing test**

```python
def test_the_resting_order_age_is_published_under_its_own_mode_and_returns_to_zero():
    """A mode that deliberately leaves an order resting for up to an hour ships with the instrument
    that shows it. The label is what keeps the panel legible across the eras: a drill's artifact and
    a rung-1 trading order are the same shape, and only the mode tells them apart."""
    client, executor = _armed_executor(_plan_with(mode="rest-hold", offset_pct=5.0, hold_minutes=45))
    _accept_first_order(executor, client)
    _advance(executor, seconds=120)
    assert _gauge("zcrypto_exec_resting_order_age_seconds", mode="rest-hold") == pytest.approx(120, abs=6)
    assert _gauge("zcrypto_exec_resting_order_age_seconds", mode="execute") == 0.0
    _expire_hold(executor, client)
    assert _gauge("zcrypto_exec_resting_order_age_seconds", mode="rest-hold") == 0.0
```

The `mode="execute"` assertion is the true positive: without it a gauge stuck at the resting value for every label would pass. The return-to-zero assertion is what catches a gauge that is set but never cleared.

- [ ] **Step 2: Run it and watch it fail**

Run: `uv run pytest tests/test_engine_metrics.py::test_the_resting_order_age_is_published_under_its_own_mode_and_returns_to_zero -v`
Expected: FAIL — no such metric family.

- [ ] **Step 3: Declare the gauge**

In `cli/engine/command.py`, beside `self.position`:

```python
        self.resting_order_age = Gauge(
            "zcrypto_exec_resting_order_age_seconds",
            "How long the engine's current resting order has been at the venue, in seconds, by plan "
            "mode; zero when none rests. This is the engine's own belief, not a venue read: if a "
            "cancel could not reach the venue the engine gives up on the order and this reads zero "
            "while it may still rest at Kraken. Nothing is published while the engine is down.",
            ["mode"],
            registry=registry,
        )
```

and the setter beside `inc_order`:

```python
    def set_resting_age(self, mode: str, seconds: float) -> None:
        self.resting_order_age.labels(mode=mode).set(seconds)
```

The HELP text carries both blind spots because it is the surface an operator reads; `.claude/rules/operator-facing-text.md` puts metric HELP in scope, and it carries no internal vocabulary.

- [ ] **Step 4: Publish it from the tick that already runs**

In `cli/engine/executor.py`, beside `_inc_order`:

```python
def _set_resting_age(mode: str, seconds: float) -> None:
    if _metrics is None:
        return
    try:
        _metrics.set_resting_age(mode, seconds)
    except Exception:
        logger.exception("executor metrics hook raised -- continuing")
```

and in `on_timer`, after the pump:

```python
            self._publish_resting_age(now)
```

with:

```python
    def _publish_resting_age(self, now: datetime) -> None:
        """Eagerly zero for every mode, then set the one that is resting: the board's convention is
        that execution numbers read flat zero rather than absent, and a rule over an absent series
        cannot distinguish 'nothing rests' from 'the engine stopped publishing'."""
        active = self._active
        resting = active is not None and active.phase == "resting"
        for mode in _MODES:
            age = 0.0
            if resting and active.intent.mode == mode:
                age = max(0.0, (now - active.placed_at).total_seconds())
            _set_resting_age(mode, age)
```

If `_ActiveIntent` carries no placement timestamp, add `placed_at: datetime` set in `_place`, and say so in the report.

- [ ] **Step 5: Run the test**

Run: `uv run pytest tests/test_engine_metrics.py -v`
Expected: PASS.

- [ ] **Step 6: Add the panel**

In `infra/grafana/engine-dashboard.json`, append to the **Execution** row (its panels end at `y=78`, `h=6`), a full-width panel at `y=84`, and shift the **Venue truth** row (`id` 70) and its panels (71–73) down by 6.

```json
{
  "id": 67,
  "type": "timeseries",
  "title": "Resting order age — by plan mode",
  "description": "How long the engine's current resting order has been at the venue. A rest-hold series is a drill's deliberate artifact, not trading; an execute series is a real trading order and should be short-lived, since its own time box is fifteen minutes. Zero means the engine believes nothing rests — which is not the same as the venue holding nothing, if a cancel never reached it.",
  "gridPos": {"x": 0, "y": 84, "w": 24, "h": 6},
  "datasource": {"type": "prometheus", "uid": "${GRAFANA_PROM_DS_UID}"},
  "targets": [
    {
      "refId": "A",
      "expr": "max by (mode) (zcrypto_exec_resting_order_age_seconds)",
      "legendFormat": "{{mode}}"
    }
  ],
  "fieldConfig": {"defaults": {"unit": "s"}, "overrides": []}
}
```

- [ ] **Step 7: Correct the board's explainer**

Panel `id: 1` currently tells the reader the Execution row is what happened at the venue and reads flat zero outside an attended window. A resting drill order is venue activity that is *not* trading, so append to its `content`:

```text
 A resting order is the one execution number that can appear without any trading: the `rest-hold` mode places a real order at the venue on purpose and leaves it there for a drill to act on. Read the mode label before reading activity as trading.
```

- [ ] **Step 8: Run the coverage guard**

Run: `uv run pytest tests/test_dashboards_cover_metrics.py tests/test_engine_metrics.py -q`
Expected: PASS — assertion (2) is what forces the panel, so it fails if the panel is missing or its expression names the family wrongly.

- [ ] **Step 9: Prove the gauge guard bites**

```bash
infra/scripts/mutate-probe.sh --file cli/engine/executor.py \
  --test 'tests/test_engine_metrics.py::test_the_resting_order_age_is_published_under_its_own_mode_and_returns_to_zero' \
  --mutation 's/if resting and active.intent.mode == mode:/if False:/'
```

Expected: **KILLED**.

- [ ] **Step 10: Commit**

```bash
git add cli/engine/command.py cli/engine/executor.py infra/grafana/engine-dashboard.json tests/test_engine_metrics.py
git commit -m "feat(engine): publish the resting order's age by mode, and chart it"
```

---

### Task 4: The stuck-order alert rule

**Files:**

- Modify: `infra/grafana/alerts.yaml`
- Test: `tests/test_infra_alert_rules.py`

- [ ] **Step 1: Add the rule**

Threshold: the declared cap plus one evaluation. Nothing legal can exceed it — `execute` is bounded by the fifteen-minute `_TIME_BOX`, `rest-cancel` cancels on the acknowledgement, and `rest-hold` is capped at sixty minutes by the plan wall — so the number holds in the rung-1 era too, without a drill having to measure anything first.

```yaml
  - uid: zcrypto-engine-resting-order-stuck
    title: "Engine · an order has rested longer than any plan may declare"
    ruleGroup: zcrypto-gate
    folderUID: "${GRAFANA_ALERT_FOLDER_UID}"
    orgId: 1
    # 61 min = the plan wall's 60-minute cap plus one evaluation. Every legal path is bounded below
    # it: `execute` by its 15-minute time box, `rest-cancel` by the acknowledgement, `rest-hold` by
    # the cap itself. Above it, the order is stuck rather than resting.
    condition: C
    annotations:
      summary: "An order has been resting at the venue for over an hour, which is longer than any plan is allowed to ask for. Either a drill overran its window or an order is stuck with nothing left to end it — the engine cancels a resting order only while its intent is still live, so a stuck one is not swept by anything on its own. Check the engine's open orders against Kraken directly, since this number is the engine's belief rather than a venue read. Runbook: infra/runbooks/engine.md#zcrypto-engine-resting-order-stuck"
      __dashboardUid__: "zcrypto-engine"
      __panelId__: "67"
```

Match the surrounding rules' `data:` block shape — a `max_over_time` reduce and a `> 3660` threshold — from `zcrypto-engine-exec-armed-too-long`, which is the nearest structural sibling.

- [ ] **Step 2: Add the runbook section its summary names**

`infra/runbooks/engine.md` gains `#zcrypto-engine-resting-order-stuck` in the house *What you are seeing / What it means / What to do* shape. The *What to do* must say to read Kraken's open orders directly, because the gauge cannot see an order the engine has given up on.

- [ ] **Step 3: Run the guards**

Run: `uv run pytest tests/test_infra_alert_rules.py tests/test_dashboards_cover_metrics.py tests/test_internal_terms_not_operator_visible.py -q`
Expected: PASS. The last one matters: an alert summary is read on a phone with nothing open, and carries no internal vocabulary.

- [ ] **Step 4: Commit**

```bash
git add infra/grafana/alerts.yaml infra/runbooks/engine.md
git commit -m "feat(engine): page when an order rests longer than any plan may declare"
```

**Do not push this rule.** Its metric first appears when the engine converges, and a rule pushed before its metric's first record pages a spurious no-data alert. The push is an attended step after the engine converge, recorded in the closeout.

---

### Task 5: The operator's surfaces, and the closeout

**Files:**

- Modify: `infra/runbooks/engine-procedures.md`, `infra/runbooks/drills-order-path.md`, `README.md` (only if it documents the plan-file schema), `docs/iterations-history-phase6.md`, `docs/open-topics/README.md`

- [ ] **Step 1: The plan shape an operator authors**

Beside Drill A's JSON in `engine-procedures.md`, add the `rest-hold` shape with both fields and a sentence fixing the units — `offset_pct` is a percentage, `5.0` is five percent — because that is the misreading which fills.

- [ ] **Step 2: The outcome vocabulary**

`rest_hold_expired` joins the outcomes an operator reads back, beside `rest_cancel_ok`.

- [ ] **Step 3: Re-tense the blocked note**

`drills-order-path.md:13` says six drills are blocked because no plan mode keeps an order resting. The mode now exists; they remain blocked on the attended converge. Re-tense in place — do not delete the note, and do not claim the drills are runnable.

- [ ] **Step 4: Verify the whole reachable set**

Run: `uv run pytest tests/test_engine_executor.py tests/test_engine_probeplan.py tests/test_engine_metrics.py tests/test_engine_stub_fidelity.py tests/test_infra_alert_rules.py tests/test_dashboards_cover_metrics.py tests/test_internal_terms_not_operator_visible.py tests/test_code_prose_citations.py -q`
Expected: PASS. `test_engine_stub_fidelity.py` is in the list because it globs sibling `test_engine_*.py` files and classifies their doubles — any new double in the tests above must be classified in the same change.

- [ ] **Step 5: The iterations-history entry**

Append to `docs/iterations-history-phase6.md`, routed by subject. Load `.claude/skills/iteration-closeout/SKILL.md` for the entry format. **Write it at closeout against the full branch log, never from this plan's expectations.**

State plainly what is *not* proven: no rest-hold order has ever been placed at Kraken, the alert rule is committed but unpushed, and the six drills stay blocked on the attended converge.

- [ ] **Step 6: Commit**

```bash
git add infra/runbooks/ docs/iterations-history-phase6.md docs/open-topics/README.md
git commit -m "docs(engine): the rest-hold plan shape, its outcome, and iter-NNN closeout"
```
