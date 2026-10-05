# 00092 — rung-3 accumulation: the engine submits `target − actually held` from the cycle record, continuously armed — implementation plan

> Every value a rollout reading decides is a marked slot, `ROLLOUT:` inside double square brackets, listed at the end.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** At each 4-hourly boundary, after the cycle journals, the engine reads the venue's own book, drafts the ten EUR legs as `target − held` through the helper's decision table, runs the placeable legs as one plan through the executor's existing machine inside a bounded submission window, carries what the venue's floors refuse, marks equity at the cycle's closes against a high-water mark and the UTC day, freezes on a stale socket, nets a same-symbol late fill into the reconciliation it would otherwise trip, and does all of it continuously armed under a reviewed host variable — with the alert set, the dashboard row, the record, the runbook procedure, the drills' forms and the topics that go with it. Rung 3's rollout is its own, after the week-of-2026-11-02 engine rollout's pin passes its attended order-semantics pass, never inside rung 2's box.

**Architecture:** The loop is three additions to shapes the tree already runs. `on_boundary` gains a third act after the series birth and the tracking trip: it arms a pending draft, and the 5-second tick drafts it once nothing is in flight — the book read on a bare client (`read_venue_book`, `read_venue_holdings` extended by the EUR balance's `total` and `free`), the helper's `decide_leg` / `trim_buys_to_cash` / `assemble_plans` with keyword parameters that default to the hand-window constants, `plan_document` under `r3-<YYYYMMDD>-<HH>`, and `_accept_plan`, which is `_pickup` from its `parse_plan` line on with the file path removed. The executor's three holds fold into the verdict `_evaluate` publishes, and `on_boundary` re-journals that folded verdict into the boundary's exec record, so the gauge, the record, the disarmed rule and the tracking trip's eligibility read one figure. A new `accum-<HH>.json` per boundary (`cli/engine/accumledger.py`, the `venueledger` pattern) carries the decision table, the equity mark and the day-loss hold; five metric families join the `zcrypto_exec_*` block end to end — the gap, the equity, the drawdown, the watchdog's freeze and the draft's state, the last watched by a rule of its own — and the gate's `zcrypto_exec_venue_read_failed` beside them. Ansible renders `exec_armed` from a fact derived from the host's `vars.yml` in the tree, which the arming backstop reads too. The alert set: the venue-divergence rule is authored on the engine's own read failure and the watchdog's freeze gets its own rule here; the armed-too-long rule's replacement by the disarmed-across-a-boundary rule is the Rollout's rules pull request, merged inside the entry sitting (R3), since this branch merges inside rung 2's box and a routine push from `develop` would otherwise ship a rule that pages on the box's daily disarm (spec D11).

**Tech Stack:** Python 3.14 through `uv run`; nautilus-trader `2.0.0rc6.dev20260921` as pinned in `pyproject.toml` at this plan's base (the rollout pins the November bump's build, which D15's gate reads); prometheus_client; pytest with the executor test file's stub harness (`StubClient`, `StubCache`, `_VenueHoldings`, `_socket`, `_resting_executor`, `_tracking_executor`) and `tests/kraken_loopback.py`; Ansible (ansible-core 2.21, the `engine` and `capture` roles); Grafana alert rules and dashboards under `infra/grafana/`; `infra/scripts/mutate-probe.sh` for every guard verdict.

**Spec:** `docs/specs/00092-rung-3-accumulation-design.md` at the branch's tip, every decision D1 to D17 ruled on 2026-10-05; the `## Verification` list is discharged task by task below, each task naming its bullets; `## The slots rung 2's box fills` are the box's and the rollout's gate reads them, never a task.

## Global Constraints

- No engine converge on `zcrypto` inside rung 2's box, Mon 2026-10-05 to Sun 2026-11-01, or to its slipped close: nothing in this plan converges, re-pins or restarts the engine before the box's exit report is recorded (`infra/runbooks/engine-procedures.md#engine-rung-2-box`, step 10; `.claude/rules/fleet-deploys.md`). The rollout below starts after the week-of-2026-11-02 engine rollout.
- The engine converges only inside the 4-hourly inter-cycle gap, which `site.yml` computes from the boundary cycle's journalled completion (`-e '{"engine_window_override": "<reason>"}'` is the bypass and is not used here), and never inside a published Kraken maintenance window, the feed read whole at planning time and again immediately before (`.claude/rules/fleet-deploys.md`).
- No executor step reaches a fleet host, the venue, Grafana Cloud, the observability node, Slack or healthchecks.io: every such step is in the Rollout, marked attended, `W$` the workstation and `H$` the host. `tests/kraken_loopback.py` is the only venue a test reaches; a test that would reach the real venue is gated by `ZCRYPTO_LIVE_VENUE_TESTS` in one of the six forms `tests/test_live_venue_opt_in.py` admits, and none is added here.
- A commit that adds or changes a guard — a test, an assertion, an alert rule, an Ansible assert — proves it with `infra/scripts/mutate-probe.sh`, never a hand-rolled mutate-and-restore loop; the verdict is recorded in the commit's message by a message-only amend of the placeholder line `PROBE_VERDICT`, with the tree clean, the branch unpushed while the tasks run; a message that records a verdict names `mutate-probe`.
- `tests/test_internal_terms_not_operator_visible.py`'s surfaces carry no `Phase <N>`, `T<NNNN>`, `iter-<N>`, `spec <NNNNN>`, `D<N>` or `WP<N>`: metric HELP, CLI `--help`, alert summaries, dashboard titles and descriptions, runbook pages, Ansible task names and operator messages. A provenance token goes in an adjacent code comment; the allowlist is never widened.
- Python 3.14 (`.python-version`); PEP 758's `except A, B:` is valid and is not "fixed".
- A comment or docstring gets its place only if a reader would do something differently without it, and if it stays it is correct: state and decisions stay, an event (what was measured, read, found or corrected) goes to the commit message. Each task's Files entries quote the comments and docstrings its edits falsify, each re-trued in that task's commit.
- Markdown: one line per paragraph and list item, no column wrap, no filler blank line; a fenced block keeps its own lines. A universal word in a new runbook bullet carries its `(set: …; count: …)` or `(no count command: …)` clause, or the bullet is worded without it.
- The commit gate, before every commit: the commit's files are staged by path, new files among them, then `uv run pre-commit run -a` runs clean; a run that rewrites files is re-run until clean and the rewrites staged. Every commit is green over the changed files' consumers — `grep -rl <the changed script or module> tests/ infra/ .claude/` and the test files each task's consumer step names — never the full suite locally, which is CI's on every push and Task 19's once.
- `docs/specs/00095-twelve-leg-deployable-design.md` and `docs/reference/trial-registry.jsonl` are never touched; the exec ledger's `EXEC_SCHEMA_VERSION` 2, `_ROW_KEYS` and `_PLAN_ENTRY_KEYS` are untouched (spec D14: no readers-before-writer deploy is owed on the exec ledger); `probeplan.py`'s `_PLAN_KEYS` and `_INTENT_KEYS` are untouched.
- The helper `cli/engine/draftplan.py` and the rung-2 box running on it are unchanged in behaviour: the three functions the loop reuses gain keyword parameters whose defaults are the module constants, `tests/test_engine_draftplan.py`'s 153 cases pass unchanged, and no module constant moves (spec D3).
- The executor's envelope constants — `_TICK_SECONDS`, `_QUOTE_SILENCE`, `_TIME_BOX`, `_ACK_WAIT`, `_MAX_REPRICES`, `_MAX_IOC_ATTEMPTS`, `_GATE_REFRESH`, `_REREAD_ATTEMPTS`, `_VENUE_READ_TIMEOUT_SECONDS` — keep their values (spec D3, D10); `PLAN_TTL` stays 60 minutes.
- Nothing widens a `00088` floor: the restart hold clears only by a human act, the kill file latches and no code clears it, arming needs both keys; `_submit` keeps taking the gate itself and accepting no verdict parameter (`00090` D4).
- Task 18 alone edits files under `docs/open-topics/` and `docs/research/`; no task edits `CLAUDE.md`, a file under `.claude/`, or a page under `infra/runbooks/` outside Tasks 4, 15 and 17, each of which loads `zcrypto-refine-rules` before its first runbook edit.
- A commit message ends with this trailer, the placeholder replaced by the executing model's own name, followed by the executing session's `Claude-Session:` line where its harness supplies one:

```
Co-Authored-By: Claude <actual executing model> <noreply@anthropic.com>
```

## File structure

- `cli/engine/draftplan.py`: keyword parameters on `decide_leg`, `trim_buys_to_cash`, `assemble_plans`, and `trim_to_plan_cap` (Task 1).
- `cli/engine/executor.py`: `VenueBook`, `read_venue_book`, the executor's kept book (Task 2); the fold and the boundary's re-journal (Task 5); `foreign_filled` (Task 6); the hand-act arm (Task 7); the sell path's source and the dust floor (Task 8); the watchdog (Task 9); `_accept_plan` (Task 10); the pending draft, the window, the carry, the record (Task 11); the equity series and the trips (Task 12).
- `cli/engine/accumledger.py` (new): the `accum-<HH>.json` writer, reader, validator and window reader (Task 3).
- `cli/engine/command.py`: `_ExecutionMetrics`' five families and the hooks (Task 4); `_ExecGauges`' `venue_read_failed` (Task 15); `accum-replay --floor-shorts` (Task 14). `cli/engine/feeders.py`: the floored targets (Task 14). `cli/engine/node.py`: the two polling fields stated, `_exec_client_config`'s docstring (Tasks 8, 13).
- `infra/ansible/roles/capture/files/config.alloy`: the five names in the keep regex (Task 4), the sixth (Task 15). `infra/grafana/engine-dashboard.json`: the accumulation row, panel 52's description, the head panel's sentence (Task 4); panel 55's second target (Task 15). `infra/grafana/alerts.yaml`: `zcrypto-engine-exec-watchdog-frozen` and `zcrypto-engine-exec-boundary-not-drafted` (Task 4); `zcrypto-engine-exec-venue-diverged` (Task 15); `zcrypto-engine-exec-disarmed-across-a-boundary` replacing `zcrypto-engine-exec-armed-too-long`: the Rollout's rules pull request (R3), not a task's. `infra/scripts/ops_daily.py`: `_UID_HOST` gains each new uid with its rule (Tasks 4 and 15, R3).
- `infra/ansible/roles/engine/templates/zcrypto.toml.j2`, `roles/engine/tasks/main.yml`, `roles/engine/defaults/main.yml`: `exec_armed` rendered from the tree's fact, the band line, the backstop's input (Task 16). `infra/ansible/host_vars/zcrypto/vars.yml`: untouched by a task; the Rollout's arm PR writes it.
- `infra/runbooks/engine.md`: the watchdog's and the not-drafted sections (Task 4), the venue-divergence section (Task 15); the disarmed section replacing the armed-too-long one: R3's rules pull request. `infra/runbooks/engine-procedures.md`: `engine-rung-3`, the probe-window `Retire when`, the tracking-band precondition (Task 17). `infra/runbooks/drills-order-path.md`: the standing rules' armed-too-long bullet (Task 15), the rung-3 forms and drill H (Task 17).
- `README.md`: the `accum-replay` row's flag (Task 14).
- `tests/test_engine_draftplan.py`, `tests/test_engine_executor.py`, `tests/test_engine_accumledger.py` (new), `tests/test_engine_metrics.py`, `tests/test_engine_node.py`, `tests/test_nautilus_interface_pin.py`, `tests/test_engine_feeders.py`, `tests/test_engine_command.py`, `tests/test_infra_alloy_series.py`, `tests/test_infra_alert_rules.py`, `tests/test_dashboards_cover_metrics.py`, `tests/test_infra_converge_guards.py`, `tests/test_config.py`, `tests/test_ops_daily.py`: tests per task. `tests/fixtures/rung2/` (new): the 2026-10-05 12Z cycle record, and a venue record and a `balance.json` synthesized in the exports' shape at invented quantities (Task 11).
- `docs/open-topics/T0119-*.md`, `T0120-*.md` (archived), `T0216-*.md`, `T0018-*.md`, `docs/open-topics/README.md`, `docs/research/14.phase6-decisions.md` (Task 18).
- `docs/reference/deploy-log.jsonl`, `fleet-pins.md`, `drill-log.md`, the spec's measured basis: the Rollout's records pull request, not a task's.

## Review Focus

- A sell sized or bounded against the stored account: the book `_classify_spot_close` and `_mixed_inventory_refusals` read must be the process's venue book, never `_newest_venue_balances` or `state.balances`, and a process with no book read refuses (Task 8); the draft's `held` must be the book's, never `_cache_net` or the record's `held` (Task 11).
- A hold the gate's level does not show: `_frozen`, `_reconciliation_refusal` and `_day_loss_hold` each lower the published level and the boundary's journaled level (Tasks 5, 9, 12); a boundary record reading `full` while any stands is the defect; a boundary that drafted nothing reading 0 on `zcrypto_exec_boundary_not_drafted`, or a week holding one scored by `_score_closed_week`, is its sibling (Task 11).
- The draft's wait and bound: the book read, the table and the document run only with nothing in flight, the plan's `created_at` is the drafting tick's `now`, and no intent starts past `B + 3h30m` (Task 11).
- The mark's figure: equity at the EUR balance's `total`, never `free`; the HWM and the day's base over the records at or after the series' start instant; the day-loss hold derived from the date's records, never stored (Task 12).
- The arming render and the backstop reading one fact from the host's `vars.yml` in the tree, never the variable namespace: an extra var must neither render `true` nor pass the backstop (Task 16).
- The watchdog's grace and lift: a 3-second blip revokes nothing; a cut past 30 seconds sends the cancel with `socket_down` within the next tick, the terminal `revoked` on an ack or `ambiguous` on the mint; the freeze lifts only with the set empty and a completed pass whose settle answered (Task 9).

---

### Task 1: The helper's three functions take the loop's parameters as keywords, the hand window's constants their defaults, and `trim_to_plan_cap` bounds a plan at the cap it will be judged by

**Files:**
- Modify: `cli/engine/draftplan.py` (`decide_leg` gains `eur_per_weight: float = EUR_PER_WEIGHT`; `trim_buys_to_cash` gains `cash_reserve_eur: float = CASH_RESERVE_EUR`; `assemble_plans` gains `plan_cap_eur: float | None = PLAN_CAP_EUR` beside its existing `max_intents: int = MAX_INTENTS`, which becomes `int | None`; `None` on either means no split and no cap; the trim's two reason strings read the parameter, not the constant; `trim_to_plan_cap(decisions, cap_eur)` beside `trim_buys_to_cash`, the loop's cap applied by the table — spec D3, D4)
- Test: `tests/test_engine_draftplan.py`

**Interfaces:**
- Consumes: `decide_leg(symbol, *, weight, price, constraints, kraken_held, engine_held, venue_b, exiting=False)`; `trim_buys_to_cash(decisions, free_eur)`; `assemble_plans(decisions, max_intents=MAX_INTENTS)`; the module constants at the values the spec's measured basis records (`EUR_PER_WEIGHT` 720.0, `CASH_RESERVE_EUR` 5.0, `PLAN_CAP_EUR` 95.0, `MAX_INTENTS` 3).
- Produces, for Task 11 by these exact names: `decide_leg(..., eur_per_weight=record.nav)`, `trim_buys_to_cash(decisions, free_eur, cash_reserve_eur=10.0)`, `trim_to_plan_cap(decisions, cap_eur)`, `assemble_plans(decisions, max_intents=None, plan_cap_eur=None)` returning at most one plan.

**What this task decides, where the spec leaves it open:**
- `None` is the no-bound spelling on both of `assemble_plans`' parameters, so `assemble_plans(decisions, max_intents=None, plan_cap_eur=None)` returns `[]` for no placed leg and one plan otherwise; the `DraftPlanError` on a leg over the cap is raised only when a cap is given.
- `decide_leg`'s `target` reads `0.0 if exiting else eur_per_weight * max(weight, 0.0)`: the `max(weight, 0.0)` stays, since D5's long-only entry is this rule.
- `trim_to_plan_cap(decisions, cap_eur)` carries placed legs from the smallest `eur` until the plan fits the cap, in the order the executor's walls cumulate it (`plan_refusals` sums every buy's `notional_eur` and refuses the whole plan over the cap; `_over_cap_reason` adds each sell's `qty × price` at sizing, sells running first): sells first, the smallest `carried` until `Σ sell eur ≤ cap_eur`, then buys, the smallest `carried` until `Σ buy notional_eur + Σ sell eur ≤ cap_eur` — whole legs, never a trimmed quantity (a trimmed sell would leave a lot the next boundary sells again), each carried leg's reason `over the plan cap <cap> EUR; carries to the next boundary`, its `qty` and `notional_eur` `None` as the cash trim's carry leaves them; a sell's `eur` is `qty × price` at the close the table sized at, so a sell the live touch prices over the cap at sizing is that one intent's refusal at `_over_cap_reason` and its leg's carry at the next boundary, never the plan's.

- [ ] **Step 1: Write the failing tests** in `tests/test_engine_draftplan.py`, beside `_decide` and `_placed`:

```python
def test_decide_leg_prices_the_target_at_the_eur_per_weight_it_is_handed():
    leg = _decide(weight=0.1, price=100.0, eur_per_weight=1000.0)
    assert leg.target_eur == 100.0 and leg.outcome == "placed" and leg.notional_eur == 100.0


def test_decide_leg_without_the_keyword_prices_at_the_hand_windows_constant():
    assert _decide(weight=0.1, price=100.0).target_eur == 72.0


def test_trim_buys_to_cash_takes_the_reserve_it_is_handed_and_names_it_in_the_reason():
    buys = [_placed("SOL/EUR", "buy", notional=30.0), _placed("ADA/EUR", "buy", notional=5.0)]
    trimmed = trim_buys_to_cash(buys, 40.0, cash_reserve_eur=10.0)
    assert [d.outcome for d in trimmed] == ["placed", "carried"]
    assert "free EUR - 10" in trimmed[1].reason
    assert trim_buys_to_cash(buys, 40.0)[0].notional_eur == 30.0 and trim_buys_to_cash(buys, 40.0)[1].notional_eur == 5.0


def test_assemble_plans_with_no_cap_and_no_split_returns_one_plan_carrying_every_placed_leg():
    legs = [_placed("BTC/EUR", "buy", notional=160.0), *[_placed(s, "buy", notional=20.0) for s in ("ETH/EUR", "SOL/EUR", "XRP/EUR")]]
    plans = assemble_plans(legs, max_intents=None, plan_cap_eur=None)
    assert len(plans) == 1 and [d.symbol for d in plans[0]] == ["BTC/EUR", "ETH/EUR", "SOL/EUR", "XRP/EUR"]
    with pytest.raises(DraftPlanError):
        assemble_plans(legs)
    assert assemble_plans([], max_intents=None, plan_cap_eur=None) == []


def test_trim_to_plan_cap_carries_sells_then_buys_from_the_smallest_until_the_plan_fits_the_cap():
    legs = [_placed("BTC/EUR", "sell", qty=0.004, price=100000.0), _placed("ETH/EUR", "sell", qty=0.1, price=3000.0), _placed("SOL/EUR", "buy", notional=250.0), _placed("ADA/EUR", "buy", notional=200.0), _placed("XRP/EUR", "buy", notional=50.0)]
    trimmed = draftplan.trim_to_plan_cap(legs, 1000.0)  # sells 700, buys 500: XRP then ADA carry, SOL stays at 950
    assert [(d.symbol, d.outcome) for d in trimmed] == [("BTC/EUR", "placed"), ("ETH/EUR", "placed"), ("SOL/EUR", "placed"), ("ADA/EUR", "carried"), ("XRP/EUR", "carried")]
    assert "over the plan cap 1000 EUR" in trimmed[3].reason and trimmed[3].notional_eur is None
    assert draftplan.trim_to_plan_cap(legs, 2000.0) == legs
    sells_over = draftplan.trim_to_plan_cap([_placed("BTC/EUR", "sell", qty=0.008, price=100000.0), _placed("ETH/EUR", "sell", qty=0.1, price=3000.0)], 1000.0)
    assert [(d.symbol, d.outcome) for d in sells_over] == [("BTC/EUR", "placed"), ("ETH/EUR", "carried")]
```

`_decide` gains a pass-through `eur_per_weight=None` keyword that is forwarded only when given, so the existing cases stay byte-identical. The sketch reaches the new function as `draftplan.trim_to_plan_cap` through a new `import cli.engine.draftplan as draftplan` line, so the file collects before Step 3 writes it.

- [ ] **Step 2: Run the tests and read the failure** — `uv run pytest tests/test_engine_draftplan.py -q -p no:cacheprovider`; Expected: three of the five new cases fail on `TypeError: … unexpected keyword argument` and the cap trim's on `AttributeError: … 'trim_to_plan_cap'`; the keyword-less case passes at the base (72.0 is `EUR_PER_WEIGHT` × 0.1 today) and is the hand window's pin; the 153 existing pass.
- [ ] **Step 3: The three signatures, the trim's reason strings, and `trim_to_plan_cap`**
- [ ] **Step 4: Run the tests** — the same command; Expected: 158 passed.
- [ ] **Step 5: The consumers** — `grep -rl 'draftplan' tests/ cli/ infra/ .claude/ | sort`; run every test file it names, `tests/test_engine_command.py` among them.
- [ ] **Step 6: The commit gate**
- [ ] **Step 7: Commit** — `feat(engine): the plan-drafting helper's three functions take the loop's parameters as keywords, the hand window's constants their defaults`, with `PROBE_VERDICT` and the trailer.
- [ ] **Step 8: The tree is clean** — `git status --porcelain`; Expected: empty.
- [ ] **Step 9: Prove the guards with one probe per guard, then record their verdicts by a message-only amend** — mutations: the cap check left reading `PLAN_CAP_EUR` with `plan_cap_eur=None` handed in (`test_assemble_plans_with_no_cap…` must catch the EUR 160 leg raising); `eur_per_weight` ignored in favour of the constant; the reserve's reason string left reading the constant; the cap trim's sell pass skipped (the sells-over-the-cap case reads both `placed`). Each run ends `mutate-probe: KILLED (control proven, tree restored byte-identically)`.

---

### Task 2: `read_venue_book` — the holdings read extended by the EUR balance's `total` and `free`, and the executor keeps the newest book it read

**Files:**
- Modify: `cli/engine/executor.py` (`VenueBook`; `read_venue_book`; `read_venue_holdings` as `read_venue_book(base_url=base_url).held`; the constructor's `venue_holdings` seam now answers a `VenueBook`, its docstring line "`venue_holdings` is `read_venue_holdings`'" re-trued; `_settle_positions_from_venue` keeps the book on `self._venue_book`, reads with no metrics hook installed too, returns `True` when its read answered, and hands the book to `_settle_from_book(book, moment)`, its apply half — the cross-check WARNING per symbol, `_venue_correction`, the gauge publish only when a hook is installed — which Task 11 calls on the book it already holds; its docstring's "The read serves the gauge alone, so with no metrics hook installed, the exporter off, nothing is read" re-trued)
- Test: `tests/test_engine_executor.py` (`_VenueHoldings` answers a `VenueBook`; the loopback case; `_no_production_venue_read` wraps `read_venue_book` as it wraps `read_venue_holdings` — a `base_url` let through, a default refused — since the seam's default is now the book read)

**Interfaces:**
- Consumes: `read_venue_holdings`' three reads on `_bare_client` (`request_instruments`, `request_position_status_reports(... AccountType.MARGIN ...)`, `request_account_state(... AccountType.CASH)`), `_margin_positions`, `resolve_base`, `_SPOT_SYMBOL_BY_BASE`, `FLAT_TOLERANCE`; the CASH read's wallet entries carrying `locked = hold_trade` and `free = total − locked` (`docs/reference/adapter-verification/2.0.0rc6.dev20260915.md`, item 9); `tests/kraken_loopback.py`'s `serve()` and its balance fixture.
- Produces, by these exact names:

```python
@dataclass(frozen=True)
class VenueBook:
    held: dict[str, float]  # per INSTRUMENT_IDS symbol, read_venue_holdings' figure
    eur_total: float  # the EUR balance's total, the equity mark's figure
    eur_free: float  # the EUR balance's free, net of hold_trade, the cash budget's
    read_at: datetime


def read_venue_book(*, base_url: str | None = None) -> VenueBook: ...
def read_venue_holdings(*, base_url: str | None = None) -> dict[str, float]:
    return read_venue_book(base_url=base_url).held
```

and on the executor `self._venue_book: VenueBook | None`, `None` until a read answers; `_settle_positions_from_venue(moment) -> bool`; `_settle_from_book(book: VenueBook, moment: str) -> None`.

**What this task decides, where the spec leaves it open:**
- The EUR entry is the wallet entry whose `currency.code` is `ZEUR` or `EUR`, read as `float(balance.total)` and `float(balance.free)`; absent, both read 0.0 and the book is still returned — an account with no EUR is a legitimate book, and the cash budget then refuses every buy.
- The read's raises are `read_venue_holdings`' own: a timeout, an empty listing, a `None` positions answer. Nothing new is swallowed.
- `_settle_positions_from_venue` is the read then `_settle_from_book(book, moment)`: it keeps `self._venue_book = book` and returns `False` on a failed read, `True` on an answered one, the WARNING on a failed read unchanged; `_settle_from_book` is the apply half — the cross-check WARNING per symbol over `FLAT_TOLERANCE`, `_venue_correction`, the gauge publish — with the `_metrics is None` return inside it, ahead of the publish alone, so Task 8's sell path and Task 11's draft read a book whether or not the exporter is on, and Task 11 settles the gauge from the book it already holds with no second read.

- [ ] **Step 1: Write the failing tests** — the harness's `_VenueHoldings.__call__` returns `VenueBook(held=dict(self.held), eur_total=self.eur_total, eur_free=self.eur_free, read_at=NOW)` — `VenueBook` spelled `executor_module.VenueBook` inside `__call__`, so the file collects before Step 3 mints it — with the two new constructor keywords defaulting to 0.0; then:

```python
def test_read_venue_book_carries_the_eur_balances_total_and_free_beside_the_holdings(_loopback_credentials):
    with kraken_loopback.serve() as venue:
        venue.balances["ZEUR"] = {"balance": "1000.0000", "hold_trade": "150.0000"}
        venue.balances["XXBT"] = {"balance": "0.00100000", "hold_trade": "0.00000000"}
        book = executor_module.read_venue_book(base_url=venue.base_url)
    assert book.eur_total == 1000.0 and book.eur_free == 850.0
    assert book.held["BTC/EUR"] == 0.001
    assert executor_module.read_venue_holdings(base_url=venue.base_url) == book.held


def test_the_settle_keeps_the_book_it_read_and_reads_with_no_metrics_hook_installed(tmp_path):
    set_executor_hooks()
    holdings = _VenueHoldings({"BTC/EUR": 0.001}, eur_total=1000.0, eur_free=850.0)
    ex = _executor(tmp_path, venue_holdings=holdings)
    ex.on_timer(NOW)  # the startup pass's settle
    assert holdings.calls == 1 and ex._venue_book.eur_free == 850.0 and ex._venue_book.held["BTC/EUR"] == 0.001
```

The loopback's balance-fixture shape is read from `tests/kraken_loopback.py` before the test is written; if its `balances` mapping spells `hold_trade` differently, the test follows the fixture, never the other way round.

- [ ] **Step 2: Run the tests and read the failure** — `uv run pytest tests/test_engine_executor.py -q -p no:cacheprovider -k 'venue_book or settle_keeps'`; Expected: the loopback case `AttributeError: … has no attribute 'read_venue_book'`; the hook-less case `holdings.calls == 1` reading 0 — today's settle returns before reading when no metrics hook is installed (`if _metrics is None: return`, its first statement).
- [ ] **Step 3: `VenueBook`, `read_venue_book`, the wrapper, the seam, the settle**
- [ ] **Step 4: Run the tests** — `uv run pytest tests/test_engine_executor.py -q -p no:cacheprovider`; Expected: 598 passed (596 at the base plus the two), none skipped.
- [ ] **Step 5: The consumers** — `grep -rl 'read_venue_holdings\|_VenueHoldings\|venue_holdings' tests/ cli/ | sort`; run every test file it names, `tests/test_engine_flatten.py` and `tests/test_engine_metrics.py` among them if listed.
- [ ] **Step 6: The commit gate**
- [ ] **Step 7: Commit** — `feat(engine): the venue book -- the holdings read extended by the EUR balance's total and free, kept on the executor at each settle`, with `PROBE_VERDICT` and the trailer.
- [ ] **Step 8: The tree is clean**
- [ ] **Step 9: Prove the guards with one probe per guard, then record their verdicts by a message-only amend** — mutations: `eur_free` read from `balance.total` (the loopback case reads 1000.0 where 850.0 is required); the settle's read left behind the `_metrics is None` return (the hook-less case reads `calls == 0`).

---

### Task 3: `cli/engine/accumledger.py` — `accum-<HH>.json`, schema 1, invisible to the gate

**Files:**
- Create: `cli/engine/accumledger.py`
- Create: `tests/test_engine_accumledger.py`

**Interfaces:**
- Consumes: `cli/engine/venueledger.py`'s shape (own `_PREFIX`, its own schema constant, `validate_*` refusing by exact key set, the comment on why the prefix is neither `cycle-` nor `failed-cycle-`); `cli/engine/execledger.py`'s `_store` (tmp sibling + `os.replace`) and `_day_dirs`; `EngineJournalError`.
- Produces, by these exact names:

```python
ACCUM_SCHEMA_VERSION = 1
ACCUM_STATUSES = frozenset({"ok", "no-cycle", "book-unread", "window-closed", "refused"})
_PREFIX = "accum"
_RECORD_KEYS = frozenset({"schema_version", "cycle_ts", "drafted_at", "status", "nav", "eur_total", "eur_free", "equity_eur", "hwm_eur", "drawdown_bps", "day_loss_bps", "day_loss_hold", "plan_id", "legs"})
_LEG_KEYS = frozenset({"symbol", "weight", "target_eur", "close", "held_qty", "cache_net", "delta_eur", "outcome", "side", "qty", "notional_eur", "reason"})

def accum_record_path(journal_dir: Path, cycle_ts: datetime) -> Path: ...
def validate_accum_record(doc: dict) -> None: ...
def write_accum_record(journal_dir: Path, cycle_ts: datetime, doc: dict) -> Path: ...
def read_accum_record(path: Path) -> dict: ...
def accum_records_since(journal_dir: Path, since: datetime, until: datetime) -> list[dict]: ...
```

**What this task decides, where the spec leaves it open:**
- `validate_accum_record` refuses: a `schema_version` other than 1; a top-level key set other than `_RECORD_KEYS`; a `status` outside `ACCUM_STATUSES`; a `legs` that is not a list, or a leg whose key set is not `_LEG_KEYS`; a non-finite number in any numeric field; `day_loss_hold` not a bool. `nav`, `eur_total`, `eur_free`, `equity_eur`, `hwm_eur`, `drawdown_bps`, `day_loss_bps` and `plan_id` may each be `None` — a `no-cycle` or `book-unread` boundary has no figure — and `legs` is `[]` on those statuses; a leg's `side`, `qty`, `notional_eur` are `None` on a carried or on-target leg. `write_accum_record` validates before it stores, so a malformed record can never land.
- `accum_records_since` walks `<journal_dir>/<YYYY-MM-DD>/accum-*.json` for day dirs at or after `since.date()`, validates each, and returns the records sorted by `cycle_ts` with `since <= cycle_ts <= until` — the bound is the instant, so a record earlier on `since`'s own day is out; a record that will not validate raises — the HWM scan refuses rather than reading past a broken record.
- The record is written with `indent=2, sort_keys=True`, the sibling ledgers' spelling.

- [ ] **Step 1: Write the failing tests** — the round trip; each refusal above as its own case, each flipping one thing; `accum_records_since` over a constructed three-day journal, excluding a record of the day before `since`, one earlier on `since`'s own day and one past `until`, and raising on a corrupt record; and the gate immunity, through the real `report` path as `tests/test_engine_execledger.py::test_populated_exec_records_leave_the_report_byte_identical` does it:

```python
def test_accum_records_leave_the_report_byte_identical(tmp_path, monkeypatch):
    from typer.testing import CliRunner

    import cli.engine.command as command
    from cli.__main__ import app

    day = tmp_path / "2026-11-09"
    day.mkdir(parents=True)
    for hh in (0, 4, 8, 12, 16, 20):
        (day / f"cycle-{hh:02d}.json").write_text("{not json")
    monkeypatch.setattr(command, "_utc_now", lambda: CYCLE_TS + timedelta(days=1))
    runner = CliRunner()
    args = ["engine", "report", "--journal-dir", str(tmp_path)]
    without = runner.invoke(app, args)
    for hh in (0, 4, 8, 12, 16, 20):
        write_accum_record(tmp_path, CYCLE_TS.replace(hour=hh), _ok_doc(CYCLE_TS.replace(hour=hh)))
    with_records = runner.invoke(app, args)
    assert with_records.output == without.output and with_records.exit_code == without.exit_code
```

- [ ] **Step 2: Run the tests and read the failure** — `uv run pytest tests/test_engine_accumledger.py -q -p no:cacheprovider`; Expected: `ModuleNotFoundError: No module named 'cli.engine.accumledger'`.
- [ ] **Step 3: The module**
- [ ] **Step 4: Run the tests** — the same command; Expected: no failure.
- [ ] **Step 5: The consumers** — `uv run pytest tests/test_engine_execledger.py tests/test_engine_venueledger.py tests/test_engine_command.py tests/test_engine_journal_readers.py -q -p no:cacheprovider`, the sibling ledgers and the command the immunity test drives; `grep -n '_journal_artifacts(' cli/engine/command.py` still prints thirteen lines naming the four globs and no `accum-` glob.
- [ ] **Step 6: The commit gate**
- [ ] **Step 7: Commit** — `feat(engine): the accumulation record -- accum-<HH>.json per boundary, schema 1, outside the gate's globs`, with `PROBE_VERDICT` and the trailer.
- [ ] **Step 8: The tree is clean**
- [ ] **Step 9: Prove the guards with one probe per guard, then record their verdicts by a message-only amend** — mutations: a leg key dropped from `_LEG_KEYS` (the exact-set case); `ACCUM_STATUSES` widened by `"pending"`; `write_accum_record` storing before validating; `accum_records_since` reading a record before `since` (the same-day one); and the immunity's control, `_PREFIX` set to `cycle` (the report then reads the records and the output differs).

---

### Task 4: The five metric families, their admission, the Engine board's accumulation row, the watchdog's and the not-drafted rules and their runbook sections

**Files:**
- Modify: `cli/engine/command.py` (`_ExecutionMetrics` gains `gap_eur`, `equity_eur`, `drawdown_bps`, `watchdog_frozen`, `boundary_not_drafted` and `set_gap(symbol, eur)`, `set_equity(value)`, `set_drawdown(bps)`, `set_watchdog_frozen(flag)`, `set_boundary_not_drafted(flag)`; HELP text operator-clean)
- Modify: `cli/engine/executor.py` (module hooks `_set_gap`, `_set_equity`, `_set_drawdown`, `_set_frozen`, `_set_boundary_not_drafted`, None-safe like `_set_tracking_state`)
- Modify: `infra/ansible/roles/capture/files/config.alloy` (the keep regex gains `|zcrypto_exec_gap_eur|zcrypto_exec_equity_eur|zcrypto_exec_drawdown_bps|zcrypto_exec_watchdog_frozen|zcrypto_exec_boundary_not_drafted` after `zcrypto_exec_tracking_state`)
- Modify: `infra/grafana/engine-dashboard.json` (the accumulation row; panel 1's `options.content` sentence "published by the execution path and reading flat zero, not absent, outside an attended trading window" re-trued to "published by the execution path and reading flat zero, not absent, while the loop is disarmed"; panel 52's description, "Pages after six continuous hours armed, because arming is expected only inside an attended probe window …", re-trued to a standing 1 under continuous arming, the gate level it reduces to being what pages — the disarmed-across-a-boundary rule, R3's rules pull request)
- Modify: `infra/grafana/alerts.yaml` (`zcrypto-engine-exec-watchdog-frozen`, `zcrypto-engine-exec-boundary-not-drafted`)
- Modify: `infra/runbooks/engine.md` (the `zcrypto-engine-exec-watchdog-frozen — ALERT` section, `What you are seeing / What it means / What to do / Retire when`: the read is `zcrypto_exec_watchdog_frozen` and the CRITICAL naming the endpoint and the grace in the engine's log — `exec-status` shows the gate's six reasons alone, never `socket_down` (Task 15's reads); the lift is the re-read pass on the sockets' return, or a restart inside a gap for a stale entry or a spent budget; `Retire when` the rule leaves `alerts.yaml`; and the `zcrypto-engine-exec-boundary-not-drafted — ALERT` section: the read is the newest `accum-<HH>.json` by value — its `status` names which of `no-cycle`, `book-unread`, `window-closed`, `refused`, and the engine's log the cause: the book read's WARNING per try, the status read's, the plan entry's reasons — beside `zcrypto_exec_boundary_not_drafted`; what it means: two consecutive boundaries placed nothing while the gate read `full`, so the disarmed rule is quiet — a trade key whose private permission changed, a nonce poisoned by a hand use of the key, a Cache that cannot be read, a drill plan resting through the window; what to do: the cause's own remedy, a restart inside a gap only when the process itself is wedged; and the one early page, a restart inside the scrape interval before a boundary that drafts nothing, whose fresh series then holds no 0 sample; `Retire when` the rule leaves `alerts.yaml`)
- Modify: `infra/scripts/ops_daily.py` (`_UID_HOST` gains `zcrypto-engine-exec-watchdog-frozen` and `zcrypto-engine-exec-boundary-not-drafted`, rules whose `execErrState` is `Alerting`)
- Test: `tests/test_engine_metrics.py`, `tests/test_infra_alloy_series.py` (`ENGINE_APP_SERIES` gains the five), `tests/test_infra_alert_rules.py` (`NOT_A_FAULT_SIGNAL` gains `zcrypto_exec_gap_eur`, `zcrypto_exec_equity_eur`, `zcrypto_exec_drawdown_bps` with their reasons; the watchdog replay and the not-drafted replay), `tests/test_dashboards_cover_metrics.py` (unchanged; it goes green by charting), `tests/test_ops_daily.py` (unchanged; `owed == ops_daily._UID_HOST` goes green by the entry)

**Interfaces:**
- Consumes: `_ExecutionMetrics`' registry and its eager-child convention; `_EXEC_ORDER_OUTCOMES`, which Task 11 widens; the keep regex's `zcrypto_exec_*` block; the board's datasource object and `{host=~"$host"}` scoping; `test_every_fault_signal_metric_is_watched_by_a_rule`.
- Produces, for Tasks 9, 11 and 12 by these exact names: `executor._set_gap(symbol, eur)`, `executor._set_equity(value)`, `executor._set_drawdown(bps)`, `executor._set_frozen(flag)`, `executor._set_boundary_not_drafted(flag)`; the families `zcrypto_exec_gap_eur{symbol}`, `zcrypto_exec_equity_eur`, `zcrypto_exec_drawdown_bps`, `zcrypto_exec_watchdog_frozen`, `zcrypto_exec_boundary_not_drafted`; the rules `zcrypto-engine-exec-watchdog-frozen` and `zcrypto-engine-exec-boundary-not-drafted`; panels 81 to 85.

**What this task decides, where the spec leaves it open:**
- The gap gauge is eager for the ten model EUR symbols (`_SPOT_SYMBOL_BY_BASE`'s values restated in `command.py` from `BASKET`, the EUR legs) at 0.0; equity and drawdown are lazy, registered at the first boundary that computes them, since a seeded 0 equity would read as a 100 % drawdown; `watchdog_frozen` and `boundary_not_drafted` are eager at 0 — the second so that a fresh series after a restart holds 0 samples ahead of the first boundary's write, which its rule's `min_over_time` needs.
- The rule, verbatim from spec D14: `uid: zcrypto-engine-exec-watchdog-frozen`, title `Engine · the execution watchdog has frozen the loop`, group `zcrypto-gate`, `expr: 'zcrypto_exec_watchdog_frozen{host="zcrypto"}'`, threshold `gt 0.5`, `noDataState: OK`, `execErrState: Alerting`, `for: 15m`, severity `warning`, receiver `metrics`, `__dashboardUid__: "zcrypto-engine"`, `__panelId__: "84"`, summary ending `Runbook: infra/runbooks/engine.md#zcrypto-engine-exec-watchdog-frozen` (the section is this task's, above, so `test_every_runbook_link_in_an_alert_summary_resolves` and `tests/test_runbook_triggers.py` read green at this commit).
- The second rule, from spec D14: `uid: zcrypto-engine-exec-boundary-not-drafted`, title `Engine · two consecutive boundaries drafted nothing`, group `zcrypto-gate`, node A `min_over_time(zcrypto_exec_boundary_not_drafted{host="zcrypto"}[4h30m])` over `relativeTimeRange {from: 16200, to: 0}`, threshold `gt 0.5`, `noDataState: OK`, `execErrState: Alerting`, `for: 10m`, severity `warning`, receiver `metrics`, `__dashboardUid__: "zcrypto-engine"`, `__panelId__: "84"`, the summary naming two consecutive boundaries whose accumulation record is not `ok` while the gate stayed `full`, ending `Runbook: infra/runbooks/engine.md#zcrypto-engine-exec-boundary-not-drafted`. Why `min_over_time` over a 0/1 gauge eager at 0 and not a timestamp: the window clears of 0 samples about 4h30m after the first undrafted boundary's write, so the rule fires about 4h40m after it only when the boundary 4h later wrote a non-`ok` record too; an `ok` record at that boundary puts a 0 in the window and the rule stays quiet, and a restart's fresh series starts at 0.
- The row: `{"id": 80, "type": "row", "title": "Accumulation — the loop's gap, equity and window", "gridPos": {"h": 1, "w": 24, "x": 0, "y": 97}}`; panels at `h: 6`: 81 `Gap per leg (EUR) — target minus held, after each intent's terminal` (`zcrypto_exec_gap_eur{host=~"$host"}`, legend `{{symbol}}`, x 0 w 12 y 98), 82 `Equity (EUR) against the high-water mark` (two targets, `zcrypto_exec_equity_eur{host=~"$host"}` and `max_over_time(zcrypto_exec_equity_eur{host=~"$host"}[60d])`, x 12 w 12 y 98), 83 `Drawdown from the high-water mark (bps)` (`zcrypto_exec_drawdown_bps{host=~"$host"}`, x 0 w 8 y 104), 84 `Watchdog frozen · boundary not drafted` (two targets, `zcrypto_exec_watchdog_frozen{host=~"$host"}` and `zcrypto_exec_boundary_not_drafted{host=~"$host"}`, x 8 w 8 y 104), 85 `Intents by outcome over the last window` (`increase(zcrypto_exec_orders_total{host=~"$host"}[4h])`, legend `{{outcome}}`, x 16 w 8 y 104); `fieldConfig`/`options` copied from panel 14. No title or description carries an internal token.
- The three `NOT_A_FAULT_SIGNAL` reasons: the gap and the equity are readings the tracking trip and the drawdown kill already act on; the drawdown's fault value latches the kill, which `zcrypto-engine-exec-kill-tripped` pages. `zcrypto_exec_watchdog_frozen` and `zcrypto_exec_boundary_not_drafted` are watched and are not listed.
- The series budget, re-measured: 10 + 1 + 1 + 1 + 1 = 14 new active series against the keep list's total at this plan's base, the count stated in the commit body — `grep -o 'zcrypto_exec_[a-z_]*' infra/ansible/roles/capture/files/config.alloy | sort -u | wc -l` reads 19 after the edit, 14 before.

- [ ] **Step 1: Write the failing tests** — the five families' names and labels parsed from the registry via `text_string_to_metric_families` (the file's own pattern); `set_gap` on an unknown symbol raises nothing and mints no series outside the ten; the keep-list case; the exclusion-list case; and the two replays:

```python
def test_a_freeze_past_fifteen_minutes_pages_and_the_hourly_three_second_blip_does_not():
    rule = _rule("zcrypto-engine-exec-watchdog-frozen")
    hold_for = _duration_seconds(rule["for"])
    assert _evaluator(rule) == {"type": "gt", "params": [0.5]}

    def fires(samples):
        run = 0
        for t in range(0, 2 * 3600, 60):
            if next((v for at, v in reversed(samples) if at <= t), 0) > 0.5:
                run += 60
                if run >= hold_for:
                    return True
            else:
                run = 0
        return False

    assert fires([(0, 1), (16 * 60, 0)])
    assert not fires([(0, 1), (3, 0)])
    assert not fires([(0, 1), (14 * 60, 0)])


def test_two_consecutive_undrafted_boundaries_page_and_one_followed_by_an_ok_boundary_does_not():
    rule = _rule("zcrypto-engine-exec-boundary-not-drafted")
    hold_for = _duration_seconds(rule["for"])
    assert _evaluator(rule) == {"type": "gt", "params": [0.5]}
    window = 4 * 3600 + 30 * 60  # the rule's [4h30m]
    h4 = 4 * 3600

    def fire_minute(samples):
        # a step series scraped each minute from the process's start, 0 before its first sample
        def value_at(s):
            return next((v for at, v in reversed(samples) if at <= s), 0)

        run = 0
        for t in range(0, 14 * 3600, 60):
            lowest = min(value_at(s) for s in range(max(0, t - window + 60), t + 1, 60))
            run = run + 60 if lowest > 0.5 else 0
            if run >= hold_for:
                return t
        return None

    assert fire_minute([(0, 0), (3600, 1), (3600 + h4, 1)]) == 3600 + h4 + 38 * 60  # the last 0 sample sits a minute before the boundary's write
    assert fire_minute([(0, 0), (3600, 1), (3600 + h4, 0)]) is None
    assert fire_minute([(0, 0)]) is None
```

- [ ] **Step 2: Run the tests and read the failure** — `uv run pytest tests/test_engine_metrics.py tests/test_infra_alloy_series.py tests/test_infra_alert_rules.py tests/test_dashboards_cover_metrics.py -q -p no:cacheprovider`; Expected: the family cases fail on the missing attributes, the keep-list case on five unadmitted names, the replays on `StopIteration` from `_rule`.
- [ ] **Step 3: The families, the hooks, the regex, the row, the two re-trued texts, the two rules, the exclusion entries, the two runbook sections (after loading `zcrypto-refine-rules`), the `_UID_HOST` entries**
- [ ] **Step 4: Run the tests** — the same command; Expected: no failure.
- [ ] **Step 5: The consumers** — `uv run pytest tests/test_internal_terms_not_operator_visible.py tests/test_engine_executor.py tests/test_ops_daily.py tests/test_runbook_triggers.py tests/test_runbook_internal_tokens.py -q -p no:cacheprovider`.
- [ ] **Step 6: The commit gate**
- [ ] **Step 7: Commit** — `feat(engine): the accumulation families -- gap per leg, equity, drawdown, the watchdog's freeze -- admitted end to end, the board's accumulation row, the watchdog's and the not-drafted rules`, with `PROBE_VERDICT` and the trailer; the body states the series count.
- [ ] **Step 8: The tree is clean**
- [ ] **Step 9: Prove the guards with one probe per guard, then record their verdicts by a message-only amend** — mutations: one name dropped from the keep regex (`test_keep_regex_admits_every_published_series`); the rule's `for` set to `30s` (the blip fires in the replay); the evaluator flipped to `lt`; the not-drafted rule's window set to `[3h30m]` (the one-boundary-then-`ok` case fires), its `for` to `30s` (the firing minute moves from 4h38m to 4h29m) and its evaluator flipped to `lt` (the all-0 series fires); `zcrypto_exec_watchdog_frozen` added to `NOT_A_FAULT_SIGNAL` (`test_the_exclusion_list_has_not_gone_stale`, if it refuses a watched entry; otherwise record the mutation as not probed and why).

---

### Task 5: The executor's holds fold into the verdict `_evaluate` publishes, and the boundary re-journals it

**Files:**
- Modify: `cli/engine/executor.py` (`_fold_holds(verdict) -> GateVerdict`; `_evaluate` publishes the folded verdict; `on_boundary` re-journals it as its first act; `_evaluate`'s docstring "The ONE gate read" stays true and gains the fold; `_refresh_gate`'s docstring sentence "it journals nothing, since the exec record's verdict is the boundary sink's alone" re-trued — the refresh journals nothing, and the boundary's `on_boundary` re-journals the folded verdict)
- Test: `tests/test_engine_executor.py`

**Interfaces:**
- Consumes: `ExecutionGate.evaluate` and `GateVerdict(level, reasons, inputs)`; `LEVEL_CODE`; `self._reconciliation_refusal`; `write_exec_record`'s merge-never-clobber (the verdict fields replaced, `submitted` and `plans` kept); `_ExecGauges.update`'s five `inputs` keys, which the fold keeps.
- Produces, for Tasks 9 and 12 by these exact names: the fold's three reasons `socket_down` (level `none`, read from `self._frozen`, `False` until Task 9), `reconciliation_unread` (level `none`, read from `self._reconciliation_refusal is not None`), `daily_loss_hold` (level `reduce_only` unless already `none`, read from `self._day_loss_hold`, `False` until Task 12), appended after the gate's six in that order; `inputs` gains the three booleans under those names.

**What this task decides, where the spec leaves it open:**
- `on_boundary`'s first act is `verdict = self._evaluate(now, heartbeat=False)` — the heartbeat stays the sink's, so a failing ledger write still starves `zcrypto-engine-exec-not-evaluated` — followed by `write_exec_record(self._journal_dir, boundary, verdict, evaluated_at=now)` inside the method's existing total catch, before `_record_series_birth` (Task 12 puts the day-loss hold's re-derivation from the date's records ahead of this evaluate, and Task 11's draft re-journals the same way at its terminal, so the record carries the level the boundary ends at): the boundary sink in `command.py` wrote the bare gate verdict moments earlier and the merge replaces its verdict fields alone, so the exec record's `level` is the folded figure `_evaluate_tracking`'s `held_back` reads. A boundary whose cycle raised and wrote no exec record gets one here carrying the verdict and empty lists.
- The plan-level refusals those three states already make stand unchanged; the fold is what makes them visible.

- [ ] **Step 1: Write the failing tests**:

```python
def test_an_unread_startup_reconciliation_reads_none_with_its_reason_in_the_published_verdict(tmp_path):
    metrics = RecordingMetrics()
    set_executor_hooks(publish_verdict=lambda verdict, **_: metrics.verdicts.append(verdict), metrics=metrics)
    ex = _unreconciled_executor(tmp_path)
    verdict = ex._evaluate(NOW)
    assert verdict.level == GateLevel.NONE and verdict.reasons[-1] == "reconciliation_unread"
    assert verdict.inputs["reconciliation_unread"] is True and metrics.verdicts[-1] is verdict


def test_the_boundary_re_journals_the_folded_verdict_over_the_sinks_bare_one(tmp_path):
    ex = _unreconciled_executor(tmp_path)
    write_exec_record(ex._journal_dir, _boundary(NOW), _verdict(level=GateLevel.FULL), evaluated_at=NOW)
    ex.on_boundary(_boundary(NOW))
    doc = read_exec_record(exec_record_path(ex._journal_dir, _boundary(NOW)))
    assert doc["level"] == "none" and "reconciliation_unread" in doc["reasons"]
```

`_unreconciled_executor(tmp_path)` builds the refusal the way the tree sets it: `_submitted_row(tmp_path, "O-open", reduce_only=True, when=NOW - timedelta(hours=4), venue_order_id=_TXID)`, `ex = _executor(tmp_path, venue_orders=_VenueOrders(raises=RuntimeError("down")))`, then `ex.on_timer(NOW)` inside `_executor_errors(level=logging.CRITICAL)` — the startup pass's read of the venue's orders raises for a row it needed and `_reconciliation_refusal` is set, the construction of the file's `never compared against venue truth` case; `_UnreadableOrderCache` (line 5680) fails `order()` alone and only once `fail_order_reads` is switched on, so it sets no refusal. `RecordingMetrics` gains a `verdicts` list if it has none, and `_verdict(level=...)` is built from `GateVerdict` with the gate's five input keys.

- [ ] **Step 2: Run the tests and read the failure** — `uv run pytest tests/test_engine_executor.py -q -p no:cacheprovider -k 'fold or re_journals or reconciliation_unread'`; Expected: the first fails on `verdict.level` reading `full` (the gate's own verdict, with no reason appended), the second on `doc["level"] == "full"`.
- [ ] **Step 3: `_fold_holds`, `_evaluate`, `on_boundary`'s first act**
- [ ] **Step 4: Run the tests** — `uv run pytest tests/test_engine_executor.py tests/test_engine_execgate.py tests/test_engine_metrics.py -q -p no:cacheprovider`; Expected: no failure — the existing cases that read `verdict.reasons` whole against the gate's tuple are re-read: a case asserting equality with the six-reason tuple on a healthy executor still holds, since the fold appends nothing then.
- [ ] **Step 5: The consumers** — `uv run pytest tests/test_engine_node.py tests/test_engine_command.py -q -p no:cacheprovider`.
- [ ] **Step 6: The commit gate**
- [ ] **Step 7: Commit** — `feat(engine): the executor's holds fold into the verdict it publishes, and each boundary journals the folded level`, with `PROBE_VERDICT` and the trailer.
- [ ] **Step 8: The tree is clean**
- [ ] **Step 9: Prove the guards with one probe per guard, then record their verdicts by a message-only amend**:

```bash
infra/scripts/mutate-probe.sh \
  --file cli/engine/executor.py \
  --control 's/if self._reconciliation_refusal is not None:\(.*\)reasons.append("reconciliation_unread")/if False:\1reasons.append("reconciliation_unread")/' \
  --mutation 's/verdict = self._fold_holds(self._gate.evaluate(now))/verdict = self._gate.evaluate(now)/' \
  -- uv run pytest tests/test_engine_executor.py::test_an_unread_startup_reconciliation_reads_none_with_its_reason_in_the_published_verdict -x -q
```

The two sed expressions are adjusted to the committed lines' exact spelling; a second probe deletes the `write_exec_record` call in `on_boundary` against the re-journal test. Expected: `KILLED (control proven, …)` each.

---

### Task 6: The same-symbol late fill is netted into `expected`

**Files:**
- Modify: `cli/engine/executor.py` (`_ActiveIntent.foreign_filled: float = 0.0`; `_on_detached_event` adds the fill's signed quantity when the fill's `instrument_id` equals the active intent's, `_claims` is False and the row's Cache order carries this strategy's id; `_reconcile_terminal` reads `expected = own_position_before + own_delta + foreign_filled`; `_record_trip_fill`'s credit is left alone — it runs on the two overfill-trip arms alone, where `_trip_kill` latches, so no `expected` is computed from it (spec D13); `_reconcile_terminal`'s docstring gains the netting and keeps its five-exits paragraph)
- Test: `tests/test_engine_executor.py`

**Interfaces:**
- Consumes: `_on_detached_event`'s `attached` row and `qty`; `_cache_lookup(row, venue_order_id)` and the order's `strategy_id`; `_claims`; `_reconcile_terminal`'s lot-step tolerance and strategy scoping; the `_terminal_intent` helper at line 7849 and `_deliver_fill` at 1955.
- Produces: nothing a later task consumes by name.

**What this task decides, where the spec leaves it open:**
- The sign is the row's `intent["side"]`, `+qty` for a buy and `-qty` for a sell; a fill whose Cache order cannot be read nets nothing and logs at WARNING — an unread order is not evidence of the strategy's id, and the trip stays armed on the side of stopping.
- A fill on a row the startup pass adopted whose Cache order is an `EXTERNAL` copy nets nothing: its position books under strategy `EXTERNAL`, outside the strategy-scoped `actual`.

- [ ] **Step 1: Write the failing tests**:

```python
def test_a_late_fill_of_an_earlier_intent_on_the_same_instrument_does_not_trip_the_terminal_reconciliation(tmp_path):
    """Cycle N's sell of BTC/EUR, its row open, fills while cycle N+1's buy of BTC/EUR runs: the
    strategy-scoped position moves by the sell, which is in `actual` and not in the intent's own
    fills. Netted, the terminal reads clean; un-netted it latches the kill file."""
    ex, client, clock = _resting_executor(tmp_path, intents=[_intent(symbol="BTC/EUR", side="buy", notional_eur=30.0)])
    earlier = _submitted_row(tmp_path, "O-earlier", reduce_only=False, when=NOW - timedelta(hours=4), plan_id="r3-20261109-00", symbol="BTC/EUR", side="sell", qty=0.001)
    ex._attach((_boundary(NOW - timedelta(hours=4)), earlier), "O-earlier", venue_order_id=None)
    client.cache.hold_strategy_order("O-earlier", strategy_id=client.strategy_id)
    _deliver_fill(ex, client, "O-earlier", 0.001, symbol="BTC/EUR", side="sell")
    client.cache.set_own_position("BTC/EUR", -0.001)
    _deliver_fill(ex, client, client.last_order_id, 0.001, symbol="BTC/EUR", side="buy")  # the active buy fills whole
    client.cache.set_own_position("BTC/EUR", 0.0)
    assert not _kill_file(tmp_path).exists()
    assert _intent_outcome(tmp_path) == "filled"


def test_a_fill_on_a_restored_external_copy_is_not_netted(tmp_path):
    ...  # the same shape with the earlier row's Cache order under strategy EXTERNAL: `foreign_filled` stays 0.0
```

The stub Cache helpers (`hold_strategy_order`, `set_own_position`) are added beside `set_position` where no equivalent exists, mirroring its shape; `_submitted_row` gains `plan_id=`, `symbol=` and `side=` keywords, today's values their defaults, and journals under `_boundary(when)` as it does, so the row the fill updates lives in the record the test attaches it under.

- [ ] **Step 2: Run the tests and read the failure** — `uv run pytest tests/test_engine_executor.py -q -p no:cacheprovider -k 'late_fill_of_an_earlier_intent or restored_external_copy_is_not_netted'` (`late_fill` alone selects five existing cases); Expected: the first fails on the kill file existing (read the kill file's text: it names BTC/EUR's position against the intent's fills).
- [ ] **Step 3: `foreign_filled`, the netting, `_reconcile_terminal`**
- [ ] **Step 4: Run the tests** — `uv run pytest tests/test_engine_executor.py -q -p no:cacheprovider`; Expected: no failure.
- [ ] **Step 5: The consumers** — none beyond the file.
- [ ] **Step 6: The commit gate**
- [ ] **Step 7: Commit** — `fix(engine): a same-symbol late fill of an earlier intent is netted into the terminal reconciliation's expectation`, with `PROBE_VERDICT` and the trailer.
- [ ] **Step 8: The tree is clean**
- [ ] **Step 9: Prove the guards with one probe per guard, then record their verdicts by a message-only amend** — the mutation deletes `+ active.foreign_filled` from `_reconcile_terminal`'s `expected` (the late-fill test latches the kill); the control nets with the wrong sign. Expected: `KILLED (control proven, …)`.

---

### Task 7: An unmatched external fill arms the re-read pass

**Files:**
- Modify: `cli/engine/executor.py` (`_on_external_event`'s unmatched branch calls `self._arm_reread_after_mint()` for an `OrderFilled` alone, before its return; the branch's docstring sentence "Unmatched …: counted, logged, and NOTHING else" re-trued — counted, logged, and for a fill the pass armed, which reads an empty population and settles the holdings)
- Test: `tests/test_engine_executor.py`

**Interfaces:**
- Consumes: `_arm_reread_after_mint` (arms three tries with no socket down, nothing with one held down); `_reread_pass`'s settle; `_VenueHoldings.calls`; `_deliver_external_event`.
- Produces: nothing by name; D12's mechanism.

- [ ] **Step 1: Write the failing tests**:

```python
def test_an_unmatched_external_fill_arms_the_re_read_pass_and_the_next_tick_settles_the_holdings(tmp_path):
    holdings = _VenueHoldings({"SOL/EUR": 0.5})
    ex, client, _ = _idle_executor(tmp_path)
    ex._venue_holdings = holdings
    ex.on_timer(NOW)  # the startup pass: one read
    _deliver_external_event(ex, client, _fill("O-hand", 0.5, symbol="SOL/EUR", side="buy"))
    assert ex._reread_tries == 3
    ex.on_timer(NOW + timedelta(seconds=5))
    assert holdings.calls == 2 and ex._reread_tries == 0


def test_an_unmatched_external_cancel_arms_nothing(tmp_path):
    ex, client, _ = _idle_executor(tmp_path)
    ex.on_timer(NOW)
    _deliver_external_event(ex, client, _canceled("O-hand"))
    assert ex._reread_tries == 0
```

- [ ] **Step 2: Run the tests and read the failure** — `-k 'unmatched_external'`; Expected: `ex._reread_tries == 0` after the fill.
- [ ] **Step 3: The one call and the docstring**
- [ ] **Step 4: Run the tests** — `uv run pytest tests/test_engine_executor.py -q -p no:cacheprovider`; Expected: no failure.
- [ ] **Step 5: The consumers** — none beyond the file.
- [ ] **Step 6: The commit gate**
- [ ] **Step 7: Commit** — `feat(engine): a hand act's own fill arms the re-read pass, so the position gauge takes the venue's figure within a tick of it`, with `PROBE_VERDICT` and the trailer.
- [ ] **Step 8: The tree is clean**
- [ ] **Step 9: Prove the guard with one probe, then record its verdict by a message-only amend** — the mutation deletes the `_arm_reread_after_mint()` call in the unmatched branch; the control arms on every unmatched event (the cancel case). Expected: `KILLED (control proven, …)`.

---

### Task 8: The sell path reads the venue's balances, a dust balance reads as absent, and the two docstrings are re-trued

**Files:**
- Modify: `cli/engine/executor.py` (`_classify_spot_close(intent, *, balances, level, ordermin)` with the dust floor; `_classify_close` reads `self._venue_book` and refuses with `the venue's balances have not been read in this process` when it is `None`; `_mixed_inventory_refusals` tests `self._venue_book is None` first and refuses every opening intent with the sentence `_classify_close` uses, else reads `_spot_balance(self._venue_book.balances, base)` in place of `state.balances` — its `try`'s `{type(exc).__name__}: {exc}` arm would otherwise name an `AttributeError` where the state is a book not read; the two refusal strings `the venue record's balance does not cover the signed qty` and `the venue record refutes the signed qty` re-worded to `the venue's balance does not cover the signed qty` and `the venue's balance refutes the signed qty`, the source they now name; `_newest_venue_balances` deleted with its one caller gone; `_classify_spot_close`'s docstring rewritten to name the process's venue book as its source and the dust floor; `_classify_close`'s docstring "a spot disposal reads the newest venue record's balances" re-trued)
- Modify: `cli/engine/node.py` (`_exec_client_config`'s docstring: "spot position reports cover the ZEUR-quoted instruments" → `spot_positions_quote_currency` is unread under `spot_account_type=MARGIN`, where the adapter takes the OpenPositions branch and builds no spot position report)
- Test: `tests/test_engine_executor.py`, `tests/test_engine_node.py` (the docstring's claim is not tested; the node's config pins are unchanged)

**Interfaces:**
- Consumes: Task 2's `VenueBook`; `_spot_balance(balances: dict, base: str)`, which tries the venue alias spellings; `_classify_close`'s `state.instruments[intent.symbol].ordermin`; the executor's `_venue_record` and `_held` test helpers.
- Produces, for Task 11: `VenueBook.balances` — a property mapping each held symbol's base to its spot quantity (`{base: held[symbol]}` over `_SPOT_SYMBOL_BY_BASE`), the dict `_spot_balance` reads; `_classify_spot_close`'s `ordermin` keyword.

**What this task decides, where the spec leaves it open:**
- The book's spot balances are keyed by base (`BTC`, `ETH`, …) from `read_venue_book`'s per-symbol holdings, which already fold each coin's balance under its EUR pair and sign a margin position: for a spot-only book the figure is the coin's `balance.total`, which is what `_classify_spot_close` bounds a sell against. `_spot_balance`'s alias loop reads the base key first and resolves at once.
- Under `reduce_only` the bound is `qty <= balance` with a dust balance read as 0.0, so a sell under the hold of a leg the venue holds as dust is refused — which is right: no order can sell it.
- `_newest_venue_balances` goes rather than lingering unused: the next reader of a balance would otherwise find a function whose docstring says the record's figure is the bound.
- This task stays in this plan and rides this spec's rollout, never cut ahead as its own PR onto the November one: the `[iter-173]` ordering constraint — the bump never deploys ahead of the balance-reading sell check — is held by the disarmed interval between the week-of-2026-11-02 engine rollout and this spec's own, in which no sell runs; the owner's ruling of 2026-10-05 on the plan, spec D15 item 3.

- [ ] **Step 1: Write the failing tests** — the spec's three constructions, each ending in a classification read from the stub client:

```python
def test_a_dust_balance_under_ordermin_reads_as_absent_in_both_arms():
    close = ProbeIntent(symbol="BTC/EUR", side="sell", action="close", mode="execute", notional_eur=None, qty=0.001, leverage=None)
    full = executor_module._classify_spot_close(close, balances={"BTC": 1e-08}, level=GateLevel.FULL, ordermin=5e-05)
    held = executor_module._classify_spot_close(close, balances={"BTC": 1e-08}, level=GateLevel.REDUCE_ONLY, ordermin=5e-05)
    assert full.refusal is None and full.qty == 0.001
    assert held.refusal == "the venue's balance does not cover the signed qty"


def test_the_disposal_is_bounded_by_the_venues_book_and_not_by_the_record_it_refused_under(tmp_path):
    _venue_record(tmp_path, balances={"XXBT": 0.0005})
    ex, client, clock = _resting_executor(tmp_path, intents=[_intent(symbol="BTC/EUR", side="sell", action="close", qty=0.001)], venue_holdings=_VenueHoldings({"BTC/EUR": 0.001}))
    assert len(client.submitted) == 1 and client.submitted[0].side == "sell"


def test_a_process_that_has_read_no_book_refuses_the_disposal(tmp_path):
    ex, client, clock = _resting_executor(tmp_path, intents=[_intent(symbol="BTC/EUR", side="sell", action="close", qty=0.001)], venue_holdings=_VenueHoldings(raises=RuntimeError("down")))
    assert client.submitted == [] and _intent_outcome(tmp_path) == "refused"
    assert "have not been read in this process" in _intent_entry(tmp_path, 0)["reasons"][0]


def test_a_process_that_has_read_no_book_refuses_an_opening_plan_with_the_same_sentence(tmp_path):
    ex, client, clock = _resting_executor(tmp_path, intents=[_intent(symbol="ETH/EUR", side="buy", action="open", notional_eur=20.0)], venue_holdings=_VenueHoldings(raises=RuntimeError("down")))
    assert client.submitted == [] and "have not been read in this process" in _plan_entry(tmp_path)["reasons"][0]
```

`_resting_executor` gains a `venue_holdings=` pass-through to `_executor` if it lacks one. The existing disposal cases that write a `_venue_record` to bound a sell are re-based on the book: each keeps its assertion and moves its figure from `_venue_record(balances=…)` to `_VenueHoldings({...})`, the `reduce_only` cases included; the stale-record construction ("the pre-restart record cannot see the settle, the intent proceeds on the signed figure") is deleted, since the book is the venue's own and a figure it does not carry is 0.0.

- [ ] **Step 2: Run the tests and read the failure** — `-k 'dust_balance or venues_book or read_no_book'`; Expected: `TypeError` on `ordermin`, then the record's refutation on the second case, the third and fourth submitting.
- [ ] **Step 3: The classifier, its caller, the mixed-inventory read, the deletion, the two docstrings**
- [ ] **Step 4: Run the tests** — `uv run pytest tests/test_engine_executor.py tests/test_engine_node.py -q -p no:cacheprovider`; Expected: no failure.
- [ ] **Step 5: The consumers** — `grep -rn '_newest_venue_balances\|venue record refutes\|does not cover the signed qty' cli/ tests/ infra/runbooks/ docs/open-topics/`; every hit outside the executor and its test is read: the rung-2 runbook's sentences on the record's `b` (`engine-rung-2-box`'s `What it means` bullet and its step 5 item 5) describe the frozen image `f102ca375382` the box runs on, true until R2 converges this branch's image, by which time that section has retired at the box's exit report (spec D16; R0 (2) orders the two) — no task edits them, an explicit drop; `cli/engine/draftplan.py`'s `venue_b` cap stays, the helper modelling the engine the box runs on.
- [ ] **Step 6: The commit gate**
- [ ] **Step 7: Commit** — `fix(engine): the spot-sell check reads the venue's own balances, never the stored account, and a balance under ordermin reads as absent`, with `PROBE_VERDICT` and the trailer.
- [ ] **Step 8: The tree is clean**
- [ ] **Step 9: Prove the guards with one probe per guard, then record their verdicts by a message-only amend** — mutations: the dust floor deleted (`if balance < ordermin: balance = 0.0` removed; the first case refuses at `full`); the book's figure replaced by the record's (`_classify_close` reading `_newest_venue_balances` again, restored for the probe's sed; the second case's sell is refused); the `None` book read as `{}` (the third and fourth cases submit). Expected: `KILLED (control proven, …)` each.

---

### Task 9: The account-wide stale-socket watchdog — the grace, the freeze, the revoke, the cancel-all, the lift

**Files:**
- Modify: `cli/engine/executor.py` (`_SOCKET_DOWN_GRACE = timedelta(seconds=30)` in the constants block; `self._sockets_down` becomes `dict[str, datetime]`, endpoint → the time its `DISCONNECTED` arrived, `self._now()` at the event, the three set-literal asserts on it in the test file re-read as Step 4 says; `self._frozen = False`; `self._sockets_emptied_at: datetime | None`; `self._reread_completed_at: datetime | None`; `_watch_sockets(now)` on the tick before the re-read pass; `_reread_pass` spends its budget at its end — `_reread_tries = 0` and the stamp `_reread_completed_at` once its reads answered and the settle returned `True`; a settle that returned `False` spends one try as a failed read does (WARNING `asking again next tick`, CRITICAL at 0 with the freeze standing), so the next tick runs the pass again under the same budget, its rows those still open and minted-closed, as on any re-arm today; the fold's `socket_down` reads `self._frozen`; `on_socket_state`'s docstring paragraph on the set and its arms re-trued for the dict and the freeze; `_arm_reread_after_mint`'s docstring sentence on the stale entry's cost re-trued, the freeze now standing and paging)
- Test: `tests/test_engine_executor.py`

**Interfaces:**
- Consumes: `on_socket_state`'s `SocketState.DISCONNECTED` / `CONNECTED`; `_cancel_resting(active)` and the two `_revoke` lines it lacks (`revoke_reasons`, `_enter(active, "cancelling")`); `_level_permits`; Task 4's `_set_frozen`; Task 5's fold; the `_socket` and `_reconnect` helpers.
- Produces: the state `_frozen` the fold and D11's rule read; the gauge `zcrypto_exec_watchdog_frozen`.

**What this task decides, where the spec leaves it open:**
- `_watch_sockets(now)` runs on every tick, first in `on_timer` after the startup pass. Not frozen: an endpoint whose `now − down_since > _SOCKET_DOWN_GRACE` sets `_frozen = True`, publishes `_set_frozen(1)`, logs CRITICAL naming the endpoint and the grace, and cancels in `_trip_kill`'s order — `_cancel_resting(active)`: one cancel of the active intent's resting order (its id in the sweep's `requested` set) and one per other Cache-open order — then, for a resting active intent, the two lines of `_revoke` the sweep lacks, `active.revoke_reasons = ("socket_down",)` and `self._enter(active, "cancelling")`, so the ack, where the socket that carries it is up, lands the terminal as a revocation with `socket_down` among its reasons (`quote_silence`'s shape) — and under the cut both endpoints share, the ack never arrives: the row ends `ambiguous` on the minted terminal (`_on_order_event` takes a `reconciliation=True` terminal above its dispatch) or at `_ACK_WAIT` (`_poll`'s non-resting arm), the plan halted, the return's pass settling it (spec D7); `_pump`'s level path on the same tick — the fold reads `none` with `socket_down` — finds the intent `cancelling` and `_poll` waits on the ack: one cancel per order. (`_revoke` followed by `_cancel_resting(active)`, or `_cancel_resting(None)` with the level path left to revoke, each send the active's cancel twice: the sweep cancels the active itself and excludes only what it has just requested.) Frozen: `self._sockets_down` empty, `_sockets_emptied_at` set, and `_reread_completed_at >= _sockets_emptied_at` lifts it — `_frozen = False`, `_set_frozen(0)`, INFO. A pass whose budget is spent stamps nothing, so the freeze stands; a restart inside a gap is the lift, and the rule pages at 15 minutes.
- `_sockets_emptied_at` is set in `on_socket_state` when a `CONNECTED` pops the last entry; a `DISCONNECTED` while frozen re-arms nothing new — the freeze is one state.
- `_start_intent` needs no own check: the fold's `none` refuses every intent with `socket_down` in its reasons, which the ledger shows.
- The cancel-all is `_cancel_resting(active)`'s existing sweep, best effort by F2's measurement; the re-read pass's re-cancel on the return is the mechanism, which the lift waits on.

- [ ] **Step 1: Write the failing tests**:

```python
def test_a_three_second_blip_revokes_nothing_and_a_partial_cut_past_the_grace_revokes_the_resting_intent_on_its_ack(tmp_path):
    ex, client, clock = _resting_executor(tmp_path, intents=[_intent(mode="rest-hold", offset_pct=5.0, hold_minutes=45)])
    ex.on_socket_state(_socket(SocketState.DISCONNECTED, "kraken-spot-user-streams"))
    clock.now += timedelta(seconds=3)
    ex.on_socket_state(_socket(SocketState.CONNECTED, "kraken-spot-user-streams"))
    _advance_with_quotes(ex, client, clock, minutes=1)
    assert client.canceled == [] and not ex._frozen
    ex.on_socket_state(_socket(SocketState.DISCONNECTED, "kraken-spot-data-streams"))  # the execution socket stays up
    _advance_with_quotes(ex, client, clock, minutes=1)  # a tick every 10 s, past the 30 s grace
    assert ex._frozen and client.canceled == [client.last_order_id]
    ex.on_order_event(_canceled(client.last_order_id))  # the ack the execution socket carries
    assert _intent_outcome(tmp_path) == "revoked" and "socket_down" in _intent_entry(tmp_path, 0)["reasons"]


def test_a_cut_of_both_endpoints_past_the_grace_sends_the_cancel_and_the_row_ends_ambiguous_on_the_minted_terminal(tmp_path):
    ex, client, clock = _frozen_executor(tmp_path)  # both endpoints down, the freeze's one cancel out, the terminal minted
    assert ex._frozen and [str(cid) for cid in client.canceled] == ["O-1"]
    assert _intent_outcome(tmp_path) == "ambiguous" and ex._plan is None
    assert "was reconciled, not received" in _intent_entry(tmp_path, 0)["reasons"][0]


def test_the_freeze_lifts_only_once_the_set_is_empty_and_a_completed_pass_has_settled(tmp_path):
    holdings = _VenueHoldings({})
    ex, client, clock = _frozen_executor(tmp_path, venue_holdings=holdings)  # helper: the cut above, frozen
    ex.on_socket_state(_socket(SocketState.CONNECTED, "kraken-spot-data-streams"))
    assert ex._frozen  # one endpoint still down
    ex.on_socket_state(_socket(SocketState.CONNECTED, "kraken-spot-user-streams"))
    assert ex._frozen  # the set is empty but no pass has run
    ex.on_timer(clock.now)  # the pass runs with nothing in flight and settles
    assert not ex._frozen and holdings.calls >= 2


def test_a_stale_entry_holds_the_freeze_and_the_published_level_at_none(tmp_path):
    ex, client, clock = _frozen_executor(tmp_path)
    ex.on_socket_state(_socket(SocketState.CONNECTED, "kraken-spot-data-streams"))
    ex.on_socket_state(_socket(SocketState.CONNECTED, "kraken-spot-user-streams-2"))  # the execution socket's return under another string
    _advance_ticks(ex, minutes=20)
    verdict = ex._evaluate(clock.now)
    assert ex._frozen and verdict.level == GateLevel.NONE and "socket_down" in verdict.reasons


def test_a_pass_whose_budget_is_spent_leaves_the_freeze_standing(tmp_path):
    ex, client, clock = _frozen_executor(tmp_path, venue_orders=_VenueOrders(raises=RuntimeError("down")))
    ex.on_socket_state(_socket(SocketState.CONNECTED, "kraken-spot-data-streams"))
    ex.on_socket_state(_socket(SocketState.CONNECTED, "kraken-spot-user-streams"))
    _advance_ticks(ex, minutes=1)
    assert ex._frozen and ex._reread_tries == 0


def test_a_settle_that_fails_on_the_returns_pass_spends_one_try_and_the_next_ticks_pass_lifts_the_freeze(tmp_path):
    holdings = _VenueHoldings({})
    ex, client, clock = _frozen_executor(tmp_path, venue_holdings=holdings)
    holdings._raises = RuntimeError("down")  # the startup's settle answered; the return's fails
    ex.on_socket_state(_socket(SocketState.CONNECTED, "kraken-spot-data-streams"))
    ex.on_socket_state(_socket(SocketState.CONNECTED, "kraken-spot-user-streams"))
    ex.on_timer(clock.now)  # the pass's reads answer, its settle fails: one try spent, the freeze stands
    assert ex._frozen and ex._reread_tries == 2
    holdings._raises = None
    ex.on_timer(clock.now + timedelta(seconds=5))
    assert not ex._frozen and ex._reread_tries == 0
```

Plus: a freeze with no intent live refuses the next plan's every intent with `socket_down` in the ledger; the sweep at the freeze, built on the first case's cut with the active still resting (no mint, so nothing to pop) — a second order held in the Cache through `_hold_in_cache` beside the active's appears once in `client.canceled`, the active's once, nothing twice.

`_frozen_executor(tmp_path, *, venue_orders=None, venue_cancel=None, venue_holdings=None)` is the cut carried to the mint: a rest-hold intent accepted under `_TXID` and held in the Cache (`_resting_limit_order`, `_hold_in_cache`), both endpoints reported `DISCONNECTED`, ticks with quotes (`_advance_with_quotes`, so quote silence stays out and the freeze's cancel is the one) past the grace, then the terminal minted as `_minted_after_a_cut` mints it — `_event(OrderCanceled, client_order_id="O-1", reconciliation=True)` applied to the order and delivered, and the order moved from `client.cache._open_orders` to `client.cache._closed_orders`, as the real Cache lists a canceled order under `orders_closed` and not `orders_open` where the stub's two lists are static and `order.apply(minted)` moves the order's status alone — so the row is one the re-read pass reads (`_minted_closed`, whose `_cache_lookup` finds the order through the stub's `order()` over both lists), nothing is in flight, and a later sweep finds nothing open; `venue_orders` defaults to `_VenueOrders(_report(_TXID, OrderStatus.CANCELED))`, `venue_cancel` to `_VenueCancel()`. Without the mint the pass holds no row (`_reread_pass` reads the venue only when it holds rows), reads nothing, stamps `_reread_completed_at`, and the budget case lifts for the wrong reason. Its lift takes both endpoints' `CONNECTED`, since both were reported down.

- [ ] **Step 2: Run the tests and read the failure** — `-k 'blip or both_endpoints or freeze or stale_entry or budget_is_spent or settle_that_fails'`; Expected: `AttributeError: … '_frozen'`.
- [ ] **Step 3: The constant, the dict, the watcher, the stamps, the fold's read, the two docstrings**
- [ ] **Step 4: Run the tests** — `uv run pytest tests/test_engine_executor.py -q -p no:cacheprovider`; Expected: no failure once two existing shapes are re-based in this task. The existing socket cases pass unchanged on the grace, since none holds an endpoint down past 30 s of ticks; the asserts comparing `_sockets_down` with a set literal — three at this plan's base, the file's whole family, found by `grep -n '_sockets_down' tests/test_engine_executor.py` — read `set(ex._sockets_down)`. And `test_a_returns_arm_pending_behind_a_live_intent_is_cleared_by_the_cut_and_the_return_settles_the_row`, the one case in the file holding an endpoint down past the grace — the sweep over the file's `DISCONNECTED` sites (`grep -n 'DISCONNECTED' tests/test_engine_executor.py`, fourteen at this plan's base) finds no other; `_minted_after_a_cut` reports no socket — reports both endpoints down at clock `NOW+5 s` and ticks at `NOW+31`, `+36`, `+41` and `+46`, so the freeze fires on the `NOW+36` tick: its `_executor_errors` assertion admits the freeze's one CRITICAL (the record naming `kraken-spot-user-streams` and the grace), it asserts `ex._frozen` after that tick and `not ex._frozen` after the return's tick (the pass it already asserts is the lift's), and the minted order is moved from `client.cache._open_orders` to `client.cache._closed_orders` before the freeze's tick — the real Cache lists a canceled order under `orders_closed`, not `orders_open`, where the stub's `orders_open` is a static list `_hold_in_cache` appends to and `order.apply(minted)` moves the order's status alone — so the freeze's sweep finds nothing open and `client.canceled` stays `["O-1"]`.
- [ ] **Step 5: The consumers** — `uv run pytest tests/test_engine_node.py tests/test_engine_metrics.py -q -p no:cacheprovider`.
- [ ] **Step 6: The commit gate**
- [ ] **Step 7: Commit** — `feat(engine): the account-wide stale-socket watchdog -- a 30 s grace, the freeze that revokes and cancels, the lift behind the re-read pass`, with `PROBE_VERDICT` and the trailer.
- [ ] **Step 8: The tree is clean**
- [ ] **Step 9: Prove the guards with one probe per guard, then record their verdicts by a message-only amend** — mutations: `_SOCKET_DOWN_GRACE` set to `timedelta(seconds=1)` (the blip revokes); the lift's `_reread_completed_at >= _sockets_emptied_at` dropped to `not self._sockets_down` alone (the lift case lifts before the pass); the fold's `socket_down` arm deleted (the stale-entry case reads `full`); `_cancel_resting(active)` dropped from the freeze (the sweep case's second order is never cancelled); the budget's spend moved back above the settle (the settle-failure case reads `_reread_tries == 0` after its first tick and never lifts). Expected: `KILLED (control proven, …)` each.

---

### Task 10: `_accept_plan` — `_pickup` from its `parse_plan` line on, with the file path removed

**Files:**
- Modify: `cli/engine/executor.py` (`_accept_plan(plan, *, cycle_ts, now, path=None) -> str` returning `"accepted"`, `"refused"` or `"waiting"`; `_pickup` keeps the `lstat`, the parse and the unparseable refusal and calls `_accept_plan(..., path=path)`, which deletes the file after journaling as `_pickup` did; `self._plan_window_close: datetime | None = None`, set by Task 11; `_pickup`'s docstring, if any, and the comment "Journal FIRST, delete SECOND, run THIRD" move with the code)
- Test: `tests/test_engine_executor.py`

**Interfaces:**
- Consumes: everything `_pickup` reads from its `parse_plan` line on: the kill backstop, `_reconciliation_refusal`, `venue_state_from_cache`, the in-flight wait, `plan_refusals`, `_mixed_inventory_refusals`, `_journal_plan`, `_delete`, `self._plan`/`_plan_cycle_ts`/`_index`/`_resolved_notional`.
- Produces, for Task 11 by these exact names: `self._accept_plan(plan, cycle_ts=boundary, now=now)` with no path — the in-memory hand-off; the three outcomes.

**What this task decides, where the spec leaves it open:**
- Behaviour-preserving for a file plan: every existing pickup test passes unchanged; the refactor adds no branch. The in-flight wait returns `"waiting"` with nothing journaled and the file kept, as today; for a plan with no path the caller (Task 11's draft) never reaches the wait, since the draft itself runs only with nothing in flight — the branch is kept for the drill file alone.

- [ ] **Step 1: Write the failing test** — `parse_plan` added to the file's `cli.engine.probeplan` import (line 79 imports `MODES, PLAN_FILENAME, ProbeIntent` and names `parse_plan` only in comments; Tasks 8 and 11 read the same name), then one, the in-memory hand-off:

```python
def test_a_plan_handed_in_memory_runs_through_the_pickups_refusals_and_journals_under_the_boundary_it_is_given(tmp_path):
    ex, client, _ = _idle_executor(tmp_path)
    ex.on_timer(NOW)
    plan = parse_plan(json.dumps(_plan_dict(plan_id="r3-20261109-00")))
    assert ex._accept_plan(plan, cycle_ts=_boundary(NOW), now=NOW) == "accepted"
    assert ex._plan is plan and _plan_entry(tmp_path)["plan_id"] == "r3-20261109-00"
    assert ex._accept_plan(plan, cycle_ts=_boundary(NOW), now=NOW) == "refused"
    assert _plan_entry(tmp_path, index=1)["reasons"] == ["plan_id already ledgered"]
    assert not _plan_path(tmp_path).exists()
```

- [ ] **Step 2: Run the test and read the failure** — `-k handed_in_memory`; Expected: `AttributeError: … '_accept_plan'`.
- [ ] **Step 3: The refactor**
- [ ] **Step 4: Run the tests** — `uv run pytest tests/test_engine_executor.py -q -p no:cacheprovider`; Expected: no failure, every pickup case among them.
- [ ] **Step 5: The consumers** — none beyond the file.
- [ ] **Step 6: The commit gate**
- [ ] **Step 7: Commit** — `refactor(engine): the plan pickup's acceptance is one method the file path is handed to, so a plan built in memory takes the same walls`, with the trailer; no guard changes, so no probe.
- [ ] **Step 8: The tree is clean**

---

### Task 11: The boundary drafts the cycle's plan — the book read with its retry, the table, the window, the carry, the record, the gap gauge

**Files:**
- Modify: `cli/engine/executor.py` (`_SUBMISSION_WINDOW = timedelta(hours=3, minutes=30)`; `_LOOP_CASH_RESERVE_EUR = 10.0`; `read_instrument_statuses(*, base_url)` on `_bare_client`, the constructor seam `instrument_statuses` it is the default of, and the status carry in `_draft_cycle_plan` (spec D17); `_PendingDraft` dataclass; `on_boundary`'s third act `_arm_cycle_draft(boundary)` after `_evaluate_tracking`; `_draft_cycle_plan(now)` on the tick, after the re-read pass and before `_pickup`; the window close in `_start_intent`; the first tick's re-arm after a restart inside a window; the `no-cycle`, `book-unread`, `window-closed`, `refused` and `ok` records, each write setting `_set_boundary_not_drafted` and each terminal re-journaling the boundary's exec record; `self._cycle_legs`, the draft's per-leg `(delta_eur, close)` the gap gauge re-reads at a cycle-plan intent's terminal; `_score_closed_week`'s `held_back` reading the boundary's `accum-<HH>.json`; `_inc_order("carried")`; `on_boundary`'s docstring "THE call site" paragraph re-trued for three acts)
- Modify: `cli/engine/command.py` (`_EXEC_ORDER_OUTCOMES` gains `"carried"`)
- Create: `tests/fixtures/rung2/cycle-12.json` (a byte-identical copy of `data/rung2/`'s 2026-10-05 12Z cycle record — the model's `final_targets`, `closes` and `nav`, no balance), `tests/fixtures/rung2/venue-12.json` and `tests/fixtures/rung2/balance.json` (synthesized in the venue record's and the extended-balance export's shapes at invented quantities, never copied: the account's real balances and positions stay out of git, the owner's ruling of 2026-10-05 on the plan)
- Test: `tests/test_engine_executor.py`, `tests/test_engine_metrics.py` (the outcome label)

**Interfaces:**
- Consumes: Task 1's keyword parameters and `trim_to_plan_cap`; Task 2's `VenueBook`, `_settle_from_book` and `_venue_holdings` seam; Task 3's `write_accum_record` and `read_accum_record`; Task 4's `_set_gap` and `_set_boundary_not_drafted`; Task 5's fold; `self._config.exec_max_plan_notional_eur`; Task 10's `_accept_plan`; `from_json`, `validate_record`, `require_comparable_cycle_ts` (`cli/engine/journal.py`); `CycleRecord.final_targets`, `.closes`, `.nav`; `venue_state_from_cache` for the pair's constraints; `draftplan.Constraints`, `decide_leg`, `trim_buys_to_cash`, `assemble_plans`, `plan_document`; `parse_plan`; `open_submitted_rows`; `_cache_net`; `_MODEL_BASES`, `_SPOT_SYMBOL_BY_BASE`; `_REREAD_ATTEMPTS` as the book read's try budget; `KrakenSpotHttpClient.request_instrument_statuses()` (spec D17: `dict[InstrumentId, MarketStatusAction]` from two public `AssetPairs` GETs, `online` → `TRADING`, `cancel_only` → `HALT`, `post_only`, `limit_only` and `reduce_only` → `PAUSE`) and `_SYMBOL_BY_INSTRUMENT_ID`.
- Produces, for Task 12: `_draft_cycle_plan`'s book and record in hand before the table, the hook `self._mark_equity(book, record, now) -> dict` (a stub returning `None` fields here, Task 12's to fill), the `accum` record's equity fields written from it.

**What this task decides, where the spec leaves it open:**
- `_arm_cycle_draft(boundary)`: reads `<journal_dir>/<boundary:%Y-%m-%d>/cycle-<HH>.json` through `from_json`, `require_comparable_cycle_ts` and `validate_record`; absent, unreadable, or a `failed-cycle-<HH>.json` sidecar beside it → `write_accum_record(..., status="no-cycle", legs=[])` and nothing armed; else `self._pending_draft = _PendingDraft(boundary=boundary, record=record, tries=_REREAD_ATTEMPTS, window_close=boundary + _SUBMISSION_WINDOW)`. A boundary armed while a previous draft is still pending replaces it, its record written `window-closed` first.
- On the first tick after the startup pass, with no draft pending: if `_boundary(now) + _SUBMISSION_WINDOW >= now`, the boundary's cycle record exists and its `accum-<HH>.json` is absent or carries `plan_id: None`, `_arm_cycle_draft(_boundary(now))` — the alert fired in the previous process. A record carrying a `plan_id` says the boundary drafted, and re-arming would overwrite its legs with a dedup refusal (`write_accum_record` is a plain store), so nothing is armed and nothing written; where the record is absent but the plan was journaled — the previous process ended between `_journal_plan` and the record write — the re-drafted plan meets `ledgered_plan_ids` and is refused `plan_id already ledgered` (the spec's dedup-wall verification, constructed that way: the plan entry ledgered, the record deleted); a boundary whose window has closed arms nothing and writes nothing.
- `_draft_cycle_plan(now)` runs when `self._pending_draft is not None and self._plan is None`: `now > window_close` → `window-closed` record, cleared; `not self._nothing_in_flight()` → return (wait); the book read `(self._venue_holdings or read_venue_book)()` in `try` — a raise spends one try at WARNING, and at 0 writes `book-unread` and clears; the venue truth `venue_state_from_cache(self._cache, clock=self._now)` the same way (a Cache that cannot be read is a read that failed). Then `self._venue_book = book`, `self._settle_from_book(book, "the boundary read")` (Task 2's apply half: the cross-check WARNING per symbol over `FLAT_TOLERANCE` and the gauge publish, no second read), `self._mark_equity(book, record, now)`; then the table over the ten model symbols in `sorted(_SPOT_SYMBOL_BY_BASE.values())`: `weight = record.final_targets[symbol]`, `close = record.closes[base]`, `Constraints(ordermin=state.instruments[symbol].ordermin, lot_step=state.instruments[symbol].lot_step)`, `decide_leg(symbol, weight=weight, price=close, constraints=…, kraken_held=book.held[symbol], engine_held=self._cache_net(symbol), venue_b=0.0, eur_per_weight=record.nav)`; a symbol absent from `final_targets`, `closes` or the venue truth refuses the whole draft at WARNING (`refused` record, reason naming the symbol) — a half-drafted book is the drift the loop exists to close. The open-row carry: a placed leg whose symbol names an `open_submitted_rows(journal_dir, now)` row's `intent["symbol"]` becomes `carried` with `an order of this symbol may still rest at the venue`. The status carry (spec D17), beside it: `statuses = (self._instrument_statuses or read_instrument_statuses)()` runs inside the book read's `try`, right after the book, so a raise spends the same try, and answers `dict[str, str]` per `INSTRUMENT_IDS` symbol — the `MarketStatusAction`'s name, `absent` for a symbol the venue's answer does not name; a `placed` leg whose status is not `TRADING` becomes `carried` with `side`, `qty` and `notional_eur` `None` and the reason `the venue lists the instrument <ACTION>, not TRADING`, and logs the WARNING `the venue lists %s %s, not TRADING -- the leg carries to the next boundary`; the leg keys are Task 3's unchanged, the status in the reason's text. Then `trim_buys_to_cash(decisions, book.eur_free, cash_reserve_eur=_LOOP_CASH_RESERVE_EUR)`, `trim_to_plan_cap(decisions, self._config.exec_max_plan_notional_eur)` (Task 1: sells then buys carried from the smallest until the plan fits the cap `plan_refusals` and `_over_cap_reason` judge it by, so a plan is never refused whole at the wall and drafted again unchanged at every boundary — spec D3, D4), `assemble_plans(decisions, max_intents=None, plan_cap_eur=None)`; no plan → the `ok` record with `plan_id: None`; else `plan_document(f"r3-{boundary:%Y%m%d}-{boundary:%H}", now, plans[0])`, `parse_plan(json.dumps(doc))`, `self._plan_window_close = window_close`, `outcome = self._accept_plan(plan, cycle_ts=boundary, now=now)`; `"refused"` → the record `refused` with every placed leg carried under the plan entry's reasons; `"accepted"` → `ok` with `plan_id`. The record carries, per leg, the decision's fields and `cache_net` (`_cache_net(symbol)` at the draft); the WARNING per differing leg is `_settle_from_book`'s, logged once above. The gap gauge: `delta_eur` for every leg at the draft, the per-leg `(delta_eur, close)` kept on `self._cycle_legs` (replaced at each draft); an intent of the cycle plan — a plan run under `_plan_window_close` — re-sets its leg at its terminal, in `_journal_intent(index, outcome, reasons, filled_qty)`, the one write every terminal of an intent passes through (`_finish_active` and `_refuse_intent` journal through it, and so do the `ambiguous` exits — `_strand_ambiguous`, `_submit`'s, the cancel-rejected and quote-silence ones — `_trip_kill`'s `revoked` and `_halt_plan`'s `refused`, each calling it directly), the leg's symbol read as `self._plan.intents[index].symbol` while `self._plan` still stands, to `delta_eur − filled_qty × close` signed by side, so a refused, carried, unfilled, partly filled, ambiguous, kill-revoked or halt-refused intent reads what is still open and a filled one about 0 (spec D14). Every record write sets `_set_boundary_not_drafted(0 if status == "ok" else 1)`, `_arm_cycle_draft`'s `no-cycle` included, and every terminal of the draft — `ok`, `refused`, `book-unread`, `window-closed` — ends with the boundary's exec record re-journaled, `verdict = self._evaluate(now, heartbeat=False)` then `write_exec_record(self._journal_dir, boundary, verdict, evaluated_at=now)`, the merge keeping `submitted` and `plans`, so the record carries the level the boundary ends at — the day-loss hold or the kill the mark latched (Task 12) — where Task 5's first act carried the one it began at. Raises: the draft from the book read to the `_accept_plan` call runs under one guard — a raise anywhere in it spends a try at WARNING, the `book-unread` arm's, and at 0 writes `refused` with the exception's class and text and clears the draft, so a corrupt record under `_mark_equity` or a zero base cannot re-read the book every tick until `window_close` with the budget untouched; and everything after `_accept_plan` returns `"accepted"` — the record write, the gap gauge, the cross-check WARNING — runs inside its own `try`/`except Exception: logger.exception(...)`, `_publish_resting_age`'s rule, so a journaled plan is never dropped by `on_timer`'s catch over telemetry.
- The same-cycle rule: the plan id is the boundary's, one plan per boundary, and `ledgered_plan_ids` refuses a second — an intent that ended `unfilled`, `partial`, `refused`, `rejected`, `ambiguous` or `revoked` is therefore never re-placed in its cycle, structurally; a test holds that a re-armed draft after a simulated restart is refused `plan_id already ledgered`.
- The window close in `_start_intent`, before the dedup belt: `if self._plan_window_close is not None and now > self._plan_window_close: self._journal_intent(index, "carried", ("the submission window closed",)); _inc_order("carried"); self._index += 1; return`. `_accept_plan` resets `_plan_window_close = None` for a plan with a path.
- The cross-check reads `_cache_net(symbol)` at the draft, the Cache's instrument-scoped net; nothing is drafted from it.
- `_score_closed_week`'s `held_back` (the `00091` trip's eligibility read, `cli/engine/executor.py`) gains the boundary's `accum-<HH>.json`: a boundary whose record exists with a `status` other than `ok` is held back beside one whose exec record's `level` is not `full`, the refusal reading `below the full level or undrafted`; an absent record holds nothing back — a boundary before this code ran, or a process that ended between the exec record and the accum write, the dedup wall's gap above — so the tracking tests' journals of exec records alone score as today. The exec record's `level` stays the gate's: the gate did not hold the loop, the draft did not run (spec D3).

- [ ] **Step 1: The fixtures** — `cp -p /home/zhaow/Projects/zcrypto-kraken/data/rung2/cycle-12.json tests/fixtures/rung2/` from the main checkout's gitignored data, read-only, its `sha256sum` against the copy printed in the commit body; `venue-12.json` written by hand in the venue record's shape, `validate_venue_record` passing — the twelve legs' `ordermin` and lot step at the values the spec's measured basis records (BTC 5e-05, ETH 0.001, SOL 0.06, XRP 1.65, DOGE 50, LTC 0.1, ADA 20, AVAX 0.5, DOT 3.9, LINK 0.55, lot step 1e-08), every position 0, `balances` `{"EUR": 1500.0}`; `balance.json` written by hand in the extended-balance export's shape (`asset -> {balance, hold_trade}`, `parse_balance_export` passing) — an `EUR` row at `1500.0000` with `hold_trade` `0.0000`, the nine coins at invented quantities above their `ordermin`, `XDG` for DOGE, zero rows for BNB, EURC and LINK. Neither file is copied from `data/rung2/`, and no real quantity enters the tree: the Verification values (the ten notionals, LINK's among them) come from the cycle record's weights and closes and the venue minimums, not from the account.
- [ ] **Step 2: Write the failing tests** — the helper `_boundary_executor(tmp_path, *, record_path, holdings, eur_total, eur_free, now, statuses=None, series=())`, returning `(ex, client, clock)`, that writes the fixture's cycle record under `<journal>/<day>/cycle-12.json`, builds the venue truth from `venue-12.json`'s instruments, hands a `_VenueHoldings` built from `balance.json` (zero for every leg on entry day's draft, the nine invented quantities after) and a `statuses` mapping for the `instrument_statuses` seam through a new `instrument_statuses=` pass-through on `_executor`, every leg `TRADING` unless the test says otherwise, builds its `_config` with `exec_max_plan_notional_eur=1000.0` — `cli/config.py`'s default 100.0 would refuse the entry day's 231 EUR of buys at `plan_refusals` — and seeds `series`, prior equities, as `accum-*.json` records of earlier boundaries (Task 12's cases); with `RUNG2 = Path(__file__).parent / "fixtures" / "rung2"`, `_RUNG2_12Z = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)` (the fixture's `cycle_ts`) and `_TEN_EUR_LEGS = sorted(executor_module._SPOT_SYMBOL_BY_BASE.values())` defined beside it, and `RecordingMetrics` gaining `gaps` and `not_drafted` lists for the two hooks; then:

```python
def test_rung_twos_entry_day_drafts_the_ten_legs_at_nav_1000_with_the_notionals_the_floor_arithmetic_gives(tmp_path):
    ex, client, clock = _boundary_executor(tmp_path, record_path=RUNG2 / "cycle-12.json", holdings={}, eur_total=1500.0, eur_free=1500.0, now=_RUNG2_12Z + timedelta(minutes=2))
    ex.on_boundary(_RUNG2_12Z)
    ex.on_timer(clock.now)
    plan = _plan_entry(tmp_path, when=_RUNG2_12Z)
    assert plan["plan_id"] == "r3-20261005-12" and plan["disposition"] == "accepted"
    intents = {i["symbol"]: i for i in plan["plan"]["intents"]}
    assert set(intents) == set(_TEN_EUR_LEGS) and "LINK/EUR" in intents
    assert intents["BTC/EUR"]["notional_eur"] == pytest.approx(42.06, abs=0.01) and intents["LINK/EUR"]["notional_eur"] == pytest.approx(17.09, abs=0.01)
    record = read_accum_record(accum_record_path(tmp_path / "journal", _RUNG2_12Z))
    assert record["status"] == "ok" and record["nav"] == 1000.0 and record["eur_free"] == 1500.0
    assert all(leg["outcome"] == "placed" for leg in record["legs"])


def test_the_loops_rows_at_eur_720_on_the_nine_legs_equal_the_helpers_decision_rows(tmp_path):
    """The helper's rows are recomputed in the test — `decide_leg` at its hand-window defaults over
    the same fixtures — since the real day's `data/rung2/decisions.jsonl` is gitignored; the loop's
    `decide_leg` rows from a record copy at `nav: 720` carry the same (symbol, outcome, side,
    notional, qty, reason) tuples for the helper's nine legs, read BEFORE `trim_buys_to_cash` and
    `assemble_plans`, where the two differ by design: the reserve (10 against 5), the split (none
    against three) and the cap (the plan's against 95), which mark six of the nine `queued` under
    the helper and `placed` under the loop."""
    ...


def test_a_sidecar_boundary_writes_no_cycle_and_drafts_nothing(tmp_path): ...
def test_a_book_read_that_fails_three_ticks_writes_book_unread_and_the_next_boundary_absorbs_the_gap(tmp_path): ...
def test_the_whole_draft_waits_on_a_tick_with_nothing_in_flight_and_created_at_is_that_ticks_now(tmp_path): ...
def test_a_draft_still_waiting_past_the_window_writes_window_closed(tmp_path): ...
def test_an_intent_does_not_start_past_the_windows_close_and_is_journaled_carried(tmp_path):
    """An intent whose predecessor ends at B+3h31 is carried with `the submission window closed`;
    at B+3h29 it starts. The probe deletes the close and the B+3h45 start then happens."""
    ...
def test_a_leg_with_an_open_ledger_row_is_carried_until_the_venue_has_answered_it(tmp_path):
    """A BTC/EUR row `ambiguous` inside the window: the draft carries BTC/EUR with the open-row
    reason and drafts no second sell; with the row closed the next draft sells."""
    ...
def test_a_re_armed_draft_after_a_restart_inside_the_window_is_refused_by_the_dedup_wall(tmp_path): ...
def test_a_drill_plan_dropped_during_a_cycle_plan_waits_in_its_file(tmp_path): ...
def test_a_eur_160_leg_at_nav_1000_is_drafted_into_the_boundarys_one_plan(tmp_path):
    """A synthetic record with BTC/EUR at weight 0.16: the loop drafts the leg where the helper's
    `assemble_plans` raises at the 95 EUR cap; the helper's own tests are untouched."""
    ...
def test_a_long_book_over_the_cap_from_a_flat_book_drafts_one_plan_at_the_cap_and_carries_the_rest(tmp_path):
    """A synthetic record with the ten EUR legs at 0.12 (long gross 1.2) from a flat book with
    `eur_free` 1,500: the table trims buys from the smallest until the plan fits
    `exec_max_plan_notional_eur` 1000.0, the plan is `accepted` with Σ `notional_eur` ≤ 1000 and
    the carried legs name the cap; the probe deletes the trim and `plan_refusals` refuses the plan
    whole, every leg carried."""
    ...
def test_a_closed_week_holding_an_undrafted_boundary_is_refused_naming_it(tmp_path):
    """42 `full` exec records with a `book-unread` record at one boundary: `_score_closed_week`
    refuses the week at that boundary; with the record `ok` it scores. The probe deletes the
    accum read and the week scores either way."""
    ...
def test_a_refused_intent_of_the_cycle_plan_reads_its_whole_delta_on_the_gap_gauge(tmp_path):
    """The entry-day plan accepted under a disarmed gate: every intent `refused` at `_start_intent`,
    and the gap gauge reads each leg's whole `delta_eur` after the terminals, where the draft alone
    read it as if filled."""
    ...
def test_the_cross_check_logs_the_venue_holds_warning_and_drafts_from_the_venues_figure(tmp_path, caplog): ...
def test_the_gap_gauge_carries_the_post_decision_gap_per_leg(tmp_path): ...


def test_a_leg_whose_instrument_is_not_online_at_the_boundary_is_carried_with_the_status_in_its_reason(tmp_path, caplog):
    ex, client, clock = _boundary_executor(tmp_path, record_path=RUNG2 / "cycle-12.json", holdings={}, eur_total=1500.0, eur_free=1500.0, now=_RUNG2_12Z + timedelta(minutes=2), statuses={"SOL/EUR": "HALT"})
    ex.on_boundary(_RUNG2_12Z)
    ex.on_timer(clock.now)
    plan = _plan_entry(tmp_path, when=_RUNG2_12Z)
    assert plan["disposition"] == "accepted" and {i["symbol"] for i in plan["plan"]["intents"]} == set(_TEN_EUR_LEGS) - {"SOL/EUR"}
    legs = {leg["symbol"]: leg for leg in read_accum_record(accum_record_path(tmp_path / "journal", _RUNG2_12Z))["legs"]}
    assert legs["SOL/EUR"]["outcome"] == "carried" and legs["SOL/EUR"]["side"] is None and "HALT, not TRADING" in legs["SOL/EUR"]["reason"]
    assert legs["SOL/EUR"]["delta_eur"] == pytest.approx(25.99, abs=0.01)
    assert "the venue lists SOL/EUR HALT, not TRADING" in caplog.text


def test_a_status_read_that_raises_spends_the_book_reads_try_and_three_write_book_unread(tmp_path): ...


def test_read_instrument_statuses_reads_the_action_per_symbol_from_the_loopback(_loopback_credentials):
    pairs = json.loads(kraken_loopback.ASSET_PAIRS_FIXTURE.read_text())
    pairs["SOLEUR"]["status"] = "cancel_only"
    with kraken_loopback.serve(pairs) as venue:
        statuses = executor_module.read_instrument_statuses(base_url=venue.base_url)
        assert statuses["SOL/EUR"] == "HALT" and statuses["BTC/EUR"] == "TRADING" and statuses["ADA/EUR"] == "absent"
        assert venue.private_calls == []
        venue.errors["AssetPairs"] = "EService:Unavailable"
        with pytest.raises(RuntimeError, match="EService:Unavailable"):
            executor_module.read_instrument_statuses(base_url=venue.base_url)
```

- [ ] **Step 3: Run the tests and read the failure** — `-k 'rung_twos or sidecar_boundary or book_read_that_fails or whole_draft or windows_close or window_closed or open_ledger_row or re_armed or drill_plan_dropped or eur_160 or cross_check or gap_gauge or not_online or status_read or instrument_statuses or long_book_over_the_cap or undrafted_boundary or whole_delta'` (`window` alone selects five existing cases); Expected: `TypeError: … unexpected keyword argument 'instrument_statuses'` from `ProbeExecutor.__init__` on every `_boundary_executor` case — the seam is Step 4's — and `AttributeError: … 'read_instrument_statuses'` on the loopback case.
- [ ] **Step 4: The draft, the window, the carry, the record, the label**
- [ ] **Step 5: Run the tests** — `uv run pytest tests/test_engine_executor.py tests/test_engine_metrics.py -q -p no:cacheprovider`; Expected: no failure; `test_the_order_outcome_labels_cover_every_outcome_the_executor_can_emit` passes with `carried` on both sides.
- [ ] **Step 6: The consumers** — `uv run pytest tests/test_engine_node.py tests/test_engine_accumledger.py tests/test_engine_draftplan.py tests/test_engine_command.py -q -p no:cacheprovider`.
- [ ] **Step 7: The commit gate**
- [ ] **Step 8: Commit** — `feat(engine): the boundary drafts the cycle's plan -- target minus the venue's held, the helper's table at the record's NAV, one plan inside the submission window, the carry, the accumulation record`, with `PROBE_VERDICT` and the trailer; the body carries `cycle-12.json`'s sha256 sum against the main checkout's copy and names `venue-12.json` and `balance.json` as synthesized at invented quantities.
- [ ] **Step 9: The tree is clean**
- [ ] **Step 10: Prove the guards with one probe per guard, then record their verdicts by a message-only amend** — mutations: the window close deleted from `_start_intent` (an intent starts at B+3h45); the open-row carry deleted (a second sell of the `ambiguous` leg is drafted); `kraken_held` fed from `_cache_net` (the cross-check case drafts from the Cache); the book read's try budget made unbounded (the `book-unread` case never writes); the draft's in-flight wait deleted (`created_at` precedes the tick); `_arm_cycle_draft` reading `held` from the record; the status carry deleted (the `HALT` leg is drafted and placed); the status read moved outside the book read's `try` (the raising case escapes the tick instead of spending a try); the plan-cap trim deleted (the over-the-cap case's plan is refused whole at `plan_refusals`); `held_back`'s accum read deleted (the undrafted-week case scores); the terminal's gap re-set deleted (the refused intent's leg reads the draft's figure). Expected: `KILLED (control proven, …)` each.

---

### Task 12: The equity series and the two drawdown trips

**Files:**
- Modify: `cli/engine/executor.py` (`EQUITY_SERIES_FILE = "equity-series-start"`; `_DRAWDOWN_KILL_BPS = 1500`; `_DAY_LOSS_HOLD_BPS = 300`; `_mark_equity(book, record, now) -> dict` filled; `_series_start()`; `_mint_series_start(cycle_ts)`; `_day_loss_hold` derived in `on_boundary` ahead of its first act's evaluate, in `_mark_equity` with the boundary's own figure, and at the first tick after a restart; the fold's `daily_loss_hold` arm reads it; Task 4's `_set_equity`, `_set_drawdown`)
- Test: `tests/test_engine_executor.py`

**Interfaces:**
- Consumes: Task 3's `accum_records_since`; Task 11's `_mark_equity` seam and record write; `_trip_kill`; `FIRST_FILL_FILE`'s write-once shape (tmp sibling + `os.replace`); `_MODEL_BASES`.
- Produces: the record fields `equity_eur`, `hwm_eur`, `drawdown_bps`, `day_loss_bps`, `day_loss_hold`; the state `self._day_loss_hold`.

**What this task decides, where the spec leaves it open:**
- `equity_eur = book.eur_total + Σ book.held[symbol] × record.closes[base]` over the ten EUR legs; a base missing from `closes` prices nothing: the fields read `None`, the trips evaluate nothing, and the WARNING names the base — an unpriced mark is not a 100 % drawdown.
- The series start: `exec/equity-series-start` carries the boundary's `cycle_ts` in ISO 8601; absent at the first mark, written then with that boundary's `cycle_ts`; read to bound `accum_records_since(journal_dir, start, now)`, the one set of records both figures read. The HWM is the max `equity_eur` over those records plus this boundary's; `drawdown_bps = (1 − equity / hwm) × 10000`; the day's base, over the same bounded records: the date's 00Z record with an equity, else the previous day's last record with one, else — the series having started on the date — the date's earliest record with one, else this boundary's own equity (a loss of 0); `day_loss_bps = (1 − equity / base) × 10000`. So a re-mint inside a UTC day (spec D8, G1: a withdrawal taken paused) puts the day's earlier records outside both the HWM and the base, and neither trips on the withdrawn amount.
- The hold is derived, never stored: `self._day_loss_hold = any(r["day_loss_bps"] is not None and r["day_loss_bps"] >= 300 for r in today's records)` — over the date's records at or after the series' start — in `on_boundary` ahead of its first act's evaluate (Task 5), so a hold latched on date D is dropped at D+1's first boundary whether or not that boundary marks (`no-cycle`, `book-unread`, `window-closed`, a `refused` draft that raised before the mark); again in `_mark_equity` with this boundary's figure included, after which the draft's terminal re-journal (Task 11) writes the boundary's record under the level it ends at; and at the first tick after a restart from the date's records the same way. Under it the fold reads `reduce_only`, so `_start_intent` refuses opens with `daily_loss_hold` in the verdict's reasons and closes run.
- `drawdown_bps >= 1500` calls `_trip_kill(f"equity {equity:.2f} EUR is {drawdown_bps:.0f} bps under the series' high-water mark of {hwm:.2f} EUR")` inside `_mark_equity`, before the table; the table and `_accept_plan` still run and the kill backstop refuses, so the one record Task 11 writes after the table reads `refused` under the plan entry's `kill_switch` reason and carries the figures that tripped. Nothing re-mints the series file: after a trip the next boundary trips again on the same drawdown until the owner re-mints, by design.

- [ ] **Step 1: Write the failing tests**:

```python
def test_equity_is_marked_at_the_eur_balances_total_and_a_resting_bid_on_hold_trips_nothing(tmp_path):
    """total 1,000, free 850, nothing lost: the mark at `total` reads no drawdown; the probe marks
    at `free` and the 15 % floor trips on a book that lost nothing."""
    ex, client, clock = _boundary_executor(tmp_path, ..., holdings={}, eur_total=1000.0, eur_free=850.0, series=[1000.0])
    ...
    assert not _kill_file(tmp_path).exists() and record["drawdown_bps"] == 0.0


def test_a_fifteen_percent_fall_from_the_high_water_mark_latches_the_kill_file_with_the_figures(tmp_path): ...
def test_the_hwm_scan_is_bounded_by_the_series_start_and_an_older_drawdown_trips_nothing(tmp_path):
    """A record at equity 1,300 at the boundary before `equity-series-start`'s instant, the same UTC
    day, and this boundary's at 1,000: the bounded scan reads an HWM of 1,000; the probe deletes the
    bound and the kill latches."""
    ...


def test_a_same_day_re_mint_puts_the_days_earlier_records_outside_the_day_loss_base(tmp_path):
    """EUR 160 withdrawn paused at 10Z from a book of 1,000 and the file re-minted at the 12Z boundary:
    the 12Z base is its own equity (840, a loss of 0) and the 16Z base is 12Z's; the probe bounds the
    base by the day instead of the instant and the hold latches on the withdrawal."""
    ...
def test_a_three_percent_day_loss_latches_the_hold_for_the_date_and_a_recovery_does_not_lift_it(tmp_path): ...
def test_the_hold_is_derived_after_a_restart_from_the_dates_records(tmp_path): ...
def test_a_hold_latched_yesterday_is_dropped_at_the_new_dates_first_boundary_whether_or_not_it_marks(tmp_path):
    """The hold latched at 20Z; the 00Z cycle a sidecar (`no-cycle`, no mark): 00Z's exec record reads
    `full` with no `daily_loss_hold`, and the 04Z mark derives afresh."""
    ...
def test_under_the_hold_the_boundarys_sells_run_and_its_buys_are_refused_with_the_reason(tmp_path):
    """The boundary whose mark latches the hold: its sells run, its buys are refused with the reason,
    and its own `exec-<HH>.json` reads `reduce_only` with `daily_loss_hold` — the draft's terminal
    re-journal, not the next boundary's first act."""
    ...
def test_the_series_file_is_written_once_at_the_first_mark_and_never_rewritten(tmp_path): ...
```

- [ ] **Step 2: Run the tests and read the failure** — `-k 'equity or high_water or day_loss or series_file or latched_yesterday'`; Expected: the record's `equity_eur` reads `None`.
- [ ] **Step 3: The mark, the series file, the two trips, the fold's arm**
- [ ] **Step 4: Run the tests** — `uv run pytest tests/test_engine_executor.py -q -p no:cacheprovider`; Expected: no failure.
- [ ] **Step 5: The consumers** — `uv run pytest tests/test_engine_accumledger.py tests/test_engine_metrics.py -q -p no:cacheprovider`.
- [ ] **Step 6: The commit gate**
- [ ] **Step 7: Commit** — `feat(engine): the drawdown kill switch and the daily-loss hold -- equity marked at the cycle's closes against a dated high-water mark, both re-derived from the record`, with `PROBE_VERDICT` and the trailer.
- [ ] **Step 8: The tree is clean**
- [ ] **Step 9: Prove the guards with one probe per guard, then record their verdicts by a message-only amend** — mutations: equity marked at `book.eur_free` (the resting-bid case trips); the scan's `since` dropped to `datetime.min` (the older-drawdown case trips); the day's base read over the date's records unbounded (the re-mint case latches the hold); the hold stored on a flag the boundary clears (the recovery case lifts); the fold's `daily_loss_hold` arm deleted (the buys run); `on_boundary`'s derivation deleted (the sidecar case's 00Z record reads `reduce_only`); the terminal re-journal deleted (the latching boundary's record reads `full`). Expected: `KILLED (control proven, …)` each.

---

### Task 13: The node states the two polling fields as `None`

**Files:**
- Modify: `cli/engine/node.py` (`_exec_engine_config` gains `open_check_interval_secs=None, position_check_interval_secs=None` beside the six knobs it states, and its docstring gains why: the library's reconciler's events reach the executor flagged `reconciliation=True`, which `_on_order_event` and `_venue_terminal_state` read as a mint, and its own `request_order_status_reports` would race the executor's bare-client reads for the nonce; the engine's three reconciliations — the startup pass, the re-read pass, the boundary read — are the go/no-go's "zero unreconciled states")
- Test: `tests/test_engine_node.py`, `tests/test_nautilus_interface_pin.py`

**What this task decides, where the spec leaves it open:**
- The stand-in test at `tests/test_engine_node.py` line 1301 cannot tell a stated `None` from an inherited one, so the pin is textual: `test_the_engine_config_states_the_two_polling_fields_as_none` reads `inspect.getsource(node._exec_engine_config)` and asserts both `open_check_interval_secs=None` and `position_check_interval_secs=None` appear in the call; `test_nautilus_interface_pin.py::test_the_polling_defaults_we_state_explicitly_are_unchanged` holds the library's defaults at `None` for both, the `inflight` test's shape — so a bump's flip of either is a decision.

- [ ] **Step 1: Write the failing tests** — the two above.
- [ ] **Step 2: Run them and read the failure** — `uv run pytest tests/test_engine_node.py tests/test_nautilus_interface_pin.py -q -p no:cacheprovider -k polling`; Expected: the source read lacks both names.
- [ ] **Step 3: The two keywords and the docstring**
- [ ] **Step 4: Run the tests** — `uv run pytest tests/test_engine_node.py tests/test_nautilus_interface_pin.py -q -p no:cacheprovider`; Expected: no failure; `test_every_exec_engine_default_is_the_one_we_measured` unchanged, since the library's defaults are `None`.
- [ ] **Step 5: The commit gate**
- [ ] **Step 6: Commit** — `feat(engine): the venue discrepancy polls are stated off, with the arithmetic that keeps them so`, with `PROBE_VERDICT` and the trailer.
- [ ] **Step 7: The tree is clean**
- [ ] **Step 8: Prove the guard with one probe, then record its verdict by a message-only amend** — the mutation sets `open_check_interval_secs=60.0`; the control removes the keyword. Expected: `KILLED (control proven, …)`.

---

### Task 14: `accum-replay --floor-shorts` — the band re-derived for the floored book

**Files:**
- Modify: `cli/engine/feeders.py` (`accumulation_payload(stages, minimums, navs, *, floor_shorts=False)`: with the flag each stage's `final` targets are clamped `max(w, 0.0)` per leg before the drift arithmetic, and the payload's header line and `accumulation_report`'s first line say `targets floored at 0 for every shorting leg`)
- Modify: `cli/engine/command.py` (`accum_replay` gains `floor_shorts: bool = typer.Option(False, "--floor-shorts", help="Clamp every negative target to 0 before measuring, the book rung 3 realizes long-only; the p95 it quotes is the band's edge for that book.")`)
- Modify: `README.md` (the `accum-replay` row names the flag)
- Test: `tests/test_engine_feeders.py`, `tests/test_engine_command.py`

- [ ] **Step 1: Write the failing tests** — a stage with one leg at −0.05: with the flag its target reads 0 and the per-cycle drift differs from the unflagged run; a stage with no negative leg is byte-identical in both payloads; the CLI's flag reaches `accumulation_report` (a recording stand-in) and the header line names the flooring; `uv run zcrypto engine accum-replay --help` carries the flag.
- [ ] **Step 2: Run them and read the failure** — `uv run pytest tests/test_engine_feeders.py tests/test_engine_command.py -q -p no:cacheprovider -k floor_shorts`; Expected: `TypeError` on the keyword.
- [ ] **Step 3: The clamp, the flag, the README row**
- [ ] **Step 4: Run the tests** — the two files whole; Expected: no failure.
- [ ] **Step 5: The consumers** — `uv run pytest tests/test_internal_terms_not_operator_visible.py tests/test_engine_tracking.py -q -p no:cacheprovider`.
- [ ] **Step 6: The commit gate**
- [ ] **Step 7: Commit** — `feat(engine): accum-replay --floor-shorts measures the drift floor on the long-only book rung 3 realizes`, with `PROBE_VERDICT` and the trailer.
- [ ] **Step 8: The tree is clean**
- [ ] **Step 9: Prove the guard with one probe, then record its verdict by a message-only amend** — the mutation clamps at `max(w, w)` (no clamp; the negative-leg case reads equal payloads); the control clamps every leg to 0. Expected: `KILLED (control proven, …)`.

---

### Task 15: The venue-divergence rule on the engine's own read failure, its gauge and its `engine.md` section, and the sentences the disarmed rule's rollout re-trues

**Files:**
- Modify: `cli/engine/command.py` (`_ExecGauges` gains `venue_read_failed` — `zcrypto_exec_venue_read_failed`, set in `update` to 1 when `inputs["venue_status"]` is `unreachable` or `unreadable`, the two words `read_system_status` mints for a failed read, else 0 — the rule's input, spec D9)
- Modify: `infra/ansible/roles/capture/files/config.alloy` (the keep regex gains `|zcrypto_exec_venue_read_failed` after Task 4's five: 20 names, 14 at the base, 19 after Task 4)
- Modify: `infra/grafana/engine-dashboard.json` (panel 55, `Venue status — last evaluated reading`, gains a second target `zcrypto_exec_venue_read_failed{host=~"$host"}`, the read failure beside the venue's word, so `test_every_alerted_family_is_charted` and `test_every_published_app_family_is_charted` hold)
- Modify: `infra/grafana/alerts.yaml` (`zcrypto-engine-exec-venue-diverged`; `zcrypto-engine-exec-armed-too-long` stays, and its replacement `zcrypto-engine-exec-disarmed-across-a-boundary` is R3's rules pull request — this branch merges inside rung 2's box, a routine push from `develop` sends the tree's rules whole, and the rule would page on the box's daily disarm; spec D11)
- Modify: `infra/runbooks/engine.md` (the `zcrypto-engine-exec-venue-diverged — ALERT` section, `What you are seeing / What it means / What to do / Retire when`; the armed-too-long section stays until R3's rules pull request replaces it under the new anchor, since `tests/test_runbook_triggers.py` reads an ALERT section with no rule linking it as untriggered; the watchdog's section is Task 4's)
- Modify: `infra/runbooks/drills-order-path.md` (the standing rule "A window that stays armed past six hours pages …" re-trued in a form true before and after R3's rules pull request — the old rule stays in Cloud through the box: it pages until rung 3's entry replaces it with the disarmed-across-a-boundary rule, after which a drill that leaves the engine below `full` across a whole boundary pages, D's hold above all)
- Modify: `infra/runbooks/engine-procedures.md` (arm step 6's sentence "`engine.md#zcrypto-engine-exec-armed-too-long` will page if the window outlives six hours" re-trued the same way; the rung-2 box's "`zcrypto-engine-exec-armed-too-long` stays quiet" sentence, true as written while the box runs on the old rule, gains the rule that replaces it at rung 3's entry, which the box's day-long windows below `full` would reach only across a boundary)
- Modify: `tests/test_infra_alert_rules.py` (`NOT_A_FAULT_SIGNAL` keeps `zcrypto_exec_venue_ok` with its comment re-trued — the divergence is watched through `zcrypto_exec_venue_read_failed`, no longer a deferred alert — and keeps `zcrypto_exec_gate_level` until R3's rules pull request; the venue replay), `tests/test_engine_metrics.py` (the `_ExecGauges` case: `zcrypto_exec_venue_read_failed` 1 on a verdict whose `venue_status` is `unreachable` or `unreadable`, 0 on `online` and on `maintenance`, beside the file's `zcrypto_exec_venue_ok` case), `tests/test_infra_alloy_series.py` (`ENGINE_APP_SERIES` gains the name), `infra/scripts/ops_daily.py` (`_UID_HOST` gains `zcrypto-engine-exec-venue-diverged`), `tests/test_ops_daily.py`

**Interfaces:**
- Consumes: the rule file's shape (`condition`, `data`, `relativeTimeRange`, `__expr__` nodes, `noDataState`, `execErrState`, `for`, `annotations`, `labels`, `notification_settings`); `_rule`, `_duration_seconds`, `_evaluator`; `test_every_runbook_link_in_an_alert_summary_resolves`; `test_every_fault_signal_metric_is_watched_by_a_rule`.
- Produces, for the Rollout: the uid `zcrypto-engine-exec-venue-diverged` and its gauge; the disarmed rule's shape below, which R3's rules pull request lands verbatim, its first sample on the armed engine verified by value before the old uid is pruned.

**What this task decides, where the spec leaves it open:**
- The disarmed rule, verbatim from D11, landed by R3's rules pull request and not here: group `zcrypto-gate`, node A `max_over_time(zcrypto_exec_gate_level{host="zcrypto"}[4h30m])` over `relativeTimeRange {from: 16200, to: 0}`, node B `zcrypto_exec_kill_tripped{host="zcrypto"}`, a math node `C` `$A < 1.5 && $B < 0.5`, the threshold `D` reading `C` at `gt 0`; `noDataState: OK`, `execErrState: Alerting`, `for: 10m`, severity `warning`, receiver `metrics`, `__panelId__: "51"`, the summary naming the causes and the section's reads (never `exec-status` alone, which shows the gate's six reasons and none of the three folded), ending `Runbook: infra/runbooks/engine.md#zcrypto-engine-exec-disarmed-across-a-boundary`. The replay, the rules pull request's: a level series at 2 throughout stays quiet; a level held at 1 (the hold) or 0 (the arm file gone) from a sample on fires at exactly 4h40m after the last `full` sample — the first minute `max_over_time` over `[4h30m]` reads under 1.5, plus `for: 10m` — asserted as the minute and never as "fires"; a 4h15m dip below `full` followed by `full` stays quiet, every 4h30m window carrying a 2; a kill tripped alongside stays quiet (the kill rule pages). That pull request's probes: the window set to `[4h]` — the dip case fires for fifteen minutes and the fire minute moves to 4h10m, each killing it, where a replay asserting "fires" alone survives it, since a level held low fires under both windows; its kill half dropped (the kill-alongside case fires).
- The venue-diverged rule, verbatim from D9, the watchdog rule's shape: node A `zcrypto_exec_venue_read_failed{host="zcrypto"}`, instant, over `relativeTimeRange {from: 600, to: 0}`, the threshold `gt 0.5`; `noDataState: OK` (the gauge is absent until R2's converge and quiet then), `execErrState: Alerting`; `for: 15m`; severity `warning`; `__panelId__: "55"`; the summary naming the engine's REST read of `SystemStatus` as failed — unreachable, or a body it could not read — for fifteen minutes, while the venue's own word is unknown to it, ending `Runbook: infra/runbooks/engine.md#zcrypto-engine-exec-venue-diverged`. The replay: the gauge at 1 for 16 minutes fires; at 1 for 14 minutes does not; a venue-side maintenance of two hours — `zcrypto_exec_venue_ok` 0 and this gauge 0 throughout — does not.
- The sections' reads, this task's and R3's alike: `zcrypto engine exec-status` on the host builds its own gate in a fresh process (`cli/engine/command.py`'s `exec_status`) and shows the gate's six reasons alone — it cannot see `_frozen`, `_reconciliation_refusal` or `_day_loss_hold`; the three folded reasons are read from the boundary's `exec-<HH>.json` on the host (`sudo cat /var/lib/zcrypto-engine/journal/$(date -u +%F)/exec-<HH>.json`, its `reasons`, the folded verdict Task 5 journals and Task 11's terminal re-journals, as of that boundary) — the one read that answers WHICH; in Cloud `zcrypto_exec_gate_level{host="zcrypto"}`, which `_evaluate` publishes folded, shows the level alone (`socket_down` and `reconciliation_unread` both read 0) and `zcrypto_exec_watchdog_frozen` separates the freeze; a section names the record's `reasons` as the read for which, never `exec-status` for the three and never the level gauge for it. The venue section: the cause (the engine's REST read of `SystemStatus` failing while the venue's word is unknown to it — the host's egress, DNS, Kraken's error envelope), the read (`exec-status`'s `venue_status` input at `unreachable` or `unreadable`), the lift (the read answering again, which the gate's next refresh shows; a restart inside a gap only when the process itself is wedged). The disarmed section, R3's: the cause per reason — the arm file (`arm_file_absent`), the hold (`restart_hold`), a rollout (`config_not_armed`), the venue (`venue_not_online`), a bump (`nautilus_unverified`), the freeze (`socket_down`), the startup read (`reconciliation_unread`), the day's loss (`daily_loss_hold`) — the read per reason as above, and the lift (the arm file, the hold's clear after the restart step, a restart inside a gap for the freeze or the unread reconciliation, the re-read pass's return, the next UTC day for the day-loss hold); its `What to do` names the deliberate pause (`engine-rung-3`'s pause step) as silenced for its duration, by the owner's ruling.

- [ ] **Step 1: Load `zcrypto-refine-rules`** and read its *Before you write guidance*.
- [ ] **Step 2: Write the failing tests** — the venue replay, the gauge case, the keep-list case, the uid and field cases (`test_every_rule_has_the_fields_the_api_requires` covers the shape).
- [ ] **Step 3: Run them and read the failure** — `uv run pytest tests/test_infra_alert_rules.py tests/test_engine_metrics.py tests/test_infra_alloy_series.py -q -p no:cacheprovider`; Expected: the replay fails on `StopIteration` from `_rule`, the gauge case on the missing sample, the keep-list case on one unadmitted name.
- [ ] **Step 4: The gauge, the regex, the panel's target, the rule, the section (after loading `zcrypto-refine-rules`), the four re-trued sentences, the comments, the `_UID_HOST` entry**
- [ ] **Step 5: Run the tests** — `uv run pytest tests/test_infra_alert_rules.py tests/test_engine_metrics.py tests/test_dashboards_cover_metrics.py tests/test_internal_terms_not_operator_visible.py tests/test_runbook_internal_tokens.py tests/test_runbook_triggers.py tests/test_infra_alloy_series.py tests/test_ops_daily.py -q -p no:cacheprovider`; Expected: no failure.
- [ ] **Step 6: The consumers** — `grep -rn 'armed-too-long\|armed_too_long' tests/ infra/ docs/ .claude/ cli/`; every remaining hit is a historical record (`docs/open-topics/T0018-*.md`, Task 18's; `docs/reference/drill-log.md` entries), R3's rules pull request's (`infra/grafana/alerts.yaml`'s rule, `infra/runbooks/engine.md`'s section, `infra/scripts/ops_daily.py`'s `_UID_HOST` entry, `tests/test_infra_alert_rules.py`'s hit at line 400, the comment naming the two paging rules — its lines 380-381, which this grep does not hit, are the sentence that PR re-trues when `armed` leaves the watched set — and `tests/test_infra_alloy_series.py`'s at line 78), Task 17's (`infra/runbooks/engine-procedures.md`'s tracking-band standing condition, line 672) or re-trued here.
- [ ] **Step 7: The commit gate**
- [ ] **Step 8: Commit** — `feat(grafana): the venue-divergence rule on the engine's own read failure, its gauge and runbook section, and the sentences rung 3's disarmed rule re-trues`, with `PROBE_VERDICT` and the trailer.
- [ ] **Step 9: The tree is clean**
- [ ] **Step 10: Prove the guards with one probe per guard, then record their verdicts by a message-only amend** — mutations: the venue rule's evaluator flipped to `lt` (the read-failure case reads quiet); its `for` set to `30m` (the 16-minute case reads quiet); the gauge set from `venue_ok`'s condition, `!= "online"` (the `maintenance` case reads 1); one name dropped from the keep regex. The disarmed rule's probes are R3's rules pull request's. Expected: `KILLED (control proven, …)` each.

---

### Task 16: The engine role renders `exec_armed` from the tree's own fact, the band line, and the backstop reads that fact

**Files:**
- Modify: `infra/ansible/roles/engine/tasks/main.yml` (the backstop's first `set_fact` reads `engine_host_vars_text: "{{ lookup('file', playbook_dir ~ '/host_vars/' ~ inventory_hostname ~ '/vars.yml') }}"` in place of the template text; the derive task gains `engine_exec_armed_in_tree: "{{ (engine_host_vars_text | regex_search('(?m)^engine_exec_armed: *true *$')) is not none }}"` and `engine_exec_armed_declared: "{{ (engine_host_vars_text | regex_search('(?m)^engine_exec_armed:')) is not none }}"`; the assert's first disjunct becomes `(not (engine_exec_armed_declared | bool) or (engine_host_vars_text | regex_search('(?m)^engine_exec_armed: *false *$')) is not none)` — a converge counts as DISARMED only when the key is absent or the literal `false`, and any other form counts as ARMED and must clear the gate; the override echo's `when` mirrors it; a second conjunct closes the variable namespace — `(engine_exec_armed_in_tree | bool) == ((lookup('file', playbook_dir ~ '/host_vars/' ~ inventory_hostname ~ '/vars.yml') | regex_search('(?m)^engine_exec_armed: *true *$')) is not none)`, the regex recomputed from the lookup inside the assert itself, so an extra var outranking either of the two `set_fact` names the render's fact depends on (`-e engine_exec_armed_in_tree=true`, `-e engine_host_vars_text=…`: Ansible ranks `-e` above `set_fact`, and a `set_fact` to a name an extra var holds is ignored) fails the converge before the render, the `fail_msg` naming the disagreement; the third name, `-e engine_exec_armed_declared=false`, is not closed and is an explicit drop — on an armed file with the pin unverified the first item's `not (engine_exec_armed_declared | bool)` reads true on the injected value, the second item compares the fact to the file and both read `true`, and the converge renders `exec_armed = true` past the pin gate — a line only a deliberate hand types, `arming_override` being the bypass the role already admits; `tests/test_infra_converge_guards.py` pins the assert's regex literal equal to the derive task's; the comment block above the backstop rewritten for the file it now reads and why — the template and the assert read one fact set from the host's `vars.yml` in the tree, never the variable namespace an extra var reaches)
- Modify: `infra/ansible/roles/engine/templates/zcrypto.toml.j2` (`exec_armed = {{ engine_exec_armed_in_tree | lower }}` with its comment re-trued: rendered from the fact the arming backstop derives from this host's `vars.yml` in the tree, `true` only on the literal line `engine_exec_armed: true` there, which the arm PR commits; and `{% if engine_tracking_band_bps is defined %}tracking_band_bps = {{ engine_tracking_band_bps }}{% endif %}` after `settle_delay_secs`)
- Modify: `infra/ansible/roles/engine/defaults/main.yml` (no `engine_exec_armed` default, stated in a comment beside the `[zcrypto.engine]` knobs: the value is derived from the host's `vars.yml`, so no default and no `-e` reaches it; `engine_exec_max_plan_notional_eur: 100.0` stays, the arm PR's host var overriding it)
- Test: `tests/test_infra_converge_guards.py` (the arming cases re-parametrised over host-vars text), `tests/test_config.py` (the template render context gains `engine_exec_armed_in_tree`; a case that renders the band line when `engine_tracking_band_bps` is set and omits it otherwise; the literal pin `exec_armed = {{ engine_exec_armed_in_tree | lower }}`)

**Interfaces:**
- Consumes: the `load_tasks`, `find_task`, `assert_that`, `set_facts`, `when_conditions`, `truthy` helpers of `tests/test_infra_converge_guards.py`; `test_arming_backstop_reads_the_real_committed_files`; the engine play's render task `render the engine zcrypto.toml`.
- Produces, for the Rollout's arm PR by these exact names in `infra/ansible/host_vars/zcrypto/vars.yml`: `engine_exec_armed: true`, `engine_exec_max_plan_notional_eur: 1000.0`, `engine_tracking_band_bps: <the band>`.

**What this task decides, where the spec leaves it open:**
- Two facts, not one: the render reads `engine_exec_armed_in_tree`, true on the literal `true` alone, so a templated or garbled value renders `false`; the backstop reads the key's presence and refuses any form but the literal `false` unless the pin is recorded — fail-closed in both directions. `-e engine_exec_armed=true` reaches neither, since both read the file; and the fact's own name is closed — `-e engine_exec_armed_in_tree=true` outranks the `set_fact`, so the assert's second conjunct recomputes the render's fact from the lookup and refuses a converge whose fact disagrees with the file.
- `DISARMED_HOST_VARS` is the file with no key and with `engine_exec_armed: false`; `ARMED_HOST_VARS` is `engine_exec_armed: true`; `TEMPLATED_ARMED_HOST_VARS` is `engine_exec_armed: "{{ x }}"`, which the backstop counts as ARMED and the render reads `false` — both asserted. `test_arming_backstop_reads_the_real_committed_files` reads the real `host_vars/zcrypto/vars.yml` through the real derive task: at this plan's base it derives `False` and the assert passes on the real pyproject and record; with `engine_exec_armed: true` substituted into the text it passes only because the real pin is recorded — asserted after `pin in versions`. `test_an_extra_var_on_the_facts_name_fails_the_backstop`: the assert evaluated with `engine_exec_armed_in_tree=True` bound ahead of the derive task over `DISARMED_HOST_VARS` (the lookup stubbed to that text) fails on the second conjunct, and with the fact derived it passes.
- The template render in `tests/test_config.py` passes `engine_exec_armed_in_tree=False` in its context, and one case `True`, reading `exec_armed = true` back through `load_config`.

- [ ] **Step 1: Write the failing tests**
- [ ] **Step 2: Run them and read the failure** — `uv run pytest tests/test_infra_converge_guards.py tests/test_config.py -q -p no:cacheprovider -k 'arming or template'`; Expected: the host-vars cases fail on the derive task lacking the fact.
- [ ] **Step 3: The tasks, the template, the defaults' comment**
- [ ] **Step 4: Run the tests** — the two files whole; Expected: no failure.
- [ ] **Step 5: The consumers** — `grep -rl 'zcrypto.toml.j2\|engine_exec_armed\|exec_armed = ' tests/ infra/ .claude/ docs/open-topics/ | sort`; run every test file it names, `tests/test_internal_terms_not_operator_visible.py` (the Ansible task names) and `tests/test_infra_shell_templates_render.py` among them; `uv run ansible-lint infra/ansible/roles/engine` through the commit gate.
- [ ] **Step 6: The commit gate**
- [ ] **Step 7: Commit** — `feat(infra): the engine renders exec_armed from the host's vars.yml in the tree and the arming backstop reads the same fact; the tracking band renders when set`, with `PROBE_VERDICT` and the trailer.
- [ ] **Step 8: The tree is clean**
- [ ] **Step 9: Prove the guards with one probe per guard, then record their verdicts by a message-only amend** — mutations: the backstop's disjunct reading `engine_exec_armed_in_tree` alone (the templated case passes the gate); the lookup's path moved to `role_path ~ '/defaults/main.yml'`; the render reading `engine_exec_armed | default(false)` from the namespace (the extra-var case renders `true`); the band line unconditional; the assert's second conjunct deleted (the injected-fact case passes the gate). Expected: `KILLED (control proven, …)` each.

---

### Task 17: The operating surface — `engine-rung-3`, the drills' rung-3 forms and drill H, the re-trued sentences

**Files:**
- Modify: `infra/runbooks/engine-procedures.md` (`engine-rung-3 — PROCEDURE` after `engine-rung-2-box`, anchors `engine-rung-3`, `rung-3-entry`, `rung-3-the-daily-read`, `rung-3-after-a-restart`, `rung-3-pause`, `rung-3-the-weekly-read`, `rung-3-hand-act`, `rung-3-drawdown-reset`, `rung-3-go-no-go`; `engine-probe-window`'s `Retire when` re-trued: `PLAN_FILENAME` pickup survives for the drills' plans, so the procedure retires when no drill places a plan file through its steps, checked with `grep -c 'probe-plan' infra/runbooks/engine-procedures.md infra/runbooks/drills-order-path.md` reading 0 on both — today 15 and 0: the drills link to this procedure's placement steps and never spell the file name, so a check on the drills page alone is satisfied before its condition is; `engine-tracking-band`'s precondition 3 re-trued: the template renders `tracking_band_bps` from `engine_tracking_band_bps` in the host's `vars.yml`, the arm PR's line; its standing condition on the armed-too-long alert (line 672) re-trued in a form true before and after R3's rules pull request: the rule rung 3's entry replaces it with, the disarmed-across-a-boundary rule, pages a boundary below `full`)
- Modify: `infra/runbooks/drills-order-path.md` (the standing rule "Every drill here runs inside an attended probe window" gains rung 3's first attended week as the other sanctioned frame; a `### Rung-3 form` paragraph in E, G, F2, D and B; the new `## Drill H — the disarmed boundary — PROCEDURE` under `drill-h`, seven parts)
- Test: none new; `tests/test_internal_terms_not_operator_visible.py`, `tests/test_runbook_internal_tokens.py`, `tests/test_runbook_triggers.py`, `tests/test_infra_alert_rules.py`'s anchor cases walk both pages.

**What this task decides, where the spec leaves it open:**
- `engine-rung-3`'s steps, each with the commands and their expected reads, built from the rung-2 procedure's step text where the act is the same: entry (D15's gate as the Rollout's R0 lists it, the arm PR, the converge's boot reads, the hold's clear, the arm file at `sudo touch /var/lib/zcrypto-engine/exec/armed` before the Monday 00Z boundary, the gate read `level=full`, the equity series file — written by the loop at R2's first boundary, the book flat and the EUR the sleeve's from then on, so nothing re-mints it at entry — read back `sudo cat /var/lib/zcrypto-engine/exec/equity-series-start` as that boundary's `cycle_ts`); the daily read (the newest `accum-<HH>.json` by value — `sudo cat /var/lib/zcrypto-engine/journal/$(date -u +%F)/accum-$(printf %02d $(( $(date -u +%-H) / 4 * 4 ))).json` — the board's accumulation row, the ledger read over the day's six records with the rung-2 window's `HOURS` read, the record's `cache_net` column against `held_qty`); a restart (rung-2 step 5's items 1 to 3, 6 and 7 — the clear is item 7; items 4 and 5 describe the stored account Task 8 retires — the boot's `cache restore` lines read at Kraken's quantity with no `EXTERNAL` line on the new pin, the hold's reduce-only boundary running its sells and refusing its buys, the hold cleared after the reads); a pause (the arm file removed, the disarmed rule silenced in Grafana for the pause's span, resumed on the owner's word by re-placing the file); the weekly read (`uv run zcrypto engine tracking-report --journal-dir <pulled journal> --since <entry Monday> --gate-from <the first ISO week under continuous arming>`, the ledger export reconciled, an unmatched row a finding); the hand act (no stop: the next boundary drafts against it, the record's `cache_net` column names the leg, the reconciliation names the row; a deposit or withdrawal is taken paused and re-mints the series file by hand: `sudo rm` then the loop writes it at the next boundary); the drawdown trip's reset (the post-mortem recorded, the series re-minted, the kill file removed last); the go/no-go read (`00091` D7's, over three complete ISO weeks inside the band, zero unreconciled states, the drills passed).
- The rung-3 forms, from spec D16, each a paragraph naming what differs from the drill's probe-window form and the reads: E — the kill file placed while a cycle intent rests revokes it within a tick, the next boundary's plan is refused with `kill_switch` on every intent and the record reads `refused`; G — a restart inside a gap with the book held, the boot lines at Kraken's quantity with no `EXTERNAL` line, the hold's boundary running sells and refusing buys, the hold cleared; F2 — the container cut from its network while an intent rests, the watchdog's cancel inside 35 s with `socket_down` as its reason (the CRITICAL naming the endpoint and the grace, the cancel in the log), the row ending `ambiguous` on the minted terminal or at `_ACK_WAIT` — the cut's own terminal, spec D7; `revoked` with `socket_down` is the partial cut's, the data socket alone — `zcrypto_exec_watchdog_frozen` 1, the re-read pass's re-cancel on the return, the freeze lifting, the `CONNECTED` string of the execution socket read in the log; D — the exposure page with the full book; B — decision-to-flat with a EUR 1,000 book. Drill H: *What this proves* — a disarmed boundary carries its legs and pages; *Preconditions* — rung 3 armed, no plan running, the disarmed rule quiet by value; *Induce* — `sudo rm /var/lib/zcrypto-engine/exec/armed` at least 10 minutes before a boundary; *Must fire* — the boundary's plan `accepted` in `exec-<HH>.json` with every intent `refused` under `arm_file_absent` (`_accept_plan` judges no level), `accum-<HH>.json` `status: ok` with the plan's id and its legs `placed`, `zcrypto-engine-exec-disarmed-across-a-boundary` at about 4h40m after the file's removal (4h30m window from the last `full` sample + `for: 10m`, each group at 60 s), about 4h30m from the boundary when the removal was 10 minutes before it; *Operator action* — `sudo touch` the file after the page, the next boundary drafts the legs again as its own `target − held`; *Record* — the page's `activeAt` and Slack time; *Retire when* — the rule leaves `alerts.yaml`.

- [ ] **Step 1: Load `zcrypto-refine-rules`** and read its *Before you write guidance*.
- [ ] **Step 2: The procedure, the forms, drill H, the four re-trued sentences**
- [ ] **Step 3: The consumers** — `uv run pytest tests/test_internal_terms_not_operator_visible.py tests/test_runbook_internal_tokens.py tests/test_runbook_triggers.py tests/test_infra_alert_rules.py tests/test_guidance_guard.py tests/test_guidance_refs_resolve.py tests/test_count_list.py tests/test_drill_log.py -q -p no:cacheprovider`; Expected: no failure.
- [ ] **Step 4: The commit gate** (`mdformat` leaves the runbooks alone or rewrites; re-stage).
- [ ] **Step 5: Commit** — `docs(runbooks): the rung-3 procedure, the drills' rung-3 forms and the disarmed-boundary drill`, with the trailer; no guard changes, so no probe.
- [ ] **Step 6: The tree is clean**

---

### Task 18: The topics and the decisions log

**Files:**
- Modify: `docs/open-topics/T0119-delta-formula-target-minus-held.md` → `resolved`, `git mv` to `docs/open-topics/archive/` (a `## Resolution` naming `_draft_cycle_plan` in `cli/engine/executor.py` as the formula's site, `accum-<HH>.json` as the gap series per asset per cycle, `zcrypto_exec_gap_eur` as its gauge, and the tests of Task 11; `ripe_when` deleted)
- Modify: `docs/open-topics/T0120-live-order-config-gaps.md` → stays `partial` (`## Done so far` gains Task 13's statement of both intervals as `None` and the arithmetic; `## Suggested next steps` keeps its S9 arm alone; `ripe_when` re-pointed at the box's exit report carrying S9, on which it resolves — in the exit report's pull request, or R6's — since S9 is read after this task runs)
- Modify: `docs/open-topics/T0216-the-position-gauge-lags-a-hand-act-until-the-next-venue-read.md` → `partial` (`## Done so far`: Task 7's read on each unmatched external fill; `## Suggested next steps` trimmed to the measured span, S4, and rung 3's own first hand act; `ripe_when` re-pointed at rung 2's exit report carrying S4, or the first hand act under rung 3)
- Modify: `docs/open-topics/T0018-phase6-build-sequence.md` (the spec table's `00092` row → `landed (iter-<N>)`, deployment state owed to the Rollout; `## Done so far` gains the iteration's paragraph; the deferral bullets discharged here rewritten as what landed — the armed-too-long replacement, the venue-divergence alert, the drawdown trips, the same-symbol false fire, [[T0120]]'s intervals — and the `00092` deferrals list under "The deferrals `00090` itself carries forward" rewritten; the reconciliation-clearing bullet stays owed, re-pointed; the `[iter-173]` bullet on the deferred engine changes names which three landed here and which two the November bump carries; the next-steps row on the per-instrument `InstrumentStatus` consultation rewritten as landed (spec D17, Task 11's `read_instrument_statuses`); a row for shorts and the long-to-short flip rule, the class-C change spec D5 names, with D5's three preconditions as its *Waits on*, so the spec's Out-of-scope bullet has a registered holder; `ripe_when` re-pointed at rung 3's entry)
- Modify: `docs/open-topics/README.md` (re-rendered by `uv run python infra/scripts/topics-index.py`)
- Modify: `docs/research/14.phase6-decisions.md` (the `[iter-<N>]` entries: the ten rulings of 2026-10-05 on the spec — the nine open questions and D17's, the consultation `00090` deferred — each with the spec's recommendation and rejected alternatives as its options and `(Decision: 1)`, and the four of the same day on the plan — the `[iter-173]` ordering constraint held by the disarmed interval with Task 8 in this plan, the fixtures synthesized at invented quantities, the rules pushed on the entry's Sunday after the arm file, R2's shape with the bake's necessity read at rollout time; the three accepted mechanisms; the stored-account items' move into D4 with the ordering constraint's reading)

**What this task decides, where the spec leaves it open:**
- `<N>` is the iteration serial minted when the implementation branch is cut, the change index's highest plus one; the plan names it nowhere else.
- T0216 stays `partial`: D12's mechanism landed; the measure is S4's, which only a hand act supplies.
- The memo is `zcrypto-marco`'s: a queue change this task needs is reported to the orchestrator, never written here.

- [ ] **Step 1: Load `topic-ops` and `iteration-closeout`**, then the four topic edits by their mechanics (anchor on a string verified unique, compare the heading set before and after, `git mv` then `git add` the archived path).
- [ ] **Step 2: The decisions-log entries**, in the skill's entry format, appended under the last `[iter-173]` entry.
- [ ] **Step 3: Re-render the index** — `uv run python infra/scripts/topics-index.py`.
- [ ] **Step 4: The consumers** — `uv run pytest tests/test_open_topics_frontmatter.py tests/test_topics_index.py tests/test_decisions_log_shape.py tests/test_internal_terms_not_operator_visible.py -q -p no:cacheprovider`; Expected: no failure.
- [ ] **Step 5: The commit gate**
- [ ] **Step 6: Commit** — `docs(topics): rung-3 accumulation -- T0119 and T0120 resolve, T0216 partial, T0018's rows and deferrals re-trued, the rulings of 2026-10-05 recorded`, with the trailer.
- [ ] **Step 7: The tree is clean**

---

### Task 19: The whole-branch sweep

**Files:** none modified (a fix found here lands as its own typed commit with its own targeted run, and the sweep re-runs after it).

- [ ] **Step 1: Every probe verdict re-read** — `git log develop..HEAD --format='%h %s%n%b' | grep -c 'mutate-probe: KILLED'` against the count of guard-changing commits; a commit whose message still carries `PROBE_VERDICT` is a stop.
- [ ] **Step 2: The operator-facing read** — `uv run pytest tests/test_internal_terms_not_operator_visible.py -q`, then a read of every new operator-visible string (the six families' HELP, `--floor-shorts`' help, the panel titles and descriptions, the two rule summaries, the runbook sections, the Ansible task names) for internal tokens the test's literals do not catch.
- [ ] **Step 3: The full suite, foreground** — `uv run pytest -q -p no:cacheprovider`; Expected: green, the skip count read and not read as coverage; the data-gated family runs on the checkout holding the datasets before the first push (`open-pr`'s rule).
- [ ] **Step 4: The gate** — `uv run pre-commit run -a` clean; `infra/scripts/count-list.sh probe-verdicts-without-the-script` reads 0 over the branch; `infra/scripts/count-list.sh operator-term-surfaces` unchanged.

Then the pull request opens through the `open-pr` skill over the whole branch, a different agent reads it, and `merge-pr` merges it; the Rollout follows from merged `develop`, after the week-of-2026-11-02 engine rollout.

---

## Rollout (attended)

**Operator steps (attended).** Nothing below is an executor step: each reaches a fleet host, the venue, Grafana Cloud, the observability node, Slack or healthchecks.io, or moves money. Every converge goes through `infra/ansible/scripts/converge.sh` from merged `develop`, which previews, asks for the typed `--limit` and appends its line to `docs/reference/deploy-log.jsonl`; it is never wrapped in `timeout`. `W$` is the workstation at the repository root, `H$` a shell on `zcrypto` (`ssh zcrypto`), `R$` one on `zcrypto-red`. `KRAKEN` is the whole-feed read, `curl -fsS https://status.kraken.com/api/v2/scheduled-maintenances.json | jq .`, read entire and judged by `.claude/rules/fleet-deploys.md`'s test, at planning and again immediately before each converge of `zcrypto-red` and `zcrypto`. `GAP` is the engine's inter-cycle gap as `site.yml` computes it from the boundary cycle's journalled completion, read with `engine-adhoc-key-read` step 3's read, never from a clock. The running digests are read off the containers immediately before — `docker inspect <name> --format '{{.Config.Image}}'`, never `.Image` — and matched against `docs/reference/fleet-pins.md`. Nothing here runs inside rung 2's box, and nothing here runs before R0's six reads each pass.

**R0. The gate — six reads, each a stop (spec D15).** (1) The November rollout's pin: `W$ uv run pytest tests/test_cache_restart.py -k test_a_restored_spot_lot -q -p no:cacheprovider` on the checkout at that pin reads red at the restore assertion whose message opens `no longer books an EXTERNAL short equal to the lot beside the strategy's long`, and not only at its last three; and that pin's attended pass record under `docs/reference/adapter-verification/<version>.md` carries the live read, one spot lot held across an engine restart restored at Kraken's quantity with no `EXTERNAL` line: [[ROLLOUT: the November rollout's engine digest and nautilus build, whether its history carries #5181's fix, and its attended pass's record — S11, D15's first read]]. (2) Rung 2's exit report is recorded in `docs/research/14.phase6-decisions.md` with S1 to S12 filled; S2 and S3 against D3's window and box, S9's p95 against the band below. (3) The two `[iter-173]` items the November bump carries are read as deployed on that rollout's record; D4's three ride this one, and the list's ordering constraint — the bump never deploying ahead of the balance-reading sell check — is held by the disarmed interval between that rollout and this one, in which no sell runs: the owner's ruling of 2026-10-05 on the plan (spec D15 item 3), a decision this read records and never re-opens. (4) `W$ uv run python infra/scripts/grafana-query.py 'zcrypto_engine_limit_bound_total{host="zcrypto"}'` and `'zcrypto_engine_active_sleeves{host="zcrypto"}'` each a number. (5) The refdata sweep inside the week of entry, `zcrypto-refdata-sweep`'s verdict read from the rendered tables. (6) The band: `W$ uv run zcrypto engine accum-replay --journal-dir <the pulled journal> --since 2026-10-05 --until <the box's last day> --nav 1000 --floor-shorts`, its p95 at NAV 1,000 the number: [[ROLLOUT: `tracking_band_bps` — the p95 of the per-cycle drift floor at NAV 1,000 on the floored book over the box's cycles, recorded in the decisions log (G4)]].

**R1. The arm PR.** From `develop`: `infra/ansible/host_vars/zcrypto/vars.yml` gains `engine_exec_armed: true`, `engine_exec_max_plan_notional_eur: 1000.0` and `engine_tracking_band_bps: <R0's band>`; `tests/test_infra_converge_guards.py` and `tests/test_config.py` green; reviewed and merged through `open-pr` and `merge-pr`. Its merge arms nothing: the host renders at its next engine converge, R2.

**R2. The converge — two hosts, the primary inside the gap.** The engine image is the capture image: the branch's merge builds a new digest through the capture-image workflow, pulled on both hosts with `sudo docker pull ghcr.io/zhaow-de/zcrypto-capture@sha256:<new>`, its rows written in `docs/reference/fleet-pins.md` first. `KRAKEN` at planning. `zcrypto-red` first — the secondary's bake, the rollout-image skill's phases 1 and 2: `KRAKEN` immediately before; `W$ infra/ansible/scripts/converge.sh site.yml --limit zcrypto-red -e capture_image_digest=sha256:<new> -e capture_alloy_digest=sha256:<running alloy>`; the preview names the capture compose file and `config.alloy`; the bake window read by the skill's abort signals. Then `zcrypto`, at least an hour later and inside `GAP`: `KRAKEN` immediately before; `W$ infra/ansible/scripts/converge.sh site.yml --limit zcrypto --tags capture,engine -e converge_primary=true -e engine_image_digest=sha256:<new> -e capture_image_digest=sha256:<running on the primary, held> -e capture_alloy_digest=sha256:<running alloy> -e cache_proxy_image_digest=sha256:<running proxy>` — `--tags capture,engine`, since `config.alloy` changed and the keep list lives in the capture role; the primary's capture digest is held at its running value, so live capture is neither re-pinned nor restarted — the shape the owner confirmed on 2026-10-05; whether the secondary's bake is owed at all is read from the merged branch's diff at rollout time under the fleet rule then in force (`.claude/rules/fleet-deploys.md`'s first bullet as it then reads — a change to the engine's bake gate is under the owner's consideration and is not this pair's), and this step runs the bake as that rule orders it; the preview names `/opt/zcrypto-engine/zcrypto.toml` with `exec_armed = true`, `exec_max_plan_notional_eur = 1000.0` and `tracking_band_bps = <band>`, the engine compose file and `config.alloy`, and nothing else. After it: `H$ sudo docker inspect --format '{{.State.StartedAt}}' zcrypto-engine` moved; the boot read of `engine-rung-3`'s restart step (the `cache restore` lines, the WARNING per held leg, no `Unresolved positions`, no `could not be read` CRITICAL); `H$ sudo zcrypto engine exec-status` reads `level=none`, `reasons=arm_file_absent,restart_hold`; the next `cycle-<HH>.json` lands with `completed_at` inside `[B, B+30 min]`, and beside it the first `accum-<HH>.json` reads `status: ok` with `plan_id: "r3-<date>-<HH>"` and its legs `placed` with their `delta_eur` — `_accept_plan` judges no level, so the disarmed boundary's plan is accepted — while `exec-<HH>.json`'s plan entry reads `accepted` with each intent `refused` under `arm_file_absent,restart_hold`, and `exec/equity-series-start` is written with this boundary's `cycle_ts`, the series' start: [[ROLLOUT: R2's first `accum-<HH>.json` beside its `cycle-<HH>.json`, read whole by value]]. `W$ uv run python infra/scripts/grafana-query.py 'zcrypto_exec_watchdog_frozen{host="zcrypto"}'` reads 0 and `'zcrypto_exec_gap_eur{host="zcrypto"}'` ten series after the first boundary, `'zcrypto_exec_boundary_not_drafted{host="zcrypto"}'` 0 after its `ok` record, `(no series)` a stop.

**R3. The entry Sunday — the arm file, then the push, the first sample, the prune.** The attended entry sitting, on the Sunday before R4's Monday 00Z boundary, opened after the Sunday 20Z boundary's `accum-20.json` has landed (so no boundary drafts armed before the entry's) and closed before 00Z; nothing in it is silenced, and the disarmed rule is neither in the tree nor in Cloud before the engine is armed — the owner's ruling of 2026-10-05 on the plan, spec D11: the rules pull request below carries it. In order: Kraken's balance page read for the EUR 1,000 sleeve (G1), no deposit or withdrawal from here while armed: [[ROLLOUT: Kraken's equity at entry (G1) and the series file's instant, R2's first boundary]]. The hold cleared after the restart step's reads: `H$ sudo rm /var/lib/zcrypto-engine/exec/restart-hold`; the gate read `level=none`, `reasons=arm_file_absent`. The arm file: `H$ sudo touch /var/lib/zcrypto-engine/exec/armed`; the gate read `level=full`, `reasons=-`; `W$ uv run python infra/scripts/grafana-query.py 'zcrypto_exec_gate_level{host="zcrypto"}'` reads 2 before the push goes. Then the rules pull request — opened from `develop` after R2, read by a different agent before the sitting, merged on the owner's word here, after the arm file: `infra/grafana/alerts.yaml` (`zcrypto-engine-exec-disarmed-across-a-boundary` in, as Task 15's decision text shapes it; `zcrypto-engine-exec-armed-too-long` out), `infra/runbooks/engine.md` (the disarmed section under its anchor replacing the armed-too-long one, the cause and the read per reason as Task 15 states them), `tests/test_infra_alert_rules.py` (the disarmed replay; `NOT_A_FAULT_SIGNAL`: `zcrypto_exec_gate_level` out, `zcrypto_exec_armed` in with its reason — a standing 1 under continuous arming, the gate level it reduces to being what pages — the comment at line 400 re-trued and the sentence at lines 380-381 re-trued for `armed` leaving the watched set), `tests/test_infra_alloy_series.py` (the comment at line 78), `infra/scripts/ops_daily.py` (`_UID_HOST`: the disarmed uid in, the armed-too-long uid out) and `tests/test_ops_daily.py`; its probes as Task 15 names them, their verdicts in its message; then `git pull` on the checkout that pushes. Then the push, from merged `develop` under the `zcrypto-grafana-push` skill: Step 1's preflight over the four rules — `zcrypto_exec_gate_level{host="zcrypto"}`, `zcrypto_exec_kill_tripped{host="zcrypto"}`, `zcrypto_exec_venue_read_failed{host="zcrypto"}`, `zcrypto_exec_watchdog_frozen{host="zcrypto"}`, `zcrypto_exec_boundary_not_drafted{host="zcrypto"}` each a number; Step 0's invocation, both stacks in the dual period; Step 3's verification by value — the disarmed rule's first sample on the armed engine: `W$ uv run python infra/scripts/grafana-query.py 'max_over_time(zcrypto_exec_gate_level{host="zcrypto"}[4h30m])'` reads 2, over the rule's 1.5, so the condition is false and the rule's state in the rules API reads normal, no silence: [[ROLLOUT: the disarmed rule's first sample by value, on the armed engine, and the instant of the arm file it followed]]; the venue rule's first sample a value, quiet; the watchdog's and the not-drafted rule's first samples 0; the new panels rendering. Then the prune inside the same sitting, `fleet-deploys.md`'s order and before six hours of arming would fire the old rule: `GRAFANA_PRUNE=1` from the same checkout, `zcrypto-engine-exec-armed-too-long` deleted, and `curl` of its uid through the rules API reading 404: [[ROLLOUT: the old uid's 404, with the instant]].

**R4. Entry — a Monday 00Z.** [[ROLLOUT: the entry Monday — the first Monday whose 00Z boundary follows R2, with R3's sitting on its Sunday and the drills' instruments on the host]]. After the 00Z cycle completes: `accum-00.json` reads `status: ok` with `plan_id: r3-<date>-00`, `exec-00.json` reads `level: "full"`, the intents run and terminal inside the window, `exec/equity-series-start` still carrying R2's first boundary's `cycle_ts` (the series' start; nothing re-mints it at entry); `zcrypto_exec_equity_eur` a number in Cloud: [[ROLLOUT: the first armed boundary — `exec-00.json`'s level, `accum-00.json`'s plan and legs, the equity mark]].

**R5. The first attended week.** The daily read each day (`engine-rung-3`'s step); the drills in rung-3 form, each inside the week, one at a time, reverted and verified by value before the next, each an entry in `docs/reference/drill-log.md` opening its *host* clause with `` `zcrypto`, the engine ``: E, G, F2, D, B and H. Readings: [[ROLLOUT: F2's rung-3 reading — the cancel's time from the cut against 35 s and the row's `ambiguous` terminal, the execution socket's `CONNECTED` string, the freeze's lift]]; [[ROLLOUT: drill H's page — the disarmed rule's `activeAt` against ≈4h40m from the arm file's removal, and the legs drafted again at the next boundary]]; [[ROLLOUT: the unmatched-external baseline on the new pin — pre-probe step 4's read at one clean restart, S8's rung-3 reading]].

**R6. The records pull request.** From `develop`: the deploy-log rows R2 appended; `docs/reference/fleet-pins.md`'s engine and capture rows re-trued from those rows, `since` the containers' `.State.StartedAt`; the six drill-log entries; `docs/reference/fleet.md` where a label moved; the spec's measured basis amended with R2's series count in Cloud and R4's first readings; T0018's `00092` row's deployment state and T0216's `ripe_when` if a hand act happened; `infra/scripts/count-list.sh canary-bypasses-on-the-primary`, `un-tagged-primary-runs`, `engine-rows-outside-the-gap`, `converges-inside-a-kraken-window` and `pins-not-yet-converged` each at their expected value over the rows added. The commit `chore(fleet): rung-3 accumulation rolled out and entered`, its message carrying every slot's reading, with the trailer.

**R7. The weekly reads and the go/no-go.** Each Monday after a complete ISO week — the first scored week the second complete one, since the first holds the series' first fill (R4's Monday 00Z) and D16's drills, each a refusal of `_score_closed_week`'s (spec D15): `W$ uv run zcrypto engine tracking-report --journal-dir <pulled journal> --since <entry Monday> --gate-from <the first ISO week under continuous arming>` with the ledger export reconciled; the three complete weeks inside the band, counted from it, zero unreconciled states (the three reconciliations' journal, `accum-*.json`'s cross-check column), the drills passed — §12's human decision: [[ROLLOUT: the three ISO weeks' verdicts and the go/no-go]].

## Coverage self-check (spec → task)

D1 → T10, T11; D2 → T2, T11; D3 → T1, T11; D4 → T8, T11; D5 → T1 (`max(weight, 0.0)` kept), T14; D6 → T5, T16; D7 → T9; D8 → T12; D9 → T15; D10 → T13; D11 → T15 (the rule's shape, the sections' reads), R3 (the rules pull request); D12 → T7; D13 → T6; D14 → T3, T4, T11 (the gauges' values and the not-drafted state); D15 → R0; D16 → T17, R5; D17 → T11. Every `## Verification` bullet of the spec: the probes are each task's Step 9 or 10; rung 2's own day is T11's first two tests; the in-process plan's four shapes are T11; the loopback reads are T2 and T11's status read; the venue rule's replay is T15, the watchdog's and the not-drafted rule's T4 and the disarmed rule's R3's rules pull request; the `accum-` immunity is T3; deploy verification by value is R2 to R4.

## Slots the rollout fills

- `[[ROLLOUT: the November rollout's engine digest and nautilus build, whether its history carries #5181's fix, and its attended pass's record — S11, D15's first read]]` (R0) — read before anything else.
- `[[ROLLOUT: `tracking_band_bps` — the p95 of the per-cycle drift floor at NAV 1,000 on the floored book over the box's cycles, recorded in the decisions log (G4)]]` (R0, R1) — the arm PR's line.
- `[[ROLLOUT: R2's first `accum-<HH>.json` beside its `cycle-<HH>.json`, read whole by value]]` (R2) — the record's first live reading.
- `[[ROLLOUT: Kraken's equity at entry (G1) and the series file's instant, R2's first boundary]]` (R3) — the series' start.
- `[[ROLLOUT: the disarmed rule's first sample by value, on the armed engine, and the instant of the arm file it followed]]` (R3) — the prune's precondition.
- `[[ROLLOUT: the old uid's 404, with the instant]]` (R3) — the prune's proof.
- `[[ROLLOUT: the entry Monday — the first Monday whose 00Z boundary follows R2, with R3's sitting on its Sunday and the drills' instruments on the host]]` (R4) — the rung's date.
- `[[ROLLOUT: the first armed boundary — `exec-00.json`'s level, `accum-00.json`'s plan and legs, the equity mark]]` (R4) — the loop's first reading.
- `[[ROLLOUT: F2's rung-3 reading — the cancel's time from the cut against 35 s and the row's `ambiguous` terminal, the execution socket's `CONNECTED` string, the freeze's lift]]` (R5) — the watchdog's live reading.
- `[[ROLLOUT: drill H's page — the disarmed rule's `activeAt` against ≈4h40m from the arm file's removal, and the legs drafted again at the next boundary]]` (R5) — the rule's live reading.
- `[[ROLLOUT: the unmatched-external baseline on the new pin — pre-probe step 4's read at one clean restart, S8's rung-3 reading]]` (R5) — the version's record.
- `[[ROLLOUT: the three ISO weeks' verdicts and the go/no-go]]` (R7) — §12's decision.
