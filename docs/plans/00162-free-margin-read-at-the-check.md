# The margin floor reads Kraken's free margin when a plan opening on margin is picked up Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A plan carrying a margin open — a leveraged `open`, the one intent that extends margin — has its margin floor, summed over its margin opens, measured against Kraken's free margin read from Kraken at its pickup, a read that fails refuses the plan's margin opens alone and none of its closes or spot intents, a plan with none — spot, or margin closes alone — reads nothing and has no floor, a plan of margin closes waiting for nothing, and spec 00090 and the probe window's funding step say free margin.

**Architecture:** `cli/engine/probeplan.py` splits the floor out of `plan_refusals` into `margin_floor_refusals(plan, *, free_margin_eur)`, which answers nothing for a plan `extends_margin` says carries no margin open and sums the margin opens alone (spec D3, D8). The executor gains `read_free_margin`, TradeBalance's `mf` for `ZEUR` on the bare client beside `read_venue_positions` (D4), and `_accept_plan` calls it through `_margin_floor_refusals` once the other walls pass, a failure held for the running plan as `_free_margin_unread`, by which `_start_intent` refuses each margin open (D5), the wait for nothing in flight widened to a margin open (D3); `probe-plan --check` measures the floor against the venue record's figure through the same function (D6). The docs tasks amend spec 00090 (D8), re-true the funding step (D9), log the `[00162]` entries and resolve T0230.

**Tech Stack:** Python 3.14, pytest, `nautilus-trader` 2.0.0rc9.dev20261106 (`KrakenSpotHttpClient.request_margin_metrics`), `tests/kraken_loopback.py`, `tests/cache_restart_child.py` against a local `valkey-server`, `infra/scripts/mutate-probe.sh`.

**Spec:** `docs/specs/00162-free-margin-read-at-the-check-design.md`

**Tier** — `uv run python infra/scripts/tier.py --paths cli/engine/probeplan.py cli/engine/executor.py cli/engine/node.py cli/engine/command.py cli/engine/venuestate.py cli/engine/flatten.py tests/test_engine_probeplan.py tests/test_engine_executor.py tests/test_engine_command.py tests/test_engine_stub_fidelity.py tests/kraken_loopback.py tests/cache_restart_child.py docs/specs/00090-rung-1-order-path-design.md infra/runbooks/engine-procedures.md docs/research/14.phase6-decisions.md docs/open-topics/T0230-the-margin-floor-reads-a-free-margin-figure-refreshed-only-at-connect.md docs/open-topics/archive/T0230-the-margin-floor-reads-a-free-margin-figure-refreshed-only-at-connect.md docs/open-topics/README.md`, run at `5d268c422`:

```
tier: full
full cli/engine/probeplan.py — under cli/engine/, read as a non-prose change
full cli/engine/executor.py — under cli/engine/, read as a non-prose change
full cli/engine/node.py — under cli/engine/, read as a non-prose change
full cli/engine/command.py — under cli/engine/, read as a non-prose change
full cli/engine/venuestate.py — under cli/engine/, read as a non-prose change
full cli/engine/flatten.py — under cli/engine/, read as a non-prose change
full tests/test_engine_probeplan.py — a test importing cli.engine, read as a non-prose change
full tests/test_engine_executor.py — a test importing cli.config, read as a non-prose change
full tests/test_engine_command.py — a test importing cli.config, read as a non-prose change
```

Every fence below was run in a detached scratch worktree, never pushed: by the author against `6795cd513`, and as it now stands at the plan review's third fix against `6d0941296`, whose code is the same, Task 1's fences applied to that tree by a script that read them from this file. Every count a step below expects is that scratch reading, which the step re-runs on the branch. Task 1's cases read `831 deselected, 19 errors` (executor), `1 error` (probeplan) and `1 failed, 72 deselected` (command) with its test files alone, and `19 passed, 831 deselected`, `64 passed` and `1 passed, 72 deselected` with its code; its twenty-seven probe arms each read `mutate-probe: KILLED (control proven, tree restored byte-identically)` in one pass on the scratch commit; `tests/test_cache_restart.py` read `22 passed` there. Tasks 2–5's texts went through the repository's commit hooks on the scratch tree — `mdformat` left the runbook page unchanged, `guidance-guard.py --uncounted` printed no line for it before or after — and `tests/test_decisions_log_shape.py`, `tests/test_decisions_log_ties.py`, `tests/test_open_topics_frontmatter.py`, `tests/test_topics_index.py`, `tests/test_internal_terms_not_operator_visible.py` and `tests/test_trial_registry_provenance.py` passed over them; Task 5's fence ran with the scratch commit's hash in place of each `<sha …>`. The spec's *The measured basis* pastes each reading.

## Global Constraints

- The spec, `docs/specs/00162-free-margin-read-at-the-check-design.md`, is the authority, and a task that names one of its sections reads it there; where it is silent this plan rules, in *Rulings where the spec is silent*.
- No task converges, builds an image, pushes or reaches a venue: the change ships on the engine image spec D10 names, the converge the fleet's concern. Every venue read in a test goes to `tests/kraken_loopback.py` or a stub; the autouse `_no_production_venue_read` fixture in `tests/test_engine_executor.py` fails a case that reaches a production reader, `read_free_margin` among them once Task 1 lands.
- The worktree is `/home/zhaow/Projects/zcrypto-kraken/.claude/worktrees/t0230` (branch `feat/t0230-free-margin-read-at-the-check`); every command runs with it as the working directory, and git takes `-C` that path. The main checkout is live.
- Before a task's first command, `mkdir -p .tmp/implementer .local/free-margin-read-at-the-check`, its own call: every pytest run takes `--basetemp=.tmp/implementer/pt`, and pytest makes no parent of its basetemp.
- Tests per commit: `infra/scripts/consumers.sh --tests --direct <the commit's changed paths> 2>.tmp/implementer/cons.err >.tmp/implementer/cons.list`, its own call, exit 2 meaning no reader; `cat .tmp/implementer/cons.err`, its own call; then `T="$(sort -u .tmp/implementer/cons.list | tr '\n' ' ') <the task's test files>"; uv run pytest $T -m "not slow" -q -p no:cacheprovider --basetemp=.tmp/implementer/pt -rs`. Never the full suite.
- The restart harness's slow cases (18 of its 22), which `-m "not slow"` deselects: Task 1 changes the harness's child and loopback, so it runs the whole harness file once in its own step.
- The gate is `uv run pre-commit run -a`, re-run until clean, its rewrites staged.
- A comment or docstring stays only where a reader would act differently without it, and is correct; state and decisions stay, an event goes to the PR body. A runbook page and an engine string literal carry no `spec <NNNNN>`, `D<N>`, `T<NNNN>`, `iter-<N>`, `Phase <N>` or `WP<N>` token (`tests/test_internal_terms_not_operator_visible.py`).
- Commits: Conventional Commits, one subject per change, after a `git -C <the worktree> add <every path the commit changes, a git mv source aside, which the move stages>` of its own, through `git -C <the worktree> commit -F - <<'EOF'`; the message says what changed and pastes the result line of the test command it names, run over the commit's own tree; one state-changing git command per Bash call; never an amend, `--no-verify` or `git stash`; every message ends with `Co-Authored-By: Claude <actual executing model> <noreply@anthropic.com>`, the implementer's own model in place of the placeholder, and `Claude-Session: https://claude.ai/code/session_018eFiE9ZzjweN7A4N9yBCTV`.
- Probes (this plan's tier is `full`): each arm Task 1 lists runs as its own call on the committed tree, `infra/scripts/mutate-probe.sh --file <file> --control '1,$d' --mutation '<mutation>' -- uv run pytest <test file> -k '<selection>' -q -p no:cacheprovider --basetemp=.tmp/implementer/pt`. Before each arm its pattern's count reads `1`, its own call: `sed -n '<range>p' <file> | grep -c -F '<pattern>'` for the arm whose mutation opens with a range, `grep -c -F '<pattern>' <file>` otherwise, the pattern the mutation's search text with its sed escapes removed. `: > .local/free-margin-read-at-the-check/probes-task-1.txt` before the arms; after each arm its id and the script's last line are appended, its own call. The verdicts ride an empty commit through `git -C <the worktree> commit --allow-empty -F - <<'EOF'`, subject `test(engine): the margin floor's read at the pickup proven by infra/scripts/mutate-probe.sh`, its body the probes file pasted whole, then the trailers; it names no test run, the verdicts being its result.
- A helper this plan names in a test (`_executor`, `_plan_entry`, `_plan_dict`, `_intent`, `_drop_plan`, `_plan_path`, `_executor_errors`, `_event`, `_resting_limit_order`, `_cache_config`, `_loopback_credentials`, `_intent_entry`, `_held`, `_quote`, `StubClient`, `StubCache`, `NOW`, `executor_module`, `kraken_loopback` in `tests/test_engine_executor.py`; `_plan`, `_intent`, `_margin_plan`, `NOW` in `tests/test_engine_probeplan.py`) exists at `6795cd513`; where a fence's call does not fit its real signature, the case's intent and assertions bind, not the spelling, and the report says what changed.

## Rulings where the spec is silent

- **Names:** `extends_margin` and its per-intent `_extends_margin`, `margin_floor_refusals`, `read_free_margin`, `_margin_floor_refusals`, the constructor keyword `venue_free_margin` and its attribute `_venue_free_margin`, the running plan's `_free_margin_unread`, `_MARGIN_BALANCE_ASSET`, the test reader `_VenueFreeMargin`, the loopback field `trade_balance`.
- **Placement:** `_extends_margin` then `extends_margin` directly above `plan_refusals`, and `margin_floor_refusals` directly below it; `read_free_margin` directly after `read_venue_positions`; `_margin_floor_refusals` directly above `_mixed_inventory_refusals`; `venue_free_margin` directly after `venue_positions` in the constructor's signature and body; `_free_margin_unread` directly after `_plan_window_close` in the constructor, set directly after `self._resolved_notional = {}` in `_accept_plan`, and read in `_start_intent` directly after the gate's refusal; `_MARGIN_BALANCE_ASSET` directly after `_ACCOUNT_ID`; `_VenueFreeMargin` directly after `_VenuePositions`; `trade_balance` directly after `balances` in `KrakenLoopback`. The executor's floor cases replace `test_a_margin_floor_violating_plan_is_refused_naming_the_floor` and `test_an_eur_only_balance_is_the_free_cash_figure_the_margin_floor_is_measured_against` where they stand; the loopback read cases go directly before `test_read_venue_orders_refuses_without_credentials_before_building_a_client`; the wait case directly before `test_a_margin_position_read_that_fails_refuses_the_opening_intents_by_name`; the probeplan floor cases replace the five `plan_refusals` floor cases where they stand.
- **`probe-plan --check` keeps its `ZEUR`-then-`EUR` keys and prints no new line** (D6): its floor case's venue record writes `EUR`, the spelling the engine writes, the other `tests/test_engine_command.py` fixtures `ZEUR`, and the funding step names the check's figure (D9).
- **What a task writes is in the task, verbatim, or printed by its own first command; nothing is written from a description.** The runbook text is the spec's *Runbook texts* fence, which Task 3 prints from the spec and pastes byte for byte, so the spec's copy is the one copy.

## File structure

- Modify `cli/engine/probeplan.py`: `_extends_margin` and `extends_margin`; `plan_refusals` without the floor; `margin_floor_refusals`; the multiplier's comment.
- Modify `cli/engine/executor.py`: the import; `read_free_margin`; `ProbeExecutor`'s `venue_free_margin` and `_free_margin_unread`; `_nothing_in_flight`'s docstring; `_accept_plan`'s wait and floor; `_margin_floor_refusals`; `_start_intent`'s refusal of a margin open.
- Modify `cli/engine/node.py`: `_MARGIN_BALANCE_ASSET`. Modify `cli/engine/command.py`: `probe-plan --check`'s floor. Modify `cli/engine/venuestate.py`: `VenueState`'s docstring. Modify `cli/engine/flatten.py`: `QUOTE_CURRENCY`'s comment.
- Modify `tests/test_engine_probeplan.py`, `tests/test_engine_executor.py`, `tests/test_engine_command.py`, `tests/test_engine_stub_fidelity.py`, `tests/kraken_loopback.py`, `tests/cache_restart_child.py`.
- Modify `docs/specs/00090-rung-1-order-path-design.md`, `infra/runbooks/engine-procedures.md`, `docs/research/14.phase6-decisions.md`; move `docs/open-topics/T0230-the-margin-floor-reads-a-free-margin-figure-refreshed-only-at-connect.md` to `docs/open-topics/archive/`; re-render `docs/open-topics/README.md`.

## Review Focus

1. A plan mixing a spot buy, a margin open and a margin close: the floor sums the margin open alone. Pinned by Task 1's `test_the_margin_floor_sums_the_margin_opens_alone`.
2. A plan opening on margin that an earlier wall already refuses — expired, a duplicate id, over the cap — is refused for that alone and makes no signed read. The expired one is pinned by Task 1's `test_a_leveraged_plan_the_walls_refuse_reads_no_free_margin`; a duplicate id and the cap feed the same `reasons` its gate reads.
3. A margin close, a reducer, extends no margin: its plan reads no free margin and is picked up on a tick an order of this process is in flight, where a margin open waits for nothing in flight, both with the cache off. Pinned by `[margin-close]` and `[margin-open]` of Task 1's `test_a_margin_open_waits_for_a_tick_with_nothing_in_flight_before_the_free_margin_read_and_a_close_never_does`.
4. A read answering in another asset, or past the 30 s bound, refuses rather than compares. Pinned by Task 1's `test_read_free_margin_refuses_an_answer_labelled_other_than_eur` and `test_read_free_margin_raises_on_a_kraken_error_and_past_its_bound[past-its-bound]`.
5. The restart harness's margin opens read the loopback's TradeBalance, never a production client. Pinned by the harness's 22 cases over the child's redirect, Task 1 Step 5.
6. A read that fails refuses the plan's margin opens alone, each at its start, and a margin close or a spot open in the same plan starts, the cache off; the failure refuses no later plan's margin opens. Pinned by Task 1's `test_a_free_margin_read_that_fails_refuses_the_margin_opens_naming_the_read_and_runs_the_close[margin-close|spot-open]` and `test_a_failed_free_margin_read_is_held_for_its_plan_alone`.

---

### Task 1: The floor reads Kraken's free margin at the pickup (spec D2–D8)

**Files:**
- Modify: `cli/engine/probeplan.py`, `cli/engine/executor.py`, `cli/engine/node.py`, `cli/engine/command.py`, `cli/engine/venuestate.py`, `cli/engine/flatten.py`, `tests/kraken_loopback.py`, `tests/cache_restart_child.py`
- Test: `tests/test_engine_probeplan.py`, `tests/test_engine_executor.py`, `tests/test_engine_command.py`, `tests/test_engine_stub_fidelity.py`

**Interfaces:**
- Consumes: `_bare_client`, `_VENUE_READ_TIMEOUT_SECONDS`, `_nothing_in_flight`, `_refuse_intent`, `ledgered_plan_ids`, `KrakenSpotHttpClient.request_margin_metrics(asset=…)`.
- Produces: `extends_margin(plan: ProbePlan) -> bool`; `plan_refusals(plan, *, now, ledgered, max_plan_notional_eur) -> tuple[str, ...]`; `margin_floor_refusals(plan: ProbePlan, *, free_margin_eur: float) -> tuple[str, ...]`; `read_free_margin(*, base_url: str | None = None) -> float`; `ProbeExecutor(..., venue_free_margin=None, ...)`; `_MARGIN_BALANCE_ASSET = "ZEUR"`; the INFO line `probe plan <id>: Kraken's free margin reads <x.xx> EUR at its pickup`, a failed read's WARNING `probe plan <id>: Kraken's free margin could not be read for the margin floor -- <class>: <message>`, the wait's `probe plan <id> waits for a tick with nothing in flight -- it takes a signed venue read`, and the reason `Kraken's free margin could not be read for the margin floor -- <class>: <message>`, each margin open's at its start, spec D5 and D7's.

- [ ] **Step 1: Write the failing cases and their fixtures.**

In `tests/test_engine_probeplan.py`, the import reads:

```python
from cli.engine.probeplan import PLAN_TTL, ProbePlanError, extends_margin, margin_floor_refusals, parse_plan, plan_refusals
```

Every `plan_refusals(…)` call drops its `, free_zeur=1000.0` (`grep -c 'free_zeur' tests/test_engine_probeplan.py` reads `0` after). The five cases from `test_plan_refusals_margin_floor_passes_at_free_zeur_100` through `test_plan_refusals_an_inf_free_zeur_refuses` are replaced, `_margin_plan` kept above them, by:

```python
def test_the_margin_floor_passes_at_free_margin_100():
    # sum(notional/leverage) = 15 + 15 = 30; 30 x 2.5 = 75 <= 100.
    assert margin_floor_refusals(_margin_plan(), free_margin_eur=100.0) == ()


def test_the_margin_floor_refuses_at_free_margin_50_naming_free_margin():
    reasons = margin_floor_refusals(_margin_plan(), free_margin_eur=50.0)
    assert reasons == ("margin floor: 75.00 EUR required exceeds free margin 50.00 EUR",)


def test_the_margin_floor_exactly_at_free_margin_passes():
    # margin_required == 75.0 exactly; the boundary itself must NOT refuse.
    assert margin_floor_refusals(_margin_plan(), free_margin_eur=75.0) == ()


@pytest.mark.parametrize("free", [float("nan"), float("inf")], ids=["nan", "inf"])
def test_a_non_finite_free_margin_refuses_a_plan_opening_on_margin(free):
    assert margin_floor_refusals(_margin_plan(), free_margin_eur=free) == (f"free margin is not finite: {free!r}",)


def test_the_margin_floor_sums_the_margin_opens_alone():
    # 30 / 2 = 15; 15 x 2.5 = 37.5 > 37, the spot buy's 90 and the margin close's 30 counting for nothing.
    plan = _plan(
        intents=[
            _intent(notional_eur=90.0),
            _intent(notional_eur=30.0, leverage=2),
            _intent(side="sell", action="close", notional_eur=30.0, leverage=2),
        ]
    )
    assert margin_floor_refusals(plan, free_margin_eur=37.0) == ("margin floor: 37.50 EUR required exceeds free margin 37.00 EUR",)


def test_a_plan_that_extends_no_margin_has_no_margin_floor():
    spot = _plan(intents=[_intent(), _intent(side="sell", action="close", notional_eur=None, qty=0.001)])
    closes = _plan(intents=[_intent(side="sell", action="close", notional_eur=30.0, leverage=2)])
    for plan in (spot, closes):
        assert (extends_margin(plan), margin_floor_refusals(plan, free_margin_eur=float("nan"))) == (False, ())
    assert extends_margin(_plan(intents=[_intent(), _intent(notional_eur=30.0, leverage=2)])) is True
```

In `tests/kraken_loopback.py`, `KrakenLoopback` gains, after `balances`:

```python
    # The TradeBalance answer, whatever `asset` a request names: `mf` is the free margin, `e` the equity.
    trade_balance: dict[str, str] = field(
        default_factory=lambda: {
            "eb": "1000.0",
            "tb": "1000.0",
            "m": "0.0",
            "uv": "0.0",
            "n": "0.0",
            "c": "0.0",
            "v": "0.0",
            "e": "1000.0",
            "mf": "1000.0",
        }
    )
```

and `answer`'s TradeBalance arm, the nine-field literal it returns today, becomes `return dict(self.trade_balance), []`.

In `tests/cache_restart_child.py`, after the `read_venue_positions` partial:

```python
executor_module.read_free_margin = partial(executor_module.read_free_margin, base_url=CONFIG["base_url"])
```

and `_refuse_production_defaults`' tuple gains `executor_module.read_free_margin,` after `executor_module.read_venue_positions,`.

In `tests/test_engine_stub_fidelity.py`, after the `_VenuePositions` entry of `test_engine_executor.py`'s table:

```python
        "_VenueFreeMargin": Standin(
            OURS, "cli.engine.executor.read_free_margin, the venue_free_margin ProbeExecutor is built with", ()
        ),
```

In `tests/test_engine_command.py`, `test_probe_plan_check_refuses_a_margin_intent_over_the_free_balance`'s `_probe_plan_env(…)` call takes `balances={"EUR": 5.0}` in place of `balances={"ZEUR": 5.0}`, the one spelling the engine's venue record carries, and its last assertion reads `assert "margin floor: 50.00 EUR required exceeds free margin 5.00 EUR" in _output(result)`.

In `tests/test_engine_executor.py`: `_executor` takes `venue_free_margin=None` after `venue_positions=None` and passes, after its `venue_positions=` line:

```python
        # 1000 EUR of free margin unless a case hands in its own: a margin open's floor then passes.
        venue_free_margin=venue_free_margin if venue_free_margin is not None else _VenueFreeMargin(),
```

`_no_production_venue_read`'s docstring reads `-- the status read's and the free-margin read's let a call with a` where it read `-- and the status read's let a call with a`, and the fixture gains, after `_refuse_positions`, and its last `setattr` after the positions one:

```python
    free_margin = executor_module.read_free_margin

    def _refuse_free_margin(*, base_url=None):
        if base_url is None:
            pytest.fail("a test reached the production free-margin read -- pass venue_free_margin")
        return free_margin(base_url=base_url)
```

```python
    monkeypatch.setattr(executor_module, "read_free_margin", _refuse_free_margin)
```

After `_VenuePositions`:

```python
class _VenueFreeMargin:
    """The executor's `venue_free_margin` reader: answers `free`, Kraken's free margin in EUR, or raises
    `raises` while a case leaves it set, and counts its calls."""

    def __init__(self, free=1000.0, *, raises=None):
        self.free = free
        self.calls = 0
        self.raises = raises

    def __call__(self):
        self.calls += 1
        if self.raises is not None:
            raise self.raises
        return self.free
```

`test_a_margin_floor_violating_plan_is_refused_naming_the_floor` and `test_an_eur_only_balance_is_the_free_cash_figure_the_margin_floor_is_measured_against` are replaced by:

```python
def test_a_margin_floor_violating_plan_is_refused_naming_the_floor(tmp_path):
    """Free margin 50 against 90 EUR at 3x: 30 EUR of margin needs 75 EUR at the 250% floor."""
    client = StubClient()
    ex = _executor(tmp_path, client=client, venue_free_margin=_VenueFreeMargin(50.0))
    _drop_plan(tmp_path, _plan_dict(intents=[_intent(notional_eur=90.0, leverage=3)]))

    ex.on_timer(NOW)

    assert client.subscribed == [] and client.submitted == []
    entry = _plan_entry(tmp_path)
    assert (entry["disposition"], entry["reasons"]) == (
        "refused",
        ["margin floor: 75.00 EUR required exceeds free margin 50.00 EUR"],
    )


@pytest.mark.parametrize(
    ("cache_eur", "kraken_free", "disposition", "reasons"),
    [
        (1_000_000.0, 99.84, "refused", ["margin floor: 112.50 EUR required exceeds free margin 99.84 EUR"]),
        (0.0, 1000.0, "accepted", []),
    ],
    ids=["cache-rich-kraken-short", "cache-empty-kraken-rich"],
)
def test_the_margin_floor_reads_krakens_free_margin_at_the_pickup_and_never_the_caches_account(
    tmp_path, cache_eur, kraken_free, disposition, reasons
):
    """The basis, the owner's of 2026-09-23: free margin, read from Kraken when the plan is picked up. The
    Cache's account summary is set against Kraken's in both directions, so a check reading the Cache flips
    both cases."""
    client = StubClient(StubCache(balances={"EUR": cache_eur, "ZEUR": cache_eur}))
    free = _VenueFreeMargin(kraken_free)
    ex = _executor(tmp_path, client=client, venue_free_margin=free)
    _drop_plan(tmp_path, _plan_dict(intents=[_intent(notional_eur=90.0, leverage=2)]))

    ex.on_timer(NOW)

    entry = _plan_entry(tmp_path)
    assert (entry["disposition"], entry["reasons"], free.calls) == (disposition, reasons, 1)


def test_a_fill_between_connects_moves_the_free_margin_the_next_plans_floor_is_measured_against(tmp_path, _loopback_credentials):
    """One process, one connect: the Cache's account reads the 50 EUR it read then, while the loopback moves
    Kraken's free margin to 1000 EUR between two pickups. The first plan is refused on 50, the second accepted
    on 1000, each read from Kraken's TradeBalance on the real client."""
    client = StubClient(StubCache(balances={"EUR": 50.0}))
    with kraken_loopback.serve() as venue:
        venue.trade_balance |= {"e": "50.0", "mf": "50.0"}
        ex = _executor(tmp_path, client=client, venue_free_margin=lambda: executor_module.read_free_margin(base_url=venue.base_url))
        _drop_plan(tmp_path, _plan_dict(plan_id="p-1", intents=[_intent(notional_eur=90.0, leverage=2)]))
        ex.on_timer(NOW)
        venue.trade_balance |= {"e": "1000.0", "mf": "1000.0"}
        _drop_plan(tmp_path, _plan_dict(plan_id="p-2", intents=[_intent(notional_eur=90.0, leverage=2)]))
        ex.on_timer(NOW + timedelta(seconds=5))
        calls = list(venue.private_calls)

    first, second = _plan_entry(tmp_path, index=0), _plan_entry(tmp_path, index=1)
    assert (first["plan_id"], first["disposition"], first["reasons"]) == (
        "p-1",
        "refused",
        ["margin floor: 112.50 EUR required exceeds free margin 50.00 EUR"],
    )
    assert (second["plan_id"], second["disposition"], second["reasons"]) == ("p-2", "accepted", [])
    assert calls.count("TradeBalance") == 2


@pytest.mark.parametrize(
    ("beside", "subscribed"),
    [
        (_intent(side="sell", action="close", notional_eur=30.0, leverage=2), "BTC/EUR.KRAKEN"),
        (_intent(symbol="SOL/EUR", notional_eur=20.0), "SOL/EUR.KRAKEN"),
    ],
    ids=["margin-close", "spot-open"],
)
def test_a_free_margin_read_that_fails_refuses_the_margin_opens_naming_the_read_and_runs_the_close(tmp_path, beside, subscribed):
    """No fallback to the Cache's account summary, however much it reads, and nothing but the margin open
    refused by the read's failure, the cache off: the open is refused at its start, and the intent beside it, a
    margin close on a live position or a spot open, starts."""
    client = StubClient(StubCache(balances={"EUR": 1_000_000.0}, positions=_held(**{"BTC/EUR": 0.001})))
    free = _VenueFreeMargin(raises=RuntimeError("API error: EGeneral:Permission denied"))
    ex = _executor(tmp_path, client=client, venue_free_margin=free)
    path = _drop_plan(tmp_path, _plan_dict(intents=[_intent(symbol="ETH/EUR", notional_eur=30.0, leverage=2), beside]))

    with _executor_errors(level=logging.WARNING) as records:
        ex.on_timer(NOW)

    reason = "Kraken's free margin could not be read for the margin floor -- RuntimeError: API error: EGeneral:Permission denied"
    entry, opened = _plan_entry(tmp_path), _intent_entry(tmp_path, 0)
    assert (entry["disposition"], entry["reasons"], free.calls, path.exists()) == ("accepted", [], 1, False)
    assert (opened["outcome"], opened["reasons"]) == ("refused", [reason])
    assert (_intent_entry(tmp_path, 1)["outcome"], client.subscribed) == ("pending", [subscribed])
    assert [(r.levelname, r.getMessage()) for r in records] == [
        ("WARNING", f"probe plan p-1: {reason}"),
        ("WARNING", f"intent 0 of plan p-1 refused: {reason}"),
    ]


def test_a_failed_free_margin_read_is_held_for_its_plan_alone(tmp_path):
    """The read's failure refuses the margin opens of the plan it was read for, never a later plan's: the next
    plan's read answers, and its margin open starts."""
    client = StubClient()
    free = _VenueFreeMargin(raises=RuntimeError("API error: EService:Unavailable"))
    ex = _executor(tmp_path, client=client, venue_free_margin=free)
    _drop_plan(tmp_path, _plan_dict(plan_id="p-1", intents=[_intent(notional_eur=30.0, leverage=2)]))
    ex.on_timer(NOW)
    free.raises = None
    _drop_plan(tmp_path, _plan_dict(plan_id="p-2", intents=[_intent(notional_eur=30.0, leverage=2)]))
    ex.on_timer(NOW + timedelta(seconds=5))

    first, second = _plan_entry(tmp_path, index=0), _plan_entry(tmp_path, index=1)
    assert (first["plan_id"], first["intents"][0]["outcome"], free.calls) == ("p-1", "refused", 2)
    assert (second["plan_id"], second["disposition"], second["intents"][0]["outcome"]) == ("p-2", "accepted", "pending")
    assert client.subscribed == ["BTC/EUR.KRAKEN"]


@pytest.mark.parametrize("enabled", [True, False], ids=["cache-on", "cache-off"])
def test_a_spot_only_plan_reads_no_free_margin(tmp_path, enabled):
    """The floor gates margin opens only: a read that would refuse is never made, the cache on or off."""
    free = _VenueFreeMargin(raises=RuntimeError("must not be read"))
    ex = _executor(tmp_path, config=_cache_config(tmp_path, enabled), venue_free_margin=free)
    _drop_plan(tmp_path, _plan_dict(intents=[_intent(notional_eur=30.0)]))

    ex.on_timer(NOW)

    assert (_plan_entry(tmp_path)["disposition"], free.calls) == ("accepted", 0)


def test_a_leveraged_plan_the_walls_refuse_reads_no_free_margin(tmp_path):
    free = _VenueFreeMargin(raises=RuntimeError("must not be read"))
    ex = _executor(tmp_path, venue_free_margin=free)
    created_at = NOW - timedelta(minutes=61)
    _drop_plan(tmp_path, _plan_dict(created_at=created_at, intents=[_intent(notional_eur=30.0, leverage=2)]))

    ex.on_timer(NOW)

    entry = _plan_entry(tmp_path)
    assert (entry["disposition"], entry["reasons"], free.calls) == (
        "refused",
        [f"plan expired: created_at {created_at.isoformat()} is over 60 minutes old"],
        0,
    )


def test_the_free_margin_read_logs_the_figure_it_measured_against(tmp_path):
    ex = _executor(tmp_path, venue_free_margin=_VenueFreeMargin(812.5))
    _drop_plan(tmp_path, _plan_dict(intents=[_intent(notional_eur=30.0, leverage=2)]))

    with _executor_errors(level=logging.INFO) as records:
        ex.on_timer(NOW)

    assert "probe plan p-1: Kraken's free margin reads 812.50 EUR at its pickup" in [r.getMessage() for r in records]
```

Directly before `test_read_venue_orders_refuses_without_credentials_before_building_a_client`:

```python
def test_read_free_margin_reads_tradebalances_mf_on_the_real_client(_loopback_credentials):
    """`mf`, never the equity `e` or the trade balance `tb`, each set apart here, in one private call."""
    with kraken_loopback.serve() as venue:
        venue.trade_balance |= {"eb": "1500.1", "tb": "1400.2", "m": "12.3", "e": "1399.6", "mf": "1387.3"}
        free = executor_module.read_free_margin(base_url=venue.base_url)
        calls = list(venue.private_calls)

    assert (free, calls) == (1387.3, ["TradeBalance"])


@pytest.mark.parametrize(
    ("staging", "raised", "match"),
    [
        ({"errors": {"TradeBalance": "EGeneral:Permission denied"}}, RuntimeError, "EGeneral:Permission denied"),
        ({"stalls": {"TradeBalance": 3.0}}, TimeoutError, None),
    ],
    ids=["kraken-error", "past-its-bound"],
)
def test_read_free_margin_raises_on_a_kraken_error_and_past_its_bound(_loopback_credentials, monkeypatch, staging, raised, match):
    monkeypatch.setattr(executor_module, "_VENUE_READ_TIMEOUT_SECONDS", 0.5)
    with kraken_loopback.serve() as venue:
        for name, value in staging.items():
            setattr(venue, name, value)
        with pytest.raises(raised, match=match):
            executor_module.read_free_margin(base_url=venue.base_url)


def test_read_free_margin_refuses_an_answer_labelled_other_than_eur(_loopback_credentials, monkeypatch):
    """The client labels the answer by the asset asked: a read asked in another one is refused, never compared
    in EUR."""
    monkeypatch.setattr("cli.engine.node._MARGIN_BALANCE_ASSET", "XXBT")
    with kraken_loopback.serve() as venue:
        with pytest.raises(EngineError, match="answered in 'BTC', not EUR"):
            executor_module.read_free_margin(base_url=venue.base_url)
```

In `test_a_plan_with_an_opening_intent_waits_for_a_tick_with_nothing_in_flight_before_the_mixed_inventory_read`, `held` reads `"probe plan p-1 waits for a tick with nothing in flight -- it takes a signed venue read"`. Directly before `test_a_margin_position_read_that_fails_refuses_the_opening_intents_by_name`:

```python
@pytest.mark.parametrize(
    ("intent", "reads"),
    [(_intent(leverage=2), 1), (_intent(side="sell", action="close", leverage=2), 0)],
    ids=["margin-open", "margin-close"],
)
def test_a_margin_open_waits_for_a_tick_with_nothing_in_flight_before_the_free_margin_read_and_a_close_never_does(
    tmp_path, intent, reads
):
    """The free-margin read is signed on the trade key, so without the cache too a plan opening on margin waits
    in its file while the startup pass's cancel is PENDING_CANCEL, and is read and picked up on the next tick; a
    margin close extends no margin, so its plan reads nothing and is picked up on the first."""

    class _PendingCancel(StubClient):
        def cancel_order(self, client_order_id):
            super().cancel_order(client_order_id)
            self.cache.order(client_order_id).apply(
                _event(OrderPendingCancel, client_order_id=str(client_order_id), strategy_id=StrategyId("EXTERNAL"))
            )

    adopted = "OADOPT-AAAAA-BBBBBB"
    client = _PendingCancel(
        StubCache(open_orders=[_resting_limit_order(adopted, venue_order_id=adopted, strategy_id=StrategyId("EXTERNAL"))])
    )
    free = _VenueFreeMargin()
    ex = _executor(tmp_path, client=client, config=_cache_config(tmp_path, False), venue_free_margin=free)
    _drop_plan(tmp_path, _plan_dict(intents=[intent]))

    ex.on_timer(NOW)

    assert client.cache.order(ClientOrderId(adopted)).is_inflight
    if reads:
        assert _plan_path(tmp_path).exists() and free.calls == 0
        client.cache.order(ClientOrderId(adopted)).apply(
            _event(OrderCanceled, client_order_id=adopted, strategy_id=StrategyId("EXTERNAL"))
        )
        ex.on_timer(NOW + timedelta(seconds=5))
    assert not _plan_path(tmp_path).exists()
    assert (_plan_entry(tmp_path)["disposition"], free.calls) == ("accepted", reads)
```

- [ ] **Step 2: Run them, expect FAIL.** `uv run pytest tests/test_engine_executor.py -k 'margin_floor_violating or never_the_caches_account or fill_between_connects or free_margin_read_that_fails or held_for_its_plan_alone or spot_only_plan_reads_no_free_margin or walls_refuse_reads_no_free_margin or logs_the_figure or margin_open_waits or read_free_margin or opening_intent_waits' -q -p no:cacheprovider --basetemp=.tmp/implementer/pt` reads `831 deselected, 19 errors`, each `AttributeError: module 'cli.engine.executor' has no attribute 'read_free_margin'`; `uv run pytest tests/test_engine_probeplan.py -q -p no:cacheprovider --basetemp=.tmp/implementer/pt` reads `1 error`, the import of `extends_margin`; `uv run pytest tests/test_engine_command.py -k margin_intent_over_the_free_balance -q -p no:cacheprovider --basetemp=.tmp/implementer/pt` reads `1 failed, 72 deselected`.

- [ ] **Step 3: Implement.**

In `cli/engine/probeplan.py`, the multiplier's comment's two lines read `# Master-plan §10's 250% floor at rung scale: required margin (notional / leverage, summed over the` and `# margin opens) times this multiplier must fit under Kraken's free margin.`, and everything from `def plan_refusals(` to the file's end is replaced by:

```python
def _extends_margin(intent: ProbeIntent) -> bool:
    return intent.leverage is not None and intent.action == "open"


def extends_margin(plan: ProbePlan) -> bool:
    return any(_extends_margin(intent) for intent in plan.intents)


def plan_refusals(
    plan: ProbePlan,
    *,
    now: datetime,
    ledgered: frozenset[str],
    max_plan_notional_eur: float,
) -> tuple[str, ...]:
    """Every applicable refusal reason for `plan` but the margin floor's, in declaration order -- plural by design: the
    operator sees every condition between them and submission, not just the first. A `qty` intent contributes 0.0 to the
    notional sum, no price yet to convert it -- deferred, never exempt: the executor's `_over_cap_reason` cumulates its
    real notional at sizing time."""
    reasons: list[str] = []

    ttl_minutes = int(PLAN_TTL.total_seconds() // 60)
    if now - plan.created_at > PLAN_TTL:
        reasons.append(f"plan expired: created_at {plan.created_at.isoformat()} is over {ttl_minutes} minutes old")
    if plan.created_at > now:
        reasons.append("created_at is in the future")
    if plan.plan_id in ledgered:
        reasons.append("plan_id already ledgered")

    # The cap is checked finite at the point of use: a NaN or +inf bound compares False against any total and fails
    # its check open.
    total_notional = sum(i.notional_eur or 0.0 for i in plan.intents)
    if not math.isfinite(max_plan_notional_eur):
        reasons.append(f"max_plan_notional_eur is not finite: {max_plan_notional_eur!r}")
    elif total_notional > max_plan_notional_eur:
        reasons.append(f"plan notional {total_notional:.2f} EUR exceeds the cap {max_plan_notional_eur:.2f} EUR")

    return tuple(reasons)


def margin_floor_refusals(plan: ProbePlan, *, free_margin_eur: float) -> tuple[str, ...]:
    """The margin floor's refusal of `plan` against Kraken's free margin, or none. A margin open, a leveraged `open`, is
    the one intent that extends margin; a close, spot or leveraged, extends none. So a plan with no margin open has no
    floor and a caller reads no free margin for one, and the sum counts the margin opens alone. `free_margin_eur` is a
    venue figure, outside `cli/config.py`'s finiteness check, and a NaN or +inf compares False against any requirement."""
    if not extends_margin(plan):
        return ()
    margin_required = sum(i.notional_eur / i.leverage for i in plan.intents if _extends_margin(i)) * _MARGIN_FLOOR_MULTIPLIER
    if not math.isfinite(free_margin_eur):
        return (f"free margin is not finite: {free_margin_eur!r}",)
    if margin_required > free_margin_eur:
        return (f"margin floor: {margin_required:.2f} EUR required exceeds free margin {free_margin_eur:.2f} EUR",)
    return ()
```

In `cli/engine/node.py`, after `_ACCOUNT_ID = "KRAKEN-001"`:

```python
# TradeBalance's `asset`: the execution client's account summary is denominated in it, and the margin floor's
# read asks for the same one.
_MARGIN_BALANCE_ASSET = "ZEUR"
```

and `_exec_client_config` passes `margin_balance_asset=_MARGIN_BALANCE_ASSET,`.

In `cli/engine/executor.py`: the `cli.engine.probeplan` import becomes one name a line, `MODES`, `PLAN_FILENAME`, `ProbeIntent`, `ProbePlanError`, `_extends_margin`, `extends_margin`, `margin_floor_refusals`, `parse_plan`, `plan_refusals`, as the gate's `ruff` lays it. After `read_venue_positions`:

```python
def read_free_margin(*, base_url: str | None = None) -> float:
    """Kraken's free margin in EUR, TradeBalance's `mf` for `_MARGIN_BALANCE_ASSET`, on a client of its own
    (`_bare_client`) and on `read_venue_holdings`' terms: the margin floor's figure (`_margin_floor_refusals`). One
    private call. An answer labelled other than EUR raises -- the client labels it by the asset asked, an omitted one
    reading USD -- and so do a Kraken error, an `mf` missing or unparseable, and anything short of an answer inside
    `_VENUE_READ_TIMEOUT_SECONDS`."""
    from cli.engine.node import _MARGIN_BALANCE_ASSET

    client = _bare_client(base_url)

    async def _read():
        return await client.request_margin_metrics(asset=_MARGIN_BALANCE_ASSET)

    metrics = asyncio.run(asyncio.wait_for(_read(), timeout=_VENUE_READ_TIMEOUT_SECONDS))
    asset = None if metrics is None else metrics.get("asset")
    if asset != "EUR":
        raise EngineError(f"the venue's trade balance answered in {asset!r}, not EUR -- the margin floor is measured in EUR")
    return float(metrics["free_margin"])
```

In `ProbeExecutor`'s docstring, the line `` `venue_holdings` is `read_venue_book`' and `instrument_statuses` is `read_instrument_statuses`'. `` becomes the two lines `` `venue_holdings` is `read_venue_book`', `venue_free_margin` is `read_free_margin`'s and `` and `` `instrument_statuses` is `read_instrument_statuses`'. ``, at its indent; the constructor takes `venue_free_margin=None` directly after `venue_positions=None` and sets `self._venue_free_margin = venue_free_margin` directly after `self._venue_positions = venue_positions`, and directly after `self._plan_window_close: datetime | None = None`:

```python
        # The running plan's failed free-margin read, its reason, or None: `_start_intent` refuses each of the
        # plan's margin opens by it.
        self._free_margin_unread: str | None = None
```

`_nothing_in_flight`'s docstring, from "A Cache that cannot be read holds the pass", reads "A Cache that cannot be read holds the pass, and the pickup of a plan with a margin open (`extends_margin`), or under the cache an opening intent (`_accept_plan`), until the read answers, when its expiry refuses the file; never a plan otherwise." In `_accept_plan`, everything from `if self._cache_enabled and any(intent.action == "open" for intent in plan.intents) and not self._nothing_in_flight():` to the `plan_refusals(…)` call's closing parenthesis is replaced by:

```python
        reads_venue = extends_margin(plan) or (self._cache_enabled and any(intent.action == "open" for intent in plan.intents))
        if reads_venue and not self._nothing_in_flight():
            # The free-margin read (`_margin_floor_refusals`) and the mixed-inventory check's
            # (`_mixed_inventory_refusals`) are signed reads on the trade key, on the passes' nonce terms: on
            # the first tick the startup pass's cancels are still PENDING_CANCEL, so the plan waits in its
            # file for a tick with nothing in flight.
            logger.info("probe plan %s waits for a tick with nothing in flight -- it takes a signed venue read", plan.plan_id)
            return "waiting"
        reasons = plan_refusals(
            plan,
            now=now,
            ledgered=ledgered_plan_ids(self._journal_dir, now),
            max_plan_notional_eur=self._config.exec_max_plan_notional_eur,
        )
        unread = None
        if not reasons and extends_margin(plan):
            reasons, unread = self._margin_floor_refusals(plan)
```

and directly after `self._resolved_notional = {}`, further down `_accept_plan`, at its indent, `self._free_margin_unread = unread`. Directly above `_mixed_inventory_refusals`:

```python
    def _margin_floor_refusals(self, plan) -> tuple[list[str], str | None]:
        """The margin floor against Kraken's free margin read now (`read_free_margin`), never the Cache's account
        summary: the floor's refusals of the plan, and the read's failure or None. A read that fails is logged and
        refuses nothing here: `_start_intent` refuses each of the plan's margin opens by it, and no other intent."""
        try:
            free = (self._venue_free_margin or read_free_margin)()
        except Exception as exc:
            unread = f"Kraken's free margin could not be read for the margin floor -- {type(exc).__name__}: {exc}"
            logger.warning("probe plan %s: %s", plan.plan_id, unread)
            return [], unread
        logger.info("probe plan %s: Kraken's free margin reads %.2f EUR at its pickup", plan.plan_id, free)
        return list(margin_floor_refusals(plan, free_margin_eur=free)), None
```

In `_start_intent`, directly after the gate's refusal — `if not _level_permits(verdict.level, intent):`, its `self._refuse_intent(index, verdict.reasons)` and `return` — and its blank line, ahead of the venue-truth read's `try:`, and followed by one blank line, so an intent the gate refuses keeps the gate's reason:

```python
        if self._free_margin_unread is not None and _extends_margin(intent):
            self._refuse_intent(index, (self._free_margin_unread,))
            return
```

In `cli/engine/command.py`, the import adds `margin_floor_refusals`, and `probe_plan`'s three comment lines, its `free_zeur =` line and its `refusals = list(plan_refusals(…))` are replaced by:

```python
    # The venue record's balances carry the engine's free margin as `EUR` (`VenueState`), so this resolves on its
    # SECOND arm; the `ZEUR` arm reads nothing on this wheel. Both absent read 0.0, which refuses any margin open.
    free_margin = balances.get("ZEUR", 0.0) or balances.get("EUR", 0.0)
    refusals = [
        *plan_refusals(
            plan,
            now=now,
            ledgered=ledgered_plan_ids(config.journal_dir, now),
            max_plan_notional_eur=config.exec_max_plan_notional_eur,
        ),
        *margin_floor_refusals(plan, free_margin_eur=float(free_margin)),
    ]
```

In `cli/engine/venuestate.py`, `VenueState`'s docstring reads:

```python
    """A frozen, single-instant read of the Cache, with each `ordermin` as `held_ordermin` holds it:
    what the venue said we could trade and held at `snapshot_at`, and `balances` as the execution
    client read the account at its connect, which no fill moves -- the `EUR` row Kraken's free margin
    then. Plain data -- no Nautilus type reachable from here."""
```

In `cli/engine/flatten.py`, `QUOTE_CURRENCY`'s comment's second line reads ``# Money. Kraken's own `ZEUR` reaches the venue raw only as TradeBalance's `asset`, `_MARGIN_BALANCE_ASSET` ``, its third line as it stands.

- [ ] **Step 4: Run them, expect PASS.** Step 2's three commands read `19 passed, 831 deselected`, `64 passed` and `1 passed, 72 deselected`; `uv run pytest tests/test_engine_executor.py -m "not slow" -q -p no:cacheprovider --basetemp=.tmp/implementer/pt` reads `850 passed`; `uv run pytest tests/test_engine_stub_fidelity.py -q -p no:cacheprovider --basetemp=.tmp/implementer/pt` reads `64 passed`.

- [ ] **Step 5: The restart harness, slow cases included.** `uv run pytest tests/test_cache_restart.py -n 8 -q -p no:cacheprovider --basetemp=.tmp/implementer/pt` reads `22 passed` (277 s on the scratch tree): the child's redirect carries the harness's margin opens to the loopback's TradeBalance.

- [ ] **Step 6: Commit** `fix(engine): the margin floor reads Kraken's free margin when a plan opening on margin is picked up`, after the gate, the per-commit run's result line in the body — on the scratch tree the union of the changed files' direct readers and `tests/test_engine_probeplan.py` read `3513 passed, 14 skipped, 20 deselected` — and Step 5's line beside it.

- [ ] **Step 7: Probes**, on the committed tree, each `-- uv run pytest <test file> -k '<selection>' …`:
  - `floor-refuses`: `cli/engine/probeplan.py`, `tests/test_engine_probeplan.py`, `-k 'refuses_at_free_margin_50'`, mutation `s/    if margin_required > free_margin_eur:/    if False:/`.
  - `floor-names-free-margin`: the same file and case, mutation `s/exceeds free margin {free_margin_eur:.2f} EUR/exceeds free_zeur {free_margin_eur:.2f} EUR/`.
  - `floor-boundary`: the same file, `-k 'exactly_at_free_margin'`, mutation `s/    if margin_required > free_margin_eur:/    if margin_required >= free_margin_eur:/`.
  - `floor-margin-opens-only`: `-k 'extends_no_margin_has_no_margin_floor'`, mutation `s/    if not extends_margin(plan):/    if False:/`.
  - `close-extends-none`: `-k 'extends_no_margin_has_no_margin_floor'`, mutation `s/return intent.leverage is not None and intent.action == "open"/return intent.leverage is not None/`.
  - `floor-finite`: `-k 'non_finite_free_margin'`, mutation `s/    if not math.isfinite(free_margin_eur):/    if False:/`.
  - `floor-margin-opens-sum`: `-k 'sums_the_margin_opens_alone'`, mutation `s/for i in plan.intents if _extends_margin(i))/for i in plan.intents if i.leverage is not None)/`.
  - `basis-never-the-cache`: `cli/engine/executor.py`, `tests/test_engine_executor.py`, `-k 'never_the_caches_account'`, mutation `s/free = (self._venue_free_margin or read_free_margin)()/free = venue_state_from_cache(self._cache, clock=self._now).balances.get("EUR", 0.0)/`.
  - `spot-reads-none`: `-k 'spot_only_plan_reads_no_free_margin'`, mutation `s/if not reasons and extends_margin(plan):/if not reasons:/`.
  - `walls-first`: `-k 'walls_refuse_reads_no_free_margin'`, mutation `s/if not reasons and extends_margin(plan):/if extends_margin(plan):/`.
  - `close-reads-none`: `-k 'margin_open_waits'`, mutation `s/if not reasons and extends_margin(plan):/if not reasons and any(i.leverage is not None for i in plan.intents):/`.
  - `failed-read-caught`: `-k 'free_margin_read_that_fails'`, mutation `/def _margin_floor_refusals/,/def _mixed_inventory_refusals/s/except Exception as exc:/except ZeroDivisionError as exc:/`.
  - `failed-read-refuses-the-opens`: `-k 'free_margin_read_that_fails'`, mutation `s/if self._free_margin_unread is not None and _extends_margin(intent):/if False:/`.
  - `failed-read-runs-the-close`: `-k 'free_margin_read_that_fails'`, mutation `s/if self._free_margin_unread is not None and _extends_margin(intent):/if self._free_margin_unread is not None:/`.
  - `failed-read-runs-the-spot-intents`: `-k 'free_margin_read_that_fails'`, mutation `s/if self._free_margin_unread is not None and _extends_margin(intent):/if self._free_margin_unread is not None and intent.action == "open":/`.
  - `failed-read-logged`: `-k 'free_margin_read_that_fails'`, mutation `/logger.warning("probe plan %s: %s", plan.plan_id, unread)/d`.
  - `failed-read-held-for-its-plan-alone`: `-k 'held_for_its_plan_alone'`, mutation `s/self._free_margin_unread = unread/self._free_margin_unread = unread or self._free_margin_unread/`.
  - `read-at-each-pickup`: `-k 'fill_between_connects'`, mutation `s/free = (self._venue_free_margin or read_free_margin)()/free = self.__dict__.setdefault("_free_once", (self._venue_free_margin or read_free_margin)())/`.
  - `reads-mf`: `-k 'reads_tradebalances_mf'`, mutation `s/return float(metrics\["free_margin"\])/return float(metrics["equity"])/`.
  - `asks-zeur`: `-k 'reads_tradebalances_mf'`, mutation `s/request_margin_metrics(asset=_MARGIN_BALANCE_ASSET)/request_margin_metrics()/`.
  - `eur-label`: `-k 'labelled_other_than_eur'`, mutation `s/    if asset != "EUR":/    if False:/`.
  - `read-bound`: `-k 'read_free_margin and past_its_bound'`, mutation `s/metrics = asyncio.run(asyncio.wait_for(_read(), timeout=_VENUE_READ_TIMEOUT_SECONDS))/metrics = asyncio.run(_read())/`.
  - `margin-open-waits`: `-k 'margin_open_waits'`, mutation `s/reads_venue = extends_margin(plan) or (/reads_venue = (/`.
  - `close-waits-for-nothing`: `-k 'margin_open_waits'`, mutation `s/reads_venue = extends_margin(plan) or (/reads_venue = any(i.leverage is not None for i in plan.intents) or (/`.
  - `logs-the-figure`: `-k 'logs_the_figure'`, mutation `/free margin reads %.2f EUR at its pickup/d`.
  - `check-measures-floor`: `cli/engine/command.py`, `tests/test_engine_command.py`, `-k 'margin_intent_over_the_free_balance'`, mutation `/\*margin_floor_refusals(plan, free_margin_eur=float(free_margin)),/d`.
  - `check-reads-eur`: the same file and case, mutation `s/ or balances.get("EUR", 0.0)//`.

  Then the empty commit the Global Constraints name. No arm selects a `slow` case, and the two backstops Step 1 adds take none, an explicit drop whose reason is the spec's *Tests and guards*.

### Task 2: Spec 00090's floor lines read free margin (spec D8)

**Files:**
- Modify: `docs/specs/00090-rung-1-order-path-design.md` (D8)

**Interfaces:**
- Consumes: nothing. Produces: nothing a later task calls.

- [ ] **Step 1: Read the pin first**, its own call: `sha256sum docs/specs/00090-rung-1-order-path-design.md` prints `425e724bc60134e175f57cd05fed509be7521eee4db0fb5e4b6947868c6e0104`, and `grep -c 425e724bc60134e175f57cd05fed509be7521eee4db0fb5e4b6947868c6e0104 docs/reference/trial-registry.jsonl docs/reference/reading-ledger.jsonl` reads `0` for each; a hash or a count that differs stops the task and goes in the report.

- [ ] **Step 2: Edit.** ``grep -c -F '`sum(notional_i / leverage_i) × 2.5 ≤ free ZEUR balance`' docs/specs/00090-rung-1-order-path-design.md`` reads `1`, inside `### D8 — Sizing at the call site`; that code span becomes `` `sum(notional_i / leverage_i) × 2.5 ≤ free margin` ``. `grep -c -F "confirm free EUR balance covers the plan per D8's floor" docs/specs/00090-rung-1-order-path-design.md` reads `1`, inside `### D13 — The probe checklist is an operating surface, landed in this change`; that text becomes `confirm Kraken's free margin covers the plan per D8's floor`. The spec's two statements of the floor's basis are those two; G1's "the account balance covers the plan under D8's margin-floor check" defers to D8 and stands. Directly before the line `### D9 — [[T0140]] ruled: the venue record (and the exec record with it) gets a schema-aware validator — option (a)`, after one blank line, the paragraph:

```markdown
**Amended 2026-11-17 (spec 00162 D3 and D8, the owner's decision of 2026-09-23):** the margin floor's right-hand side is Kraken's free margin, TradeBalance's `mf` in EUR, read from Kraken when the plan is picked up, never the account summary the Cache holds from the execution client's connect; its sum runs over the plan's margin opens, a leveraged `open` being the one intent that extends margin, so a plan carrying none — spot, or margin closes alone — reads no free margin and has no floor. The decision is `[T0160]` in `docs/research/14.phase6-decisions.md`. This line read "free ZEUR balance", and D13's pre-probe line "free EUR balance", the spot wallet's free EUR; the code summed every leveraged intent, closes included, against the Cache's `EUR`, which on the pinned wheel is TradeBalance's free margin as the execution client read it at its connect (spec 00162's measured basis).
```

  followed by one blank line, as the spec's paragraphs stand.

- [ ] **Step 3: Run** the per-commit tests with `tests/test_trial_registry_provenance.py` and `tests/test_internal_terms_not_operator_visible.py` as the task's test files (`consumers.sh` exits 2 for this path).

- [ ] **Step 4: Commit** `docs(specs): spec 00090's margin floor reads free margin, the owner's basis of 2026-09-23`, the run's result line in the body.

### Task 3: The probe window's funding step names Kraken's free margin (spec D9)

**Files:**
- Modify: `infra/runbooks/engine-procedures.md` (`## engine-probe-window — PROCEDURE`, `#### 1. Pre-probe — before anything touches the host`, item 6)

**Interfaces:**
- Consumes: nothing. Produces: nothing a later task calls.

- [ ] **Step 1: Apply the spec's *Runbook texts*, verbatim.** Print it first, its own call: `sed -n '/^## Runbook texts$/,/^## Deployment$/p' docs/specs/00162-free-margin-read-at-the-check-design.md` shows one fence, item 6 whole, and its body is pasted from that output byte for byte, never retyped. `grep -c -F '6. **Confirm funding covers the plan, by hand, before the tooling does it for you.** Take the free EUR balance from the venue-truth read' infra/runbooks/engine-procedures.md` reads `1` first; that line is replaced by the fence's.

- [ ] **Step 2: Run** the per-commit tests with `tests/test_internal_terms_not_operator_visible.py` as the task's test file; `uv run pre-commit run -a` leaves the page unchanged, and `uv run python infra/scripts/guidance-guard.py --uncounted infra/runbooks/engine-procedures.md` prints no line.

- [ ] **Step 3: Commit** `docs(runbooks): the probe window's funding step measures the margin floor against Kraken's free margin`, the run's result line in the body.

### Task 4: The decisions-log entries (spec D1, D3–D6)

**Files:**
- Modify: `docs/research/14.phase6-decisions.md`

**Interfaces:**
- Consumes: nothing. Produces: nothing a later task calls.

- [ ] **Step 1: Append, verbatim, after the file's last line**, one blank line between entries as the log holds them; the asks and answers are those the spec's D1 quotes, word for word:

```markdown
[00162] Is the venue record's EUR finding registered as a topic? (Decision: 1)
  Asked 2026-11-12T11:03:01.042Z by zcrypto-marco, item 7 of its asks, verbatim: "**7. The EUR finding.** The engine sizes margin refusals from the venue record's `state.balances.EUR`, which read 1421.10. Kraken's actual free EUR was 1405.28. I recommend registering it as a topic, triggered at week 1's close beside T0226, T0227 and T0229." Answered 2026-11-12T11:06:56.778Z, verbatim: "1a, 5, 6a, 7 as recommended. go for 3."
  1. **Register it as a topic, triggered at week 1's close beside T0226, T0227 and T0229 (recommended).** **Taken** (owner, 2026-11-12); registered as T0230.
  A plain message on the one course recommended, no other laid out. T0230's review corrected the finding's basis (`docs/reference/rung3/days.md`, the entry for 2026-11-12): the record's `EUR` is Kraken's free margin as of the engine's connect, not its free EUR.

[00162] What does the margin floor measure a plan against: Kraken's free margin, or spec 00090's "free ZEUR balance"? (Decision: 1)
  Settled by the owner's decision of 2026-09-23, `[T0160]` above, its option 2's clause, verbatim: "On the MARGIN account the gate reads, EUR `locked` is margin in use, so D2's signal would mean only that a margin position is open and D3 would fire on every pickup while one is; `free_zeur` gates leveraged intents only, free margin the right measure there; an over-commit comes back as a venue rejection, the intent ending `rejected` with no money moved, and Rung 1 is capped at EUR 100 a plan (`exec_max_plan_notional_eur`)."
  1. **Kraken's free margin, TradeBalance's `mf` in EUR, gating leveraged intents only.** **Taken** (owner, 2026-09-23). The figure the code already read, as of the execution client's connect; spec 00090's line is amended to it.
  2. **The spot wallet's free EUR, spec 00090's wording.** BalanceEx's EUR less `hold_trade`: it counts neither the coins Kraken holds as collateral nor the margin open positions use.

[00162] When is T0230 resolved, and how does its fix ship? (Decision: 1)
  The owner's order, 2026-11-17T17:20:42.667Z, verbatim: "resolve T0230 in full, then we converge all the fixes in one shot".
  1. **Both of T0230's fixes now, the wording and the read at the check, on the engine image that carries T0229's, T0226's and T0227's fixes, one converge.** **Taken** (owner, 2026-11-17).
  An order, no options laid out; the converge is the fleet's.

[00162] How is Kraken's free margin read at the check? (Decision: 1)
  1. **TradeBalance on the engine's bare client, `request_margin_metrics` for `ZEUR`, beside `read_venue_positions`** — one private call, synchronous on the tick, on the bare reads' nonce terms; the plan waits for a tick with nothing in flight.
  2. **`request_account_state` on the bare client for the MARGIN account** — the same figure (measured), two private calls, `BalanceEx` and `TradeBalance`.
  3. **`query_account` through the strategy handle** — measured to refresh the Cache's account through the execution client's own client, no second client; but the figure lands on a later event, each query is two private calls, the Cache's account moves mid-run under the venue record and the library's risk engine, and its requests run beside the bare reads the same tick makes.
  Decided by the spec's author.

[00162] What does a free-margin read that fails do to the plan? (Decision: 1)
  1. **Refuses the plan's margin opens alone, each journaled `refused` at its start with the read's failure as its reason, and none of the plan's closes or spot intents** — no margin open's order goes, and a margin close riding with an open is not refused for a figure the close does not use; the operator drops the margin opens again under a new `plan_id` after reading Kraken.
  2. **Falls back to the connect-time figure** — the stale figure T0230 is about, used exactly when Kraken cannot be read.
  3. **Refuses the plan whole, the read's failure its reason** — the mixed-inventory read's terms; a margin close in the plan is refused with it, its position left open.
  Decided by the session running the plan's review, verbatim: "a failed free-margin read never refuses a close: what it refuses is the plan's margin opens alone, each journaled `refused` with the read's reason, while the plan's closes and spot intents run — whether by reading at the first margin open's submission or by refusing those intents at the pickup is the fixer's call by the code, the shape that adds the least; the Failure modes' "drop the plan again" is re-trued to it (spec :237)". The shape, the read at the pickup and its failure held for the running plan's margin opens, is the plan review's fix's.

[00162] What does the pickup refuse of a plan carrying a margin close when the read answers and the floor does not fit, or, under the cache, when the mixed-inventory check refuses? (Decision: 1)
  1. **The plan whole, its closes with it, as before this change** — the floor is the plan's, now summed over its margin opens alone, so it refuses less than before; the mixed-inventory check refuses a plan whole today; a close that must run goes in a plan of its own.
  2. **The plan's margin opens alone, its closes running, as a failed free-margin read refuses them** — a partial plan from two refusals this change does not otherwise touch.
  Decided by the session running the plan's review, verbatim: "the fixer's two questions are ruled as today, each under Out of scope with its reason — a floor refusal (the read answered, the opens over free margin) refuses the plan whole, a close in it included, D3's "the floor is the plan's", now on a sum of opens alone so refusing less than before; and a failed mixed-inventory read refuses the plan whole, as it does today — neither is behaviour this change introduces, and rung 3's plans carry no leverage; the owner is told, theirs to overturn".

[00162] Which plans read free margin, and where? (Decision: 1)
  1. **A plan carrying a margin open, a leveraged `open`, once the pickup's other walls pass, ahead of the mixed-inventory read, its floor summed over its margin opens** — the decision of 2026-09-23 gates leveraged intents only, and a close, spot or leveraged, extends no margin, so a plan of margin closes reads nothing and waits for nothing; rung 3's drafted plans are spot and read nothing.
  2. **Every plan** — one signed read per boundary on rung 3's loop for a floor that is 0 there.
  3. **A plan opening on margin whatever the other walls say** — a signed read for a plan already refused.
  4. **A plan carrying any leveraged intent, a margin close among them** — a signed read on the trade key, and a wait for a tick with nothing in flight, taken for a plan of closes, for a figure the close does not use: it is sized from the live position and goes reduce-only.
  Decided by the spec's author; the margin close's place by the session running the plan's review: "a plan whose leveraged intents extend no margin — every one reduce-only, a close — takes no read and no wait: the floor and its read gate only intents that extend margin, as the 2026-09-23 basis has free margin gate leveraged intents; a close a failed read could refuse leaves a margin position open, the opposite of the read's purpose (plan :507)".

[00162] What does `probe-plan --check` measure the floor against? (Decision: 1)
  1. **The newest venue record's `EUR`, the engine's free margin as of its last start, advisory as the check is** — the command stays offline; the engine reads Kraken's own at the pickup, and the runbook's funding step names Kraken's figure.
  2. **A live TradeBalance read** — the check would sign on the trade key from a second process beside the running engine.
  3. **No floor in the check** — the operator learns of an over-commit only at the pickup.
  Decided by the spec's author.
```

- [ ] **Step 2: Run** the per-commit tests with `tests/test_decisions_log_shape.py` and `tests/test_decisions_log_ties.py` as the task's test files (`consumers.sh` exits 2 for this path).

- [ ] **Step 3: Commit** `docs(research): the [00162] entries, the owner's three words on T0230 and the free-margin read's five calls`, the run's result line in the body.

### Task 5: T0230 resolved (the `topic-ops` skill)

**Files:**
- Modify and move: `docs/open-topics/T0230-the-margin-floor-reads-a-free-margin-figure-refreshed-only-at-connect.md` to `docs/open-topics/archive/`
- Modify: `docs/open-topics/README.md` (re-rendered)

**Interfaces:**
- Consumes: the commits of Tasks 1–3. Produces: nothing.

- [ ] **Step 1: Read the heading set and the shas**, each its own call: `grep '^#' docs/open-topics/T0230-the-margin-floor-reads-a-free-margin-figure-refreshed-only-at-connect.md` prints the H1, `## Context — what`, `## Why this matters`, `## Findings so far` and `## Suggested next steps`; `git -C <the worktree> log --format='%h %s' 6795cd513..HEAD` prints the branch's commits since `6795cd513`, among them Task 1's fix and probe commits and Tasks 2–4's, each `<sha …>` below taken from it by its subject, never typed.

- [ ] **Step 2: Edit the topic.** Each anchor reads `1` under `grep -c -F -e '<anchor>'` first, its enclosing section named. In the frontmatter, `status: open` becomes `status: resolved` and the `ripe_when:` line is deleted. Under `## Findings so far`, `_(none)_` becomes:

```markdown
- Measured on the pinned wheel against the loopback, the engine's own node started twice (spec `00162`'s measured basis): the venue record's `EUR` is TradeBalance's `mf`, read once a process at the connect; with the loopback's `mf` moved at a fill, the record's figure stayed where the connect put it, and the next start read the moved one. The execution client's account summary is built from the same answer, `e` its total and `m` its locked part.
```

  `## Suggested next steps` and its three items, to the file's end, become:

```markdown
## Resolution

- Fixed by `<sha task 1 fix>`: the pickup of a plan carrying a margin open, a leveraged `open`, reads Kraken's free margin, TradeBalance's `mf` for `ZEUR`, on the engine's bare client (`read_free_margin`, `cli/engine/executor.py`), and measures the margin floor, summed over its margin opens, against it (`margin_floor_refusals`, `cli/engine/probeplan.py`), never the Cache's account summary from the execution client's connect; a read that fails refuses the plan's margin opens alone, none of its closes or spot intents, and a plan with none — spot, or margin closes alone — reads nothing and has no floor, the owner's basis of 2026-09-23 taken to the intents that extend margin. `probe-plan --check` measures the floor against the venue record's figure, advisory as before.
- Held by `tests/test_engine_executor.py::test_a_fill_between_connects_moves_the_free_margin_the_next_plans_floor_is_measured_against` (Kraken's figure moved between two pickups in one process and the Cache's not, the second plan judged on the moved one), `::test_the_margin_floor_reads_krakens_free_margin_at_the_pickup_and_never_the_caches_account` (the basis, both directions), `::test_a_free_margin_read_that_fails_refuses_the_margin_opens_naming_the_read_and_runs_the_close` and `::test_a_spot_only_plan_reads_no_free_margin`, proven by `infra/scripts/mutate-probe.sh` in `<sha task 1 probes>`.
- The wording: spec `00090`'s margin floor reads free margin, amended in `<sha task 2>`; `infra/runbooks/engine-procedures.md`'s probe-window funding step names Kraken's free margin and the figure `probe-plan --check` reads, in `<sha task 3>`.
- The change ships on the engine image with T0229's, T0226's and T0227's fixes, one engine converge, the fleet's concern (`.claude/rules/fleet-deploys.md`).
```

- [ ] **Step 3: Move and re-render**, each its own call: `git -C <the worktree> mv docs/open-topics/T0230-the-margin-floor-reads-a-free-margin-figure-refreshed-only-at-connect.md docs/open-topics/archive/`; `uv run python infra/scripts/topics-index.py`, after which T0230's line leaves `## Open` for `## Resolved`, linking `archive/`. The heading set reads the H1, `## Context — what`, `## Why this matters`, `## Findings so far` and `## Resolution`.

- [ ] **Step 4: Run** the per-commit tests (`tests/test_merge_gate.py`, `tests/test_open_topics_frontmatter.py`, `tests/test_topics_index.py`).

- [ ] **Step 5: Commit** `docs(open-topics): T0230 resolved, the margin floor reads Kraken's free margin at the pickup`, the run's result line in the body, staged by `git -C <the worktree> add docs/open-topics/archive/T0230-the-margin-floor-reads-a-free-margin-figure-refreshed-only-at-connect.md docs/open-topics/README.md`, its own call: Step 3's `git mv` has staged the old path's removal, and an `add` naming that path aborts with nothing staged. Decisions log: Task 4's entries; the converge is the fleet's concern, never the topic's.
