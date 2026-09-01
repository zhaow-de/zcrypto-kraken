# `rest-hold` plan mode — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a third plan mode whose order is placed passively, is not cancelled on acknowledgement, rests for a duration the plan author declares, and is never re-placed once the venue takes it off the book — so the five blocked order-path drill sections have a subject — and ship the instrument that shows a resting order while it rests, over a road that actually reaches Grafana.

**Architecture:** One token in the mode vocabulary, two plan-carried fields validated at the parse wall, and five executor sites made explicit about all three modes, the two money-line arms turned around so their default is the one that cannot cross (spec D2). One labelled gauge published from the tick the executor already runs, one panel, one keep-regex admission. **No alert rule** — spec D7 rules the condition unobservable on this metric and already covered by `zcrypto-engine-error-logs`.

**Tech Stack:** Python 3.14, `nautilus_trader 2.0.0rc4.dev20260825`, `prometheus_client`, pytest, Grafana provisioned JSON, Alloy.

**Spec:** `docs/specs/00108-rest-hold-plan-mode-design.md`

## Global Constraints

- **Live trade path.** Review floor is **Fable**, per `.claude/rules/spec-plan-locations.md`. The code ships disarmed and reaches the engine only on an attended converge.
- **The defect this plan exists to prevent** (spec preamble): adding `"rest-hold"` to the mode vocabulary alone gives the new mode full `execute` semantics — joining the touch, repricing, and firing up to `_MAX_IOC_ATTEMPTS` marketable IOCs at the time box. Task 1's first step pins the vocabulary so that miswiring cannot ship green; Task 2 fixes it.
- **`offset_pct` is a PERCENTAGE**: `5.0` means five percent. `_REST_CANCEL_OFFSET = 0.05` is a *fraction*; copying its shape would price an order five hundredths of a percent from the touch, which fills. Every fence below divides by `100.0` at the pricing site and nowhere else.
- **A guard is unproven until the defect it names is constructed and seen to trip**, on a fixture where defect and correct behaviour differ. Every task states the fixture value that makes each assertion bite.
- **`infra/scripts/mutate-probe.sh`'s real interface** is `--file F --control SED --mutation SED -- CMD...`. `--control` is **required** and the probe command comes after `--`; there is no `--test` flag. The control is a sabotage the named test *must* detect: the script refuses every verdict until it has seen the control fail (`exit 5`). Every probe below names a single test, never a `-k` filter, and every sed expression is written against a **single line** — `apply()` runs `sed -i` line-by-line, so an embedded `\n` matches nothing and exits 6.
- **Every test fence below is written against the existing helpers in `tests/test_engine_executor.py`** — `_resting_executor(tmp_path, *, intents, bid, ask) -> (ex, client, clock)`, `_intent(**overrides)`, `_accepted`, `_canceled`, `_advance_with_quotes`, `_intent_outcome`, `_record`, `RecordingMetrics`, `exec_dir`/`KILL_FILE`, `_quote`. `client.submitted[i]` is an `(order, params)` tuple and the price is `order.price`. No new helper is introduced.
- `uv run pre-commit run -a` clean before each commit; stage by explicit path; `Co-Authored-By:` the actual authoring model; no `Reviewed-by:` from the implementer; never a `Claude-Session:` trailer.
- **Do not build `cancel-on-stop`.** Drill G measures the current shutdown behaviour first; building it here would answer G's question before G runs.

## File Structure

| file | responsibility |
| --- | --- |
| `cli/engine/probeplan.py` | the mode vocabulary (renamed public), the two new fields, and every refusal that stops a malformed hold at the parse wall |
| `cli/engine/executor.py` | the five mode-dependent branches, the per-intent time box, `placed_at`, and the gauge's publish site |
| `cli/engine/command.py` | the gauge's declaration and setter, and the `probe-plan --check` echo of the two new fields |
| `infra/grafana/engine-dashboard.json` | the panel that makes the gauge visible, and the board's explainer |
| `infra/ansible/roles/capture/files/config.alloy` | the keep-regex admission, without which the series never leaves the engine host |
| `infra/runbooks/engine-procedures.md`, `infra/runbooks/drills-order-path.md` | the plan shape an operator authors, the outcome vocabulary they read back, and the re-tensed blocked note |
| `docs/open-topics/T0018-phase6-build-sequence.md` | the build item this PR completes |
| `tests/test_engine_probeplan.py`, `tests/test_engine_executor.py`, `tests/test_engine_metrics.py`, `tests/test_engine_command.py`, `tests/test_infra_alloy_series.py` | the guards |

---

### Task 1: The plan wall — the vocabulary, the fields, the refusals, and the echo

**Files:**

- Modify: `cli/engine/probeplan.py`, `cli/engine/command.py`
- Test: `tests/test_engine_probeplan.py`, `tests/test_engine_command.py`

**Interfaces:**

- Consumes: nothing from later tasks.
- Produces: `probeplan.MODES` (public — Task 4 imports it), `ProbeIntent.offset_pct: float | None`, `ProbeIntent.hold_minutes: int | None`, `_MAX_HOLD_MINUTES = 60`. Task 2 reads both fields off the intent.

- [ ] **Step 1: Write the failing test that pins the vocabulary**

This test is first because its absence is why the whole-mode miswiring would ship green.

**Add the module import first.** `tests/test_engine_probeplan.py` imports names only today — `from cli.engine.probeplan import PLAN_TTL, ProbePlanError, parse_plan, plan_refusals` — and every fence in this task reaches the module attribute (`probeplan.MODES`, `probeplan._parse_intent`, `probeplan.ProbePlanError`), so add `from cli.engine import probeplan` beside it. `grep -c "probeplan\." tests/test_engine_probeplan.py` returns `0` before this step.

```python
def test_the_mode_vocabulary_is_pinned_so_a_new_mode_cannot_arrive_unnoticed():
    """Every mode name is a branch in the executor. A mode added here and nowhere else runs with
    `execute` semantics -- joining the touch and crossing the spread at the time box -- so the
    vocabulary is pinned and widening it is a deliberate, reviewed edit."""
    assert probeplan.MODES == frozenset({"execute", "rest-cancel", "rest-hold"})
```

- [ ] **Step 2: Run it and watch it fail**

Run: `uv run pytest tests/test_engine_probeplan.py::test_the_mode_vocabulary_is_pinned_so_a_new_mode_cannot_arrive_unnoticed -v`
Expected: FAIL — `AttributeError: module 'cli.engine.probeplan' has no attribute 'MODES'`.

- [ ] **Step 3: Rename the vocabulary public, widen it, and widen the key set and the dataclass**

`_MODES` becomes `MODES` because `cli/engine/executor.py` now consumes it (Task 4's gauge labels every mode); reaching across modules for a private name is the alternative and is worse. Three sites in `cli/engine/probeplan.py`: the definition at `:23`, and the two uses at `:93-94`. `grep -rn "_MODES" tests/ cli/` confirms no other reader.

```python
MODES = frozenset({"execute", "rest-cancel", "rest-hold"})
```

```python
    if mode not in MODES:
        raise ProbePlanError(f"probe plan intent mode must be one of {sorted(MODES)}, got {mode!r}")
```

```python
_INTENT_KEYS = frozenset(
    {"symbol", "side", "action", "mode", "notional_eur", "qty", "leverage", "offset_pct", "hold_minutes"}
)
_MAX_HOLD_MINUTES = 60
```

Add to `ProbeIntent`, after `leverage` — **both defaulted `None`, and the default is load-bearing**:

```python
    offset_pct: float | None = None  # rest-hold only: PERCENT passive of the touch -- 5.0 is five percent
    hold_minutes: int | None = None  # rest-hold only: how long the order rests, 1.._MAX_HOLD_MINUTES
```

Bare annotations would make both required positional arguments and break the two existing constructor sites that pass exactly the current seven kwargs — `tests/test_engine_executor.py:4773` (`_terminal_intent`, feeding the three `_reconcile_terminal` tests) and `tests/test_engine_node.py:710` — with `TypeError: ProbeIntent.__init__() missing 2 required positional arguments`. Neither is in this task's Step 9 run, and `test_engine_node.py` is reached by no step before Task 5. The defaults cost nothing: `_parse_intent` is the only constructor that ever sets either field, and it sets both explicitly.

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

- [ ] **Step 6: Implement the refusals at the parse wall**

Spec D1 puts these in `_parse_intent`, beside `leverage`'s own range check — **not** in `plan_refusals`, which carries only plan-level, environment-dependent reasons. Two consequences are taken deliberately and are stated in D1: only the first violating field is reported, and a malformed hold journals under `plan_id="unparseable"` with `plan={}` (`executor.py:996-1002`), exactly as every existing shape refusal does. Do not "improve" either here.

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

- [ ] **Step 7: Write the failing check-echo test**

Spec D1's second mitigation: the two fields that decide whether the order can fill must appear on the one pre-flight surface an operator reads. The fixture is `offset_pct: 0.05` — the slip D1 names — so the assertion is about the *rendering*, not about the `5.0` arithmetic Task 2 pins.

In `tests/test_engine_command.py`, beside the other `probe-plan --check` tests:

```python
def test_probe_plan_check_echoes_the_rest_hold_offset_and_hold(tmp_path, monkeypatch):
    """The quiet units slip is `offset_pct: 0.05` copied from `_REST_CANCEL_OFFSET`'s fractional
    shape: it parses, it prices fifteen euro off a thirty-thousand euro bid, and it fills on the
    one mode built never to. The check line is where an operator can still see it."""
    _probe_plan_env(tmp_path, monkeypatch, instruments={"BTC/EUR": _instrument("BTC/EUR")})
    plan = _write_plan(tmp_path, [_intent(mode="rest-hold", offset_pct=0.05, hold_minutes=45)])

    result = runner.invoke(app, ["engine", "probe-plan", str(plan), "--check"])

    out = _output(result)
    assert result.exit_code == 0, out
    assert "0.05% passive of the touch, holding 45 min" in out
```

Run: `uv run pytest tests/test_engine_command.py::test_probe_plan_check_echoes_the_rest_hold_offset_and_hold -v`
Expected: FAIL — the rendered line stops at the mode name.

- [ ] **Step 8: Implement the echo**

In `cli/engine/command.py`'s `_intent_floor_check`, immediately after `head` is built:

```python
    head = f"  [{index}] {intent.symbol} {intent.side} {intent.action} {intent.mode}"
    if intent.mode == "rest-hold":
        # The two fields that decide whether this order can FILL, in words, on the only surface an
        # operator reads before placing it. `offset_pct` is a percent: `0.05` here is fifteen euro
        # off a thirty-thousand euro bid, and the whole point of printing it is that it looks wrong.
        head += f" ({intent.offset_pct:g}% passive of the touch, holding {intent.hold_minutes} min)"
```

`infra/runbooks/engine-procedures.md:213` documents this line's format verbatim for Drill A's `rest-cancel` intent, which is unchanged — the branch adds nothing to the other two modes. Task 5 Step 1 adds the `rest-hold` sample beside it.

- [ ] **Step 9: Run the tests**

Run: `uv run pytest tests/test_engine_probeplan.py tests/test_engine_command.py -q`
Expected: PASS.

- [ ] **Step 10: Prove both guards bite**

```bash
# the vocabulary pin
infra/scripts/mutate-probe.sh --file cli/engine/probeplan.py \
  --control 's|"execute", "rest-cancel", "rest-hold"|"nope"|' \
  --mutation 's|"execute", "rest-cancel", "rest-hold"|"execute", "rest-cancel"|' \
  -- uv run pytest 'tests/test_engine_probeplan.py::test_the_mode_vocabulary_is_pinned_so_a_new_mode_cannot_arrive_unnoticed'

# the check echo
infra/scripts/mutate-probe.sh --file cli/engine/command.py \
  --control 's|if intent.mode == "rest-hold":|if False:|' \
  --mutation 's| ({intent.offset_pct:g}% passive of the touch, holding {intent.hold_minutes} min)||' \
  -- uv run pytest 'tests/test_engine_command.py::test_probe_plan_check_echoes_the_rest_hold_offset_and_hold'
```

Expected: **KILLED** on each, control proven. Any `exit 6` means the sed no-op'd and scored nothing — repoint it rather than record it; any `exit 5` means the control was not detectable and needs replacing, not the probe dropping.

- [ ] **Step 11: Commit**

```bash
git add cli/engine/probeplan.py cli/engine/command.py tests/test_engine_probeplan.py tests/test_engine_command.py
git commit -m "feat(engine): the rest-hold plan vocabulary, its refusals, and the check line that shows the units"
```

---

### Task 2: The executor — five mode sites, and the two that must default passive

**Files:**

- Modify: `cli/engine/executor.py`
- Test: `tests/test_engine_executor.py`

**Interfaces:**

- Consumes: `ProbeIntent.offset_pct`, `ProbeIntent.hold_minutes` from Task 1.
- Produces: the terminal outcomes `rest_hold_expired` and `rest_hold_venue_canceled`; `_ActiveIntent.hold_expired: bool`.

- [ ] **Step 1: Write the failing live-money test**

This is the plan's most important test. `_resting_executor`'s default book (`bid=30000.0, ask=30001.0`) is one an IOC would cross.

```python
def test_a_rest_hold_order_never_crosses_the_spread_when_its_hold_elapses(tmp_path):
    """The mode exists to rest, so the one thing it must never do is what the time box does for
    `execute`: cancel and then cross with a marketable IOC. The defect is a single character --
    `!=` where `==` belongs at the fallback -- and it puts the most aggressive order on the path
    from the intent built least to want it."""
    ex, client, clock = _resting_executor(
        tmp_path, intents=[_intent(mode="rest-hold", offset_pct=5.0, hold_minutes=1)]
    )
    _advance_with_quotes(ex, client, clock, minutes=3)
    assert client.canceled == [client.submitted[0][0].client_order_id]

    ex.on_order_event(_canceled(client.last_order_id))
    assert len(client.submitted) == 1, "a second order means it fell back and crossed"
    assert client.submitted[0][0].post_only is True
    assert _intent_outcome(tmp_path) == "rest_hold_expired"
```

The biting value is `len(client.submitted)`: under the defect the fallback submits a second, marketable order and the count moves from 1 to 2. Asserting only the outcome string would pass under the defect, because `_fallback` still terminates.

- [ ] **Step 2: Write the other four failing tests**

```python
def test_a_rest_hold_order_is_not_cancelled_when_the_venue_acknowledges_it(tmp_path):
    """`rest-cancel`'s defining behaviour, inverted. Without this the drills have no subject: an
    order cancelled on the ack leaves no window for any induction to act in."""
    ex, client, clock = _resting_executor(
        tmp_path, intents=[_intent(mode="rest-hold", offset_pct=5.0, hold_minutes=45)]
    )
    ex.on_order_event(_accepted(client.last_order_id))
    assert client.canceled == []
    assert ex._active.phase == "resting"


def test_an_unrequested_cancel_ends_a_rest_hold_intent_instead_of_re_placing_it(tmp_path):
    """Spec D5. `_on_cancel_ack`'s unrequested arm reprices for ANY venue-originated cancel while
    the phase is not `ioc` -- it tests nothing about crossing -- so without this branch the venue's
    (or the operator's) cancel of a resting drill order silently puts a fresh one back at a new
    price, swapping the drill's subject mid-induction."""
    ex, client, clock = _resting_executor(
        tmp_path, intents=[_intent(mode="rest-hold", offset_pct=5.0, hold_minutes=45)]
    )
    ex.on_order_event(_accepted(client.last_order_id))

    ex.on_order_event(_canceled(client.last_order_id))  # unrequested: the venue's own doing

    assert len(client.submitted) == 1, "a second order means the venue's cancel was undone"
    assert _intent_outcome(tmp_path) == "rest_hold_venue_canceled"
    assert _record(tmp_path)["submitted"][0]["state"] == "venue_canceled"


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [({"side": "buy"}, 28500.0), ({"side": "sell", "leverage": 3}, 33180.0)],
    ids=["buy-off-the-bid", "sell-off-the-ask"],
)
def test_a_rest_hold_order_is_priced_the_declared_percent_passive_of_the_touch(tmp_path, overrides, expected):
    """5.0 means five percent. The dangerous misreading is the quiet one: an author copying
    `_REST_CANCEL_OFFSET`'s fractional 0.05 would rest five hundredths of a percent off the touch
    and fill. The arithmetic here is `rest-cancel`'s own, with the constant made per-intent --
    30000 x 0.95 off the bid, 31600 x 1.05 off the ask."""
    ex, client, clock = _resting_executor(
        tmp_path,
        intents=[_intent(mode="rest-hold", offset_pct=5.0, hold_minutes=45, **overrides)],
        bid=30000.0,
        ask=31600.0,
    )
    assert client.submitted[0][0].price == expected


def test_the_kill_file_revokes_a_resting_rest_hold_order_within_one_tick(tmp_path):
    """Drill E's subject, and the only bound that acts on a resting order while it rests. The path
    is exercised today only against `execute`."""
    ex, client, clock = _resting_executor(
        tmp_path, intents=[_intent(mode="rest-hold", offset_pct=5.0, hold_minutes=45)]
    )
    ex.on_order_event(_accepted(client.last_order_id))
    resting_order = client.submitted[0][0]

    (exec_dir(tmp_path) / KILL_FILE).touch()
    clock.now = NOW + timedelta(seconds=5)
    ex.on_quote(_quote())  # a live quote: what revokes here is the gate, not silence
    ex.on_timer(clock.now)
    assert client.canceled == [resting_order.client_order_id]

    ex.on_order_event(_canceled(client.last_order_id))
    assert len(client.submitted) == 1  # a revoked intent NEVER falls back
    assert _intent_outcome(tmp_path) == "revoked", "a kill is a revoke, never an expiry"


def test_quote_silence_still_revokes_a_resting_rest_hold_order(tmp_path):
    """Drill F2 has no subject without it: 30 s of silence, one cancel attempt, no retry. Exempting
    this mode would delete the drill whose result decides whether re-cancel-on-reconnect is built."""
    ex, client, clock = _resting_executor(
        tmp_path, intents=[_intent(mode="rest-hold", offset_pct=5.0, hold_minutes=45)]
    )
    ex.on_order_event(_accepted(client.last_order_id))

    clock.now = NOW + timedelta(seconds=31)
    ex.on_timer(clock.now)

    assert client.canceled == [client.submitted[0][0].client_order_id]
    ex.on_order_event(_canceled(client.last_order_id))
    assert _intent_entry(tmp_path, 0)["reasons"] == ["quote_silence"]
```

**Do NOT request `kill_trip_expected` on the kill-file test.** That fixture is the autouse `_no_unannounced_kill_trip` guard's opt-in, and it runs both ways: requesting it *requires* a `logger.critical("execution kill switch tripped ...")` record, which lives only in `_trip_kill` and is reached from fill-time divergences. The kill FILE reaches a resting order through the gate → `_revoke` path and emits no such line — so the request would fail the test at teardown on a fully healthy run, with a message ("this construction was supposed to trip the kill switch and did not") that invites latching the kill on a file read. The existing twin, `test_a_kill_file_mid_rest_cancels_with_no_fallback_and_halts_the_plan`, requests nothing; match it. `NOW`, `KILL_FILE`, `exec_dir`, `_quote`, `_intent_entry` are all already imported in that module.

- [ ] **Step 3: Run them and watch them fail for the right reasons**

Run: `uv run pytest tests/test_engine_executor.py -v -k "rest_hold"`
Expected: FAIL — and read *which* failure fired on each, per side:

- pricing, buy: the order is at the **bid**, `30000.0`, not `28500.0`.
- pricing, sell: the order is at the **ask**, `31600.0`, not `33180.0`. The pre-fix touch differs per side; a sell failing at `30000.0` would mean the fixture is wrong, not the code.
- the hold: a *second* submission appears (the inherited `execute` fallback), and `_intent_outcome` is `unfilled`.
- the unrequested cancel: a second submission appears, both post-only GTC.

A `TypeError` or `AttributeError` anywhere means Task 1's fields are not on the intent — fix that before reading anything else.

- [ ] **Step 4: Add the two new `_ActiveIntent` fields**

After `phase_deadline` (`executor.py:518`) — **both defaulted**, because every trailing field there already carries a default and a bare annotation would be a class-creation `TypeError`:

```python
    # Set whenever an order enters `resting`, so it tracks the CURRENT order rather than the intent:
    # a post-only rejection's reprice replaces the order, and its age restarts with it.
    placed_at: datetime | None = None
    hold_expired: bool = False
```

`hold_expired` exists because a rest-hold order reaching `_on_cancel_ack` may have got there two ways — its hold elapsed, or the kill file revoked it — and only the first is `rest_hold_expired`. Matching on `revoke_reasons`' text would tie the outcome to a string written for a human.

- [ ] **Step 5: Stamp `placed_at` where the phase becomes `resting`**

In `_enter` (`executor.py:1415`), which both `_first_submission` and `_resubmit(next_phase="resting")` funnel through:

```python
    def _enter(self, active: _ActiveIntent, phase: str) -> None:
        active.phase = phase
        active.phase_deadline = self._now() + _ACK_WAIT if phase in ("cancelling", "ioc") else None
        if phase == "resting":
            active.placed_at = self._now()
```

and extend that method's docstring with the new clause rather than leaving it describing only the deadline.

- [ ] **Step 6: Make the time box per-intent**

At `executor.py:1177`, inside the `_ActiveIntent(...)` construction:

```python
            timebox_at=now + (
                timedelta(minutes=intent.hold_minutes) if intent.mode == "rest-hold" else _TIME_BOX
            ),
```

- [ ] **Step 7: Fix the fallback — the live-money line**

At `executor.py:1108-1113`, replace the `falling_back` assignment:

```python
        if now > active.timebox_at:
            # Only `execute` crosses when its box elapses. Both resting modes exist never to fill,
            # so for them the box cancels and stops there. Written `== "execute"` rather than
            # `!= "rest-cancel"` so a fourth mode inherits the arm that cannot cross; the pin on
            # `MODES` is what forces this line to be re-read when one arrives.
            active.cancel_requested = True
            active.falling_back = active.intent.mode == "execute"
            active.hold_expired = active.intent.mode == "rest-hold"
            active.revoke_reasons = ("time box elapsed",)
            self._enter(active, "cancelling")
            self._cancel(active)
```

- [ ] **Step 8: Price the order**

At `executor.py:1236-1239`, replace the `rest-cancel` branch, and extend `_limit_price`'s docstring with the third mode:

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

- [ ] **Step 9: Give the expiry its own outcome**

At `executor.py:2050`, after the existing `rest-cancel` branch:

```python
            if active.intent.mode == "rest-hold" and active.hold_expired:
                self._finish_active("rest_hold_expired" if active.filled == 0.0 else "partial", (), active.filled)
                return
```

A rest-hold order revoked by the kill file falls through to `_finish_revoked`, which is correct: it was revoked, not expired.

- [ ] **Step 10: Make the venue's own cancel terminal — spec D5**

At `executor.py:2061-2064`, between the `ioc` arm and the reprice:

```python
        if active.intent.mode == "rest-hold":
            # Spec 00108 D5. This arm runs for ANY venue-originated cancel or expiry while the
            # phase is not `ioc` -- it tests nothing about crossing -- and a resting rest-hold order
            # is a drill's SUBJECT. Re-placing it at the current touch under a new client-order-id
            # swaps the subject mid-induction, silently undoes an operator's own cancel at the
            # venue, and contaminates exactly the continuity drill G exists to measure.
            self._finish_active("rest_hold_venue_canceled" if active.filled == 0.0 else "partial", (), active.filled)
            return
        self._reprice(active)
```

**The guard goes here and NOT inside `_reprice`.** `_reprice`'s other caller — `_on_rejected` with `due_post_only=True` (`executor.py:2026`) — is a real production surface with a real job: the venue refused the *submission* because the declared price crossed, so nothing was ever resting, and the recomputed price is `offset_pct` strictly passive of the current touch. A tight-offset intent (A2's shape) needs that recovery to get resting at all, and a mode check inside `_reprice` would break it. Update `_reprice`'s docstring, whose "Both crossing surfaces funnel here" is the over-claim that produced this defect: it names two callers, not the reachability of one of them.

- [ ] **Step 11: Run the tests**

Run: `uv run pytest tests/test_engine_executor.py -v -k "rest_hold or rest_cancel"`
Expected: PASS, and `rest-cancel`'s existing tests unchanged — particularly the one pinning `order.price == 28500.0` for its 5 % constant.

- [ ] **Step 12: Prove each guard bites**

Each against a single named test. Read the exit code, not just the word: `exit 5` = the control did not bite (replace the control), `exit 6` = a no-op sed (repoint the expression), `exit 7` = the probe does not pass on unmutated code.

```bash
# the live-money one: restore the name-based fallback
infra/scripts/mutate-probe.sh --file cli/engine/executor.py \
  --control 's|active.falling_back = active.intent.mode == "execute"|active.falling_back = True|' \
  --mutation 's|active.falling_back = active.intent.mode == "execute"|active.falling_back = active.intent.mode != "rest-cancel"|' \
  -- uv run pytest 'tests/test_engine_executor.py::test_a_rest_hold_order_never_crosses_the_spread_when_its_hold_elapses'

# the per-intent box reverted to the constant
infra/scripts/mutate-probe.sh --file cli/engine/executor.py \
  --control 's|if now > active.timebox_at:|if False:|' \
  --mutation 's|timedelta(minutes=intent.hold_minutes) if intent.mode == "rest-hold" else _TIME_BOX|_TIME_BOX|' \
  -- uv run pytest 'tests/test_engine_executor.py::test_a_rest_hold_order_never_crosses_the_spread_when_its_hold_elapses'

# the units: treat the percentage as a fraction
infra/scripts/mutate-probe.sh --file cli/engine/executor.py \
  --control 's|offset = active.intent.offset_pct / 100.0|offset = 0.0|' \
  --mutation 's|offset = active.intent.offset_pct / 100.0|offset = active.intent.offset_pct|' \
  -- uv run pytest 'tests/test_engine_executor.py::test_a_rest_hold_order_is_priced_the_declared_percent_passive_of_the_touch[buy-off-the-bid]'

# cancel-on-ack widened to the new mode. The `== "rest-cancel"` line is not unique in this file --
# it appears at :1237, :1965 and :2050 -- so the address anchors on `_inc_order("accepted")`, which
# is, and `n` advances to the branch line below it.
infra/scripts/mutate-probe.sh --file cli/engine/executor.py \
  --control '/_inc_order("accepted")/{n;s|== "rest-cancel"|is not None|}' \
  --mutation '/_inc_order("accepted")/{n;s|"rest-cancel"|"rest-hold"|}' \
  -- uv run pytest 'tests/test_engine_executor.py::test_a_rest_hold_order_is_not_cancelled_when_the_venue_acknowledges_it'

# D5: the venue's cancel silently re-places the order
infra/scripts/mutate-probe.sh --file cli/engine/executor.py \
  --control 's|self._update_row(active, state="venue_canceled", event=payload)|return|' \
  --mutation 's|self._finish_active("rest_hold_venue_canceled" if active.filled == 0.0 else "partial", (), active.filled)|self._reprice(active)|' \
  -- uv run pytest 'tests/test_engine_executor.py::test_an_unrequested_cancel_ends_a_rest_hold_intent_instead_of_re_placing_it'
```

Expected: **KILLED** on each, control proven.

- [ ] **Step 13: Commit**

```bash
git add cli/engine/executor.py tests/test_engine_executor.py
git commit -m "feat(engine): rest-hold rests -- five mode branches, and the fallback defaults passive"
```

---

### Task 3: The road to Grafana — admit the family before anything publishes it

**Files:**

- Modify: `infra/ansible/roles/capture/files/config.alloy`
- Test: `tests/test_infra_alloy_series.py`

**This task comes before the gauge, and the order is not cosmetic.** `tests/test_infra_alloy_series.py` carries a source-derived guard, `test_every_published_metric_is_admitted_by_some_hosts_keep_regex`, parametrized over every `zcrypto_[a-z0-9_]{4,}` token it finds under `cli/**/*.py`. The moment Task 4 writes the family's name into `cli/engine/command.py` that guard gains a case and goes **red** unless some host's keep-regex already admits it — so admitting first is what keeps every commit on this branch green. It is also spec D6's deploy order: a metric admitted before it is published costs nothing, one published before it is admitted is simply lost.

Verified on this tree: `_keep_regex` for all four configs returns no match for `zcrypto_exec_resting_order_age_seconds` today (nas/ops/capture/access all False), and `ENGINE_APP_SERIES` carries 13 `zcrypto_exec_*` entries.

- [ ] **Step 1: Add the family to the capture keep regex**

`infra/ansible/roles/capture/files/config.alloy:157` — the single-line alternation in the `action = "keep"` relabel. Insert `|zcrypto_exec_resting_order_age_seconds` immediately after `zcrypto_exec_position`, keeping the file's existing grouping of the `zcrypto_exec_*` families. Verify by value rather than by eye:

```bash
grep -c 'zcrypto_exec_resting_order_age_seconds' infra/ansible/roles/capture/files/config.alloy
```

Expected: `1`.

- [ ] **Step 2: Add it to `ENGINE_APP_SERIES`**

In `tests/test_infra_alloy_series.py`, add `"zcrypto_exec_resting_order_age_seconds"` to `ENGINE_APP_SERIES` (`:77`), beside `"zcrypto_exec_position"` in the `_ExecutionMetrics` block. That one list is read in **both** directions: `test_keep_regex_admits_every_published_series[capture]` requires the capture config to admit it, and `test_keep_regex_excludes_families_not_published_on_this_host` requires nas, ops and access **not** to — so a stray admission on a host that runs no engine fails too.

- [ ] **Step 3: Run the guards**

Run: `uv run pytest tests/test_infra_alloy_series.py -q`
Expected: PASS. The source-derived case does not exist yet — no `cli/` file names the family until Task 4 — so this step proves only the hand-list direction; Task 4 Step 8 is where the source-derived guard is exercised.

- [ ] **Step 4: Prove the admission guard bites**

```bash
infra/scripts/mutate-probe.sh --file infra/ansible/roles/capture/files/config.alloy \
  --control 's{|zcrypto_exec_position{{' \
  --mutation 's{|zcrypto_exec_resting_order_age_seconds{{' \
  -- uv run pytest 'tests/test_infra_alloy_series.py::test_keep_regex_admits_every_published_series[capture]'
```

Expected: **KILLED**, control proven. The `{` delimiter is deliberate: the pattern contains the alternation's own `|`, which cannot also be the sed delimiter. Both expressions delete one family from the regex — the control an already-required one, the mutation the new one.

- [ ] **Step 5: Commit**

```bash
git add infra/ansible/roles/capture/files/config.alloy tests/test_infra_alloy_series.py
git commit -m "feat(engine): admit the resting-order-age family on the remote-write path"
```

**Deploy note for the closeout, not a step here:** this makes the branch's converge a **two-part attended sequence on the capture primary** — Alloy first (the capture role, so the family is admitted before anything publishes it), the engine second, inside a 4-hourly inter-cycle gap. `fleet-deploys.md`'s primary rules apply to both. Nothing is pushed to Grafana by this branch.

---

### Task 4: The gauge, its publish safety, its panel, and the board's own explainer

**Files:**

- Modify: `cli/engine/command.py`, `cli/engine/executor.py`, `infra/grafana/engine-dashboard.json`
- Test: `tests/test_engine_metrics.py`, `tests/test_engine_executor.py`

**Interfaces:**

- Consumes: `probeplan.MODES` from Task 1; `_ActiveIntent.placed_at` from Task 2; the keep-regex admission from Task 3.
- Produces: `zcrypto_exec_resting_order_age_seconds{mode}`, and `_ExecutionMetrics.set_resting_age`.

- [ ] **Step 1: Write the three failing tests**

Two live in `tests/test_engine_executor.py`, where the executor can actually be driven and `RecordingMetrics` is the house double. `MODES` joins that module's `from cli.engine.probeplan import PLAN_FILENAME, ProbeIntent` line (`:68`).

```python
def test_the_resting_order_age_is_published_under_its_own_mode_and_returns_to_zero(tmp_path):
    """A mode that deliberately leaves an order resting for up to an hour ships with the instrument
    that shows it. The label is what keeps the panel legible across the eras: a drill's artifact and
    a rung-1 trading order are the same shape, and only the mode tells them apart."""
    metrics = RecordingMetrics()
    set_executor_hooks(metrics=metrics)
    ex, client, clock = _resting_executor(
        tmp_path, intents=[_intent(mode="rest-hold", offset_pct=5.0, hold_minutes=45)]
    )
    ex.on_order_event(_accepted(client.last_order_id))

    clock.now = NOW + timedelta(seconds=120)
    ex.on_quote(_quote())
    ex.on_timer(clock.now)

    published = dict(metrics.resting_ages[-len(MODES):])
    assert published["rest-hold"] == pytest.approx(120.0, abs=6)
    # The true positive: without a second label asserted zero, a gauge stuck at the resting value
    # for every mode would pass.
    assert published["execute"] == 0.0

    ex.on_order_event(_canceled(client.last_order_id))  # the venue takes it off the book
    ex.on_timer(NOW + timedelta(seconds=125))
    assert dict(metrics.resting_ages[-len(MODES):])["rest-hold"] == 0.0


def test_a_raise_inside_the_resting_age_publish_never_ends_the_running_plan(tmp_path, monkeypatch):
    """`on_timer`'s catch-all drops the plan and nulls `_active`, so an exception raised anywhere in
    the publish would leave a live order at the venue with nothing tracking it: `_poll` is
    unreachable with no `_active`, the adopt pass has already run, and a kill file would then sweep
    nothing. The publish is wrapped WHOLE -- `_set_resting_age`'s own try/except is a helper-level
    guard and does not cover the loop, the phase read or the arithmetic around it."""
    def _boom(mode, seconds):
        raise RuntimeError("the resting-age publish is broken")

    ex, client, clock = _resting_executor(
        tmp_path, intents=[_intent(mode="rest-hold", offset_pct=5.0, hold_minutes=45)]
    )
    ex.on_order_event(_accepted(client.last_order_id))
    monkeypatch.setattr("cli.engine.executor._set_resting_age", _boom)

    clock.now = NOW + timedelta(seconds=10)
    ex.on_quote(_quote())
    ex.on_timer(clock.now)

    assert ex._plan is not None and ex._active is not None
    assert ex._active.phase == "resting"
    assert client.canceled == []
```

The patch is installed **after** `_resting_executor` deliberately: that helper's own first `on_timer` would otherwise raise before the order is submitted, and its trailing `assert len(client.submitted) == 1` would fail for a reason that says nothing about the wrapper. The autouse `_the_tick_backstop_never_fires` fixture is a second, independent witness here — it fails on the "dropping the running plan" record the unwrapped version emits.

and the exposition test in `tests/test_engine_metrics.py`, beside its siblings:

```python
def test_the_resting_age_gauge_exposes_the_name_and_label_the_panel_reads():
    """Parsed off the registry, not the object: the keep-regex and the panel both match the EXPOSED
    series name and its label."""
    registry = CollectorRegistry()
    metrics = command._ExecutionMetrics(registry)

    metrics.set_resting_age("rest-hold", 42.0)

    assert registry.get_sample_value("zcrypto_exec_resting_order_age_seconds", {"mode": "rest-hold"}) == 42.0
```

- [ ] **Step 2: Run them and watch them fail**

Run: `uv run pytest tests/test_engine_metrics.py::test_the_resting_age_gauge_exposes_the_name_and_label_the_panel_reads -v` and `uv run pytest tests/test_engine_executor.py -v -k "resting_age"`
Expected: FAIL — no such metric family, no `RecordingMetrics.resting_ages`, and `monkeypatch.setattr` raises `AttributeError` because `cli.engine.executor._set_resting_age` does not exist.

- [ ] **Step 3: Declare the gauge and extend the double**

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

In `tests/test_engine_executor.py`, `RecordingMetrics` gains the matching method — a double missing something production calls turns a wiring regression into a log line no test reads:

```python
    def set_resting_age(self, mode, seconds):
        self.resting_ages.append((mode, seconds))
```

with `self.resting_ages = []` in its `__init__`. It is classified in `tests/test_engine_stub_fidelity.py:185` as a stand-in for our own `_ExecutionMetrics`, so no new table entry is owed — but Task 5 Step 5 runs that suite to confirm.

- [ ] **Step 4: Publish it from the tick that already runs**

In `cli/engine/executor.py`, extend the import at `:51`:

```python
from cli.engine.probeplan import MODES, PLAN_FILENAME, ProbeIntent, ProbePlanError, parse_plan, plan_refusals
```

the hook beside `_inc_order`:

```python
def _set_resting_age(mode: str, seconds: float) -> None:
    if _metrics is None:
        return
    try:
        _metrics.set_resting_age(mode, seconds)
    except Exception:
        logger.exception("executor metrics hook raised -- continuing")
```

the call in `on_timer`, after the pump:

```python
            self._pump(now)
            self._publish_resting_age(now)
```

and the method itself, **wrapped whole**:

```python
    def _publish_resting_age(self, now: datetime) -> None:
        """Eagerly zero for every mode, then set the one that is resting: the board's convention is
        that execution numbers read flat zero rather than absent, and a panel over an absent series
        cannot distinguish 'nothing rests' from 'the engine stopped publishing'.

        Wrapped WHOLE, not just at the metrics call. `_set_resting_age`'s try/except is a
        helper-level guard; everything computed around it -- the mode loop, the phase read, the age
        arithmetic -- would otherwise raise into `on_timer`'s catch-all, which drops the plan and
        nulls `_active`. A live order would then rest at the venue with nothing left to end it:
        `_poll` is unreachable with no `_active`, the adopt pass has already run, and a kill file
        would sweep nothing. A telemetry defect may never end a plan.
        """
        try:
            active = self._active
            resting = active is not None and active.phase == "resting" and active.placed_at is not None
            for mode in MODES:
                age = 0.0
                if resting and active.intent.mode == mode:
                    age = max(0.0, (now - active.placed_at).total_seconds())
                _set_resting_age(mode, age)
        except Exception:
            logger.exception("executor resting-age publish raised -- continuing")
```

- [ ] **Step 5: Run the tests**

Run: `uv run pytest tests/test_engine_metrics.py tests/test_engine_executor.py -q`
Expected: PASS.

- [ ] **Step 6: Add the panel**

In `infra/grafana/engine-dashboard.json`: id `67` is unused, the **Execution** row's last panels (65, 66) sit at `y=78, h=6`, and the **Venue truth** row (`id` 70) sits at `y=84` with panels 71–73 at `y=85`. So the new panel takes `y=84` full width, and row 70 shifts to `y=90` with its three panels to `y=91`.

**The datasource uid is the literal `grafanacloud-prom`, copied from panel 65, and the `${GRAFANA_PROM_DS_UID}` form must NOT be used here.** `infra/scripts/grafana-push.sh` substitutes that placeholder on the **alert-rules** path only (a `jq walk` with `gsub`, `:244-252`); dashboards are `json.load` → `json.dumps` → POSTed **verbatim** (`:100-108`). The placeholder appears zero times in `infra/grafana/engine-dashboard.json` today, and every repo guard passes with it there — `test_every_published_app_family_is_charted` matches expression text and reads no datasource — so the panel would simply render "datasource not found" forever, on the one instrument built to show a live resting order during the drills. Same reason for the per-target `datasource` and the `{host=~"$host"}` matcher: both are this board's idiom, and the board's `host` template variable is what scopes every other panel.

```json
{
  "id": 67,
  "type": "timeseries",
  "title": "Resting order age — by plan mode",
  "description": "How long the engine's current resting order has been at the venue. A rest-hold series is a drill's deliberate artifact, not trading; an execute series is a real trading order and should be short-lived, since its own time box is fifteen minutes. Zero means the engine believes nothing rests — which is not the same as the venue holding nothing, if a cancel never reached it.",
  "gridPos": {"x": 0, "y": 84, "w": 24, "h": 6},
  "datasource": {"type": "prometheus", "uid": "grafanacloud-prom"},
  "targets": [
    {
      "datasource": {"type": "prometheus", "uid": "grafanacloud-prom"},
      "refId": "A",
      "expr": "max by (mode) (zcrypto_exec_resting_order_age_seconds{host=~\"$host\"})",
      "legendFormat": "{{mode}}"
    }
  ],
  "fieldConfig": {"defaults": {"unit": "s"}, "overrides": []}
}
```

No `__panelId__` annotation anywhere points at 67: spec D7 ships no rule, so nothing draws a red threshold line on this panel and `test_a_panels_red_line_agrees_with_the_rule_it_charts` has nothing to pair.

- [ ] **Step 7: Correct the board's explainer**

Panel `id: 1` currently tells the reader the Execution row is what happened at the venue and reads flat zero outside an attended window. A resting drill order is venue activity that is *not* trading, so append to its `content`:

```text
 A resting order is the one execution number that can appear without any trading: the `rest-hold` mode places a real order at the venue on purpose and leaves it there for a drill to act on. Read the mode label before reading activity as trading.
```

- [ ] **Step 8: Run the coverage and admission guards**

Run: `uv run pytest tests/test_dashboards_cover_metrics.py tests/test_infra_alloy_series.py tests/test_engine_metrics.py -q`
Expected: PASS. `test_dashboards_cover_metrics.py`'s assertion (2) is what forces the panel, so it fails if the panel is missing or its expression names the family wrongly; its assertion (3) is about *alerted* families and does not apply, since no rule ships. `test_every_published_metric_is_admitted_by_some_hosts_keep_regex` now has a case for this family — the name is in `cli/engine/command.py` from Step 3 — and it passes only because Task 3 admitted it first.

- [ ] **Step 9: Prove the gauge guards bite**

```bash
# the publish is wired to the resting intent at all
infra/scripts/mutate-probe.sh --file cli/engine/executor.py \
  --control 's|_set_resting_age(mode, age)|pass|' \
  --mutation 's|if resting and active.intent.mode == mode:|if False:|' \
  -- uv run pytest 'tests/test_engine_executor.py::test_the_resting_order_age_is_published_under_its_own_mode_and_returns_to_zero'

# the publish cannot end a plan: let the raise out of the wrapper and into on_timer's catch-all
infra/scripts/mutate-probe.sh --file cli/engine/executor.py \
  --control 's|self._publish_resting_age(now)|raise RuntimeError("control")|' \
  --mutation 's|logger.exception("executor resting-age publish raised -- continuing")|raise|' \
  -- uv run pytest 'tests/test_engine_executor.py::test_a_raise_inside_the_resting_age_publish_never_ends_the_running_plan'
```

Expected: **KILLED** on each. The second mutation re-raises out of `_publish_resting_age` into `on_timer`'s catch-all — exactly the failure mode D6 names — so the plan is dropped and the test's `ex._plan is not None` assertion fails.

- [ ] **Step 10: Commit**

```bash
git add cli/engine/command.py cli/engine/executor.py infra/grafana/engine-dashboard.json tests/test_engine_metrics.py tests/test_engine_executor.py
git commit -m "feat(engine): publish the resting order's age by mode, chart it, and fence the publish off the plan"
```

---

### Task 5: The operator's surfaces, the topic, and the closeout

**Files:**

- Modify: `infra/runbooks/engine-procedures.md`, `infra/runbooks/drills-order-path.md`, `docs/open-topics/T0018-phase6-build-sequence.md`, `docs/iterations-history-phase6.md`, and `README.md` only if it documents the plan-file schema (check; do not assume).

- [ ] **Step 1: The plan shape an operator authors**

Beside Drill A's JSON in `engine-procedures.md` (`:192-201`), add the `rest-hold` shape with both fields and a sentence fixing the units — `offset_pct` is a percentage, `5.0` is five percent — because that is the misreading which fills. Show the `--check` line it produces, matching Task 1 Step 8's format, so `:213`'s pinned sample gets a `rest-hold` sibling rather than being rewritten.

- [ ] **Step 2: The outcome vocabulary**

`rest_hold_expired` and `rest_hold_venue_canceled` join the outcomes an operator reads back, beside `rest_cancel_ok` (`:216`) and in the terminal-outcome sentence at `:236`. `rest_hold_venue_canceled` needs its own clause: it means the venue or the operator took the order off the book and the engine deliberately did **not** put it back — a completed intent, not a fault.

`:236` already carries the orphan instruction spec D7 relies on — "**`ambiguous` means the order may be live at the venue** — read Kraken's open orders in the web UI" — and it is unchanged. Do not add a second copy of it.

- [ ] **Step 3: Re-tense the blocked note**

`infra/runbooks/drills-order-path.md:13` reads, in the sentence to edit: "No plan mode keeps an order resting — `rest-cancel` cancels the moment the venue acknowledges — so E, G, F2, A1 and A2 have nothing to act on until a `rest-hold` mode exists". The mode now exists; they remain blocked on the attended converge. Re-tense in place — do not delete the note, and do not claim the drills are runnable. The four per-section *Preconditions* that cite "the `rest-hold` gate in the standing rules" (`:43`, `:248`, `:318`, `:380`) point at that one sentence, so they need no edit if it stays a gate.

**Out of scope, flag it and move on:** the same line's "and B is a command that has not been built" is already stale — `zcrypto engine flatten` merged in `00106`. That is the drill program's to re-tense, not this branch's; name it in the closeout.

- [ ] **Step 4: Close the T0018 build item**

`docs/open-topics/T0018-phase6-build-sequence.md:88`, under `## Suggested next steps`, lists "a `rest-hold` plan mode (an order that rests until cancelled — no existing mode keeps one resting for drills E/G/F2/A)". Load `.claude/skills/topic-ops/SKILL.md` for the mechanics, then move that clause into `## Done so far` rewritten as its outcome — built and disarmed, the two-part converge owed — leaving the sibling `cancel-on-stop` and `re-cancel-on-reconnect` items exactly where they are. The converge itself is already registered in `T0158` ("the order-path tier at rung 1 after `00106` and `rest-hold` converge"), so nothing new is deferred here.

Check `docs/open-topics/README.md`'s T0018 bullet before staging it: it does not quote the rest-hold clause today, so it may need no edit at all. Stage it only if it changed.

- [ ] **Step 5: Verify the whole reachable set**

Run: `uv run pytest tests/test_engine_executor.py tests/test_engine_node.py tests/test_engine_probeplan.py tests/test_engine_metrics.py tests/test_engine_command.py tests/test_engine_stub_fidelity.py tests/test_infra_alloy_series.py tests/test_dashboards_cover_metrics.py tests/test_internal_terms_not_operator_visible.py tests/test_code_prose_citations.py -q`
Expected: PASS. `test_engine_node.py` is in the list because it constructs a `ProbeIntent` by hand (`:710`) and no earlier step runs it: a change to that dataclass's shape is invisible on this branch until CI otherwise. `test_engine_stub_fidelity.py` is in the list because it globs sibling `test_engine_*.py` files and classifies their doubles — `RecordingMetrics` grew a method in Task 3, and any new double must be classified in the same change. `test_internal_terms_not_operator_visible.py` covers the new metric HELP, the panel title and description, and the `--check` line.

- [ ] **Step 6: The iterations-history entry**

Append to `docs/iterations-history-phase6.md`, routed by subject. Load `.claude/skills/iteration-closeout/SKILL.md` for the entry format. **Write it at closeout against the full branch log, never from this plan's expectations.**

State plainly what is *not* proven: no rest-hold order has ever been placed at Kraken; the two converges (Alloy on the primary, then the engine in an inter-cycle gap) are owed and the five drill sections stay blocked on them; and no alert rule ships — spec D7 records why the one first proposed cannot fire and what covers the condition instead.

- [ ] **Step 7: Commit**

```bash
git add infra/runbooks/engine-procedures.md infra/runbooks/drills-order-path.md docs/open-topics/T0018-phase6-build-sequence.md docs/iterations-history-phase6.md
git commit -m "docs(engine): the rest-hold plan shape, its outcomes, T0018's build item, and iter-NNN closeout"
```
