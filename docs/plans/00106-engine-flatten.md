# `zcrypto engine flatten` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the red button — one host command that, with the engine's kill file written first and the engine stopped, cancels every resting order account-wide, closes every margin position with a reduce-only market order, sells every non-EUR spot balance at market, journals every request and answer, and exits with a code that distinguishes flat from partial from could-not-reach-the-venue.

**Architecture:** One new module `cli/engine/flatten.py` holds the whole sweep — the defensive read layer over the Kraken adapter's HTTP client, leg enumeration, sizing, the confirm, the write sequence, the exit-code derivation and the journal artifact. `cli/engine/command.py` gains a thin `flatten` sub-command that reads credentials, builds the client and returns the module's exit code. A host wrapper rendered by the engine Ansible role writes the kill file, stops the unit and runs the command as a one-off container from the digest the engine itself runs. Nothing in the engine's own order machine is touched or reused: the button must work when that machine is what broke.

**Tech Stack:** Python 3.14, Typer, `nautilus_trader` 2.0.0rc4.dev20260825's `KrakenSpotHttpClient`, pytest + Typer `CliRunner`, Jinja2 (wrapper render tests), POSIX sh (the wrapper), Ansible (the engine role).

**Spec:** `docs/specs/00106-engine-flatten-design.md` — read it in full before Task 1. It is binding; where this plan and the spec disagree, the spec wins and the disagreement is a finding to report.

> **Executed and closed — do not implement from a code fence here.** Fences written before the adapter's real shape was measured show the pre-correction world: `_Book` carrying *attributes* `bids`/`asks`, and a synchronous `read_book_price(...)`. On the adapter both are the other way round — `bids()`/`asks()` are methods and every read is awaited. `cli/engine/flatten.py` and `tests/test_engine_flatten.py` are what shipped; read those.

______________________________________________________________________

## Global Constraints

Every task's requirements implicitly include this section. Read all of it — task texts do not repeat it.

### Where the work happens

- Cut the implementation branch from `develop`. This plan itself lands on its own docs branch; do not implement on that branch.
- One branch, one PR into `develop`, for the whole of this plan (`.claude/rules/branch-workflow.md`: one nameable component). Do not open the PR until every task is done and the user says so.
- **Review floor is Fable for every commit on this branch** — this is the live trade path (`.claude/rules/spec-plan-locations.md`). The reviewer is a different agent from the author; `Reviewed-by: <actual reviewer model> <noreply@anthropic.com>` is amended in the same turn the review returns.
- Commit trailers: `Co-Authored-By: <the actual authoring model> <noreply@anthropic.com>` first, `Reviewed-by:` last, no blank line between. **Never add a `Claude-Session:` trailer — it is banned in this repo.**
- The commit gate is `uv run pre-commit run -a`, run to green, re-staging everything the hooks rewrite. Never `--no-verify`.
- **The literal Python in the code fences below is not ruff-format-clean**: the first gate run rewrites a handful of lines (wrapping, and one parenthesised string that collapses). Re-stage the rewrite; never hand-fight the formatter, and if a rewrite moves a line one of the mutation-probe `sed`s targets, fix the `sed` to match the formatted line — Task 12 Step 3 rules which side to correct.
- Stage by explicit path, one commit-type's file kind per commit. Never `git add -A`.

### Vocabulary and hygiene rules the tests enforce

- **No internal traceability vocabulary on operator-visible surfaces**: `Phase <N>`, `T<NNNN>`, `iter-<N>`, `spec <NNNNN>`, `WP<N>`. `tests/test_internal_terms_not_operator_visible.py` scans, among others, every non-docstring Python string literal under `cli/` (so `help=` text, `typer.echo` text and every raised message), and every non-comment line of `infra/**/*.sh` and `infra/**/*.sh.j2`, and every ansible task `name:`/`msg:`/`fail_msg:`. Shell `#` comments and Python docstrings are out of scope — that is where the citations belong.
- **`tests/test_code_prose_citations.py`**: in `cli/`, `tests/` and `infra/` (including `*.md` and `*.j2`), any token matching `task[ -]\d+` must have a 5-digit serial on the same or the immediately preceding line. Simplest compliance: write no plan-task numbers in code, test or runbook prose at all. Cite `spec 00106` and named symbols instead.
- **Code prose** (`.claude/rules/code-prose.md`): state decisions and invariants, never statuses or schedules. Every citation resolves from the repo alone. A test docstring is a claim about the assertions below it.
- Markdown: one line per paragraph/bullet, never hard-wrapped. Escape `|` as `\|` inside a table's code spans.

### Proving a guard

- **`.claude/rules/agent-ops.md`**: a guard is unproven until the defect it names is constructed on a fixture where defect and correct behaviour DIFFER, and seen to trip it. A degenerate fixture proves nothing. The suite also needs a true positive that runs in CI.
- Mutation probes run through `infra/scripts/mutate-probe.sh`, never a hand-rolled loop, on a **clean tree after the commit**. Its exit codes: `2` usage, `3` refused (dirty worktree, or pytest under `--sandbox`), `4` restore failed, `5` control did not fail, `6` no-op sed, `7` baseline failed, `8` seeding failed, `9` cleanup restore failed. A `KILLED` verdict means the probe went red under the mutation; `SURVIVED` means the guard is blind to it. **Do not use `--sandbox` here** — it refuses pytest.
- Assert on what the defect moves, not on the headline.

### Verification scope

- Run the tests the diff can reach: `uv run pytest tests/test_engine_flatten.py tests/test_engine_flatten_wrapper.py tests/test_engine_executor.py tests/test_engine_command.py tests/test_nautilus_interface_pin.py tests/test_cli.py tests/test_cli_help_hygiene.py tests/test_internal_terms_not_operator_visible.py tests/test_code_prose_citations.py tests/test_ops_daily.py tests/test_infra_shell_templates_render.py tests/test_panel_regenerate.py tests/test_infra_alert_rules.py -q`. `tests/test_engine_command.py` is the existing suite over the module Task 9 modifies. The full suite is CI's; do not run it locally.
- `tests/test_infra_shell_templates_render.py` holds a two-way completeness registry over `roles/*/templates/*.sh.j2` **and** renders each one through Ansible's own `Templar` under the role's `defaults/main.yml` plus a fixed `RUNTIME_FACTS` dict. Creating the wrapper template turns two of its tests red until the task that creates it registers the name and adds the engine uid/gid — which the engine role sets by `set_fact` from `getent` and carries in no defaults file. It is the only test in the repo that renders a template under the role's OWN variables.
- `tests/test_nautilus_interface_pin.py::test_the_pin_covers_every_nautilus_name_cli_imports` walks `cli/**/*.py` with `ast` and fails on any `from nautilus_trader… import X` absent from `PINNED_SYMBOLS`. **Every task that adds a nautilus import widens that list in the same commit** — Task 1 for the `nautilus_trader.model` names, Task 9 for `KrakenSpotHttpClient`. It is not in any other task's verification command, so an unpinned import surfaces first in CI, after the branch was reported finished.
- `tests/test_ops_daily.py` extracts every backticked and fenced command from `infra/runbooks/*.md` and classifies it. **`zcrypto-flatten` must never classify AUTONOMOUS.** If a runbook edit turns that file red, never fix it by widening the classifier's allowlist for this command.
- No host-touching step (ssh, sudo, ansible, vault) appears anywhere in this plan. Every task runs entirely in the repo. The converge that puts the wrapper on the engine host and the live read-only dry-run through it are attended human steps, registered in the topic at closeout and out of scope here.

### Facts measured from the repo on 2026-08-30 at `develop` — do not re-derive, do not assume beyond them

- `cli/engine/execgate.py` exports `KILL_FILE = "kill"` and `exec_dir(state_dir) -> Path` returning `Path(state_dir) / "exec"`.
- `cli/engine/executor.py::ProbeExecutor._write_kill_file` writes `f"{now.isoformat()} {reason}\n"`. Nothing in the repo ever clears the kill file.
- `cli/engine/venue.py::read_system_status(*, now, opener=urllib.request.urlopen) -> VenueStatus` never raises; `VenueStatus` has `.status: str`, `.ok: bool`, `.observed_at: datetime`. `ok` is true only for `"online"`.
- `cli/engine/instruments.py` exports `EUR_CODES = ("EUR", "ZEUR")`, `COSTMIN: dict[str, tuple[float, str]]` (twelve basket symbols, value is `(amount, quote_code)` with quote spelled `"EUR"`/`"BTC"`), `_floor_to_step(value, step) -> float` (exact, Decimal-routed), and `size_order(target_qty, reference_price, *, ordermin, costmin, lot_step, tick_size) -> SizedOrder | BelowMinimum`. `SizedOrder` has `.qty`, `.price`, `.notional`; `BelowMinimum` has `.reason`.
- `cli/engine/node.py` sets `_ACCOUNT_ID = "KRAKEN-001"` and `_TRADER_ID = "SHADOW-001"` with order-id tag `"000"` (the engine's client order ids carry the infix `-001-000-`).
- `cli/engine/command.py` defines `engine_app = typer.Typer(...)`, `_abort(message)` (logs, returns `typer.Exit(code=1)`), `_utc_now()`, and imports `cli.engine.node` lazily inside command bodies so `zcrypto --help` never pays the ~1 s nautilus import.
- `nautilus_trader.adapters.kraken.KrakenSpotHttpClient` — every method returns `typing.Any`:
  - `__init__(api_key=None, api_secret=None, base_url=None, timeout_secs=60, ...)`; property `api_key_masked -> str | None`
  - `request_instruments(pairs=None)`
  - `request_order_status_reports(account_id, instrument_id=None, start=None, end=None, open_only=False)`
  - `request_position_status_reports(account_id, instrument_id=None, account_type=AccountType.CASH, use_spot_position_reports=False, quote_currency="USDT")`
  - `request_account_state(account_id, account_type=AccountType.CASH, margin_balance_asset=None)`
  - `request_book_snapshot(instrument_id, depth=None)`
  - `submit_order(account_id, instrument_id, client_order_id, order_side, order_type, quantity, time_in_force, expire_time=None, price=None, trigger_price=None, trigger_type=None, trailing_offset=None, limit_offset=None, reduce_only=False, post_only=False, quote_quantity=False, display_qty=None, leverage=None, account_type=AccountType.CASH)`
  - `cancel_all_orders()`
- `nautilus_trader.model.PositionStatusReport` exposes `.instrument_id`, `.position_side`, `.quantity`, `.is_flat`, `.is_long`, `.is_short`.
- `str(AccountType.MARGIN)` is `"MARGIN"` and `str(AccountType.CASH)` is `"CASH"` — the bare member name with no `AccountType.` prefix, so a journalled parameter can be derived from the enum the call passes instead of spelled a second time beside it.
- `nautilus_trader.model.AccountState` exposes `.balances -> list[AccountBalance]`; `AccountBalance` exposes `.currency -> Currency`, `.free -> Money`, `.total`, `.locked`. `Currency` has `.code`.
- Instruments returned by `request_instruments()` are nautilus `Instrument`s carrying `.id -> InstrumentId`, `.min_quantity`, `.size_increment`, `.price_increment` (each `Quantity`/`Price`, `float()`-able, or `None`), and `.min_notional`, which this adapter **always** reads back `None` (`cli/engine/venuestate.py`'s module docstring; that is why `COSTMIN` is committed).
- Taker fee, tier 1: **0.80 %** (`docs/reference/kraken-fee-schedule.md`, "Spot maker/taker — new schedule (effective 2026-07-09)").
- `tests/test_engine_executor.py` line 155 defines `_VENUE_MUTATING_NAMES = (".submit_order", ".cancel_order", ".order_factory")` and `test_the_venue_mutating_names_have_exactly_one_module` walks `cli/**/*.py` skipping only `cli/engine/executor.py`.
- The engine role's compose template renders `user: "{{ engine_uid }}:{{ engine_gid }}"`, `image: "{{ engine_image }}@{{ engine_image_digest }}"`, mounts `"{{ engine_state_dir }}:{{ engine_state_dir }}"` and `/opt/zcrypto-engine/zcrypto.toml:/app/zcrypto.toml:ro`, and reads `env_file: /opt/zcrypto-engine/engine.env`. `engine_state_dir` defaults to `/var/lib/zcrypto-engine`. `engine_uid`/`engine_gid` are set by a `set_fact` in `tasks/main.yml` and arrive as **strings**.
- `infra/docker/Dockerfile`'s `ENTRYPOINT` is capture's `sh -c` script. Without `--entrypoint zcrypto` a `docker run … engine flatten` starts **capture**.
- `infra/runbooks/engine-procedures.md` exists (created by spec `00104`) and holds two PROCEDURE sections, each with explicit `<a name="…"></a>` anchors. `infra/runbooks/README.md`'s index has an `### [engine-procedures.md]` block listing them.

### Operational choices this plan closes, that the spec left open

Every one of these is binding on the implementer. Do not re-litigate them mid-task; if one looks wrong, report it rather than silently deviating.

1. **Required-field validation is per-leg, never over the whole listing.** `request_instruments()` returns ~1600 instruments. Validating all of them would let one unrelated listing row abort the button. The listing as a whole is required only to be a non-empty iterable; `min_quantity`/`size_increment`/`price_increment` are required **only on the pairs a leg actually routes to**, checked at lookup time. A pair the listing does not carry **at all** is not a shape failure and never an abort: `margin_legs` routes such a position to the plan's `unclosable` list exactly as `spot_legs` routes a pairless balance to `unsellable`, nothing is sized or sent for it, the rest of the sweep runs, and `judge_final` reads it back as a `pair_not_listed` residual (spec D4).
1. **Book prices are read only before the first write, never after.** The snapshot reads `request_book_snapshot(depth=1)` for every pair a snapshot leg routes to, **plus `BTC/EUR` whenever any SPOT leg routes to a `/BTC` pair** — the deterministic pass-two case, and the only one that is deterministic: a margin leg on a `/BTC` pair leaves its proceeds in the pass-one balance read, where they are priced by nothing and sized like any other late-surfacing balance. A leg that appears only in a later pass and has no snapshot reference price is sized on `ordermin`/`lot_step` alone, sent, and journaled `no_reference_price`; its `costmin` floor is then not applicable and the final snapshot judges it on `ordermin` alone. No post-write book read ever happens.
1. **One predicate serves both the dust classification and the final-snapshot judgement** (`classify_balance`). This makes it structurally impossible for the sweep to skip a balance as dust and then report the same balance as a residual.
1. **Asset codes are resolved against the listing, never by string surgery alone.** A balance currency code is mapped to a base by trying, in order: the code itself; the explicit alias table `{"XBT": "BTC", "XXBT": "BTC", "XDG": "DOGE", "XXDG": "DOGE"}` (the adapter's own `normalize_spot_symbol` renames, recorded in `cli/engine/instruments.py`'s docstring); the code with a single leading `X` or `Z` stripped — accepting the first that is a base the listing actually lists. A code that resolves to no listed base is treated exactly as an asset with neither pair: journaled `no_eur_or_btc_pair` with the unresolved code in a `note`, and read as a residual (exit 2). It is never silently ignored.
1. **No settle wait.** The final snapshot is taken immediately after the last order. A fill that has not yet settled shows as a residual and the run exits 2 — the safe direction. The runbook tells the operator that an exit 2 whose journal shows every leg answered `ok` may be a settle race, and that the resolution is to run it again.
1. **`--execute` writes a journal on every exit-1 refusal `run_flatten` itself makes** — the absent kill file, the missing terminal, a terminal that vanished between that check and the confirm's own read, the confirm that did not match: the refusal and its reason are the record. The one exit-1 refusal that writes none is the credentials refusal, which `cli/engine/command.py` raises through `_abort` before `run_flatten` is called and before a client exists — there is no run to record, and the refusal names the variables in the log instead. **The default dry run writes none**: it prints and stops, so an accidental invocation leaves no artifact. Spec D2 carves that mode out of its own "journaled" rule: on a dry run's exit-3 abort the record is the abort message `_dry_exit` echoes, which names the field that could not be read, and nothing else.
1. **The journal filename uses ISO-8601 basic format**: `flatten-<YYYYMMDD>T<HHMMSS>Z.json`. Shell-safe with no quoting, which matters at 03:00. The extended-format timestamp lives in the body. The writer opens with mode `"x"` and appends `-2`, `-3`, … on collision, so a second run in the same second cannot destroy the first run's incident record.
1. **A journal that cannot be written never changes the exit code.** It is logged at CRITICAL and the payload is printed to stdout instead. The exit code describes the account, not our disk.
1. **The controlling-terminal check runs immediately after the kill-file gate, before any venue read** (converge.sh's order). Refusing early costs nothing; the typed word is still read at the confirm point.
1. **The dry run runs the venue-online gate too.** Only the kill-file gate is skipped without `--execute` (D5 says so explicitly of the kill file and of nothing else). A dry run against an offline venue exits 3.
1. **The per-leg estimate is printed in the leg's own quote currency and no grand total is printed.** Summing a BTC-quoted leg into a EUR total would need an FX rate the command has no mandate to invent (`_intent_floor_check`'s "NOT COMPARED" discipline).
1. **The wrapper refuses unless the unit actually reaches inactive.** After `systemctl stop` it polls `systemctl is-active` once a second for 60 s (spec `00100` measured the drain at ≤ 20 s: a 10 s residual-event drain plus up to 10 s disconnection). Still active ⇒ exit 1 and the container is never started — a second live client on the same key is precisely what the one-key-one-client rule forbids for writes. The kill file stays; the wrapper says so.
1. **The wrapper writes the kill file with the engine account's ownership** (`chown` to `engine_uid:engine_gid`, mode 0644). A root-owned 0644 file in a 0750 engine-owned directory would make a later engine-side `_write_kill_file` fail `EACCES`.
1. **The wrapper accepts exactly zero arguments or exactly `--execute`.** Anything else is a usage refusal with exit 1 and no kill file written — a half-remembered `--dry-run` must not reach the container after the button has already been half-pressed.
1. **`--name` is not passed to `docker run`.** A name collision would refuse the button on a second press.
1. **The owed live read-only dry-run is registered in the topic only**, never in `docs/reference/adapter-verification/<version>.md`'s "Owed checks not discharged" section. `infra/runbooks/engine-procedures.md`'s `engine-probe-window` step 3 refuses to **arm** on an open item there, so putting a flatten check in that section would block arming on something unrelated to arming.
1. **`_VENUE_MUTATING_NAMES` gains `.cancel_all_orders`** alongside allowlisting `flatten.py`. The guard's own docstring says a second module learning to cancel is the same escape; account-wide cancel is the most destructive cancel there is and belongs on the list it protects.
1. **`"zcrypto-flatten"` joins `_DESTRUCTIVE` in `tests/test_ops_daily.py`**, so the unattended daily pass's classifier is asserted never to call the red button autonomous.
1. **The cancel's failure is detected as a RAISE, and as nothing else.** Spec D6 row 2 also names `cancel_all_orders()` *answering* an error; what such an answer looks like is unmeasured until the live read-only dry run establishes the read shapes, and a guess at it would pin this run's verdict to message text nothing here has read — the same reason a rejection gains no label from its words. The answer itself is journaled verbatim among `record["requests"]`, and an order that outlived such a cancel is still read back by the final snapshot and still exits 2 — so the exit code is right either way, and `record["cancel"]["ok"]` is the only field an error answer can leave reading true.
1. **A venue rejection carries the venue's own words, and the only label it can gain is one this code had already earned before sending.** Six LEG reason labels exist and no more: `dust_below_venue_minimum`, `unclosable_below_minimum`, `no_eur_or_btc_pair`, `no_reference_price`, `pair_not_listed`, `unrecognised_position_side` — each one a decision *this code* made before sending. `judge_final` additionally writes `resting_order`, `sellable_balance` and `unjudgeable: <exc>` into `record["residuals"]`: those describe the FINAL SNAPSHOT, not a pre-send decision, and the runbook's exit-2 list says so. What the venue answers is journaled verbatim as the leg's `error`; the spec's D3 says so, and inferring a label from a rejection message would pin the journal to message text nothing here has measured. The one label a rejection attaches is `unclosable_below_minimum`, and only on a margin leg whose sized quantity this code had already read as below the pair's `ordermin` (spec D4): it is the only thing that routes an operator to Kraken's own settle-position, which an unlabelled `EOrder:` string never does. The rejection text is never read to decide it — so the venue's verbatim words stay beside the label, and the runbook makes reading them the operator's first step, because a refusal for a passing reason wears the same label as a refusal about the size.

### Every path that can raise before the first write, and what it does

`cancel_all_orders()` is the first write. Anything that raises before it decides the whole run's outcome, and **one bad row aborting the sweep is the worst outcome this command has**: the wrapper has already latched the kill file and stopped the engine, so exit 3 leaves every resting order resting, every position open and every balance held, with nothing else running that would act. The table is exhaustive over `run_flatten`'s pre-write span and is the check a reviewer runs: a path that must abort is fine, an unexamined one is the defect.

| raising path | verdict | why |
| --- | --- | --- |
| `check_kill_file` — the file is absent or unreadable | refuse, exit 1 | Nothing has been read or sent; the latch is the precondition and the operator places it and re-runs. |
| `tty_available()` false | refuse, exit 1 | The confirm can never be answered; refusing before five venue reads costs nothing. |
| `prompt(...)` — the terminal disappeared between the check and the read | refuse, exit 1 | Same class, caught so the operator gets the refusal and its journal rather than a traceback. |
| `check_venue` — not `online` | abort, exit 3 | Account-wide and unconditional: no leg can be closed at a venue that is not accepting orders. |
| `read_open_orders` / `read_positions` / `read_balances` / `read_listing` — transport failure, or `None`/empty where the answer is load-bearing | abort, exit 3 | Account-wide reads with no row to degrade: without them there is no plan to build and no exit code to derive. An empty listing in particular would make every pair read as pairless. |
| `read_positions` / `read_balances` — an absent or unreadable **named field** on a row | abort, exit 3 | Spec D2's ruling, kept: an absent field is the venue's answer SHAPE, which is not one row's data. The other two of the four require no per-row field: `read_open_orders` reads only the list's length, and `read_listing` skips a row carrying no `id` rather than letting one unrelated listing row abort the button (Global Constraint 1). |
| `constraints_for` — a leg's own pair missing `min_quantity`/`size_increment`/`price_increment`, or publishing a non-positive step | abort, exit 3 | The same D2 ruling, and scoped by Global Constraint 1 to the pairs a leg actually routes to, so an unrelated listing row can never reach it. |
| `margin_legs` — `position_side` present but none of LONG/SHORT/FLAT | **degrade**: the row goes to `unclosable` under `unrecognised_position_side` | The field is there and the row is nameable; only the VALUE is unusable. The installed build carries a fourth `PositionSide` member and which ones the adapter emits is unmeasured, so this is a live path, not a hypothetical (spec D3). |
| `read_book_price` inside `build_plan` — the request errors, the required side is empty, or its top level answers a price at or below zero | **degrade**: that leg is priced `None` | Spec D2's one exception. A price is never an order price here — every order is MARKET — so the leg is sized on `ordermin`/`lot_step` alone and sent, and no other leg loses its cancel, close or sale (spec D3). The non-positive price is REFUSED rather than carried, and belongs to the same family as the rows above: a notional read as nothing is below every `costmin`, so `size_leg` would list every basket leg as `dust_below_venue_minimum` and `judge_final` — one predicate, same price — would agree, and the run would report the account flat at exit 0 with the whole spot book still held. |
| `spot_legs`, `resolve_base`, `choose_pair`, `size_leg`, `classify_balance`, `render_plan` | cannot raise | Each pairless or unresolvable case is already routed to `unsellable`; `size_order`'s floors are total, and `_as_step` has already excluded the zero step that would divide. |

______________________________________________________________________

## File Structure

| File | Responsibility |
| --- | --- |
| `cli/engine/flatten.py` | Create. The whole button: read layer, leg enumeration, sizing, gates, confirm, write sequence, exit-code derivation, journal. Kept as one module a reviewer can hold at once; it shares no code path with `cli/engine/executor.py` by design. |
| `cli/engine/command.py` | Modify. Add the `flatten` sub-command on `engine_app`: credentials, lazy import of `cli.engine.flatten`, `typer.Exit(code)`. |
| `tests/test_engine_flatten.py` | Create. The fake-client suite: every fixture spec `00106` D8.1 names. |
| `tests/test_engine_flatten_wrapper.py` | Create. Renders the wrapper template and executes it against fake `docker`/`systemctl`/`id`/`chown`/`sleep` on `PATH`. |
| `tests/test_engine_executor.py` | Modify. Widen `_VENUE_MUTATING_NAMES` and its allowlist. |
| `tests/test_nautilus_interface_pin.py` | Modify. `PINNED_SYMBOLS` gains the three nautilus names this branch newly imports under `cli/`. |
| `tests/test_ops_daily.py` | Modify. Add `zcrypto-flatten` to `_DESTRUCTIVE`. |
| `tests/test_infra_shell_templates_render.py` | Modify. Register the new shell template and give `RUNTIME_FACTS` the engine uid/gid the role sets by `set_fact`. |
| `infra/ansible/roles/engine/templates/zcrypto-flatten.sh.j2` | Create. The host wrapper. |
| `infra/ansible/roles/engine/tasks/main.yml` | Modify. One template task installing the wrapper. |
| `infra/runbooks/engine-procedures.md` | Modify. The `engine-flatten` PROCEDURE section. |
| `infra/runbooks/README.md` | Modify. Its index row. |
| `README.md` | Modify. The `flatten` row in the `zcrypto engine` usage table. |
| `docs/open-topics/T0159-engine-flatten-the-red-button.md`, `docs/open-topics/README.md` | Modify at closeout. |
| `docs/iterations-history-phase6.md` | Modify at closeout. |

______________________________________________________________________

### Task 1: The defensive read layer

**Files:**

- Create: `cli/engine/flatten.py`
- Modify: `tests/test_nautilus_interface_pin.py` (`PINNED_SYMBOLS`)
- Test: `tests/test_engine_flatten.py`

**Interfaces:**

- Consumes: nothing from earlier tasks.
- Produces, for every later task:
  - `ACCOUNT_ID: str = "KRAKEN-001"`, `TAKER_RATE: float = 0.0080`, `CONFIRM_WORD: str = "FLATTEN"`, `CLIENT_ORDER_ID_PREFIX: str = "FLT-"`, `BOOK_DEPTH: int = 1`, `QUOTE_CURRENCY: str = "ZEUR"`, `MARGIN_LEVERAGE: int = 2`, `_ANSWER_REPR_LIMIT: int = 4000`
  - `logger` (`get_logger("engine.flatten")`), `_ACCOUNT` (the nautilus `AccountId`), `step_precision(step: float) -> int`
  - `class FlattenRefused(Exception)` — exit 1. `class FlattenUnreachable(Exception)` — exit 3, raised only before the first write.
  - `@dataclass(frozen=True) class PairConstraints: symbol: str; instrument_id: Any; ordermin: float; lot_step: float; tick_size: float`
  - `@dataclass(frozen=True) class PositionRow: symbol: str; instrument_id: Any; side: str; quantity: float` — `side` is `"LONG"`, `"SHORT"` or `"FLAT"`.
  - `@dataclass(frozen=True) class BalanceRow: code: str; free: float`
  - `class Recorder` with `.entries: list[dict]` and `.call(name: str, params: dict, fn: Callable[[], Any]) -> Any`
  - `read_open_orders(client, rec) -> list[Any]`
  - `read_positions(client, rec) -> list[PositionRow]`
  - `read_balances(client, rec) -> list[BalanceRow]`
  - `read_listing(client, rec) -> dict[str, Any]` — keyed `"<BASE>/<QUOTE>"` (e.g. `"BTC/EUR"`), value the raw instrument object.
  - `constraints_for(symbol: str, listing: dict[str, Any]) -> PairConstraints` — raises `FlattenUnreachable` on a required field that is absent, unreadable, or a non-positive quantization step.
  - `read_book_price(client, rec, constraints, side) -> float` — `side` `"SELL"` takes the best bid, `"BUY"` the best ask; an empty side, and a top level answering a price at or below zero, both raise `FlattenUnreachable`, which `build_plan` degrades to an unpriced leg.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_engine_flatten.py`:

```python
"""The red button's fake-client suite (spec 00106 D8): every read is parsed by named fields it
requires, and a field the venue stopped sending aborts rather than being guessed through.

The fake records every call in order, so the assertions here are about what actually reached the
venue -- never only about a return value."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from cli.engine import flatten


@dataclass
class _Level:
    price: float


class _Book:
    def __init__(self, bid: float, ask: float) -> None:
        self.bids = [_Level(bid)]
        self.asks = [_Level(ask)]


class _Instrument:
    """A listing row shaped like the adapter's: every constraint float()-able or None."""

    def __init__(self, symbol: str, *, ordermin=0.0001, lot_step=0.00000001, tick_size=None) -> None:
        self.id = f"{symbol}.KRAKEN"
        self.min_quantity = ordermin
        self.size_increment = lot_step
        # The tick defaults by QUOTE, not to one number: a BTC-quoted pair ticks at seven decimals,
        # and the euro pairs' 0.1 would floor a reference price like 0.03 BTC to zero -- turning a
        # live balance into dust and hiding every routing assertion that depends on it being sold.
        self.price_increment = tick_size if tick_size is not None else (0.0000001 if symbol.endswith("/BTC") else 0.1)
        self.min_notional = None  # this adapter never maps costmin -- cli/engine/venuestate.py


class _Position:
    def __init__(self, symbol: str, side: str, qty: float) -> None:
        self.instrument_id = f"{symbol}.KRAKEN"
        self.position_side = side
        self.quantity = qty


class _Balance:
    def __init__(self, code: str, free: float) -> None:
        self.currency = type("C", (), {"code": code})()
        self.free = free


class _AccountState:
    def __init__(self, balances: list[_Balance]) -> None:
        self.balances = balances


def _norm(value: Any) -> Any:
    """Enum -> its bare member name, everything else untouched. The module hands the client REAL
    nautilus types (`AccountId`, `AccountType`, `OrderSide`, …); the assertions below are about
    which member was chosen, so the fake normalises once here instead of in every test."""
    if isinstance(value, (bool, int, float)) or value is None:
        return value
    text = str(value)
    return text.rsplit(".", 1)[-1] if "." in text and " " not in text and "/" not in text else text


class FakeClient:
    """Answers from a script and records every call. `raises` maps a method name to an exception
    instance the next call to it will raise."""

    api_key_masked = "kr***xy"
    # The secret itself, distinct from its masked form, so a journal test can assert on the VALUE
    # that would leak rather than on the name of the variable it arrived in.
    api_key = "kNEVER-IN-THE-JOURNAL-0000"

    def __init__(self, *, instruments=None, orders=None, positions=None, balances=None, books=None) -> None:
        self.calls: list[tuple[str, dict]] = []
        self._instruments = instruments if instruments is not None else []
        self._orders = list(orders or [[]])
        self._positions = list(positions or [[]])
        self._balances = list(balances or [[]])
        self._books = books or {}
        self.raises: dict[str, Exception] = {}
        self.submitted: list[dict] = []

    def _maybe_raise(self, name):
        exc = self.raises.pop(name, None)
        if exc is not None:
            raise exc

    def _next(self, queue):
        return queue.pop(0) if len(queue) > 1 else queue[0]

    def request_instruments(self, pairs=None):
        self.calls.append(("request_instruments", {"pairs": pairs}))
        self._maybe_raise("request_instruments")
        return self._instruments

    def _record(self, name, account_id, kw):
        self.calls.append((name, {"account_id": _norm(account_id), **{k: _norm(v) for k, v in kw.items()}}))

    def request_order_status_reports(self, account_id, **kw):
        self._record("request_order_status_reports", account_id, kw)
        self._maybe_raise("request_order_status_reports")
        return self._next(self._orders)

    def request_position_status_reports(self, account_id, **kw):
        self._record("request_position_status_reports", account_id, kw)
        self._maybe_raise("request_position_status_reports")
        return self._next(self._positions)

    def request_account_state(self, account_id, **kw):
        self._record("request_account_state", account_id, kw)
        self._maybe_raise("request_account_state")
        return _AccountState(self._next(self._balances))

    def request_book_snapshot(self, instrument_id, depth=None):
        self.calls.append(("request_book_snapshot", {"instrument_id": str(instrument_id), "depth": depth}))
        self._maybe_raise("request_book_snapshot")
        return self._books[str(instrument_id)]

    def cancel_all_orders(self):
        self.calls.append(("cancel_all_orders", {}))
        self._maybe_raise("cancel_all_orders")
        return {"ok": True}

    def submit_order(self, account_id, instrument_id, client_order_id, order_side, order_type, quantity, time_in_force, **kw):
        params = {
            "instrument_id": str(instrument_id),
            "client_order_id": str(client_order_id),
            "order_side": _norm(order_side),
            "order_type": _norm(order_type),
            "quantity": float(quantity),
            "time_in_force": _norm(time_in_force),
            **{k: _norm(v) for k, v in kw.items()},
        }
        self.calls.append(("submit_order", params))
        self.submitted.append(params)
        self._maybe_raise("submit_order")
        return {"ok": True}


def names(client: FakeClient) -> list[str]:
    return [name for name, _ in client.calls]


# --- the read layer -----------------------------------------------------------------------------


def test_the_listing_is_keyed_by_symbol_and_a_missing_constraint_aborts_the_pair():
    """`constraints_for` requires ordermin, lot_step and tick_size on the pair it is asked for --
    and only on that pair: an unrelated listing row missing one must not abort the whole sweep."""
    listing_rows = [_Instrument("BTC/EUR"), _Instrument("ADA/EUR")]
    listing_rows[1].size_increment = None
    client = FakeClient(instruments=listing_rows)
    rec = flatten.Recorder()

    listing = flatten.read_listing(client, rec)
    assert set(listing) == {"BTC/EUR", "ADA/EUR"}

    good = flatten.constraints_for("BTC/EUR", listing)
    assert (good.ordermin, good.lot_step, good.tick_size) == (0.0001, 0.00000001, 0.1)

    with pytest.raises(flatten.FlattenUnreachable) as exc:
        flatten.constraints_for("ADA/EUR", listing)
    # The venue's own field name: an absent field is caught by `_required`, which never sees the
    # friendly label `_as_float` would have used.
    assert "size_increment" in str(exc.value)


@pytest.mark.parametrize("field", ["size_increment", "price_increment"])
def test_a_zero_quantization_step_aborts_rather_than_dividing_by_it(field):
    """A step of zero passes an is-it-absent check and then divides. `_floor_to_step` raises a bare
    ValueError on it, which nothing between here and the operator catches -- so the exit-code
    contract would arrive as a traceback with no journal."""
    rows = [_Instrument("BTC/EUR")]
    setattr(rows[0], field, 0.0)
    client = FakeClient(instruments=rows)
    rec = flatten.Recorder()
    with pytest.raises(flatten.FlattenUnreachable) as exc:
        flatten.constraints_for("BTC/EUR", flatten.read_listing(client, rec))
    assert "positive step" in str(exc.value)


def test_an_empty_listing_aborts():
    """An empty listing is not an account with nothing to sell -- it is a read that told us
    nothing, and every pair lookup after it would silently answer 'no pair'."""
    with pytest.raises(flatten.FlattenUnreachable):
        flatten.read_listing(FakeClient(instruments=[]), flatten.Recorder())


def test_positions_are_read_by_named_fields_and_a_missing_one_aborts():
    """`position_side` and `quantity` are the two fields a close is built from; a row missing
    either is a shape this process may not reason about."""
    rows = [_Position("BTC/EUR", "LONG", 0.5), _Position("ETH/EUR", "FLAT", 0.0)]
    read = flatten.read_positions(FakeClient(positions=[rows]), flatten.Recorder())
    assert [(r.symbol, r.side, r.quantity) for r in read] == [("BTC/EUR", "LONG", 0.5), ("ETH/EUR", "FLAT", 0.0)]

    broken = _Position("BTC/EUR", "LONG", 0.5)
    del broken.position_side
    with pytest.raises(flatten.FlattenUnreachable) as exc:
        flatten.read_positions(FakeClient(positions=[[broken]]), flatten.Recorder())
    assert "position_side" in str(exc.value)


def test_a_position_read_that_answers_nothing_aborts_rather_than_reading_as_flat():
    """`None` is not an account with no positions, and read as `[]` it is the one shape that
    confirms itself: the plan shows no margin leg, the operator confirms, the cancel and the spot
    sells run, and then `judge_final` re-reads through this same function, finds no residual and
    reports the account flat at exit 0 with leveraged positions still open.

    The fake's answer script is a queue of whole answers, so `None` is scriptable with no special
    case -- the `[[]]` default applies only when no script is given and cannot mask this."""
    client = FakeClient(positions=[None])
    with pytest.raises(flatten.FlattenUnreachable) as exc:
        flatten.read_positions(client, flatten.Recorder())
    assert "answered nothing" in str(exc.value)
    # The read went out and its answer is what was refused -- not a refusal before reaching the venue.
    assert names(client) == ["request_position_status_reports"]


def test_the_position_read_is_scoped_to_margin_with_spot_reports_off():
    """The three parameters that scope this read are asserted rather than assumed: MARGIN, spot
    position reports off, and the euro quote. Whether they actually keep a spot holding out of the
    report is a live property no fake can show; spec 00106 D8.2's read-only dry-run establishes
    that, and until it runs the parameters are all that is pinned here."""
    client = FakeClient(positions=[[]])
    flatten.read_positions(client, flatten.Recorder())
    _, params = client.calls[0]
    assert params["account_type"] == "MARGIN"
    assert params["use_spot_position_reports"] is False
    assert params["quote_currency"] == flatten.QUOTE_CURRENCY


def test_balances_are_read_from_the_cash_account():
    """Under MARGIN the account reports one EUR figure, not per-asset balances (the same record,
    observation 2), so the spot enumeration reads CASH."""
    client = FakeClient(balances=[[_Balance("XXBT", 0.5), _Balance("ZEUR", 100.0)]])
    read = flatten.read_balances(client, flatten.Recorder())
    assert [(r.code, r.free) for r in read] == [("XXBT", 0.5), ("ZEUR", 100.0)]
    assert client.calls[0][1]["account_type"] == "CASH"


def test_the_open_order_read_asks_for_open_only():
    client = FakeClient(orders=[[]])
    flatten.read_open_orders(client, flatten.Recorder())
    assert client.calls[0][1]["open_only"] is True


def test_the_book_read_takes_the_bid_for_a_sell_and_the_ask_for_a_buy():
    listing = {"BTC/EUR": _Instrument("BTC/EUR")}
    client = FakeClient(instruments=[listing["BTC/EUR"]], books={"BTC/EUR.KRAKEN": _Book(bid=60000.0, ask=60010.0)})
    rec = flatten.Recorder()
    constraints = flatten.constraints_for("BTC/EUR", flatten.read_listing(client, rec))
    assert flatten.read_book_price(client, rec, constraints, "SELL") == 60000.0
    assert flatten.read_book_price(client, rec, constraints, "BUY") == 60010.0
    assert client.calls[-1][1]["depth"] == flatten.BOOK_DEPTH


def test_an_empty_book_side_aborts_rather_than_guessing_a_price():
    """A price is what sizes the dust boundary; an absent one must not be defaulted."""
    listing = {"BTC/EUR": _Instrument("BTC/EUR")}
    book = _Book(bid=60000.0, ask=60010.0)
    book.bids = []
    client = FakeClient(instruments=[listing["BTC/EUR"]], books={"BTC/EUR.KRAKEN": book})
    rec = flatten.Recorder()
    constraints = flatten.constraints_for("BTC/EUR", flatten.read_listing(client, rec))
    with pytest.raises(flatten.FlattenUnreachable):
        flatten.read_book_price(client, rec, constraints, "SELL")


def test_a_non_positive_book_price_aborts_the_read_rather_than_pricing_a_leg_at_nothing():
    """Zero passes every is-it-absent check and then makes every notional read as nothing: below
    every `costmin`, so each basket leg would be listed as dust and not sent, and the one predicate
    judging the final snapshot would agree the account is flat with the whole spot book still held.
    The other side of the same book is the true negative -- a check refusing every price fails it."""
    listing = {"BTC/EUR": _Instrument("BTC/EUR")}
    book = _Book(bid=60000.0, ask=60010.0)
    book.bids = [_Level(0.0)]
    client = FakeClient(instruments=[listing["BTC/EUR"]], books={"BTC/EUR.KRAKEN": book})
    rec = flatten.Recorder()
    constraints = flatten.constraints_for("BTC/EUR", flatten.read_listing(client, rec))
    with pytest.raises(flatten.FlattenUnreachable):
        flatten.read_book_price(client, rec, constraints, "SELL")
    assert flatten.read_book_price(client, rec, constraints, "BUY") == 60010.0


def test_the_recorder_keeps_every_call_with_its_parameters_and_answer():
    """The journal's whole value is that it says what was asked and what came back; a recorder
    that drops the answer leaves an operator with a list of intentions."""
    client = FakeClient(orders=[[]])
    rec = flatten.Recorder()
    flatten.read_open_orders(client, rec)
    assert rec.entries[0]["call"] == "request_order_status_reports"
    assert rec.entries[0]["params"]["open_only"] is True
    assert "answer" in rec.entries[0]


def test_a_raising_read_is_recorded_with_its_error_and_re_raised():
    client = FakeClient(orders=[[]])
    client.raises["request_order_status_reports"] = RuntimeError("connection reset")
    rec = flatten.Recorder()
    with pytest.raises(flatten.FlattenUnreachable):
        flatten.read_open_orders(client, rec)
    assert "connection reset" in rec.entries[0]["error"]


def test_the_account_id_matches_the_engine_node():
    """One account, one id. A drift here sends every read at an account the engine does not
    trade."""
    from cli.engine import node

    assert flatten.ACCOUNT_ID == node._ACCOUNT_ID


def test_step_precision_matches_the_lot_step_s_own_decimal_places():
    """The docstring's worked examples, asserted: a coarse EUR-quoted step and a fine BTC-quoted
    one, so a minted `Quantity` is exact at either end of the basket."""
    assert flatten.step_precision(0.1) == 1
    assert flatten.step_precision(0.00000001) == 8


def test_a_huge_answer_is_truncated_in_the_journal_and_says_that_it_was():
    """`request_instruments()` alone answers with ~1600 rows, and every answer's `repr` goes into
    one JSON string field. The cap keeps the incident artifact openable; the suffix is what stops a
    reader mistaking a truncated repr for the venue's whole answer."""
    rec = flatten.Recorder()
    rec.call("request_instruments", {"pairs": None}, lambda: "x" * (flatten._ANSWER_REPR_LIMIT * 2))
    answer = rec.entries[0]["answer"]
    assert len(answer) < flatten._ANSWER_REPR_LIMIT * 2
    assert answer.endswith("chars total]")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_engine_flatten.py -q`
Expected: collection error — `ModuleNotFoundError: No module named 'cli.engine.flatten'`.

- [ ] **Step 3: Write the module**

Create `cli/engine/flatten.py`:

```python
"""`zcrypto engine flatten` -- the red button (spec 00106).

A standalone sweep of the whole Kraken account over the adapter's HTTP client: cancel every
resting order, close every margin position with a reduce-only MARKET order, sell every non-EUR
spot balance at MARKET. It shares NO code path with `cli/engine/executor.py` by design -- the
button must work when the engine's own order machine is what broke, which is why
`tests/test_engine_executor.py::test_the_venue_mutating_names_have_exactly_one_module` allowlists
this module as a second venue-mutating one rather than being satisfied by reuse.

Every venue answer is `typing.Any` (`nautilus_trader/adapters/kraken/__init__.pyi`), so the read
layer below names the fields it requires and ABORTS on an absent one rather than guessing: a shape
the venue changed is a finding. Before the first write that abort is exit 3; after it, exit 2 --
the account may already have moved.

MARKET is used deliberately, overriding spec 00090 D6's rejection of it for the probe machine: in
a crash the price is not the variable, time is, and a bounded IOC in a fast market leaves residue
that IS the exposure.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Callable

from nautilus_trader.model import AccountId, AccountType, ClientOrderId, OrderSide, OrderType, Quantity, TimeInForce

from cli.logging import get_logger

logger = get_logger("engine.flatten")

# The account the exec client reports under -- `cli/engine/node.py`'s `_ACCOUNT_ID`, pinned equal
# by tests/test_engine_flatten.py so a rename cannot point the sweep at another account.
ACCOUNT_ID = "KRAKEN-001"
# Tier 1 taker, docs/reference/kraken-fee-schedule.md (schedule effective 2026-07-09). Printed as
# an estimate only; nothing branches on it.
TAKER_RATE = 0.0080
CONFIRM_WORD = "FLATTEN"
# Never collides with the engine's ids, which carry the `-001-000-` infix minted from
# TraderId("SHADOW-001") plus order-id tag "000" (`cli/engine/node.py`): the executor's own-order
# routing would otherwise treat an ack of ours as its own.
CLIENT_ORDER_ID_PREFIX = "FLT-"
BOOK_DEPTH = 1
# The venue-alias spelling of the euro on the quote surfaces (546 live instruments carry `ZEUR`,
# zero carry `EUR` -- docs/reference/adapter-verification/2.0.0rc4.dev20260825.md observation 4).
QUOTE_CURRENCY = "ZEUR"
# The rung-1 leverage, and the only value ever accepted live from this repo (probes 4c/4d in
# docs/reference/adapter-verification/2.0.0rc4.dev20260825.md). PositionStatusReport carries no
# leverage field, so a closer cannot echo the position's; what the venue does with a mismatched
# leverage on a reduce-only closer is unmeasured, and the go-live drill program's red-button drill
# is where it gets measured.
MARGIN_LEVERAGE = 2
# `Recorder.call` writes one `repr` per answer into a single JSON string field, and
# `request_instruments()` alone answers with ~1600 rows -- around 110 KB at the installed adapter's
# ~68-char `CurrencyPair.__repr__`. Capped so the incident artifact stays openable mid-incident.
_ANSWER_REPR_LIMIT = 4000

# Real nautilus types reach the client; the journal records their string forms. A plain `str` where
# the compiled signature wants `AccountId`/`AccountType` fails at the venue, not in a test.
_ACCOUNT = AccountId(ACCOUNT_ID)


class FlattenRefused(Exception):
    """Refused with nothing sent -- exit 1. The kill-file and terminal gates precede every read;
    the confirm mismatch follows the plan's reads and still precedes every write."""


class FlattenUnreachable(Exception):
    """The venue could not be reached or read. Exit 3 while raised before the first write; the
    caller converts it to exit 2 once `cancel_all_orders` has gone out."""


@dataclass(frozen=True)
class PairConstraints:
    symbol: str
    instrument_id: Any
    ordermin: float
    lot_step: float
    tick_size: float


@dataclass(frozen=True)
class PositionRow:
    symbol: str
    instrument_id: Any
    side: str  # LONG / SHORT / FLAT
    quantity: float  # unsigned; PositionStatusReport carries no signed quantity


@dataclass(frozen=True)
class BalanceRow:
    code: str
    free: float


class Recorder:
    """Every request with its parameters and every answer verbatim -- the journal's spine.

    `repr` is the verbatim form available: the adapter returns opaque objects with no committed
    serialization, and a reader mid-incident needs what came back, not our summary of it. Capped at
    `_ANSWER_REPR_LIMIT` with the full length named in the suffix, so the one ~1600-row listing
    answer cannot make the artifact awkward to open and no reader mistakes a cut repr for the whole.
    """

    def __init__(self) -> None:
        self.entries: list[dict] = []

    def call(self, name: str, params: dict, fn: Callable[[], Any]) -> Any:
        entry: dict = {"call": name, "params": dict(params)}
        self.entries.append(entry)
        try:
            answer = fn()
        except Exception as exc:  # noqa: BLE001 -- every transport failure is recorded, then classified
            entry["error"] = f"{type(exc).__name__}: {exc}"
            raise
        answer_repr = repr(answer)
        if len(answer_repr) > _ANSWER_REPR_LIMIT:
            answer_repr = f"{answer_repr[:_ANSWER_REPR_LIMIT]}... [truncated, {len(answer_repr)} chars total]"
        entry["answer"] = answer_repr
        return answer


def _required(obj: Any, field: str, what: str) -> Any:
    value = getattr(obj, field, None)
    if value is None:
        raise FlattenUnreachable(f"{what}: the venue's answer carries no readable {field}")
    return value


def _as_float(value: Any, field: str, what: str) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError) as exc:
        raise FlattenUnreachable(f"{what}: {field} {value!r} is not a number") from exc
    if not math.isfinite(out):
        raise FlattenUnreachable(f"{what}: {field} {value!r} is not finite")
    return out


def _as_step(value: Any, field: str, what: str) -> float:
    """A quantization step, which must be positive to be one.

    `_required` only rejects `None`, so a venue publishing `0` would reach `_floor_to_step` and
    raise a bare `ValueError` no caller here catches -- the operator would get a traceback where
    the exit-code contract promises a named unreachable. A zero step IS a shape the venue changed.
    """
    out = _as_float(value, field, what)
    if out <= 0.0:
        raise FlattenUnreachable(f"{what}: {field} {value!r} is not a positive step")
    return out


def _symbol_of(instrument_id: Any) -> str:
    """`BTC/EUR.KRAKEN` -> `BTC/EUR`. The venue half is stripped; the adapter has already renamed
    Kraken's legacy XBT/XDG codes (`cli/engine/instruments.py`)."""
    return str(instrument_id).rsplit(".", 1)[0]


def _journalled(kwargs: dict[str, Any]) -> dict[str, Any]:
    """The keyword arguments as the journal records them: a nautilus enum by its string form, every
    other value verbatim.

    Each read below builds ONE kwargs dict and both sends and journals it, so no scoping value is
    spelled a second time beside the call. A hand-written literal is a journal that can read MARGIN
    while CASH went out, and the journal is what an operator reads mid-incident.
    """
    return {key: str(value) if isinstance(value, AccountType) else value for key, value in kwargs.items()}


def read_open_orders(client: Any, rec: Recorder) -> list[Any]:
    """Every order resting at the venue. Only the LIST is load-bearing here -- its length decides
    the exit code -- so no per-row field is required: an unparseable row must not abort a sweep
    whose whole answer is 'something is still working'."""
    # `account_id` is the constant `_ACCOUNT` is minted from, not a second spelling of it.
    kwargs: dict[str, Any] = {"open_only": True}
    params = {"account_id": ACCOUNT_ID, **_journalled(kwargs)}
    try:
        rows = rec.call(
            "request_order_status_reports",
            params,
            lambda: client.request_order_status_reports(_ACCOUNT, **kwargs),
        )
    except FlattenUnreachable:
        raise
    except Exception as exc:  # noqa: BLE001
        raise FlattenUnreachable(f"open orders could not be read: {exc}") from exc
    if rows is None:
        raise FlattenUnreachable("open orders could not be read: the venue answered nothing")
    return list(rows)


def read_positions(client: Any, rec: Recorder) -> list[PositionRow]:
    kwargs: dict[str, Any] = {
        "account_type": AccountType.MARGIN,
        "use_spot_position_reports": False,
        "quote_currency": QUOTE_CURRENCY,
    }
    params = {"account_id": ACCOUNT_ID, **_journalled(kwargs)}
    try:
        rows = rec.call(
            "request_position_status_reports",
            params,
            lambda: client.request_position_status_reports(_ACCOUNT, **kwargs),
        )
    except FlattenUnreachable:
        raise
    except Exception as exc:  # noqa: BLE001
        raise FlattenUnreachable(f"margin positions could not be read: {exc}") from exc
    # `None` read as "no positions" is the one shape that CONFIRMS ITSELF: `build_plan` shows no
    # margin leg, the writes run, and `judge_final` re-reads through this same function, finds no
    # residual and reports the account flat at exit 0 with leveraged positions still open. Unlike
    # its three siblings this read has no downstream backstop -- `read_listing` has its empty-map
    # raise and `read_balances` has `_required(state, "balances")`.
    if rows is None:
        raise FlattenUnreachable("margin positions could not be read: the venue answered nothing")
    out = []
    for row in list(rows or []):
        what = "a margin position row"
        instrument_id = _required(row, "instrument_id", what)
        side = str(_required(row, "position_side", what))
        # `PositionSide.LONG` and a bare `LONG` both reduce to the last dotted component.
        side = side.rsplit(".", 1)[-1].upper()
        qty = _as_float(_required(row, "quantity", what), "quantity", what)
        out.append(PositionRow(symbol=_symbol_of(instrument_id), instrument_id=instrument_id, side=side, quantity=qty))
    return out


def read_balances(client: Any, rec: Recorder) -> list[BalanceRow]:
    kwargs: dict[str, Any] = {"account_type": AccountType.CASH}
    params = {"account_id": ACCOUNT_ID, **_journalled(kwargs)}
    try:
        state = rec.call(
            "request_account_state",
            params,
            lambda: client.request_account_state(_ACCOUNT, **kwargs),
        )
    except FlattenUnreachable:
        raise
    except Exception as exc:  # noqa: BLE001
        raise FlattenUnreachable(f"spot balances could not be read: {exc}") from exc
    what = "the account state"
    balances = _required(state, "balances", what)
    out = []
    for row in list(balances):
        currency = _required(row, "currency", "a balance row")
        code = str(_required(currency, "code", "a balance row's currency"))
        free = _as_float(_required(row, "free", f"the {code} balance"), "free", f"the {code} balance")
        out.append(BalanceRow(code=code, free=free))
    return out


def read_listing(client: Any, rec: Recorder) -> dict[str, Any]:
    """ONE no-argument call for the whole listing. A per-pair request would error on an unknown
    pair and abort the sweep over an unrelated holding; pairlessness is read from this map."""
    try:
        rows = rec.call("request_instruments", {"pairs": None}, lambda: client.request_instruments())
    except FlattenUnreachable:
        raise
    except Exception as exc:  # noqa: BLE001
        raise FlattenUnreachable(f"the instrument listing could not be read: {exc}") from exc
    listing = {}
    for row in list(rows or []):
        instrument_id = getattr(row, "id", None)
        if instrument_id is None:
            continue
        listing[_symbol_of(instrument_id)] = row
    if not listing:
        raise FlattenUnreachable("the instrument listing came back empty -- every pair lookup after it would read as pairless")
    return listing


def constraints_for(symbol: str, listing: dict[str, Any]) -> PairConstraints:
    """The three constraints a sized order needs, required on THIS pair only. Validating the whole
    ~1600-row listing would let one unrelated row abort the button.

    Reaching the absent-row raise below means a caller handed over a leg it should have routed:
    `margin_legs` and `spot_legs` both hold back a pairless one, precisely so that one row cannot
    abort a sweep that has not yet cancelled, closed or sold anything.
    """
    row = listing.get(symbol)
    if row is None:
        raise FlattenUnreachable(f"{symbol} is not in the venue's listing")
    what = f"{symbol}'s listing row"
    return PairConstraints(
        symbol=symbol,
        instrument_id=_required(row, "id", what),
        ordermin=_as_float(_required(row, "min_quantity", what), "ordermin", what),
        lot_step=_as_step(_required(row, "size_increment", what), "lot_step", what),
        tick_size=_as_step(_required(row, "price_increment", what), "tick_size", what),
    )


def read_book_price(client: Any, rec: Recorder, constraints: PairConstraints, side: str) -> float:
    """Best bid for a sell, best ask for a buy. Used for the printed estimate and for the dust
    boundary -- never as an order price, since every order this module sends is MARKET."""
    params = {"instrument_id": str(constraints.instrument_id), "depth": BOOK_DEPTH}
    try:
        book = rec.call(
            "request_book_snapshot",
            params,
            lambda: client.request_book_snapshot(constraints.instrument_id, depth=BOOK_DEPTH),
        )
    except FlattenUnreachable:
        raise
    except Exception as exc:  # noqa: BLE001
        raise FlattenUnreachable(f"{constraints.symbol}: the book could not be read: {exc}") from exc
    what = f"{constraints.symbol}'s book"
    levels = _required(book, "bids" if side == "SELL" else "asks", what)
    levels = list(levels)
    if not levels:
        raise FlattenUnreachable(f"{what}: the {'bid' if side == 'SELL' else 'ask'} side is empty")
    price = _as_float(_required(levels[0], "price", what), "price", what)
    if price <= 0.0:
        # `_required` rejects only `None` and `_as_float` only the non-finite, so a zero would flow
        # into `plan.prices` and make every notional read as nothing -- below every `costmin`, so
        # `size_leg` lists every basket leg as dust and `judge_final`, one predicate at the same
        # price, agrees: the account reported flat at exit 0 with the whole spot book still held.
        # Refused here, the leg degrades to unpriced, which is the direction that SELLS it.
        raise FlattenUnreachable(f"{what}: the top of the {'bid' if side == 'SELL' else 'ask'} side is {price!r}, not a price")
    return price


def step_precision(step: float) -> int:
    """The decimal precision one venue step implies -- 0.1 -> 1, 0.00000001 -> 8. Kraken publishes
    `lot_decimals` alongside the step and the two agree across the basket, so deriving one from the
    other keeps a minted Quantity exactly representable at the floored value."""
    return max(0, -Decimal(str(step)).as_tuple().exponent)
```

In the **same** step, pin the two nautilus names this module's import adds that `PINNED_SYMBOLS` does not already carry. In `tests/test_nautilus_interface_pin.py`, insert into `PINNED_SYMBOLS` in the list's existing alphabetical order — after `("nautilus_trader.model", "OrderStatus")` and before `("nautilus_trader.model", "StrategyId")`:

```python
    ("nautilus_trader.model", "OrderType"),
    ("nautilus_trader.model", "Quantity"),
```

The other five names in the import (`AccountId`, `AccountType`, `ClientOrderId`, `OrderSide`, `TimeInForce`) are pinned already. Without these two, `test_the_pin_covers_every_nautilus_name_cli_imports` goes red the moment `cli/engine/flatten.py` lands.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_engine_flatten.py tests/test_nautilus_interface_pin.py -q`
Expected: PASS, all tests.

- [ ] **Step 5: Commit**

```bash
git add cli/engine/flatten.py tests/test_engine_flatten.py tests/test_nautilus_interface_pin.py
git commit -m "feat(engine): the flatten read layer -- named fields, and an abort where a shape changed"
```

The body explains that every read names the fields it requires, that validation is per-leg-pair rather than over the whole listing, and that `Recorder` keeps the answer verbatim because the journal is what an operator reads mid-incident.

______________________________________________________________________

### Task 2: Leg enumeration — what "everything" is

**Files:**

- Modify: `cli/engine/flatten.py`
- Test: `tests/test_engine_flatten.py`

**Interfaces:**

- Consumes from Task 1: `PairConstraints`, `PositionRow`, `BalanceRow`, `FlattenUnreachable`, `constraints_for`, `read_listing`.
- Produces:
  - `ASSET_ALIASES: dict[str, str]`
  - `resolve_base(code: str, bases: frozenset[str]) -> str | None`
  - `listed_bases(listing: dict[str, Any]) -> frozenset[str]`
  - `choose_pair(base: str, listing: dict[str, Any]) -> str | None` — `"<BASE>/EUR"` if listed, else `"<BASE>/BTC"` if listed, else `None`.
  - `@dataclass(frozen=True) class Leg: kind: str; base: str; symbol: str; side: str; quantity: float; account_type: str; source: str`
  - `margin_legs(positions: list[PositionRow], listing: dict[str, Any]) -> tuple[list[Leg], list[dict]]` — the second element is the unclosable list, each `{"symbol": …, "side": …, "quantity": …, "reason": "pair_not_listed" | "unrecognised_position_side", "note": …}`, `side` being the row's own value and not a close side, since no order is constructed for it. It raises nothing: no single position row may abort the sweep before the cancel.
  - `spot_legs(balances: list[BalanceRow], listing: dict[str, Any]) -> tuple[list[Leg], list[dict]]` — the second element is the unsellable list, each `{"base": …, "code": …, "free": …, "reason": "no_eur_or_btc_pair", "note": …}`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_engine_flatten.py`:

```python
# --- leg enumeration ----------------------------------------------------------------------------


def _listing(*symbols: str) -> dict[str, Any]:
    return {s: _Instrument(s) for s in symbols}


def test_a_long_row_becomes_a_sell_and_a_short_row_a_buy():
    """The side comes from `position_side` and never from a sign: PositionStatusReport carries an
    UNSIGNED quantity, so a sign-derived side would close in the wrong direction on a short."""
    legs, unclosable = flatten.margin_legs(
        [
            flatten.PositionRow("BTC/EUR", "BTC/EUR.KRAKEN", "LONG", 0.5),
            flatten.PositionRow("ETH/EUR", "ETH/EUR.KRAKEN", "SHORT", 2.0),
        ],
        _listing("BTC/EUR", "ETH/EUR"),
    )
    assert unclosable == []
    assert [(leg.symbol, leg.side, leg.quantity) for leg in legs] == [("BTC/EUR", "SELL", 0.5), ("ETH/EUR", "BUY", 2.0)]
    assert all(leg.account_type == "MARGIN" and leg.kind == "margin" for leg in legs)


def test_a_flat_row_is_not_a_leg():
    rows = [flatten.PositionRow("BTC/EUR", "BTC/EUR.KRAKEN", "FLAT", 0.0)]
    assert flatten.margin_legs(rows, _listing("BTC/EUR")) == ([], [])


def test_an_unrecognised_position_side_is_named_and_never_read_as_flat_or_aborted_on():
    """Two failures at once are refused here. Reading an unknown side as 'nothing to do' would call
    an open position flat; RAISING on it would abort the sweep before the cancel, costing every
    other leg. The installed build's `PositionSide` carries a fourth member, `NO_POSITION_SIDE`,
    and which members the Kraken adapter emits is unmeasured -- so the row is named and the rest of
    the account is still flattened."""
    legs, unclosable = flatten.margin_legs(
        [
            flatten.PositionRow("BTC/EUR", "BTC/EUR.KRAKEN", "NO_POSITION_SIDE", 1.0),
            flatten.PositionRow("ETH/EUR", "ETH/EUR.KRAKEN", "SHORT", 2.0),
        ],
        _listing("BTC/EUR", "ETH/EUR"),
    )
    assert [leg.symbol for leg in legs] == ["ETH/EUR"]
    assert unclosable == [
        {
            "symbol": "BTC/EUR",
            "side": "NO_POSITION_SIDE",
            "quantity": 1.0,
            "reason": "unrecognised_position_side",
            "note": "the venue answered a side this command cannot derive a close from",
        }
    ]


def test_a_margin_row_on_a_pair_the_listing_does_not_carry_is_named_and_never_aborts():
    """The pairless class the whole button turns on: aborting one row among many would cancel
    nothing, close nothing and sell nothing, leaving the operator the entire account by hand."""
    legs, unclosable = flatten.margin_legs(
        [
            flatten.PositionRow("GONE/EUR", "GONE/EUR.KRAKEN", "LONG", 1.0),
            flatten.PositionRow("BTC/EUR", "BTC/EUR.KRAKEN", "SHORT", 0.5),
        ],
        _listing("BTC/EUR"),
    )
    assert [leg.symbol for leg in legs] == ["BTC/EUR"]
    assert unclosable == [
        {
            "symbol": "GONE/EUR",
            "side": "LONG",
            "quantity": 1.0,
            "reason": "pair_not_listed",
            "note": "the listing carries no such pair, so nothing can be sized against it",
        }
    ]


def test_euro_balances_in_either_spelling_are_not_legs():
    legs, unsellable = flatten.spot_legs(
        [flatten.BalanceRow("EUR", 100.0), flatten.BalanceRow("ZEUR", 50.0)], _listing("BTC/EUR")
    )
    assert legs == [] and unsellable == []


def test_a_zero_or_negative_balance_is_not_a_leg():
    legs, unsellable = flatten.spot_legs(
        [flatten.BalanceRow("ADA", 0.0), flatten.BalanceRow("DOT", -1.0)], _listing("ADA/EUR", "DOT/EUR")
    )
    assert legs == [] and unsellable == []


def test_a_classic_asset_code_resolves_through_the_listing_not_through_string_surgery():
    """`XXBT` is the venue's classic spelling of BTC; a sweep that failed to resolve it would leave
    a real BTC balance unsold and call the account flat."""
    legs, unsellable = flatten.spot_legs([flatten.BalanceRow("XXBT", 0.5)], _listing("BTC/EUR"))
    assert unsellable == []
    assert [(leg.base, leg.symbol, leg.side) for leg in legs] == [("BTC", "BTC/EUR", "SELL")]


def test_an_x_prefixed_code_resolves_by_stripping_one_prefix_when_the_listing_lists_it():
    legs, _ = flatten.spot_legs([flatten.BalanceRow("XXRP", 100.0)], _listing("XRP/EUR"))
    assert [leg.symbol for leg in legs] == ["XRP/EUR"]


def test_the_eur_pair_wins_over_the_btc_pair():
    legs, _ = flatten.spot_legs([flatten.BalanceRow("ETH", 2.0)], _listing("ETH/EUR", "ETH/BTC"))
    assert [leg.symbol for leg in legs] == ["ETH/EUR"]


def test_an_asset_with_only_a_btc_pair_sells_against_btc():
    legs, _ = flatten.spot_legs([flatten.BalanceRow("ETH", 2.0)], _listing("ETH/BTC"))
    assert [leg.symbol for leg in legs] == ["ETH/BTC"]


def test_an_asset_with_neither_pair_is_unsellable_and_never_silently_dropped():
    legs, unsellable = flatten.spot_legs([flatten.BalanceRow("WEIRD", 3.0)], _listing("BTC/EUR"))
    assert legs == []
    assert unsellable == [
        {"base": "WEIRD", "code": "WEIRD", "free": 3.0, "reason": "no_eur_or_btc_pair", "note": "no listed base matched the code"}
    ]


def test_an_unresolvable_code_is_reported_in_the_same_class_never_ignored():
    """A code the listing cannot map is not evidence of nothing held -- it is a balance this
    process could not route, and it reads as a residual exactly like a pairless one."""
    _, unsellable = flatten.spot_legs([flatten.BalanceRow("ZZZQ", 1.0)], _listing("BTC/EUR"))
    assert [u["reason"] for u in unsellable] == ["no_eur_or_btc_pair"]
    assert "ZZZQ" in unsellable[0]["code"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_engine_flatten.py -q -k "row or leg or pair or balance or side or code"`
Expected: FAIL with `AttributeError: module 'cli.engine.flatten' has no attribute 'margin_legs'`.

- [ ] **Step 3: Implement**

Append to `cli/engine/flatten.py` (below `step_precision`):

```python
# Kraken's legacy codes, renamed by the adapter's own `normalize_spot_symbol` before an
# InstrumentId is built (`cli/engine/instruments.py`'s module docstring). The `X`/`Z` strip below
# handles the mechanical prefixes; these two renames it cannot derive.
ASSET_ALIASES = {"XBT": "BTC", "XXBT": "BTC", "XDG": "DOGE", "XXDG": "DOGE"}


@dataclass(frozen=True)
class Leg:
    kind: str  # margin | spot
    base: str
    symbol: str
    side: str  # BUY | SELL
    quantity: float
    account_type: str  # MARGIN | CASH
    source: str  # what the quantity came from, for the journal


def listed_bases(listing: dict[str, Any]) -> frozenset[str]:
    return frozenset(symbol.split("/")[0] for symbol in listing)


def resolve_base(code: str, bases: frozenset[str]) -> str | None:
    """Map one balance currency code onto a base the listing actually lists. The LISTING is the
    authority -- a spelling rule alone would invent a base the venue does not trade."""
    upper = code.upper()
    for candidate in (upper, ASSET_ALIASES.get(upper), upper[1:] if len(upper) > 3 and upper[0] in ("X", "Z") else None):
        if candidate and candidate in bases:
            return candidate
    return None


def choose_pair(base: str, listing: dict[str, Any]) -> str | None:
    """EUR first, BTC second, nothing third. Read from the ONE listing taken at the snapshot, never
    from a per-pair request that would error on an unknown pair."""
    for quote in ("EUR", "BTC"):
        symbol = f"{base}/{quote}"
        if symbol in listing:
            return symbol
    return None


def margin_legs(positions: list[PositionRow], listing: dict[str, Any]) -> tuple[list[Leg], list[dict]]:
    """One leg per LONG or SHORT row, plus the rows this code cannot build a closer for.

    A FLAT row is not a leg. Every other row this code cannot act on -- a side that is none of the
    three (the installed `PositionSide` carries a fourth member and which ones the adapter emits is
    unmeasured), a pair the listing does not carry -- is NAMED rather than raised on and never read
    as flat: nothing can be sized for it, and one such row must not abort a button that has not yet
    cancelled an order, closed another position or sold a single balance. `judge_final` reads both
    classes back out of the final snapshot, so neither can leave the run reading 0.
    """
    sides = {"LONG": "SELL", "SHORT": "BUY"}
    out = []
    unclosable: list[dict] = []
    for row in positions:
        if row.side == "FLAT":
            continue
        side = sides.get(row.side)
        if side is None:
            unclosable.append(
                {
                    "symbol": row.symbol,
                    "side": row.side,
                    "quantity": row.quantity,
                    "reason": "unrecognised_position_side",
                    "note": "the venue answered a side this command cannot derive a close from",
                }
            )
            continue
        if row.symbol not in listing:
            unclosable.append(
                {
                    "symbol": row.symbol,
                    "side": row.side,
                    "quantity": row.quantity,
                    "reason": "pair_not_listed",
                    "note": "the listing carries no such pair, so nothing can be sized against it",
                }
            )
            continue
        out.append(
            Leg(
                kind="margin",
                base=row.symbol.split("/")[0],
                symbol=row.symbol,
                side=side,
                quantity=row.quantity,
                account_type="MARGIN",
                source="position_status_report.quantity",
            )
        )
    return out, unclosable


def spot_legs(balances: list[BalanceRow], listing: dict[str, Any]) -> tuple[list[Leg], list[dict]]:
    """One SELL leg per non-EUR free balance above zero, plus the balances no pair can carry.

    `EUR_CODES` is imported rather than restated so the euro's two venue spellings have one home.
    """
    from cli.engine.instruments import EUR_CODES

    bases = listed_bases(listing)
    legs: list[Leg] = []
    unsellable: list[dict] = []
    for row in balances:
        if row.code.upper() in EUR_CODES:
            continue
        if row.free <= 0.0:
            continue
        base = resolve_base(row.code, bases)
        if base is None:
            unsellable.append(
                {
                    "base": row.code,
                    "code": row.code,
                    "free": row.free,
                    "reason": "no_eur_or_btc_pair",
                    "note": "no listed base matched the code",
                }
            )
            continue
        symbol = choose_pair(base, listing)
        if symbol is None:
            unsellable.append(
                {
                    "base": base,
                    "code": row.code,
                    "free": row.free,
                    "reason": "no_eur_or_btc_pair",
                    "note": "the listing carries neither a EUR nor a BTC pair for it",
                }
            )
            continue
        legs.append(
            Leg(
                kind="spot",
                base=base,
                symbol=symbol,
                side="SELL",
                quantity=row.free,
                account_type="CASH",
                source="account_state.free",
            )
        )
    return legs, unsellable
```

Note the test for an unresolvable code expects `"base": row.code` — the code stands in for the base when nothing resolved, so the journal line still names what was held.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_engine_flatten.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add cli/engine/flatten.py tests/test_engine_flatten.py
git commit -m "feat(engine): flatten leg enumeration -- side from the report, base from the listing"
```

Body: the side is derived from `position_side` only because the report's quantity is unsigned; a balance code resolves against the listing rather than by string surgery, and a code that resolves to nothing reads as a residual rather than being ignored.


______________________________________________________________________

### Task 3: Sizing, the dust class, and the one predicate that judges a balance

**Files:**

- Modify: `cli/engine/flatten.py`
- Test: `tests/test_engine_flatten.py`

**Interfaces:**

- Consumes from Tasks 1–2: `PairConstraints`, `Leg`, `TAKER_RATE`.
- Produces:
  - `costmin_for(symbol: str) -> float | None`
  - `classify_balance(free: float, constraints: PairConstraints, reference_price: float | None) -> str` — `"flat"`, `"dust"` or `"residual"`.
  - `@dataclass(frozen=True) class SizedLeg: leg: Leg; qty: float; reference_price: float | None; quote: str; estimate: float | None; fee_estimate: float | None; send: bool; reason: str | None`
  - `size_leg(leg: Leg, constraints: PairConstraints, reference_price: float | None) -> SizedLeg`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_engine_flatten.py`:

```python
# --- sizing and the dust class ------------------------------------------------------------------

_ADA = flatten.PairConstraints("ADA/EUR", "ADA/EUR.KRAKEN", ordermin=15.0, lot_step=0.00000001, tick_size=0.000001)
_BTC = flatten.PairConstraints("BTC/EUR", "BTC/EUR.KRAKEN", ordermin=0.0001, lot_step=0.00000001, tick_size=0.1)
_ETHBTC = flatten.PairConstraints("ETH/BTC", "ETH/BTC.KRAKEN", ordermin=0.004, lot_step=0.00001, tick_size=0.0000001)
_UNLISTED = flatten.PairConstraints("WEIRD/EUR", "WEIRD/EUR.KRAKEN", ordermin=1.0, lot_step=0.001, tick_size=0.001)


def test_costmin_comes_from_the_committed_constant_and_only_when_the_quote_matches(monkeypatch):
    """The adapter never maps costmin onto min_notional, so it is committed per symbol and
    quote-explicit; comparing a BTC-quoted floor against a EUR notional would pass everything.

    The mismatch is CONSTRUCTED here rather than found: every quote-matching entry would pass under
    a `costmin_for` that dropped the check, so the last two lines are the only ones that read it."""
    from cli.engine import instruments

    assert flatten.costmin_for("ADA/EUR") == 0.45
    assert flatten.costmin_for("ETH/BTC") == 2e-05
    assert flatten.costmin_for("WEIRD/EUR") is None

    monkeypatch.setitem(instruments.COSTMIN, "ADA/EUR", (0.45, "BTC"))
    assert flatten.costmin_for("ADA/EUR") is None


def test_a_balance_below_ordermin_is_dust_and_one_above_every_floor_is_a_residual():
    assert flatten.classify_balance(10.0, _ADA, 0.40) == "dust"
    assert flatten.classify_balance(1200.0, _ADA, 0.40) == "residual"
    assert flatten.classify_balance(0.0, _ADA, 0.40) == "flat"


def test_a_balance_over_ordermin_but_under_costmin_is_still_dust():
    """Both floors apply; clearing one is not clearing them. 16 ADA at 0.02 EUR is 0.32 EUR, under
    the 0.45 EUR costmin."""
    assert flatten.classify_balance(16.0, _ADA, 0.02) == "dust"


def test_a_pair_with_no_committed_costmin_is_judged_on_ordermin_alone():
    assert flatten.classify_balance(2.0, _UNLISTED, 0.01) == "residual"


def test_a_balance_with_no_reference_price_is_judged_on_ordermin_alone():
    """No post-write book read ever happens, so a leg that surfaces only in a later pass has no
    price; judging it on ordermin alone is what keeps it from being skipped as dust unmeasured."""
    assert flatten.classify_balance(1200.0, _ADA, None) == "residual"
    assert flatten.classify_balance(10.0, _ADA, None) == "dust"


def test_a_quantity_that_clears_ordermin_only_before_flooring_is_dust():
    """The floors run on the POST-floor quantity -- the venue would reject an order sized on the
    pre-floor one. `ordermin` sits strictly BETWEEN 1.9 and its floored value 1.0, so an
    implementation checking the pre-floor quantity reads `residual` where this reads `dust`; 2.9,
    which floors to 2.0, is the true negative that keeps the fixture from refusing everything."""
    coarse = flatten.PairConstraints("X/EUR", "X/EUR.KRAKEN", ordermin=1.5, lot_step=1.0, tick_size=0.01)
    assert flatten.classify_balance(1.9, coarse, 100.0) == "dust"
    assert flatten.classify_balance(2.9, coarse, 100.0) == "residual"


def test_a_spot_leg_below_a_floor_is_listed_and_not_sent():
    leg = flatten.Leg("spot", "ADA", "ADA/EUR", "SELL", 10.0, "CASH", "account_state.free")
    sized = flatten.size_leg(leg, _ADA, 0.40)
    assert sized.send is False
    assert sized.reason == "dust_below_venue_minimum"
    assert sized.qty == 10.0


def test_a_spot_leg_above_every_floor_is_sent_with_its_estimate_in_its_own_quote():
    leg = flatten.Leg("spot", "ADA", "ADA/EUR", "SELL", 1200.0, "CASH", "account_state.free")
    sized = flatten.size_leg(leg, _ADA, 0.40)
    assert sized.send is True and sized.reason is None
    assert sized.qty == 1200.0
    assert sized.quote == "EUR"
    assert sized.estimate == pytest.approx(480.0)
    assert sized.fee_estimate == pytest.approx(480.0 * flatten.TAKER_RATE)


def test_a_btc_quoted_leg_estimates_in_btc_and_never_in_euros():
    """No FX rate is invented; a BTC-quoted estimate stays BTC-quoted."""
    leg = flatten.Leg("spot", "ETH", "ETH/BTC", "SELL", 2.0, "CASH", "account_state.free")
    sized = flatten.size_leg(leg, _ETHBTC, 0.03)
    assert sized.quote == "BTC"
    assert sized.estimate == pytest.approx(0.06)


def test_a_margin_leg_is_never_dust_and_is_sent_below_every_floor():
    """The engine's own machine deliberately produces sub-ordermin remainders, and a remainder left
    open is exposure -- so the closer is sent and the venue rules on it."""
    leg = flatten.Leg("margin", "BTC", "BTC/EUR", "SELL", 0.00001, "MARGIN", "position_status_report.quantity")
    sized = flatten.size_leg(leg, _BTC, 60000.0)
    assert sized.send is True and sized.reason is None
    assert sized.qty == 0.00001


def test_a_margin_quantity_that_floors_to_zero_is_unclosable_here_and_named_as_such():
    """There is no order to send; the row stays in the final snapshot, and only the venue's own UI
    settle-position can clear it."""
    coarse = flatten.PairConstraints("X/EUR", "X/EUR.KRAKEN", ordermin=1.0, lot_step=1.0, tick_size=0.01)
    leg = flatten.Leg("margin", "X", "X/EUR", "SELL", 0.4, "MARGIN", "position_status_report.quantity")
    sized = flatten.size_leg(leg, coarse, 100.0)
    assert sized.send is False
    assert sized.reason == "unclosable_below_minimum"


def test_a_margin_leg_quantity_never_exceeds_the_report_s_own():
    """Flooring may only reduce. A closer larger than the position would open the other way."""
    leg = flatten.Leg("margin", "X", "X/EUR", "SELL", 1.999, "MARGIN", "position_status_report.quantity")
    coarse = flatten.PairConstraints("X/EUR", "X/EUR.KRAKEN", ordermin=0.5, lot_step=0.5, tick_size=0.01)
    sized = flatten.size_leg(leg, coarse, 100.0)
    assert sized.qty == 1.5
    assert sized.qty <= leg.quantity


def test_the_send_decision_and_the_residual_verdict_cannot_disagree():
    """One predicate serves both, so a balance skipped as dust can never be reported as a residual
    -- the contradiction that would tell an operator the account is both flat and not."""
    for free in (0.0, 5.0, 14.999, 15.0, 1200.0):
        leg = flatten.Leg("spot", "ADA", "ADA/EUR", "SELL", free, "CASH", "account_state.free")
        sized = flatten.size_leg(leg, _ADA, 0.40)
        assert sized.send is (flatten.classify_balance(free, _ADA, 0.40) == "residual")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_engine_flatten.py -q -k "costmin or ordermin or dust or residual or floor or leg"`
Expected: FAIL — `module 'cli.engine.flatten' has no attribute 'costmin_for'`.

- [ ] **Step 3: Implement**

Append to `cli/engine/flatten.py`:

```python
@dataclass(frozen=True)
class SizedLeg:
    leg: Leg
    qty: float
    reference_price: float | None
    quote: str
    estimate: float | None
    fee_estimate: float | None
    send: bool
    reason: str | None


def costmin_for(symbol: str) -> float | None:
    """The committed per-symbol notional floor, or None when it does not apply to this pair.

    It is committed rather than read live because the adapter never maps Kraken's `costmin` onto
    `min_notional` (`cli/engine/venuestate.py`), and it applies only where its own quote matches
    the pair's -- a BTC-denominated floor compared against a EUR notional passes everything.
    """
    from cli.engine.instruments import COSTMIN

    entry = COSTMIN.get(symbol)
    if entry is None:
        return None
    amount, quote = entry
    return amount if quote == symbol.split("/")[1] else None


def _size(free: float, constraints: PairConstraints, reference_price: float | None):
    """`size_order`'s verdict on one quantity -- the engine's own arithmetic, floors and all.

    A floor that does not apply is passed as 0.0 rather than skipped, so there is ONE call and no
    second flooring implementation beside the one the engine trusts. An absent reference price
    therefore disables only the notional floor, never the quantity one.
    """
    from cli.engine.instruments import size_order

    costmin = costmin_for(constraints.symbol)
    applicable = costmin if (costmin is not None and reference_price is not None) else 0.0
    return size_order(
        free,
        reference_price if reference_price is not None else 0.0,
        ordermin=constraints.ordermin,
        costmin=applicable,
        lot_step=constraints.lot_step,
        tick_size=constraints.tick_size,
    )


def classify_balance(free: float, constraints: PairConstraints, reference_price: float | None) -> str:
    """`flat` / `dust` / `residual` for one non-EUR free balance.

    THE predicate: the sweep's send decision and the final snapshot's residual verdict both read
    it, so a balance skipped as dust can never also be reported as a residual.
    """
    from cli.engine.instruments import BelowMinimum

    if free <= 0.0:
        return "flat"
    return "dust" if isinstance(_size(free, constraints, reference_price), BelowMinimum) else "residual"


def size_leg(leg: Leg, constraints: PairConstraints, reference_price: float | None) -> SizedLeg:
    """One leg's order quantity and whether it is sent at all.

    A margin closer is sent regardless of the floors -- the engine's machine deliberately produces
    sub-`ordermin` remainders and a remainder left open is exposure, so the venue rules on it. Its
    only unsendable case is a quantity that floors to nothing: there is no order to construct.
    A spot leg below any applicable floor is listed and not sent; the venue would reject it, and it
    does not make the account not-flat.
    """
    from cli.engine.instruments import _floor_to_step

    quote = constraints.symbol.split("/")[1]
    qty = _floor_to_step(leg.quantity, constraints.lot_step)
    # Floored to the tick before anything reads it: `size_order` runs its notional check at the
    # floored price, so an estimate printed off the raw book price would disagree with the dust
    # boundary this same leg is judged by.
    price = _floor_to_step(reference_price, constraints.tick_size) if reference_price is not None else None
    estimate = qty * price if price is not None else None
    fee = estimate * TAKER_RATE if estimate is not None else None
    base = dict(leg=leg, qty=qty, reference_price=price, quote=quote, estimate=estimate, fee_estimate=fee)

    if leg.kind == "margin":
        if qty <= 0.0:
            return SizedLeg(**base, send=False, reason="unclosable_below_minimum")
        return SizedLeg(**base, send=True, reason=None)

    if classify_balance(leg.quantity, constraints, price) == "residual":
        return SizedLeg(**base, send=True, reason=None)
    return SizedLeg(**base, send=False, reason="dust_below_venue_minimum")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_engine_flatten.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add cli/engine/flatten.py tests/test_engine_flatten.py
git commit -m "feat(engine): flatten sizing -- one predicate for dust and for the residual verdict"
```

Body: dust is a spot-only class; a margin closer is sent below every floor because a remainder left open is exposure; `size_order` is reused so there is no second flooring implementation beside the one the engine trusts.

______________________________________________________________________

### Task 4: The snapshot, the plan, and what the operator reads

**Files:**

- Modify: `cli/engine/flatten.py`
- Test: `tests/test_engine_flatten.py`

**Interfaces:**

- Consumes from Tasks 1–3: every symbol above.
- Produces:
  - `@dataclass(frozen=True) class Snapshot: orders: list[Any]; positions: list[PositionRow]; balances: list[BalanceRow]`
  - `read_snapshot(client, rec) -> Snapshot` — orders, then positions, then balances, in that order.
  - `@dataclass(frozen=True) class Plan: margin: list[SizedLeg]; spot: list[SizedLeg]; unsellable: list[dict]; unclosable: list[dict]; prices: dict[str, float]; constraints: dict[str, PairConstraints]; n_open_orders: int`
  - `build_plan(client, rec, snapshot: Snapshot, listing: dict[str, Any]) -> Plan`
  - `render_plan(plan: Plan, echo: Callable[[str], None]) -> None`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_engine_flatten.py`:

```python
# --- the snapshot and the plan ------------------------------------------------------------------


def _client_with(*, orders=None, positions=None, balances=None, symbols=(), books=None):
    rows = [_Instrument(s) for s in symbols]
    return FakeClient(
        instruments=rows,
        orders=[orders or []],
        positions=[positions or []],
        balances=[balances or []],
        books=books or {},
    )


def test_the_snapshot_reads_orders_then_positions_then_balances():
    """Order matters: an order that fills between the reads must land in a read that FOLLOWS, so
    it cannot vanish from both."""
    client = _client_with(symbols=("BTC/EUR",))
    flatten.read_snapshot(client, flatten.Recorder())
    assert names(client) == ["request_order_status_reports", "request_position_status_reports", "request_account_state"]


def test_the_plan_reads_one_book_per_leg_pair_and_the_btc_euro_pair_when_a_leg_routes_through_btc():
    """Every book read happens before the first write, so a shape the venue changed aborts with
    nothing half-done -- which means pass two's BTC sell needs its price taken here, not later."""
    client = _client_with(
        balances=[_Balance("ETH", 2.0)],
        symbols=("ETH/BTC", "BTC/EUR"),
        books={"ETH/BTC.KRAKEN": _Book(0.03, 0.031), "BTC/EUR.KRAKEN": _Book(60000.0, 60010.0)},
    )
    rec = flatten.Recorder()
    listing = flatten.read_listing(client, rec)
    snapshot = flatten.read_snapshot(client, rec)
    plan = flatten.build_plan(client, rec, snapshot, listing)
    assert sorted(plan.prices) == ["BTC/EUR", "ETH/BTC"]
    assert plan.prices["ETH/BTC"] == 0.03


def test_no_btc_euro_book_is_read_when_no_leg_routes_through_btc():
    client = _client_with(
        balances=[_Balance("ADA", 1200.0)], symbols=("ADA/EUR", "BTC/EUR"), books={"ADA/EUR.KRAKEN": _Book(0.4, 0.41)}
    )
    rec = flatten.Recorder()
    listing = flatten.read_listing(client, rec)
    plan = flatten.build_plan(client, rec, flatten.read_snapshot(client, rec), listing)
    assert sorted(plan.prices) == ["ADA/EUR"]


def test_a_short_leg_prices_off_the_ask_and_a_long_off_the_bid():
    """Both halves the name claims, so neither side of the mapping can be wired to the other."""
    client = _client_with(
        positions=[_Position("BTC/EUR", "SHORT", 0.5), _Position("ETH/EUR", "LONG", 1.0)],
        symbols=("BTC/EUR", "ETH/EUR"),
        books={"BTC/EUR.KRAKEN": _Book(60000.0, 60010.0), "ETH/EUR.KRAKEN": _Book(3000.0, 3001.0)},
    )
    rec = flatten.Recorder()
    listing = flatten.read_listing(client, rec)
    plan = flatten.build_plan(client, rec, flatten.read_snapshot(client, rec), listing)
    assert plan.prices["BTC/EUR"] == 60010.0  # SHORT -> the closer BUYs -> priced off the ask
    assert plan.prices["ETH/EUR"] == 3000.0  # LONG -> the closer SELLs -> priced off the bid


def test_a_book_read_failure_on_one_leg_never_aborts_the_plan_or_any_other_leg():
    """The abort that would cost everything: the kill file is latched and the engine stopped by the
    time this runs, so raising here returns exit 3 with nothing cancelled, closed or sold. The ADA
    book is absent, so its read raises where the BTC one answers -- and the ADA leg is still sized
    and still sent, on the quantity floor alone."""
    client = _client_with(
        positions=[_Position("BTC/EUR", "LONG", 0.5)],
        balances=[_Balance("ADA", 1200.0)],
        symbols=("BTC/EUR", "ADA/EUR"),
        books={"BTC/EUR.KRAKEN": _Book(60000.0, 60010.0)},
    )
    rec = flatten.Recorder()
    listing = flatten.read_listing(client, rec)
    plan = flatten.build_plan(client, rec, flatten.read_snapshot(client, rec), listing)
    assert plan.prices == {"BTC/EUR": 60000.0}
    assert [sized.leg.symbol for sized in plan.spot] == ["ADA/EUR"]
    assert plan.spot[0].send is True and plan.spot[0].reference_price is None
    assert [sized.leg.symbol for sized in plan.margin] == ["BTC/EUR"]


def test_a_book_that_prices_at_zero_leaves_the_leg_unpriced_and_still_sold():
    """The degradation is what makes refusing a zero price safe: the leg is sized on the quantity
    floor alone and SENT, exactly as one whose book read raised. Carried instead, the zero would
    make it dust -- not sent, not a residual, and the run would report flat while still holding
    it."""
    zero = _Book(0.4, 0.41)
    zero.bids = [_Level(0.0)]
    client = _client_with(balances=[_Balance("ADA", 1200.0)], symbols=("ADA/EUR",), books={"ADA/EUR.KRAKEN": zero})
    rec = flatten.Recorder()
    listing = flatten.read_listing(client, rec)
    plan = flatten.build_plan(client, rec, flatten.read_snapshot(client, rec), listing)
    assert plan.prices == {}
    (sized,) = plan.spot
    assert sized.send is True and sized.reference_price is None


def test_a_missing_constraint_on_a_leg_s_pair_aborts_the_plan():
    rows = [_Instrument("ADA/EUR")]
    rows[0].min_quantity = None
    client = FakeClient(instruments=rows, balances=[[_Balance("ADA", 1200.0)]], books={"ADA/EUR.KRAKEN": _Book(0.4, 0.41)})
    rec = flatten.Recorder()
    listing = flatten.read_listing(client, rec)
    with pytest.raises(flatten.FlattenUnreachable):
        flatten.build_plan(client, rec, flatten.read_snapshot(client, rec), listing)


def test_the_rendered_plan_names_every_leg_every_dust_line_and_everything_it_cannot_touch():
    """What the operator reads has to include what the sweep will NOT do -- a balance no pair can
    carry and a position whose pair the listing does not have are both still there afterwards."""
    client = _client_with(
        orders=[object()],
        positions=[_Position("BTC/EUR", "LONG", 0.5), _Position("GONE/EUR", "LONG", 1.0)],
        balances=[_Balance("ADA", 1200.0), _Balance("DOT", 0.001), _Balance("WEIRD", 3.0)],
        symbols=("BTC/EUR", "ADA/EUR", "DOT/EUR"),
        books={
            "BTC/EUR.KRAKEN": _Book(60000.0, 60010.0),
            "ADA/EUR.KRAKEN": _Book(0.4, 0.41),
            "DOT/EUR.KRAKEN": _Book(4.0, 4.01),
        },
    )
    rec = flatten.Recorder()
    listing = flatten.read_listing(client, rec)
    plan = flatten.build_plan(client, rec, flatten.read_snapshot(client, rec), listing)
    lines: list[str] = []
    flatten.render_plan(plan, lines.append)
    text = "\n".join(lines)
    assert "BTC/EUR" in text and "SELL" in text
    assert "ADA/EUR" in text
    assert "DOT/EUR" in text and "not sent" in text
    assert "WEIRD" in text
    assert "GONE/EUR" in text and "cannot be closed here" in text
    assert "1 resting order" in text


def test_the_rendered_plan_prints_no_cross_currency_total():
    """A BTC-quoted estimate and a EUR one are not summable without an FX rate this command has no
    mandate to invent, so no grand total is printed at all."""
    client = _client_with(
        balances=[_Balance("ETH", 2.0)],
        symbols=("ETH/BTC", "BTC/EUR"),
        books={"ETH/BTC.KRAKEN": _Book(0.03, 0.031), "BTC/EUR.KRAKEN": _Book(60000.0, 60010.0)},
    )
    rec = flatten.Recorder()
    listing = flatten.read_listing(client, rec)
    plan = flatten.build_plan(client, rec, flatten.read_snapshot(client, rec), listing)
    lines: list[str] = []
    flatten.render_plan(plan, lines.append)
    assert not any("total" in line.lower() for line in lines)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_engine_flatten.py -q -k "snapshot or plan or book or prices_off"`
Expected: FAIL — `module 'cli.engine.flatten' has no attribute 'read_snapshot'`.

- [ ] **Step 3: Implement**

Append to `cli/engine/flatten.py`:

```python
@dataclass(frozen=True)
class Snapshot:
    orders: list
    positions: list
    balances: list


@dataclass(frozen=True)
class Plan:
    margin: list
    spot: list
    unsellable: list
    unclosable: list
    prices: dict
    constraints: dict
    n_open_orders: int


def read_snapshot(client: Any, rec: Recorder) -> Snapshot:
    """Orders, then positions, then balances -- in that order, so an order that fills between two
    of the reads lands in one that FOLLOWS rather than falling out of both."""
    return Snapshot(
        orders=read_open_orders(client, rec),
        positions=read_positions(client, rec),
        balances=read_balances(client, rec),
    )


def build_plan(client: Any, rec: Recorder, snapshot: Snapshot, listing: dict[str, Any]) -> Plan:
    """Every leg, sized, with its reference price -- and every book read taken HERE, before the
    first write.

    `BTC/EUR` is priced whenever a SPOT leg routes through a `/BTC` pair, because the second spot
    pass sells the BTC those legs produce and no read may happen after the first write. A leg with
    no price here -- one that surfaces only in a later pass, a margin leg's `/BTC` proceeds
    included, and equally one whose OWN book read failed -- is sized on the quantity floor alone,
    which is the safe direction: an unpriced balance is sold, never skipped as dust.

    A failing book read is the one pre-write read failure that does not abort (spec D2). Aborting
    here would return exit 3 with the kill file already latched and the engine already stopped: no
    order cancelled, no position closed, no balance sold, over one illiquid pair's empty side.
    """
    margin_raw, unclosable = margin_legs(snapshot.positions, listing)
    spot_raw, unsellable = spot_legs(snapshot.balances, listing)

    wanted: dict[str, str] = {}
    for leg in [*margin_raw, *spot_raw]:
        # One book read per pair, and the FIRST leg on a pair fixes which side it is priced from --
        # margin legs first. Where a margin leg and a spot leg share a pair the loser is priced one
        # spread away, which moves the printed estimate and the dust boundary and nothing else: no
        # order this module sends carries a price.
        wanted.setdefault(leg.symbol, leg.side)
    if any(leg.symbol.endswith("/BTC") for leg in spot_raw) and "BTC/EUR" in listing:
        wanted.setdefault("BTC/EUR", "SELL")

    constraints = {symbol: constraints_for(symbol, listing) for symbol in wanted}
    prices: dict[str, float] = {}
    for symbol, side in wanted.items():
        try:
            prices[symbol] = read_book_price(client, rec, constraints[symbol], side)
        except FlattenUnreachable as exc:
            # Spec D2's ONE exception to abort-on-a-pre-write-read-failure. A thin pair with an
            # empty side, or one rate-limited request, must not cost the account its cancel and
            # every other leg its close: the price is never an order price here (every order is
            # MARKET), so the leg is sized on the quantity floor alone and sent.
            logger.error("%s: no reference price -- sized on the quantity floor alone: %s", symbol, exc)

    return Plan(
        margin=[size_leg(leg, constraints[leg.symbol], prices.get(leg.symbol)) for leg in margin_raw],
        spot=[size_leg(leg, constraints[leg.symbol], prices.get(leg.symbol)) for leg in spot_raw],
        unsellable=unsellable,
        unclosable=unclosable,
        prices=prices,
        constraints=constraints,
        n_open_orders=len(snapshot.orders),
    )


def _leg_line(sized: SizedLeg) -> str:
    head = f"  {sized.leg.kind:<6} {sized.leg.symbol} {sized.leg.side} {sized.qty:.8f}".rstrip()
    if not sized.send:
        return f"{head} -- below the venue minimum: not sent"
    tail = "market, reduce-only" if sized.leg.kind == "margin" else "market"
    if sized.estimate is not None:
        tail += f", about {sized.estimate:.8f} {sized.quote}, fee about {sized.fee_estimate:.8f} {sized.quote}"
    else:
        tail += ", no reference price read"
    return f"{head} -- {tail}"


def render_plan(plan: Plan, echo: Callable[[str], None]) -> None:
    """What an operator reads before typing the word. Estimates stay in each leg's own quote
    currency and no grand total is printed -- summing a BTC-quoted leg into a euro figure would
    need an FX rate this command has no mandate to invent."""
    echo(f"{plan.n_open_orders} resting order(s) will be cancelled account-wide")
    if not plan.margin:
        echo("no margin position to close")
    for sized in plan.margin:
        echo(_leg_line(sized))
    if not plan.spot:
        echo("no non-EUR spot balance to sell")
    for sized in plan.spot:
        echo(_leg_line(sized))
    for row in plan.unsellable:
        echo(f"  balance {row['code']} {row['free']:.8f} -- neither a EUR nor a BTC pair: it cannot be sold from here")
    for row in plan.unclosable:
        # The row's own `note`, not one hard-coded sentence: two different classes land here (a pair
        # the listing does not carry, a side no closer can be derived from) and printing either as
        # the other tells the operator the wrong thing to go and do on Kraken.
        echo(f"  {row['symbol']} {row['side']} {row['quantity']:.8f} -- {row['note']}: it cannot be closed here")
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_engine_flatten.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add cli/engine/flatten.py tests/test_engine_flatten.py
git commit -m "feat(engine): the flatten snapshot and the plan an operator reads before the word"
```

Body: the snapshot's read order is orders-then-positions-then-balances so a fill between reads cannot fall out of both; every book read is taken pre-write, including `BTC/EUR` whenever a leg routes through a `/BTC` pair, so the second spot pass never needs a read after the first write.

______________________________________________________________________

### Task 5: Widen the structural guard before the module gains a mutating call

This task lands **before** `cli/engine/flatten.py` names `submit_order`, so the guard is green on both sides of the change it guards rather than red in between.

**Files:**

- Modify: `tests/test_engine_executor.py:155-170`

**Interfaces:**

- Consumes: nothing.
- Produces: `_VENUE_MUTATING_NAMES` gains `".cancel_all_orders"`; the walk's skip-list becomes `{"cli/engine/executor.py", "cli/engine/flatten.py"}`.

- [ ] **Step 1: Widen the guard and its docstring**

In `tests/test_engine_executor.py`, replace lines 155–170 with:

```python
_VENUE_MUTATING_NAMES = (".submit_order", ".cancel_order", ".cancel_all_orders", ".order_factory")
# The engine's order machine and the red button, and nothing else. `cli/engine/flatten.py` is a
# second venue-mutating module BY DESIGN (spec 00106 D7): the button has to work when the machine
# is what broke, so the two deliberately share no code path, and the price of that is a second
# entry here rather than a guard that reuse would have satisfied.
_VENUE_MUTATING_MODULES = frozenset({"cli/engine/executor.py", "cli/engine/flatten.py"})


def test_the_venue_mutating_names_have_exactly_one_module():
    """D4's structural pin, widened by spec 00106 D7: all venue-mutating calls live in
    cli/engine/executor.py or cli/engine/flatten.py. A text walk, not an import walk -- a reference
    in a comment is still a reference a refactor can activate. `cancel_order` is on the list because
    the maker-first ladder cancels: a cancel reaches the venue exactly as a submit does, so a second
    module learning to cancel is the same escape. `cancel_all_orders` is on it because an
    account-wide cancel is the largest cancel there is."""
    offenders = []
    for path in sorted(Path("cli").rglob("*.py")):
        if path.as_posix() in _VENUE_MUTATING_MODULES:
            continue
        text = path.read_text()
        if any(name in text for name in _VENUE_MUTATING_NAMES):
            offenders.append(path.as_posix())
    assert offenders == []
```

- [ ] **Step 2: Run the test to verify it is still green**

Run: `uv run pytest tests/test_engine_executor.py::test_the_venue_mutating_names_have_exactly_one_module -q`
Expected: PASS. `cli/engine/flatten.py` does not yet name a mutating call, and no module names `.cancel_all_orders`, so widening changes no verdict today.

- [ ] **Step 3: Prove the widened guard actually bites**

Construct the defect it names and watch it trip:

```bash
printf 'def escape(client):\n    return client.cancel_all_orders()\n' > cli/engine/_offender.py
uv run pytest tests/test_engine_executor.py::test_the_venue_mutating_names_have_exactly_one_module -q
```

Expected: FAIL, with `cli/engine/_offender.py` in the offenders list. A pass here means the widened name is not being matched and the task is not done.

```bash
rm cli/engine/_offender.py
uv run pytest tests/test_engine_executor.py::test_the_venue_mutating_names_have_exactly_one_module -q
```

Expected: PASS again, and `git status` clean apart from the test file.

- [ ] **Step 4: Commit**

```bash
git add tests/test_engine_executor.py
git commit -m "test(engine): the venue-mutating guard admits the red button and gains the account-wide cancel"
```

Body: records that the guard was seen red against a constructed third module naming `cancel_all_orders`, and green again once it was removed.

______________________________________________________________________

### Task 6: The gates and the confirm

**Files:**

- Modify: `cli/engine/flatten.py`
- Test: `tests/test_engine_flatten.py`

**Interfaces:**

- Consumes from Tasks 1–4: `FlattenRefused`, `FlattenUnreachable`, `CONFIRM_WORD`.
- Produces:
  - `CONFIRM_PROMPT: str`
  - `kill_file_path(state_dir: Path) -> Path`
  - `check_kill_file(state_dir: Path) -> str` — the file's text; raises `FlattenRefused` when absent.
  - `terminal_available() -> bool`
  - `read_confirm(prompt_text: str) -> str`
  - `matches_confirm(reply: str) -> bool`
  - `check_venue(venue_reader, now) -> Any` — the `VenueStatus`; raises `FlattenUnreachable` when not `online`.

- [ ] **Step 1: Write the failing tests**

Add to the imports at the top of `tests/test_engine_flatten.py`: `import os`, `import pty`, `from datetime import datetime, timezone`, `from pathlib import Path`. Then append:

```python
# --- the gates and the confirm ------------------------------------------------------------------


def _exec_dir(tmp_path: Path) -> Path:
    d = tmp_path / "exec"
    d.mkdir(parents=True, exist_ok=True)
    return d


def test_an_absent_kill_file_refuses(tmp_path):
    """The file is load-bearing: without it nothing stops the engine re-opening what this sweep
    closes, so the sweep does not start."""
    _exec_dir(tmp_path)
    with pytest.raises(flatten.FlattenRefused):
        flatten.check_kill_file(tmp_path)


def test_a_present_kill_file_passes_and_its_text_is_returned_for_the_record(tmp_path):
    (_exec_dir(tmp_path) / "kill").write_text("2026-08-30T12:00:00+00:00 flatten\n")
    assert "flatten" in flatten.check_kill_file(tmp_path)


def test_the_kill_file_path_is_the_engine_s_own(tmp_path):
    """One control-file directory. A second spelling here is a kill file the engine never reads."""
    from cli.engine.execgate import KILL_FILE, exec_dir

    assert flatten.kill_file_path(tmp_path) == exec_dir(tmp_path) / KILL_FILE


def test_a_venue_that_is_not_online_aborts():
    from cli.engine.venue import VenueStatus

    now = datetime(2026, 8, 30, 12, tzinfo=timezone.utc)
    ok = VenueStatus(status="online", ok=True, observed_at=now)
    bad = VenueStatus(status="maintenance", ok=False, observed_at=now)
    assert flatten.check_venue(lambda **_: ok, now).status == "online"
    with pytest.raises(flatten.FlattenUnreachable) as exc:
        flatten.check_venue(lambda **_: bad, now)
    assert "maintenance" in str(exc.value)


@pytest.mark.parametrize(
    ("reply", "expected"),
    [("FLATTEN", True), ("  FLATTEN  ", True), ("flatten", False), ("FLATTE", False), ("", False), ("y", False)],
)
def test_only_the_exact_word_matches(reply, expected):
    """Case-sensitive and exact: a red button that accepts `y` is a button pressed by accident."""
    assert flatten.matches_confirm(reply) is expected


def test_the_prompt_names_the_word_and_says_what_pressing_it_does():
    assert flatten.CONFIRM_WORD in flatten.CONFIRM_PROMPT
    assert "market" in flatten.CONFIRM_PROMPT
    assert "aborts" in flatten.CONFIRM_PROMPT


def test_the_confirm_reads_the_controlling_terminal_and_never_stdin(tmp_path):
    """A pipe or a heredoc must not be able to drive the confirm (converge.sh's rule). The child's
    stdin is EMPTY here, so an implementation reading stdin raises instead of returning the word."""
    out = tmp_path / "reply.txt"
    pid, fd = pty.fork()
    if pid == 0:  # child: the pty is its controlling terminal
        try:
            os.dup2(os.open(os.devnull, os.O_RDONLY), 0)
            from cli.engine import flatten as child_flatten

            out.write_text(child_flatten.read_confirm("word? "))
        except BaseException as exc:  # noqa: BLE001 -- the child reports, it does not raise into pytest
            out.write_text(f"ERROR {type(exc).__name__}")
        finally:
            os._exit(0)
    os.write(fd, b"FLATTEN\n")
    os.waitpid(pid, 0)
    os.close(fd)
    assert out.read_text().strip() == "FLATTEN"


def test_the_terminal_check_answers_false_with_no_controlling_terminal(tmp_path):
    """Refusing early costs nothing and saves an operator five venue reads before the refusal."""
    out = tmp_path / "answer.txt"
    pid = os.fork()
    if pid == 0:
        try:
            try:
                os.setsid()  # a fresh session has no controlling terminal
            except PermissionError:
                # The child inherited a session it already leads, so it cannot start a fresh one and
                # cannot shed the terminal. Said out loud: a parent reading no file at all could not
                # tell that apart from a crash in the check under test.
                out.write_text("SESSION-LEADER")
            else:
                from cli.engine import flatten as child_flatten

                out.write_text(str(child_flatten.terminal_available()))
        except BaseException as exc:  # noqa: BLE001 -- the child reports, it does not raise into pytest
            # Without this the parent reads a file that was never written: a FileNotFoundError at
            # `out.read_text()` instead of an assertion naming what went wrong inside the check.
            out.write_text(f"ERROR {type(exc).__name__}")
        finally:
            os._exit(0)
    os.waitpid(pid, 0)
    answer = out.read_text()
    if answer == "SESSION-LEADER":
        pytest.skip("the test process already leads its session, so the child cannot start a new one")
    assert answer == "False"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_engine_flatten.py -q -k "kill_file or venue or confirm or terminal or prompt or exact_word"`
Expected: FAIL — `module 'cli.engine.flatten' has no attribute 'check_kill_file'`.

- [ ] **Step 3: Implement**

Append to `cli/engine/flatten.py`:

```python
CONFIRM_PROMPT = (
    f"Type {CONFIRM_WORD} to close every position and sell every non-EUR balance at market, anything else aborts: "
)


def kill_file_path(state_dir):
    """The engine's own control file, not a second spelling of it -- a kill file the engine does
    not read stops nothing."""
    from cli.engine.execgate import KILL_FILE, exec_dir

    return exec_dir(state_dir) / KILL_FILE


def check_kill_file(state_dir) -> str:
    """Present or refuse. Without it, the engine's next start re-opens what this sweep closes; the
    host wrapper writes it before it stops the unit, so an absent one means the button was invoked
    some other way."""
    path = kill_file_path(state_dir)
    try:
        return path.read_text()
    except OSError as exc:
        raise FlattenRefused(
            f"the kill file {path} is absent or unreadable -- nothing was sent; place it and run this again"
        ) from exc


def terminal_available() -> bool:
    """Whether a controlling terminal exists at all. Checked before any venue read, so a session
    that could never answer the confirm is refused without spending five requests on it."""
    try:
        with open("/dev/tty", "rb"):
            return True
    except OSError:
        return False


def read_confirm(prompt_text: str) -> str:
    """The typed word, read from the controlling terminal and NEVER from stdin: a pipe or a heredoc
    must not be able to press this button (`infra/ansible/scripts/converge.sh`'s rule). There is
    deliberately no flag that skips it -- a red button pressed by a script is a different product.

    TWO opens, never one `"r+"`: text `"r+"` builds a buffered random-access stream, which requires
    a seekable file, and a tty is not one -- it raises `io.UnsupportedOperation` before a word is
    ever read.
    """
    with open("/dev/tty", "w") as out:
        out.write(prompt_text)
        out.flush()
    with open("/dev/tty", "r") as tty:
        return (tty.readline() or "").strip()


def matches_confirm(reply: str) -> bool:
    return reply.strip() == CONFIRM_WORD


def check_venue(venue_reader, now):
    """The public unsigned status endpoint the execution gate already uses, with its own 10 s
    timeout. It never raises, so a refusal here is a reading and not an exception."""
    status = venue_reader(now=now)
    if not status.ok:
        raise FlattenUnreachable(f"the venue is not online (it reads {status.status!r}) -- nothing was sent")
    return status
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_engine_flatten.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add cli/engine/flatten.py tests/test_engine_flatten.py
git commit -m "feat(engine): the flatten gates -- kill file, terminal, venue status, the typed word"
```

Body: the terminal check runs before any venue read so a session that could never answer is refused for free; the confirm reads `/dev/tty` and never stdin, proven against a child whose stdin is empty.

______________________________________________________________________

### Task 7: The write sequence

**Files:**

- Modify: `cli/engine/flatten.py`
- Test: `tests/test_engine_flatten.py`

**Interfaces:**

- Consumes from Tasks 1–4: `Recorder`, `Plan`, `Snapshot`, `SizedLeg`, `PairConstraints`, `FlattenUnreachable`, `read_open_orders`, `read_positions`, `read_balances`, `read_snapshot`, `margin_legs`, `spot_legs`, `constraints_for`, `size_leg`, `step_precision`, `_ACCOUNT`, `ACCOUNT_ID`, `MARGIN_LEVERAGE`, `CLIENT_ORDER_ID_PREFIX`, `logger`, and the nautilus names Task 1's import already carries: `Quantity`, `ClientOrderId`, `OrderSide`, `OrderType`, `TimeInForce`, `AccountType`.
- Produces:
  - `@dataclass(frozen=True) class LegOutcome: kind: str; symbol: str; side: str; qty: float; pass_name: str; source: str; client_order_id: str | None; sent: bool; reason: str | None; answer: str | None; error: str | None`
  - `@dataclass(frozen=True) class SweepResult: cancel_ok: bool; cancel_error: str | None; orders_after_cancel: int | None; post_write_failure: str | None; outcomes: list[LegOutcome]; final: Snapshot | None`
  - `mint_client_order_id(stamp: datetime, index: int) -> str`
  - `submit_leg(client, rec, sized: SizedLeg, constraints: PairConstraints, client_order_id: str) -> Any`
  - `sweep(client, rec, plan: Plan, listing: dict, *, stamp: datetime) -> SweepResult`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_engine_flatten.py` (`import itertools` is not needed; `datetime`/`timezone` were added in the previous task):

```python
# --- the write sequence -------------------------------------------------------------------------

_STAMP = datetime(2026, 8, 30, 12, 0, 0, tzinfo=timezone.utc)


def _sweep_client(*, orders, positions, balances, symbols, books):
    """Queues, one entry per read of that kind, in call order: orders 3 (snapshot, post-cancel,
    final), positions 4 (snapshot, post-cancel, post-margin, final), balances 4 (snapshot,
    post-margin, post-pass-one, final). The last entry repeats if a read happens again."""
    return FakeClient(
        instruments=[_Instrument(s) for s in symbols],
        orders=orders,
        positions=positions,
        balances=balances,
        books=books,
    )


def _plan_of(client):
    rec = flatten.Recorder()
    listing = flatten.read_listing(client, rec)
    plan = flatten.build_plan(client, rec, flatten.read_snapshot(client, rec), listing)
    return rec, listing, plan


def test_the_full_sequence_calls_the_venue_in_the_order_the_design_fixes():
    """The order is the design: nothing is sized from the pre-confirm snapshot, a fill during the
    human-paced confirm lands in the post-cancel read, and the final snapshot reads orders before
    positions before balances."""
    client = _sweep_client(
        orders=[[], [], []],
        positions=[[_Position("BTC/EUR", "LONG", 0.5)], [_Position("BTC/EUR", "LONG", 0.5)], [], []],
        balances=[[_Balance("ADA", 1200.0)], [_Balance("ADA", 1200.0)], [], []],
        symbols=("BTC/EUR", "ADA/EUR"),
        books={"BTC/EUR.KRAKEN": _Book(60000.0, 60010.0), "ADA/EUR.KRAKEN": _Book(0.4, 0.41)},
    )
    rec, listing, plan = _plan_of(client)
    before = len(client.calls)
    flatten.sweep(client, rec, plan, listing, stamp=_STAMP)
    assert names(client)[before:] == [
        "cancel_all_orders",
        "request_order_status_reports",
        "request_position_status_reports",
        "submit_order",
        "request_position_status_reports",
        "request_account_state",
        "submit_order",
        "request_account_state",
        "request_order_status_reports",
        "request_position_status_reports",
        "request_account_state",
    ]


def test_a_margin_closer_carries_reduce_only_market_ioc_leverage_and_the_margin_account():
    """The client-side side-and-cap invariant is the bound this repo has proven; the venue's own
    reduce_only flag is the second, and it must actually be sent."""
    client = _sweep_client(
        orders=[[]],
        positions=[[_Position("BTC/EUR", "SHORT", 0.5)], [_Position("BTC/EUR", "SHORT", 0.5)], [], []],
        balances=[[]],
        symbols=("BTC/EUR",),
        books={"BTC/EUR.KRAKEN": _Book(60000.0, 60010.0)},
    )
    rec, listing, plan = _plan_of(client)
    flatten.sweep(client, rec, plan, listing, stamp=_STAMP)
    (sent,) = client.submitted
    assert sent["order_side"] == "BUY"  # a SHORT closes with a BUY, never a SELL
    assert sent["order_type"] == "MARKET"
    assert sent["time_in_force"] == "IOC"
    assert sent["reduce_only"] is True
    assert sent["leverage"] == flatten.MARGIN_LEVERAGE
    assert sent["account_type"] == "MARGIN"
    assert sent["quantity"] == 0.5


def test_a_spot_sell_carries_no_reduce_only_and_no_leverage():
    """Kraken's reduce_only is a margin concept a spot order cannot carry."""
    client = _sweep_client(
        orders=[[]],
        positions=[[]],
        balances=[[_Balance("ADA", 1200.0)], [_Balance("ADA", 1200.0)], [], []],
        symbols=("ADA/EUR",),
        books={"ADA/EUR.KRAKEN": _Book(0.4, 0.41)},
    )
    rec, listing, plan = _plan_of(client)
    flatten.sweep(client, rec, plan, listing, stamp=_STAMP)
    (sent,) = client.submitted
    assert sent["order_side"] == "SELL"
    assert sent["account_type"] == "CASH"
    assert sent.get("reduce_only") is False
    assert "leverage" not in sent


def test_a_fill_during_the_confirm_is_closed_at_the_post_cancel_size_not_the_snapshot_size():
    """The closes are sized from the read AFTER the cancel. Sizing from the pre-confirm snapshot
    would leave the difference open and call the account flat."""
    client = _sweep_client(
        orders=[[]],
        positions=[
            [_Position("BTC/EUR", "LONG", 0.5)],
            [_Position("BTC/EUR", "LONG", 0.9)],
            [_Position("BTC/EUR", "LONG", 0.9)],
            [_Position("BTC/EUR", "LONG", 0.9)],
        ],
        balances=[[]],
        symbols=("BTC/EUR",),
        books={"BTC/EUR.KRAKEN": _Book(60000.0, 60010.0)},
    )
    rec, listing, plan = _plan_of(client)
    result = flatten.sweep(client, rec, plan, listing, stamp=_STAMP)
    assert client.submitted[0]["quantity"] == 0.9
    assert result.final.positions[0].quantity == 0.9


def test_a_rejected_margin_leg_is_journaled_and_the_sweep_continues_to_the_spot_pass():
    """A rejection is never retried and never stops the rest of the account being flattened, and a
    leg that cleared `ordermin` before it was sent gains no label from having been refused -- the
    rejection text is never read."""
    client = _sweep_client(
        orders=[[]],
        positions=[[_Position("BTC/EUR", "LONG", 0.5)], [_Position("BTC/EUR", "LONG", 0.5)], [], []],
        balances=[[_Balance("ADA", 1200.0)], [_Balance("ADA", 1200.0)], [], []],
        symbols=("BTC/EUR", "ADA/EUR"),
        books={"BTC/EUR.KRAKEN": _Book(60000.0, 60010.0), "ADA/EUR.KRAKEN": _Book(0.4, 0.41)},
    )
    client.raises["submit_order"] = RuntimeError("EOrder:Insufficient margin")
    rec, listing, plan = _plan_of(client)
    result = flatten.sweep(client, rec, plan, listing, stamp=_STAMP)
    margin_outcome = next(o for o in result.outcomes if o.kind == "margin")
    assert margin_outcome.sent is True and "Insufficient margin" in margin_outcome.error
    assert margin_outcome.reason is None  # 0.5 clears _Instrument's 0.0001 ordermin
    assert [o.symbol for o in result.outcomes if o.kind == "spot"] == ["ADA/EUR"]
    assert result.final is not None


def test_a_failing_cancel_does_not_stop_the_closes():
    """The closes do not depend on the cancel, so its failure is recorded and the sweep runs on."""
    client = _sweep_client(
        orders=[[]],
        positions=[[_Position("BTC/EUR", "LONG", 0.5)], [_Position("BTC/EUR", "LONG", 0.5)], [], []],
        balances=[[]],
        symbols=("BTC/EUR",),
        books={"BTC/EUR.KRAKEN": _Book(60000.0, 60010.0)},
    )
    client.raises["cancel_all_orders"] = RuntimeError("EGeneral:Temporary lockout")
    rec, listing, plan = _plan_of(client)
    result = flatten.sweep(client, rec, plan, listing, stamp=_STAMP)
    assert result.cancel_ok is False and "lockout" in result.cancel_error
    assert len(client.submitted) == 1


def test_a_broken_shape_on_the_post_cancel_re_read_stops_before_any_order():
    """The first-write boundary is the cancel, not the first order: after it, a read that cannot be
    parsed leaves the account possibly changed, so nothing further is sent and nothing reads flat."""
    broken = _Position("BTC/EUR", "LONG", 0.5)
    del broken.quantity
    client = _sweep_client(
        orders=[[]],
        positions=[[_Position("BTC/EUR", "LONG", 0.5)], [broken]],
        balances=[[]],
        symbols=("BTC/EUR",),
        books={"BTC/EUR.KRAKEN": _Book(60000.0, 60010.0)},
    )
    rec, listing, plan = _plan_of(client)
    result = flatten.sweep(client, rec, plan, listing, stamp=_STAMP)
    assert "cancel_all_orders" in names(client)
    assert client.submitted == []
    assert result.post_write_failure is not None
    assert result.final is None


def test_the_second_spot_pass_sells_the_btc_the_first_pass_produced():
    """Pass one sells a BTC-quoted leg; pass two sells the BTC that produced, priced from the
    BTC/EUR book taken at the snapshot."""
    client = _sweep_client(
        orders=[[]],
        positions=[[]],
        balances=[
            [_Balance("ETH", 2.0)],
            [_Balance("ETH", 2.0)],
            [_Balance("XXBT", 0.06)],
            [_Balance("XXBT", 0.0)],
        ],
        symbols=("ETH/BTC", "BTC/EUR"),
        books={"ETH/BTC.KRAKEN": _Book(0.03, 0.031), "BTC/EUR.KRAKEN": _Book(60000.0, 60010.0)},
    )
    rec, listing, plan = _plan_of(client)
    flatten.sweep(client, rec, plan, listing, stamp=_STAMP)
    assert [s["instrument_id"] for s in client.submitted] == ["ETH/BTC.KRAKEN", "BTC/EUR.KRAKEN"]


def test_the_client_order_id_cannot_collide_with_the_engine_s_or_the_probe_harness_s():
    """The executor routes an ack it recognises as its own; an id sharing the engine's shape would
    make a flatten fill land in the engine's ledger."""
    cid = flatten.mint_client_order_id(_STAMP, 3)
    assert cid.startswith(flatten.CLIENT_ORDER_ID_PREFIX)
    assert "-001-000-" not in cid
    assert not cid.startswith("O-")
    assert cid != flatten.mint_client_order_id(_STAMP, 4)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_engine_flatten.py -q -k "sequence or closer or spot_sell or confirm_is_closed or rejected or cancel or post_cancel or second_spot or client_order_id"`
Expected: FAIL — `module 'cli.engine.flatten' has no attribute 'sweep'`.

- [ ] **Step 3: Implement**

Append to `cli/engine/flatten.py`:

```python
@dataclass(frozen=True)
class LegOutcome:
    kind: str
    symbol: str
    side: str
    qty: float
    pass_name: str
    source: str
    client_order_id: str | None
    sent: bool
    reason: str | None
    answer: str | None
    error: str | None


@dataclass(frozen=True)
class SweepResult:
    cancel_ok: bool
    cancel_error: str | None
    orders_after_cancel: int | None
    post_write_failure: str | None
    outcomes: list[LegOutcome]
    final: Snapshot | None


def mint_client_order_id(stamp, index: int) -> str:
    """`FLT-<basic ISO-8601 UTC>-<n>`. Inside the id SHAPE Kraken has already accepted from this
    repo, and structurally distinct from the engine's `-001-000-` infix -- an id the executor could
    read as its own would route a flatten fill into the engine's ledger.

    `stamp` is the run's own and `index` restarts at 1, so two runs beginning inside the same second
    would mint the same ids. Each needs its own word typed at a terminal, and that is the bound --
    the journal's own collision protection does not extend here.
    """
    return f"{CLIENT_ORDER_ID_PREFIX}{stamp:%Y%m%dT%H%M%SZ}-{index}"


# The two sides a `Leg` can carry, and the only two this module can build an order from.
ORDER_SIDES = {"SELL": OrderSide.SELL, "BUY": OrderSide.BUY}


def submit_leg(client: Any, rec: Recorder, sized: SizedLeg, constraints: PairConstraints, client_order_id: str) -> Any:
    """One MARKET IOC order. The quantity is minted at the precision the venue's own lot step
    implies, so the floored value is exactly representable and nothing is rounded UP past the
    position the report reported.

    Every scoping value is derived ONCE and then both sent and journalled -- `_journalled`'s rule,
    on the one call in this module that moves money. Spelled a second time beside the call, the
    journal an operator reads mid-incident can say MARGIN while CASH went out, or name a side the
    order did not carry.

    The side is LOOKED UP, never defaulted: `margin_legs` and `spot_legs` are the only places a
    `Leg` is built and both write a literal, so a third spelling can only be a defect -- and a
    conditional's else-branch would turn it into a real market order in the opposite direction. This
    module names what it cannot derive rather than guessing it.
    """
    margin = sized.leg.kind == "margin"
    quantity = Quantity(sized.qty, step_precision(constraints.lot_step))
    order_side = ORDER_SIDES[sized.leg.side]
    order_type, time_in_force = OrderType.MARKET, TimeInForce.IOC
    kwargs: dict[str, Any] = {"reduce_only": margin, "account_type": AccountType.MARGIN if margin else AccountType.CASH}
    if margin:
        kwargs["leverage"] = MARGIN_LEVERAGE
    params = {
        "account_id": ACCOUNT_ID,
        "instrument_id": str(constraints.instrument_id),
        "client_order_id": client_order_id,
        "order_side": str(order_side),
        "order_type": str(order_type),
        "quantity": float(quantity),
        "time_in_force": str(time_in_force),
        **_journalled(kwargs),
    }
    return rec.call(
        "submit_order",
        params,
        lambda: client.submit_order(
            _ACCOUNT,
            constraints.instrument_id,
            ClientOrderId(client_order_id),
            order_side,
            order_type,
            quantity,
            time_in_force,
            **kwargs,
        ),
    )


def _sized_with_constraints(legs: list, listing: dict, plan: Plan) -> list:
    """Each leg paired with the constraints it will be sized and minted at. A pair absent from the
    plan's own map is looked up now; a shape failure there is a post-write failure, never a guess."""
    out = []
    for leg in legs:
        constraints = plan.constraints.get(leg.symbol) or constraints_for(leg.symbol, listing)
        out.append((size_leg(leg, constraints, plan.prices.get(leg.symbol)), constraints))
    return out


def _send(client, rec, sized: SizedLeg, constraints: PairConstraints, stamp, index: int, pass_name: str) -> LegOutcome:
    """Never raises: a rejection is journaled and the sweep continues, and is never retried.

    `sent` stays True on every failure raised inside the send -- the local minting of the quantity
    included, since nothing here can tell that apart from a request that left and was refused. The
    request may have reached the venue, and recording it as unsent would be the one lie an operator
    cannot afford here.

    A rejected margin closer this code had ALREADY sized below the pair's `ordermin` is labelled
    `unclosable_below_minimum` (spec D4): it is what routes an operator to the venue's own
    settle-position action, which a bare `EOrder:` string never does. The label comes from the
    pre-send arithmetic, never from the rejection text -- which Kraken message means "below the
    minimum" is unmeasured here -- so the venue's words are journaled beside it as the leg's
    `error`, and a refusal for a passing reason wears the same label as a refusal about the size.

    One `reason` field carries one label: where such a closer is also unpriced, the label is
    `unclosable_below_minimum` rather than `no_reference_price`. It is the one that names a next
    action, and the price costs a margin leg nothing -- a closer's quantity comes from the position
    report and never from a price.
    """
    base = dict(
        kind=sized.leg.kind,
        symbol=sized.leg.symbol,
        side=sized.leg.side,
        qty=sized.qty,
        pass_name=pass_name,
        source=sized.leg.source,
    )
    if not sized.send:
        return LegOutcome(**base, client_order_id=None, sent=False, reason=sized.reason, answer=None, error=None)
    client_order_id = mint_client_order_id(stamp, index)
    reason = "no_reference_price" if sized.reference_price is None else None
    try:
        answer = submit_leg(client, rec, sized, constraints, client_order_id)
    except Exception as exc:  # noqa: BLE001 -- one leg's rejection must not end the sweep
        if sized.leg.kind == "margin" and sized.qty < constraints.ordermin:
            reason = "unclosable_below_minimum"
        logger.error("flatten leg %s %s was rejected: %s", sized.leg.symbol, sized.leg.side, exc)
        return LegOutcome(
            **base, client_order_id=client_order_id, sent=True, reason=reason, answer=None, error=f"{type(exc).__name__}: {exc}"
        )
    return LegOutcome(**base, client_order_id=client_order_id, sent=True, reason=reason, answer=repr(answer), error=None)


def _read_for_the_record(what: str, read: Callable[[], Any]) -> Any:
    """A POST-WRITE read whose answer nothing but the journal consumes: run it, or name the failure
    and step over it.

    The asymmetry with every pre-write read is the whole point. Before the first write an unreadable
    answer must abort -- a shape the venue changed is a finding, and nothing has happened yet. After
    the cancel and the closes have gone out, aborting on a read NOTHING CONSUMES trades a
    journalling nicety for unsold balances: `read_positions` raises on a `None` answer, a live venue
    shape this module documents, and one such answer would otherwise take both spot passes and the
    final snapshot with it. `Recorder` has already written the request and whatever came back -- the
    unreadable answer itself, verbatim, or the transport error -- so the evidence an operator reads
    survives either way; only the abort goes away.

    Never widened to a read something DOES consume. The post-cancel position read that sizes the
    closers must still abort -- degraded, it would size them from an empty list and report the
    account flat.
    """
    try:
        return read()
    except FlattenUnreachable as exc:
        logger.error("%s could not be read -- it is journaled and the sweep goes on: %s", what, exc)
        return None


def sweep(client: Any, rec: Recorder, plan: Plan, listing: dict, *, stamp) -> SweepResult:
    """From the account-wide cancel to the final snapshot. Re-runnable: a second run finds less to
    do and does it, so nothing here is one-shot.

    Every read after the cancel whose answer this function CONSUMES is inside the one try: past the
    first write the account may have moved, so a read that fails ends the sweep with a named failure
    rather than with a verdict. The two that feed only the journal go through
    `_read_for_the_record`, which is where that asymmetry is argued.

    The final snapshot is read AFRESH rather than reusing the plan's -- a reused one is a second
    vote from the witness the sweep has just acted on, and it would report flat whatever the writes
    achieved.
    """
    outcomes: list[LegOutcome] = []
    cancel_ok, cancel_error = True, None
    try:
        rec.call("cancel_all_orders", {}, client.cancel_all_orders)
    except Exception as exc:  # noqa: BLE001 -- the closes do not depend on the cancel
        cancel_ok, cancel_error = False, f"{type(exc).__name__}: {exc}"
        logger.error("the account-wide cancel failed: %s", exc)

    index, orders_after, post_write_failure, final = 0, None, None, None
    try:
        # Journal-only, both of them: `orders_after_cancel` is written into the record and read by
        # no decision -- the exit code judges the FINAL snapshot's orders, never this count.
        rows = _read_for_the_record("the orders still resting after the cancel", lambda: read_open_orders(client, rec))
        orders_after = len(rows) if rows is not None else None
        margin_now, _ = margin_legs(read_positions(client, rec), listing)
        for sized, constraints in _sized_with_constraints(margin_now, listing, plan):
            index += 1
            outcomes.append(_send(client, rec, sized, constraints, stamp, index, "margin"))

        _read_for_the_record("what the closes left behind", lambda: read_positions(client, rec))
        for pass_name in ("spot-1", "spot-2"):
            legs, _ = spot_legs(read_balances(client, rec), listing)
            for sized, constraints in _sized_with_constraints(legs, listing, plan):
                index += 1
                outcomes.append(_send(client, rec, sized, constraints, stamp, index, pass_name))

        final = read_snapshot(client, rec)
    except FlattenUnreachable as exc:
        post_write_failure = str(exc)
        logger.error("a read after the first write failed: %s", exc)

    return SweepResult(
        cancel_ok=cancel_ok,
        cancel_error=cancel_error,
        orders_after_cancel=orders_after,
        post_write_failure=post_write_failure,
        outcomes=outcomes,
        final=final,
    )
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_engine_flatten.py tests/test_engine_executor.py -q`
Expected: PASS, including the widened venue-mutating guard now that `flatten.py` names `submit_order`.

- [ ] **Step 5: Commit**

```bash
git add cli/engine/flatten.py tests/test_engine_flatten.py
git commit -m "feat(engine): the flatten write sequence -- cancel, close, sell twice, read back"
```

Body: the closes are sized from the post-cancel read so a fill during the confirm cannot be left open; a rejection is journaled, never retried, and never ends the sweep; every read after the cancel that fails ends the run with a named failure rather than a verdict.

______________________________________________________________________

### Task 8: The exit code, the journal, and the command end to end

**Files:**

- Modify: `cli/engine/flatten.py`
- Test: `tests/test_engine_flatten.py`

**Interfaces:**

- Consumes from Tasks 1–7: every symbol above.
- Produces:
  - `judge_final(final: Snapshot, listing: dict, prices: dict) -> list[dict]` — one dict per residual.
  - `exit_code(result: SweepResult, residuals: list[dict]) -> int`
  - `journal_path(state_dir, stamp) -> Path`
  - `write_journal(state_dir, stamp, payload: dict) -> Path | None`
  - `_dry_exit(code: int, message: str, echo) -> int` — the dry run's return path, which writes no journal.
  - `run_flatten(client, *, state_dir, execute: bool, now=..., venue_reader=..., tty_available=..., prompt=..., echo=...) -> int`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_engine_flatten.py` (add `import json` to the imports):

```python
# --- exit codes, the journal, and the command end to end ----------------------------------------


def _online(**_):
    from cli.engine.venue import VenueStatus

    return VenueStatus(status="online", ok=True, observed_at=_STAMP)


def _offline(**_):
    from cli.engine.venue import VenueStatus

    return VenueStatus(status="maintenance", ok=False, observed_at=_STAMP)


def _armed(tmp_path: Path) -> Path:
    (_exec_dir(tmp_path) / "kill").write_text("2026-08-30T12:00:00+00:00 flatten\n")
    return tmp_path


def _run(client, tmp_path, *, execute=True, reply="FLATTEN", venue=_online, tty=True, lines=None):
    return flatten.run_flatten(
        client,
        state_dir=tmp_path,
        execute=execute,
        now=lambda: _STAMP,
        venue_reader=venue,
        tty_available=lambda: tty,
        prompt=lambda _: reply,
        echo=(lines.append if lines is not None else (lambda _: None)),
    )


def _flat_client(**kw):
    defaults = dict(orders=[[]], positions=[[]], balances=[[]], symbols=("BTC/EUR",), books={"BTC/EUR.KRAKEN": _Book(60000.0, 60010.0)})
    defaults.update(kw)
    return _sweep_client(**defaults)


def test_the_default_invocation_sends_nothing_needs_no_kill_file_and_exits_zero(tmp_path):
    """The invocation an operator reaches by accident or by muscle memory must be the one that
    changes nothing -- which is why there is no flag meaning 'do nothing' to forget."""
    client = _flat_client(balances=[[_Balance("ADA", 1200.0)]], symbols=("BTC/EUR", "ADA/EUR"),
                          books={"BTC/EUR.KRAKEN": _Book(60000.0, 60010.0), "ADA/EUR.KRAKEN": _Book(0.4, 0.41)})
    lines: list[str] = []
    assert _run(client, tmp_path, execute=False, lines=lines) == 0
    assert "cancel_all_orders" not in names(client)
    assert "submit_order" not in names(client)
    assert any("ADA/EUR" in line for line in lines)
    assert list(_exec_dir(tmp_path).glob("flatten-*.json")) == []


@pytest.mark.parametrize(
    ("setup", "reply", "tty", "armed"),
    [("kill-absent", "FLATTEN", True, False), ("confirm", "nope", True, True), ("no-tty", "FLATTEN", False, True)],
)
def test_every_refusal_exits_one_with_no_request_and_no_write(tmp_path, setup, reply, tty, armed):
    """The only path to `submit_order` or `cancel_all_orders` runs through --execute AND a matched
    confirm. Each refusal is asserted on what reached the venue, not on the exit code alone."""
    if armed:
        _armed(tmp_path)
    else:
        _exec_dir(tmp_path)
    client = _flat_client()
    assert _run(client, tmp_path, reply=reply, tty=tty) == 1
    assert "cancel_all_orders" not in names(client)
    assert "submit_order" not in names(client)
    if setup == "kill-absent":
        assert client.calls == []  # refused before a single request
    # Every exit-1 refusal `run_flatten` itself makes leaves the record: the refusal and its reason
    # are what the artifact exists for, and an unrecorded refusal is one nobody can reconstruct.
    assert len(list(_exec_dir(tmp_path).glob("flatten-*.json"))) == 1


@pytest.mark.parametrize("execute", [True, False])
def test_a_venue_that_is_not_online_exits_three_with_nothing_sent(tmp_path, execute):
    """The dry run takes the venue gate too -- only the kill-file gate is skipped without
    `--execute`. The two invocations differ in exactly one way: the dry run leaves no artifact,
    which is `_dry_exit`'s whole contract and is reachable from no other fixture."""
    _armed(tmp_path)
    client = _flat_client()
    assert _run(client, tmp_path, execute=execute, venue=_offline) == 3
    assert client.calls == []
    assert len(list(_exec_dir(tmp_path).glob("flatten-*.json"))) == (1 if execute else 0)


@pytest.mark.parametrize("execute", [True, False])
def test_a_missing_field_on_a_pre_write_read_exits_three_and_the_cancel_never_goes_out(tmp_path, execute):
    """The first write is the cancel. Before it, a shape the venue changed aborts with the account
    untouched -- that is the whole difference between exit 3 and exit 2. An absent NAMED FIELD is
    that case; an unrecognised VALUE in a field that is present is not, and has its own fixture.
    The dry run reaches the same code through `_dry_exit` and leaves no artifact."""
    _armed(tmp_path)
    broken = _Position("BTC/EUR", "LONG", 0.5)
    del broken.position_side
    client = _flat_client(positions=[[broken]])
    assert _run(client, tmp_path, execute=execute) == 3
    assert "cancel_all_orders" not in names(client)
    assert len(list(_exec_dir(tmp_path).glob("flatten-*.json"))) == (1 if execute else 0)


def test_an_unrecognised_position_side_never_aborts_the_button_and_exits_two(tmp_path):
    """The row the venue answers with a side this build knows (`NO_POSITION_SIDE`) and this command
    cannot close from. Aborting would leave the resting orders resting, every balance held and the
    engine already stopped; reading it as flat would exit 0 over an open position. So: the cancel
    goes out, every other leg is sent, the row is named in the record, and the account reads 2."""
    _armed(tmp_path)
    odd = [_Position("BTC/EUR", "NO_POSITION_SIDE", 1.0)]
    client = _flat_client(
        positions=[odd, odd, odd, odd],
        balances=[[_Balance("ADA", 1200.0)], [_Balance("ADA", 1200.0)], [], []],
        symbols=("BTC/EUR", "ADA/EUR"),
        books={"BTC/EUR.KRAKEN": _Book(60000.0, 60010.0), "ADA/EUR.KRAKEN": _Book(0.4, 0.41)},
    )
    assert _run(client, tmp_path) == 2
    assert "cancel_all_orders" in names(client)
    assert [sent["instrument_id"] for sent in client.submitted] == ["ADA/EUR.KRAKEN"]
    (path,) = list(_exec_dir(tmp_path).glob("flatten-*.json"))
    positions = [row for row in json.loads(path.read_text())["residuals"] if row["kind"] == "position"]
    assert [row["reason"] for row in positions] == ["unrecognised_position_side"]


def test_a_clean_sweep_of_a_flat_account_exits_zero(tmp_path):
    _armed(tmp_path)
    client = _flat_client()
    assert _run(client, tmp_path) == 0


def test_a_flat_row_alone_in_the_final_snapshot_exits_zero(tmp_path):
    """A FLAT row is not a leg and is not a residual; reading it as one would report a flat account
    as partial forever."""
    _armed(tmp_path)
    flat = [_Position("BTC/EUR", "FLAT", 0.0)]
    client = _flat_client(positions=[flat, flat, flat, flat])
    assert _run(client, tmp_path) == 0
    assert client.submitted == []


def test_a_resting_order_that_outlived_the_cancel_exits_two_even_with_nothing_else_open(tmp_path):
    """It can fill after the operator was told the book was flat."""
    _armed(tmp_path)
    client = _flat_client(orders=[[], [], [object()]])
    assert _run(client, tmp_path) == 2


def test_a_residual_position_after_the_closes_exits_two(tmp_path):
    _armed(tmp_path)
    row = [_Position("BTC/EUR", "LONG", 0.5)]
    client = _flat_client(positions=[row, row, row, row])
    assert _run(client, tmp_path) == 2
    assert client.submitted != []


def test_a_fill_during_the_confirm_leaves_its_residual_in_the_final_snapshot_and_exits_two(tmp_path):
    """The close is sized from the post-cancel read, and what that read shows is what gets closed --
    but the account still has to be JUDGED afterwards, so a position the sweep could not finish
    reads 2 rather than flat."""
    _armed(tmp_path)
    grown = [_Position("BTC/EUR", "LONG", 0.9)]
    client = _flat_client(positions=[[_Position("BTC/EUR", "LONG", 0.5)], grown, grown, grown])
    assert _run(client, tmp_path) == 2
    assert client.submitted[0]["quantity"] == 0.9


def test_a_broken_shape_on_the_post_cancel_re_read_exits_two_with_no_order_sent(tmp_path):
    """The first-write boundary is the cancel: past it, neither 0 nor 3 is a claim this run can
    make. `test_a_broken_shape_on_the_post_cancel_re_read_stops_before_any_order` pins the same
    fixture at sweep level; this one pins the code it composes to."""
    _armed(tmp_path)
    broken = _Position("BTC/EUR", "LONG", 0.5)
    del broken.quantity
    client = _flat_client(positions=[[_Position("BTC/EUR", "LONG", 0.5)], [broken]])
    assert _run(client, tmp_path) == 2
    assert "cancel_all_orders" in names(client)
    assert client.submitted == []


def test_a_sub_ordermin_margin_row_is_sent_and_its_rejection_still_exits_two(tmp_path):
    """The engine's own machine produces sub-ordermin remainders by design, and a remainder left
    open is exposure -- so it is sent, and the venue rules on it. The label is minted from the
    pre-send arithmetic and the venue's own words are kept beside it: the exit code says 2 for a
    hundred reasons, an operator reading a bare `EOrder:` string is never routed to the venue's
    settle-position action, and the words are what say whether the refusal was about the size."""
    _armed(tmp_path)
    tiny = [_Position("BTC/EUR", "LONG", 0.00002)]  # under _Instrument's 0.0001 ordermin
    client = _flat_client(positions=[tiny, tiny, tiny, tiny])
    client.raises["submit_order"] = RuntimeError("EOrder:Invalid volume")
    assert _run(client, tmp_path) == 2
    assert client.submitted != []
    (path,) = list(_exec_dir(tmp_path).glob("flatten-*.json"))
    (leg,) = [row for row in json.loads(path.read_text())["legs"] if row["kind"] == "margin"]
    assert leg["reason"] == "unclosable_below_minimum"
    assert "EOrder:Invalid volume" in leg["error"]  # the venue's own words are kept beside the label


def test_a_margin_row_on_an_unlisted_pair_never_aborts_the_button_and_exits_two(tmp_path):
    """The one pairlessness that could cost everything: aborting before the cancel would leave the
    resting orders resting, every other position open and every balance held, with the engine
    already stopped. So the row is named, the rest of the sweep runs, and the account reads 2."""
    _armed(tmp_path)
    stranded = [_Position("GONE/EUR", "LONG", 1.0)]
    client = _flat_client(
        positions=[stranded, stranded, stranded, stranded],
        balances=[[_Balance("ADA", 1200.0)], [_Balance("ADA", 1200.0)], [], []],
        symbols=("BTC/EUR", "ADA/EUR"),
        books={"BTC/EUR.KRAKEN": _Book(60000.0, 60010.0), "ADA/EUR.KRAKEN": _Book(0.4, 0.41)},
    )
    assert _run(client, tmp_path) == 2
    assert "cancel_all_orders" in names(client)
    assert [sent["instrument_id"] for sent in client.submitted] == ["ADA/EUR.KRAKEN"]
    (path,) = list(_exec_dir(tmp_path).glob("flatten-*.json"))
    positions = [row for row in json.loads(path.read_text())["residuals"] if row["kind"] == "position"]
    assert [row["symbol"] for row in positions] == ["GONE/EUR"]
    assert positions[0]["reason"] == "pair_not_listed"


def test_a_balance_in_an_asset_with_neither_pair_exits_two_never_zero(tmp_path):
    _armed(tmp_path)
    held = [_Balance("WEIRD", 3.0)]
    client = _flat_client(balances=[held, held, held, held])
    assert _run(client, tmp_path) == 2


def test_a_dust_balance_alone_in_the_final_snapshot_exits_zero(tmp_path):
    """Dust is listed, not sent, and does not make the account not-flat -- the venue would reject
    the order that would clear it."""
    _armed(tmp_path)
    dust = [_Balance("ADA", 10.0)]
    client = _flat_client(
        balances=[dust, dust, dust, dust],
        symbols=("BTC/EUR", "ADA/EUR"),
        books={"BTC/EUR.KRAKEN": _Book(60000.0, 60010.0), "ADA/EUR.KRAKEN": _Book(0.4, 0.41)},
    )
    for row in client._instruments:
        if row.id.startswith("ADA"):
            row.min_quantity = 15.0
    assert _run(client, tmp_path) == 0
    assert client.submitted == []


def test_a_failed_cancel_exits_two_whatever_each_leg_answered(tmp_path):
    _armed(tmp_path)
    client = _flat_client()
    client.raises["cancel_all_orders"] = RuntimeError("EGeneral:Temporary lockout")
    assert _run(client, tmp_path) == 2


def test_a_read_that_fails_after_the_first_write_exits_two_and_never_three(tmp_path):
    """Never 0 and never 3: the account may already have changed, so neither 'flat' nor 'untouched'
    is a claim this run can make."""
    _armed(tmp_path)
    client = _flat_client()
    # Break the THIRD open-order read -- the final snapshot's, the last read of the whole run.
    original, state = client.request_order_status_reports, {"n": 0}

    def counting(account_id, **kw):
        state["n"] += 1
        if state["n"] == 3:
            raise RuntimeError("connection reset")
        return original(account_id, **kw)

    client.request_order_status_reports = counting
    assert _run(client, tmp_path) == 2


def test_an_instrument_with_no_committed_costmin_is_still_sized_and_sent(tmp_path):
    """min_notional always reads None from this adapter, so a pair outside the committed table has
    no notional floor at all -- and must still be sold, not skipped."""
    _armed(tmp_path)
    held = [_Balance("WEIRD", 3.0)]
    client = _flat_client(
        # snapshot, the read that sizes pass one, then flat: pass two finds nothing left to send.
        balances=[held, held, [], []],
        symbols=("BTC/EUR", "WEIRD/EUR"),
        books={"BTC/EUR.KRAKEN": _Book(60000.0, 60010.0), "WEIRD/EUR.KRAKEN": _Book(1.0, 1.01)},
    )
    assert _run(client, tmp_path) == 0
    assert [s["instrument_id"] for s in client.submitted] == ["WEIRD/EUR.KRAKEN"]


def test_a_balance_that_appears_after_the_snapshot_is_sold_unpriced_and_the_journal_says_so(tmp_path):
    """No post-write book read ever happens, so a balance surfacing only in a later pass has no
    reference price. It is still sold -- skipping it would leave a live holding the run then calls
    flat -- and the label is what tells the operator no estimate backed that order."""
    _armed(tmp_path)
    late = [_Balance("ADA", 1200.0)]
    client = _flat_client(
        # Empty at the snapshot, so no ADA/EUR book is read and the plan carries no ADA price.
        balances=[[], late, [], []],
        symbols=("BTC/EUR", "ADA/EUR"),
    )
    assert _run(client, tmp_path) == 0
    assert [s["instrument_id"] for s in client.submitted] == ["ADA/EUR.KRAKEN"]
    assert "request_book_snapshot" not in names(client)
    (path,) = list(_exec_dir(tmp_path).glob("flatten-*.json"))
    (leg,) = [row for row in json.loads(path.read_text())["legs"] if row["kind"] == "spot"]
    assert leg["sent"] is True and leg["reason"] == "no_reference_price"


def test_the_journal_records_the_snapshots_the_requests_the_confirm_and_the_exit_code(tmp_path):
    _armed(tmp_path)
    row = [_Position("BTC/EUR", "LONG", 0.5)]
    client = _flat_client(positions=[row, row, [], []])
    assert _run(client, tmp_path) == 0
    (path,) = list(_exec_dir(tmp_path).glob("flatten-*.json"))
    doc = json.loads(path.read_text())
    assert doc["mode"] == "execute"
    assert doc["confirm"] == "matched"
    assert doc["exit_code"] == 0
    assert doc["snapshot_before"]["positions"][0]["symbol"] == "BTC/EUR"
    assert doc["snapshot_after"]["positions"] == []
    assert [e["call"] for e in doc["requests"]].count("submit_order") == 1
    assert doc["api_key_masked"] == "kr***xy"
    # The key's own VALUE, and never the name of the variable it arrived in: that name reaches no
    # part of this process, so asserting its absence is green under every implementation, leak
    # included. Only the masked form may appear in an artifact written to the engine's exec dir.
    assert FakeClient.api_key not in path.read_text()


def test_a_refused_run_still_journals_the_refusal(tmp_path):
    """The confirm that did not match is exactly the thing worth having a record of."""
    _armed(tmp_path)
    assert _run(_flat_client(), tmp_path, reply="nope") == 1
    (path,) = list(_exec_dir(tmp_path).glob("flatten-*.json"))
    doc = json.loads(path.read_text())
    assert doc["confirm"] == "mismatch" and doc["exit_code"] == 1


def test_a_second_run_in_the_same_second_does_not_destroy_the_first_record(tmp_path):
    _armed(tmp_path)
    assert _run(_flat_client(), tmp_path) == 0
    assert _run(_flat_client(), tmp_path) == 0
    assert len(list(_exec_dir(tmp_path).glob("flatten-*.json"))) == 2


def test_the_journal_filename_needs_no_shell_quoting(tmp_path):
    """An operator types this path mid-incident."""
    name = flatten.journal_path(tmp_path, _STAMP).name
    assert name == "flatten-20260830T120000Z.json"
    assert not set(name) & set(":+ '\"")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_engine_flatten.py -q -k "run or journal or exits or refusal or sized_and_sent"`
Expected: FAIL — `module 'cli.engine.flatten' has no attribute 'run_flatten'`.

- [ ] **Step 3: Implement**

Add `import json` and `from datetime import datetime, timezone` and `from pathlib import Path` to `cli/engine/flatten.py`'s imports, plus `from dataclasses import asdict, dataclass` and `from cli.engine.venue import read_system_status`. Then append:

```python
def _utc_now():
    return datetime.now(timezone.utc)


def _snapshot_payload(snapshot: Snapshot | None) -> dict | None:
    if snapshot is None:
        return None
    return {
        "open_orders": len(snapshot.orders),
        "positions": [{"symbol": r.symbol, "side": r.side, "quantity": r.quantity} for r in snapshot.positions],
        "balances": [{"code": r.code, "free": r.free} for r in snapshot.balances],
    }


def judge_final(final: Snapshot, listing: dict, prices: dict) -> list[dict]:
    """Everything in the final snapshot that says the account is not flat.

    A balance the listing cannot route, and a pair whose constraints cannot be read here, both
    count as residuals: neither is evidence of flatness, and the safe direction is to say so.

    Only FLAT is skipped, never a whitelist of LONG/SHORT: a side this code could not close from is
    exposure it could not act on, and reading it as flat would report the one row nothing was sent
    for as nothing to do.
    """
    residuals: list[dict] = []
    if final.orders:
        residuals.append({"kind": "order", "count": len(final.orders), "reason": "resting_order"})
    for row in final.positions:
        if row.side == "FLAT":
            continue
        residual = {"kind": "position", "symbol": row.symbol, "side": row.side, "quantity": row.quantity}
        if row.side not in ("LONG", "SHORT"):
            residual["reason"] = "unrecognised_position_side"
        elif row.symbol not in listing:
            # Nothing was sent for it and nothing could be: this is where that reaches the record.
            residual["reason"] = "pair_not_listed"
        residuals.append(residual)
    from cli.engine.instruments import EUR_CODES

    bases = listed_bases(listing)
    for row in final.balances:
        if row.code.upper() in EUR_CODES or row.free <= 0.0:
            continue
        base = resolve_base(row.code, bases)
        symbol = choose_pair(base, listing) if base else None
        if symbol is None:
            residuals.append({"kind": "balance", "code": row.code, "free": row.free, "reason": "no_eur_or_btc_pair"})
            continue
        try:
            constraints = constraints_for(symbol, listing)
        except FlattenUnreachable as exc:
            residuals.append({"kind": "balance", "code": row.code, "free": row.free, "reason": f"unjudgeable: {exc}"})
            continue
        if classify_balance(row.free, constraints, prices.get(symbol)) == "residual":
            residuals.append({"kind": "balance", "code": row.code, "free": row.free, "symbol": symbol, "reason": "sellable_balance"})
    return residuals


def exit_code(result: SweepResult, residuals: list) -> int:
    """0 flat, 2 partial. Derived from the final snapshot plus the two write-side failures -- never
    from what an individual leg answered, which the journal carries instead."""
    if result.post_write_failure is not None or not result.cancel_ok or residuals:
        return 2
    return 0


def journal_path(state_dir, stamp) -> Path:
    """ISO-8601 BASIC form: an operator types this path mid-incident, and the extended form's `:`
    and `+` need shell quoting to do it. The body carries the extended timestamp.

    The stamp is converted to UTC before it is formatted, so the `Z` in the name is never a claim
    about a zone the caller happened to be in while `started_at` carried the truth."""
    from cli.engine.execgate import exec_dir

    return exec_dir(state_dir) / f"flatten-{stamp.astimezone(timezone.utc):%Y%m%dT%H%M%SZ}.json"


def write_journal(state_dir, stamp, payload: dict) -> Path | None:
    """Its own artifact, never the engine's `exec-<HH>.json` (an unlocked single-writer
    read-modify-write this process must not join). Refuses to overwrite: a second run in the same
    second must not destroy the first one's incident record."""
    base = journal_path(state_dir, stamp)
    for suffix in ("", *(f"-{n}" for n in range(2, 100))):
        candidate = base.with_name(f"{base.stem}{suffix}.json")
        try:
            candidate.parent.mkdir(parents=True, exist_ok=True)
            with candidate.open("x", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2, sort_keys=True, default=str)
            return candidate
        except FileExistsError:
            continue
        except OSError:
            logger.critical("the flatten journal could not be written to %s -- the record follows on stdout", candidate, exc_info=True)
            print(json.dumps(payload, indent=2, sort_keys=True, default=str))
            return None
    logger.critical("the flatten journal could not be given a free name under %s", base.parent)
    return None


def run_flatten(
    client: Any,
    *,
    state_dir,
    execute: bool,
    now: Callable[[], Any] = _utc_now,
    venue_reader: Callable[..., Any] = read_system_status,
    tty_available: Callable[[], bool] = terminal_available,
    prompt: Callable[[str], str] = read_confirm,
    echo: Callable[[str], None] = print,
) -> int:
    """The whole button. Returns the process exit code; raises nothing.

    0 flat (or the default dry run completed) · 1 refused with nothing sent · 2 partial:
    the final snapshot is not flat, or a write-side failure means it cannot be called flat ·
    3 the venue could not be reached or read BEFORE the first write, which is the cancel.
    """
    stamp = now()
    rec = Recorder()
    record: dict = {
        "schema_version": 1,
        "mode": "execute" if execute else "dry-run",
        "started_at": stamp.isoformat(),
        "state_dir": str(state_dir),
        "api_key_masked": getattr(client, "api_key_masked", None),
        "confirm": "not-required",
        "kill_file": None,
        "requests": rec.entries,
    }

    def _finish(code: int, message: str | None = None) -> int:
        if message:
            echo(message)
        record["exit_code"] = code
        record["finished_at"] = now().isoformat()
        path = write_journal(state_dir, stamp, record)
        if path is not None:
            echo(f"the record of this run is {path}")
        return code

    if execute:
        try:
            record["kill_file"] = check_kill_file(state_dir)
        except FlattenRefused as exc:
            return _finish(1, str(exc))
        if not tty_available():
            return _finish(1, "there is no controlling terminal to read the confirmation from -- nothing was sent")

    try:
        status = check_venue(venue_reader, stamp)
    except FlattenUnreachable as exc:
        record["venue_status"] = {"status": "not-online", "ok": False}
        return _finish(3, str(exc)) if execute else _dry_exit(3, str(exc), echo)
    record["venue_status"] = {"status": status.status, "ok": status.ok}

    try:
        snapshot = read_snapshot(client, rec)
        listing = read_listing(client, rec)
        plan = build_plan(client, rec, snapshot, listing)
    except FlattenUnreachable as exc:
        record["error"] = str(exc)
        return _finish(3, str(exc)) if execute else _dry_exit(3, str(exc), echo)

    record["snapshot_before"] = _snapshot_payload(snapshot)
    render_plan(plan, echo)

    if not execute:
        echo("nothing was sent: this run reads and prints only")
        return 0

    try:
        reply = prompt(CONFIRM_PROMPT)
    except OSError as exc:
        # `tty_available()` passed a moment ago; between then and here the terminal can still go.
        # This function promises to raise nothing, and a traceback where the refusal contract
        # promises exit 1 leaves the operator with no journal and no code to read.
        return _finish(1, f"the confirmation could not be read from the terminal -- nothing was sent: {exc}")
    if not matches_confirm(reply):
        record["confirm"] = "mismatch"
        return _finish(1, "the confirmation did not match -- nothing was sent")
    record["confirm"] = "matched"

    result = sweep(client, rec, plan, listing, stamp=stamp)
    residuals = judge_final(result.final, listing, plan.prices) if result.final is not None else []
    code = exit_code(result, residuals)
    record["cancel"] = {"ok": result.cancel_ok, "error": result.cancel_error, "orders_after": result.orders_after_cancel}
    record["post_write_failure"] = result.post_write_failure
    record["legs"] = [asdict(outcome) for outcome in result.outcomes]
    record["snapshot_after"] = _snapshot_payload(result.final)
    record["residuals"] = residuals
    if code == 0:
        echo("the account reads flat: no resting order, no open position, no sellable balance left")
    else:
        echo("the account does NOT read flat -- what is left:")
        for row in residuals:
            echo(f"  {row}")
        if result.post_write_failure:
            echo(f"  a read after the cancel failed: {result.post_write_failure}")
        if not result.cancel_ok:
            echo(f"  the account-wide cancel failed: {result.cancel_error}")
    return _finish(code)


def _dry_exit(code: int, message: str, echo: Callable[[str], None]) -> int:
    """A dry run leaves no artifact: it changed nothing, and the terminal is its whole record."""
    echo(message)
    return code
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_engine_flatten.py -q`
Expected: PASS. If `test_a_read_that_fails_after_the_first_write_exits_two_and_never_three` is awkward against the fake, keep the assertion (exit 2) and adjust only how the third orders read is made to fail — never the expected code.

- [ ] **Step 5: Commit**

```bash
git add cli/engine/flatten.py tests/test_engine_flatten.py
git commit -m "feat(engine): flatten exit codes and its own journal artifact"
```

Body: the code is derived from the final snapshot plus the cancel's own failure and a post-write read failure, never from what a leg answered; a read that fails after the first write is 2 and never 3 because the account may already have moved; the journal is its own artifact and never the engine's exec ledger.

______________________________________________________________________

### Task 9: The CLI command and the README row

**Files:**

- Modify: `cli/engine/command.py` (a new `flatten` command on `engine_app`, placed immediately after `exec_status` and its `_echo_gate_verdict` helper — other commands follow it in the file; the position is convention, nothing depends on it)
- Modify: `README.md` (the `zcrypto engine` subcommand table, after the `exec-status` row)
- Modify: `tests/test_nautilus_interface_pin.py` (`PINNED_SYMBOLS`)
- Test: `tests/test_engine_flatten.py`

**Interfaces:**

- Consumes from Task 8: `cli.engine.flatten.run_flatten(client, *, state_dir, execute, ...) -> int`.
- Produces: `zcrypto engine flatten --state-dir <PATH> [--execute]`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_engine_flatten.py` (add `import logging`, `from typer.testing import CliRunner` and `from cli.__main__ import app`):

```python
# --- the CLI surface ----------------------------------------------------------------------------

_runner = CliRunner()


def test_the_subcommand_is_registered_and_its_help_says_what_pressing_it_does():
    result = _runner.invoke(app, ["engine", "flatten", "--help"])
    assert result.exit_code == 0
    assert "--execute" in result.output
    assert "--state-dir" in result.output
    assert "market" in result.output


def test_the_state_dir_is_required_so_the_button_never_depends_on_a_config_mount():
    """The environment being broken is the situation this command exists for."""
    result = _runner.invoke(app, ["engine", "flatten"])
    assert result.exit_code != 0


def test_absent_credentials_refuse_with_exit_one_and_never_construct_a_client(monkeypatch, tmp_path):
    """Exit 1 is the refusal code, and it lands here before a client exists: one built without a
    key is a single request away from the venue."""
    monkeypatch.delenv("KRAKEN_SPOT_API_KEY", raising=False)
    monkeypatch.delenv("KRAKEN_SPOT_API_SECRET", raising=False)
    result = _runner.invoke(app, ["engine", "flatten", "--state-dir", str(tmp_path)])
    assert result.exit_code == 1


def test_the_command_never_names_a_credential_value(monkeypatch, tmp_path, caplog):
    """The refusal goes through `_abort`, which LOGS and never echoes, so the log record is the only
    surface a key could leak on -- an assertion on `result.output` alone stays green on an
    implementation that prints the value into it (`tests/test_error_paths_are_logged.py`)."""
    monkeypatch.setenv("KRAKEN_SPOT_API_KEY", "the-key-value")
    monkeypatch.delenv("KRAKEN_SPOT_API_SECRET", raising=False)
    with caplog.at_level(logging.ERROR):
        result = _runner.invoke(app, ["engine", "flatten", "--state-dir", str(tmp_path)])
    assert result.exit_code == 1
    assert "KRAKEN_SPOT_API_SECRET" in caplog.text  # the refusal really did reach the log
    assert "the-key-value" not in caplog.text
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_engine_flatten.py -q -k "subcommand or state_dir_is_required or credential"`
Expected: FAIL — `zcrypto engine flatten --help` exits non-zero because no such command exists.

- [ ] **Step 3: Implement**

Append to `cli/engine/command.py`, immediately after `exec_status` and its `_echo_gate_verdict` helper:

```python
@engine_app.command()
def flatten(
    state_dir: Path = typer.Option(
        ...,
        "--state-dir",
        help="Engine state directory holding the control files and receiving this run's record. Required: this command must not depend on a config file when the environment is what broke.",
    ),
    execute: bool = typer.Option(
        False,
        "--execute",
        help="Actually send. Without it the account is read, the plan is printed and nothing is sent.",
    ),
) -> None:
    """Close every open position and sell every non-EUR balance at market, account-wide.

    Without `--execute` it reads the account, prints the plan and stops. With `--execute` it needs
    the engine's kill file already in place, asks for a typed confirmation on the terminal, then
    cancels every resting order, closes every margin position reduce-only, and sells every non-EUR
    balance -- all at market, all journaled. Exit 0 the account reads flat, 1 refused before the
    venue was touched, 2 something is still open, 3 the venue could not be read before anything was
    sent.
    """
    # Imported HERE, not at module scope: `cli.engine.flatten` pulls nautilus (~1 s) and
    # `zcrypto --help` must never pay it -- the same reason `cli.engine.node` is lazy above.
    from cli.engine.flatten import run_flatten

    key = os.environ.get(_API_KEY_VAR)
    secret = os.environ.get(_API_SECRET_VAR)
    missing = [name for name, value in ((_API_KEY_VAR, key), (_API_SECRET_VAR, secret)) if not value]
    if missing:
        # The refusal names the VARIABLES and never their contents.
        raise _abort(f"the trade credentials are not in this environment: {', '.join(missing)}")

    from nautilus_trader.adapters.kraken import KrakenSpotHttpClient

    client = KrakenSpotHttpClient(key, secret)
    raise typer.Exit(code=run_flatten(client, state_dir=state_dir, execute=execute, echo=typer.echo))
```

Add near the other module constants at the top of `cli/engine/command.py`:

```python
# The two variables carrying the trade credentials, rendered onto the engine host by the deploy.
# Named here so a refusal can say WHICH is missing without ever touching a value.
# `cli/engine/node.py` defines the same two names for the same reason. The copy is deliberate and
# not shared: importing them would pull nautilus into this module's scope and defeat the lazy
# import that keeps `zcrypto --help` off the ~1 s adapter load. `engine.env.j2` renders both.
_API_KEY_VAR = "KRAKEN_SPOT_API_KEY"
_API_SECRET_VAR = "KRAKEN_SPOT_API_SECRET"
```

And pin the adapter name this command newly imports under `cli/`. In `tests/test_nautilus_interface_pin.py`, insert into `PINNED_SYMBOLS` in the list's existing alphabetical order — after `("nautilus_trader.adapters.kraken", "KrakenProductType")`:

```python
    ("nautilus_trader.adapters.kraken", "KrakenSpotHttpClient"),
```

- [ ] **Step 4: Update the README in the same change**

In `README.md`'s `zcrypto engine` subcommand table, add this row directly below the `exec-status` row:

```markdown
| `flatten --state-dir <PATH> [--execute]` | Close every open position and sell every non-EUR balance at **market**, account-wide — the emergency halt, run on the engine host through `sudo zcrypto-flatten` and never by hand. Without `--execute` it reads the account, prints every leg with its side, quantity, pair and estimate at the taker rate, lists every balance below the venue minimum and every balance no EUR or BTC pair can carry, and **sends nothing**. With `--execute` it refuses unless the engine's kill file is already present, refuses without a controlling terminal, prints the same plan, and reads a typed `FLATTEN` from the terminal (never from stdin; there is deliberately no flag that skips it) before it cancels every resting order account-wide, closes each margin position with a reduce-only market IOC order sized from a fresh post-cancel read, and sells each non-EUR balance at market in two passes so a BTC-quoted leg's proceeds are sold too. Dust — a balance below the venue's quantity or notional minimum — is listed and not sent, and does not make the account not-flat; a margin remainder is never dust and is sent regardless, since a remainder left open is exposure. Every request and every venue answer is written to `<state-dir>/exec/flatten-<timestamp>.json`, its own artifact. Exit **0** the final read shows no resting order, no open position and nothing sellable left; **1** refused with nothing sent (no kill file, no terminal, confirmation did not match, credentials absent); **2** something is still open, or the cancel failed, or a read after the cancel failed — never 0 and never 3, because the account may already have moved; **3** the venue could not be reached or read before anything was sent. Re-runnable: a second run finds less to do and does it. |
```

- [ ] **Step 5: Run the tests**

Run: `uv run pytest tests/test_engine_flatten.py tests/test_engine_command.py tests/test_nautilus_interface_pin.py tests/test_cli.py tests/test_cli_help_hygiene.py tests/test_internal_terms_not_operator_visible.py -q`
Expected: PASS. `tests/test_engine_command.py` is the existing suite over the module this task edits — the diff reaches it, so it runs here.

- [ ] **Step 6: Commit**

```bash
git add cli/engine/command.py README.md tests/test_engine_flatten.py tests/test_nautilus_interface_pin.py
git commit -m "feat(engine): register zcrypto engine flatten and document it"
```

Body: `--state-dir` is required so the button does not depend on a config mount; the module is imported lazily so `--help` never pays the nautilus import; the credential refusal names the variables and never a value.

______________________________________________________________________

### Task 10: The host wrapper

**Files:**

- Create: `infra/ansible/roles/engine/templates/zcrypto-flatten.sh.j2`
- Modify: `infra/ansible/roles/engine/tasks/main.yml` (one task, directly after `install the engine systemd unit`)
- Modify: `tests/test_infra_shell_templates_render.py` (`REGISTERED`, `RUNTIME_FACTS`)
- Test: `tests/test_engine_flatten_wrapper.py`

**Interfaces:**

- Consumes: `zcrypto engine flatten --state-dir <PATH> [--execute]` from Task 9.
- Produces: `/usr/local/sbin/zcrypto-flatten` on the engine host, rendered from `engine_state_dir`, `engine_image`, `engine_image_digest`, `engine_uid`, `engine_gid`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_engine_flatten_wrapper.py`:

```python
"""Guard: the rendered `zcrypto-flatten` wrapper starts the flatten command and not the capture
daemon, refuses to run a second live client beside a still-running engine, and writes the kill file
BEFORE it stops the unit.

Rendered through a bare jinja2 Environment with Ansible's own block settings
(`tests/test_infra_tape_bars_template.py`'s precedent), then EXECUTED against fakes on PATH
(`tests/test_converge_sh.py`'s precedent) -- the properties that matter here are orderings, and no
text assertion can see an ordering.
"""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import jinja2
import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
TEMPLATE = REPO / "infra/ansible/roles/engine/templates/zcrypto-flatten.sh.j2"
ROLE_TASKS = REPO / "infra/ansible/roles/engine/tasks/main.yml"

_ENV = jinja2.Environment(trim_blocks=True, lstrip_blocks=False, undefined=jinja2.StrictUndefined)

DIGEST = "sha256:" + "d" * 64
CONTEXT = {
    "engine_image": "ghcr.io/zhaow-de/zcrypto-capture",
    "engine_image_digest": DIGEST,
    # uid/gid arrive as STRINGS from the role's getent-driven set_fact, not the ints a guess supplies.
    "engine_uid": "998",
    "engine_gid": "998",
    "engine_state_dir": "/var/lib/zcrypto-engine",
}

_FAKE = """#!/bin/sh
echo "$0 $*" >> "$LOG"
"""


def _render(**overrides) -> str:
    return _ENV.from_string(TEMPLATE.read_text()).render(**{**CONTEXT, **overrides})


def _harness(tmp_path, *, state_dir=None, unit_active_calls=0, create_exec_dir=True):
    """A bin/ of fakes on PATH. `systemctl is-active` succeeds for the first `unit_active_calls`
    probes, so a unit that never goes inactive can be modelled.

    `sleep` is faked to a no-op: the wrapper's stop-wait polls once a second for its whole bound, and
    the property under test is the refusal, never the wall clock spent reaching it.

    `create_exec_dir=False` models the FRESHLY CONVERGED host: the role creates the state dir,
    store/ and journal/ and never exec/, which the engine's own kill-file writer creates lazily on
    a host that has tripped a kill. Creating it unconditionally here would put every wrapper test on
    a host that has already tripped one, which is the case the button is least often used on."""
    state = state_dir or (tmp_path / "state")
    if create_exec_dir:
        (state / "exec").mkdir(parents=True, exist_ok=True)
    else:
        state.mkdir(parents=True, exist_ok=True)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "calls.log"
    counter = tmp_path / "is-active-count"

    (bin_dir / "id").write_text('#!/bin/sh\necho 0\n')
    (bin_dir / "sleep").write_text("#!/bin/sh\nexit 0\n")
    (bin_dir / "chown").write_text(_FAKE)
    (bin_dir / "docker").write_text(_FAKE)
    (bin_dir / "systemctl").write_text(
        "#!/bin/sh\n"
        'echo "systemctl $*" >> "$LOG"\n'
        '# the kill file must already exist by the time the unit is stopped\n'
        'if [ "$1" = "stop" ]; then [ -f "$KILLPATH" ] && echo "kill-file-present-at-stop" >> "$LOG"; fi\n'
        'if [ "$1" = "is-active" ]; then\n'
        '  n=$(cat "$COUNTER" 2>/dev/null || echo 0); n=$((n + 1)); echo "$n" > "$COUNTER"\n'
        '  [ "$n" -le "$ACTIVE_CALLS" ] && exit 0\n'
        '  exit 3\n'
        "fi\n"
        "exit 0\n"
    )
    for name in ("id", "sleep", "chown", "docker", "systemctl"):
        p = bin_dir / name
        p.chmod(p.stat().st_mode | stat.S_IXUSR)

    script = tmp_path / "zcrypto-flatten"
    script.write_text(_render(engine_state_dir=str(state)))
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    env = {
        **os.environ,
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "LOG": str(log),
        "COUNTER": str(counter),
        "ACTIVE_CALLS": str(unit_active_calls),
        "KILLPATH": str(state / "exec" / "kill"),
    }
    return script, state, log, env


def _run(script, env, args=()):
    return subprocess.run([str(script), *args], capture_output=True, text=True, env=env)


def _log(log: Path) -> list[str]:
    return log.read_text().splitlines() if log.exists() else []


def _docker_argv(log: Path) -> list[str]:
    """The argv the fake `docker` was actually invoked with. Every assertion about what the container
    is told to run reads THIS and never the rendered text: a value the wrapper holds in a shell
    variable is not a token of the render, so a text assertion hunting for one silently pins
    nothing."""
    (line,) = [entry for entry in _log(log) if "docker" in entry]
    return line.split()


def test_the_rendered_invocation_overrides_the_image_entrypoint_before_the_image(tmp_path):
    """The image's own ENTRYPOINT is the capture daemon's shell script. Without the override the
    words `engine flatten` are appended to THAT, and the container starts capture on a host whose
    engine was just stopped with positions open."""
    script, _state, log, env = _harness(tmp_path)
    assert _run(script, env).returncode == 0
    argv = _docker_argv(log)
    image = f"{CONTEXT['engine_image']}@{DIGEST}"
    assert "--entrypoint" in argv
    assert argv[argv.index("--entrypoint") + 1] == "zcrypto"
    assert image in argv
    assert argv.index("--entrypoint") < argv.index(image)
    assert argv[argv.index(image) + 1 : argv.index(image) + 3] == ["engine", "flatten"]


def test_the_container_runs_as_the_engine_account_and_names_the_state_dir(tmp_path):
    """`--user` is what keeps the journal out of root's ownership inside the engine's own control
    directory, and `--state-dir` is what keeps the button off a config mount."""
    script, state, log, env = _harness(tmp_path)
    assert _run(script, env).returncode == 0
    argv = _docker_argv(log)
    assert argv[argv.index("--user") + 1] == "998:998"
    assert argv[argv.index("--state-dir") + 1] == str(state)
    assert f"{state}:{state}" in argv  # mounted at the path it is named at


def test_the_default_invocation_writes_no_kill_file_stops_nothing_and_passes_no_execute(tmp_path):
    script, state, log, env = _harness(tmp_path)
    result = _run(script, env)
    assert result.returncode == 0, result.stderr
    # The dry run's reads run beside a LIVE engine on the same key. Spec 00106 D1 accepts that cost
    # on condition the wrapper says so, and stdout is the only place it can.
    assert "share the trade key" in result.stdout
    assert not (state / "exec" / "kill").exists()
    assert not any(line.startswith("systemctl") for line in _log(log))
    docker_lines = [line for line in _log(log) if "docker" in line]
    assert docker_lines and "--execute" not in docker_lines[0]


def test_execute_writes_the_kill_file_before_it_stops_the_unit(tmp_path):
    """The order is the whole point: stopping first leaves a window in which a restart re-opens
    what is about to be closed."""
    script, state, log, env = _harness(tmp_path)
    result = _run(script, env, ["--execute"])
    assert result.returncode == 0, result.stderr
    assert "flatten" in (state / "exec" / "kill").read_text()
    assert "kill-file-present-at-stop" in _log(log)
    # The ownership hand-over, asserted where the fake already records it: a root-owned kill file in
    # the engine's 0750 control directory makes the engine's own later write fail EACCES.
    assert any(line.endswith(f"chown 998:998 {state}/exec/kill") for line in _log(log))
    assert any("--execute" in line for line in _log(log) if "docker" in line)


def test_execute_creates_the_missing_exec_directory_before_writing_the_kill_file(tmp_path):
    """A freshly converged or rebuilt host has no `exec/`: the role creates only the state dir,
    store/ and journal/, and the engine's own kill-file writer is what creates it lazily — on a host
    that has already tripped a kill, which is not the host the button is pressed on. Without the
    wrapper's own mkdir the redirection dies under `set -eu` with nothing latched and the engine
    still trading."""
    script, state, log, env = _harness(tmp_path, create_exec_dir=False)
    assert not (state / "exec").exists()
    result = _run(script, env, ["--execute"])
    assert result.returncode == 0, result.stderr
    assert "flatten" in (state / "exec" / "kill").read_text()
    assert "kill-file-present-at-stop" in _log(log)


def test_execute_refuses_to_start_the_container_while_the_unit_is_still_active(tmp_path):
    """One key, one client. A flatten running beside a live engine fights it over nonces, and the
    writes are exactly where that is not acceptable."""
    script, state, log, env = _harness(tmp_path, unit_active_calls=999)
    result = _run(script, env, ["--execute"])
    assert result.returncode == 1
    assert not any("docker" in line for line in _log(log))
    assert (state / "exec" / "kill").exists()  # the latch stays; it is what stops a restart


def test_an_unknown_argument_refuses_before_anything_is_written(tmp_path):
    script, state, log, env = _harness(tmp_path)
    result = _run(script, env, ["--dry-run"])
    assert result.returncode == 1
    assert not (state / "exec" / "kill").exists()
    assert _log(log) == [] or not any("docker" in line for line in _log(log))


def test_a_non_root_invocation_refuses(tmp_path):
    script, state, log, env = _harness(tmp_path)
    bin_dir = Path(env["PATH"].split(":")[0])
    (bin_dir / "id").write_text("#!/bin/sh\necho 1000\n")
    result = _run(script, env, ["--execute"])
    assert result.returncode == 1
    assert not (state / "exec" / "kill").exists()


def test_the_role_installs_the_wrapper_root_owned_and_not_world_readable():
    """Root-owned and 0750: a wrapper the engine account could rewrite would turn the engine's own
    compromise into a path to the trade key. Read from the PARSED task -- a substring search over
    the whole file is satisfied by any other task's owner and mode."""
    (task,) = [t for t in yaml.safe_load(ROLE_TASKS.read_text()) if "zcrypto-flatten.sh.j2" in str(t)]
    template = task["ansible.builtin.template"]
    assert template["dest"] == "/usr/local/sbin/zcrypto-flatten"
    assert template["owner"] == "root" and template["group"] == "root"
    assert template["mode"] == "0750"


def test_the_template_renders_with_nothing_left_undefined():
    """`_ENV` is `StrictUndefined`, so a `{{ name }}` this file's own CONTEXT does not carry
    RAISES rather than surviving into the output -- the assertion is that the render completes
    and produces the script. Whether the ROLE defines every name is
    `tests/test_infra_shell_templates_render.py`'s question, not this file's."""
    assert _render().startswith("#!/bin/sh")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_engine_flatten_wrapper.py -q`
Expected: FAIL — the template file does not exist.

- [ ] **Step 3: Write the template**

Create `infra/ansible/roles/engine/templates/zcrypto-flatten.sh.j2`:

```sh
#!/bin/sh
# Rendered by the `engine` Ansible role at /usr/local/sbin/zcrypto-flatten — do not hand-edit on
# the host, it is overwritten on the next converge. Edit
# infra/ansible/roles/engine/templates/zcrypto-flatten.sh.j2 instead.
#
# The emergency halt (spec 00106 D1). Order is load-bearing throughout:
#   1. the kill file FIRST, so nothing re-opens what is about to be closed;
#   2. the unit stopped, and PROVEN inactive — one key means one client, and a second live client
#      fights the engine over nonces;
#   3. the command, as a one-off container from the digest the engine itself runs.
# `--entrypoint zcrypto` is load-bearing: the image's own ENTRYPOINT is the capture daemon's shell
# script, and without the override `engine flatten` is appended to THAT — the container would start
# capture on a host whose engine was just stopped with positions open. The rendered compose file
# bypasses the same trap with its exec-form `entrypoint:`.
# No ZCRYPTO_METRICS_PORT reaches this container (compose sets it, engine.env does not), so its
# exporter never starts and cannot collide with the running engine's published port.
set -eu

UNIT=zcrypto-engine.service
STATE_DIR="{{ engine_state_dir }}"
KILL_FILE="$STATE_DIR/exec/kill"
IMAGE="{{ engine_image }}@{{ engine_image_digest }}"
OWNER="{{ engine_uid }}:{{ engine_gid }}"
STOP_WAIT_SECONDS=60

execute=0
if [ "$#" -gt 1 ]; then
  echo "usage: zcrypto-flatten [--execute]" >&2
  exit 1
fi
case "${1:-}" in
  "") ;;
  --execute) execute=1 ;;
  *)
    echo "usage: zcrypto-flatten [--execute]" >&2
    exit 1
    ;;
esac

if [ "$(id -u)" != 0 ]; then
  echo "zcrypto-flatten: run it as root — sudo zcrypto-flatten" >&2
  exit 1
fi

if [ "$execute" -eq 0 ]; then
  echo "zcrypto-flatten: reading the account and printing the plan. Nothing is written and no order is sent."
  echo "zcrypto-flatten: these reads share the trade key with the running engine, so one engine order or cancel may be rejected and left unresolved; the engine reconciles that at its next boundary."
else
  # exec/ is created lazily by the engine's own kill-file writer, and the role's state-directory
  # task creates only the state dir, store/ and journal/ — so on a freshly converged or rebuilt host
  # exec/ does not exist and the redirection below would die under `set -eu` with nothing latched,
  # nothing stopped and no container started. 0750 is the role's own posture for these directories;
  # without the chmod a root-created one lands at root's umask.
  mkdir -p "$STATE_DIR/exec"
  chown "$OWNER" "$STATE_DIR/exec"
  chmod 0750 "$STATE_DIR/exec"
  # The latch, before anything else. Nothing in the code base ever clears it: a person does.
  printf '%s flatten\n' "$(date -u +%Y-%m-%dT%H:%M:%S+00:00)" > "$KILL_FILE"
  # Owned by the service account, not by root: a root-owned file in the engine's own 0750 control
  # directory would make the engine's later write of it fail.
  chown "$OWNER" "$KILL_FILE"
  chmod 0644 "$KILL_FILE"
  echo "zcrypto-flatten: the halt is latched at $KILL_FILE. Nothing clears it automatically."

  systemctl stop "$UNIT"
  waited=0
  while [ "$waited" -lt "$STOP_WAIT_SECONDS" ]; do
    if ! systemctl is-active --quiet "$UNIT"; then
      break
    fi
    waited=$((waited + 1))
    sleep 1
  done
  if systemctl is-active --quiet "$UNIT"; then
    echo "zcrypto-flatten: $UNIT is still running after ${STOP_WAIT_SECONDS}s — refusing to open a second client on the same key. The halt stays latched; stop the unit by hand and run this again." >&2
    exit 1
  fi
  echo "zcrypto-flatten: $UNIT is stopped."
fi

set -- engine flatten --state-dir "$STATE_DIR"
if [ "$execute" -eq 1 ]; then
  set -- "$@" --execute
fi

# -it: the confirmation is read from the controlling terminal, never from stdin.
exec docker run --rm -it --network host \
  --user "$OWNER" \
  --env-file /opt/zcrypto-engine/engine.env \
  -v "$STATE_DIR:$STATE_DIR" \
  -v /opt/zcrypto-engine/zcrypto.toml:/app/zcrypto.toml:ro \
  --entrypoint zcrypto \
  "$IMAGE" \
  "$@"
```

- [ ] **Step 4: Add the role task**

In `infra/ansible/roles/engine/tasks/main.yml`, directly after the `install the engine systemd unit` task and before the `enable + start the engine service (boot resume)` task, insert:

```yaml
# The emergency halt an operator runs by hand. Not a service: nothing starts it, and it notifies no
# handler — installing it must never restart the engine.
- name: install the engine flatten wrapper
  ansible.builtin.template:
    src: zcrypto-flatten.sh.j2
    dest: /usr/local/sbin/zcrypto-flatten
    owner: root
    group: root
    mode: "0750"
```

- [ ] **Step 5: Register the template in the repo-wide shell-template guard**

A new `roles/*/templates/*.sh.j2` turns two tests in `tests/test_infra_shell_templates_render.py` red the moment the file exists — the two-way completeness registry, and the render of every template through Ansible's own `Templar` under the role's `defaults/main.yml`. The engine role sets `engine_uid`/`engine_gid` by `set_fact` from `getent` and declares them in no defaults file, so that render aborts `AnsibleUndefinedVariable` until they are supplied. Both are one line each; neither is a reason to weaken the guard.

Add to `REGISTERED`, in its existing alphabetical order — after `"zaccess-probe.sh.j2"`:

```python
    "zcrypto-flatten.sh.j2",
```

Add to `RUNTIME_FACTS`, beside the `ops_uid`/`ops_gid` pair it mirrors:

```python
    # The engine role reads these from getent at converge time and declares them in no defaults
    # file, so the render has no other source for them.
    "engine_uid": "998",
    "engine_gid": "998",
```

Run: `uv run pytest tests/test_infra_shell_templates_render.py -q`
Expected: PASS, with `test_shell_template_renders_to_valid_bash[zcrypto-flatten.sh.j2]` among the collected ids. This is the check that the template renders under the role's own variables; the wrapper suite's own render uses a hand-written context and structurally cannot see a variable the role fails to define.

- [ ] **Step 6: Run the tests and the linters**

Run: `uv run pytest tests/test_engine_flatten_wrapper.py tests/test_infra_shell_templates_render.py tests/test_internal_terms_not_operator_visible.py tests/test_panel_regenerate.py -q`
Expected: PASS. `test_panel_regenerate.py::test_every_ansible_template_is_parseable_jinja` covers the new template; `test_internal_terms_not_operator_visible.py` covers its non-comment lines and the new ansible task name.

Run: `uv run pre-commit run -a` and fix anything ansible-lint reports on the new task.

- [ ] **Step 7: Commit**

```bash
git add infra/ansible/roles/engine/templates/zcrypto-flatten.sh.j2 infra/ansible/roles/engine/tasks/main.yml tests/test_engine_flatten_wrapper.py tests/test_infra_shell_templates_render.py
git commit -m "feat(engine): the zcrypto-flatten host wrapper the engine role deploys"
```

Body: the kill file is written before the unit is stopped and the ordering is proven by execution rather than by reading the template; the wrapper refuses to start the container while the unit is still active; `--entrypoint zcrypto` is asserted to precede the image, because without it the container starts capture.

______________________________________________________________________

### Task 11: The runbook section, its index row, and the classifier that must never press it

**Files:**

- Modify: `infra/runbooks/engine-procedures.md` (append a third section)
- Modify: `infra/runbooks/README.md` (the `engine-procedures.md` index block)
- Modify: `tests/test_ops_daily.py` (`_DESTRUCTIVE`, near line 378)
- Test: `tests/test_ops_daily.py`

**Interfaces:**

- Consumes: `sudo zcrypto-flatten [--execute]` from Task 10 and the exit codes from Task 8.
- Produces: the anchor `engine-flatten` in `infra/runbooks/engine-procedures.md`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_ops_daily.py`, beside the other corpus tests:

```python
def test_the_red_button_is_never_autonomous():
    """The unattended daily pass reads these runbooks and classifies every command in them. This
    one closes the whole book at market; nothing may ever run it without a person."""
    for command in ("sudo zcrypto-flatten", "sudo zcrypto-flatten --execute"):
        assert ops_daily.classify_action(f"`{command}`", host="zcrypto") is not ops_daily.Tier.AUTONOMOUS
```

And add `"zcrypto-flatten"` to the `_DESTRUCTIVE` tuple, with the reason on the line above it:

```python
    # Closes every position and sells every non-EUR balance at market; never a read-only diagnostic.
    "zcrypto-flatten",
```

- [ ] **Step 2: Run the test**

Run: `uv run pytest tests/test_ops_daily.py -q`
Expected: PASS — `zcrypto-flatten` is not an enumerated command head, so it already classifies as prepared.

The runbook edit below cannot move `test_most_read_only_diagnostics_are_autonomous_on_ops`: `_runbook_commands()` keeps only spans whose first word is one of its enumerated heads, so prose spans such as `--execute` or a journal path are never collected at all, and the two spans it does collect (`sudo zcrypto-flatten`, `sudo zcrypto-flatten --execute`) carry the `zcrypto-flatten` token that Step 1 just added to `_DESTRUCTIVE` — which puts them outside that test's denominator entirely. If it goes red anyway, something other than this section moved: **never widen the classifier's allowlist for `zcrypto-flatten`** — it is a destructive command, not a read head — and never narrow the extraction, which games the floor by shrinking its denominator.

- [ ] **Step 3: Write the runbook section**

Append to `infra/runbooks/engine-procedures.md`. The leading rule is the separator this file already puts between `engine-probe-window` and `engine-tracking-band`; a third section appended without it reads as a continuation of the second:

````markdown
______________________________________________________________________

<a name="engine-flatten"></a>

## engine-flatten — PROCEDURE

### What you are seeing

**Nothing fired.** You are here because the book has to be flat within minutes — a crash, a provider-level event, an engine that is dead with positions open — and you have decided to close everything at market rather than wait.

Real money moves, at whatever price the market gives. This closes the **whole account**: every resting order, every margin position, every non-EUR balance, including coin the engine never bought.

### What it means

`sudo zcrypto-flatten` runs one command in a one-off container built from the same image digest the engine runs, so the venue adapter pressing the button is the one that was verified. With `--execute` it first writes the engine's kill file, then stops the engine unit and waits for it to be gone, and only then reads the account and asks you to type a word.

**What it does**: writes the kill file · stops the engine · cancels every resting order account-wide · closes every margin position with a reduce-only market order · sells every non-EUR balance at market, in two passes so a coin with no EUR pair is sold to BTC and the BTC is then sold to EUR · writes a record of every request and every answer.

**What it does not do**: it does not clear the kill file, does not restart the engine, does not touch the engine's execution ledger, and does not close anything partially — it is the whole account or nothing.

**Two limits it carries today.** The reduce-only market close on a margin position has never been sent live from this repository on any order type; the red-button drill in the go-live drill program is where that is first proven, and until its entry reads a pass, treat a margin close as unverified and read Kraken's own positions page afterwards by eye. And the five account reads have been proven against the live venue only once the read-only dry-run recorded in `docs/reference/adapter-verification/` has been run through this wrapper; until that row exists, a live `--execute` is being run against read shapes nothing has confirmed.

### What to do

1. **Read the plan first. It sends nothing.**

```
sudo zcrypto-flatten
```

It prints every resting order it would cancel, every position it would close with its side and quantity, every balance it would sell with an estimate at the taker rate, every balance below the venue's minimum that it will list and not send, and every balance no EUR or BTC pair can carry. It exits 0 and changes nothing. Its reads run beside the still-running engine and share the trade key with it, so one engine order or cancel may be rejected around them; the engine reconciles that at its next 4-hourly boundary.

2. **Press it.**

```
sudo zcrypto-flatten --execute
```

The kill file is written, the engine is stopped, the plan is printed again from a fresh read, and it asks you to type `FLATTEN`. Anything else aborts and nothing is sent. It reads the word from the terminal, never from a pipe, and there is no flag that skips it.

3. **Read the exit code.** It is the whole verdict, and it never reads a single leg's answer.

| code | what it means | what to do |
| -- | -- | -- |
| **0** | the final read shows no resting order, no open position and nothing sellable left | go to step 4 |
| **1** | refused with nothing sent — no kill file, no terminal, the word did not match, or no credentials in the container | nothing was sent; fix what it named and run it again |
| **2** | something is still open, or the account-wide cancel failed, or a read after the cancel failed | go to step 5 |
| **3** | the venue could not be reached or read **before anything was sent** | nothing was sent; the account is as it was |

4. **Confirm it by eye on Kraken.** Open orders and open positions on Kraken's own pages. The engine stays stopped and the kill file stays in place until you decide otherwise — that is what stops anything re-opening.

5. **On exit 2, read the record.** It is `/var/lib/zcrypto-engine/exec/flatten-<timestamp>.json`, and the command prints its path. Each leg carries what was sent and what the venue answered.

- **Every leg answered without an error, and something is still listed?** The venue may simply not have settled yet — the final read is taken immediately. **Run it again**; a second run finds less to do and does it. A second exit 2 naming the same residual is real.
- **A leg reads `unclosable_below_minimum`?** That label is what *this command* read before it sent anything: the position was smaller than the pair's minimum order size. It is never read off the venue's answer, so **read the `error` beside it in the record first.** No `error` at all means the quantity floored to nothing and there was never an order to send. An `error` naming a rate limit, a temporary lockout or any other passing condition is a refusal that may not be about the size at all — **run the command again**, and judge the label on what the second run answers. An `error` that keeps saying the order is too small is the real case: no order can clear that remainder; only Kraken's own settle-position action in the web UI can, and the adapter cannot send it.
- **A balance reads `no_eur_or_btc_pair`?** The venue lists no EUR and no BTC pair for it, so this command cannot sell it. Sell it by hand on Kraken against whatever pair exists.
- **A leg reads `dust_below_venue_minimum`?** Nothing is wrong. The venue would reject that order, and a balance that small is not exposure.
- **A leg reads `no_reference_price`?** No book price backed it: either it surfaced after the plan was priced — no book is read once the cancel has gone out — or its own book could not be read, or answered no usable price. It was sent anyway, sized on the venue's quantity floor alone. The order still went out; the label asks nothing of you, and what the venue answered beside it is the answer.
- **A position reads `pair_not_listed`?** The venue's listing carries no pair for it, so nothing could be sized and no order was sent — everything else was still cancelled, closed and sold. Close that position by hand on Kraken.
- **A position reads `unrecognised_position_side`?** The venue answered a side this command cannot derive a close from, so nothing was sent for that row — everything else was still cancelled, closed and sold. Read the row on Kraken's own positions page and close it there; the side it shows is the finding.
- **A residual reads `resting_order`, `sellable_balance` or `unjudgeable: …`?** These describe the final read rather than a decision made before sending: an order still working, a balance still above the venue's minimums, and a balance whose pair's constraints could not be read back. The first two mean the sweep did not finish the job — run it again. The third means that balance could not be judged at all: check it by hand on Kraken.
- **The record says a read after the cancel failed?** The account may have moved and the run stopped where it stood. Read Kraken's own pages, then run it again.

6. **Do not clear the kill file to restart the engine until you have decided the reason no longer holds.** Clearing it is the same procedure as for any other latched halt, in [`engine.md`](engine.md#zcrypto-engine-exec-kill-tripped).

### Retire when

`flatten` is no longer a subcommand of `zcrypto engine` in `cli/engine/command.py`, or `/usr/local/sbin/zcrypto-flatten` is no longer rendered by the engine role.
````

- [ ] **Step 4: Add the index row**

In `infra/runbooks/README.md`, in the `### [engine-procedures.md]` block, append after the `engine-tracking-band` row:

```markdown
- [`engine-flatten`](engine-procedures.md#engine-flatten) — PROCEDURE: the emergency halt — one command that stops the engine and closes the whole account at market. Nothing fires this; you open it deliberately, and real money moves at whatever price the market gives.
```

- [ ] **Step 5: Run the tests**

Run: `uv run pytest tests/test_ops_daily.py tests/test_infra_alert_rules.py tests/test_code_prose_citations.py -q`
Expected: PASS. `test_every_runbook_anchor_is_defined_in_exactly_one_file` covers the new anchor; the index row Step 4 adds is covered by `test_the_index_routes_to_every_section_and_only_to_real_ones`, whose `unrouted` assertion is what goes red on a section no index row routes to. Both live in `tests/test_infra_alert_rules.py`.

Both new pins — `test_the_red_button_is_never_autonomous` and the corpus guard `test_no_runbook_command_carrying_a_destructive_token_is_ever_autonomous`, which the runbook section has just given something to catch — are green from birth and therefore unproven at this point. Construct the defect by hand before the commit (admit `zcrypto-flatten` as a `_READ_SHAPES` entry, run the two tests, see them name the real command strings, restore), then run their mutation probes **after** the commit below: `mutate-probe.sh` refuses the dirty worktree this task leaves, so a scored probe cannot run before it. The probe lines are in the mutation-probe task.

- [ ] **Step 6: Commit**

```bash
git add infra/runbooks/engine-procedures.md infra/runbooks/README.md tests/test_ops_daily.py
git commit -m "docs(runbooks): the engine-flatten procedure, and the classifier that must never press it"
```

Body: the section names both live-unverified limits explicitly; exit 2 with every leg answered clean is a settle race whose resolution is a second run; the unattended pass's classifier is now asserted never to call the button autonomous.

______________________________________________________________________

### Task 12: Mutation probes on a clean tree

Every probe below runs from the repo root with a **clean worktree** (`mutate-probe.sh` refuses a dirty one, exit 3). **Never pass `--sandbox`** — it refuses pytest. A `KILLED` verdict is what each probe must return; a `SURVIVED` verdict means the guard is blind to the defect it names and the task is not done until a test that bites is added and the probe re-run.

Each probe's `--control` breaks the thing under proof outright — usually by renaming its symbol, and where the target is a shell template by removing the flag or the exit status the test actually reads — so the probe fails; the harness scores nothing until that control has been seen to fail (`mutate-probe.sh` exits 5 otherwise).

- [ ] **Step 1: Confirm the tree is clean**

Run: `git status --porcelain`
Expected: empty.

- [ ] **Step 2: Run each probe and record its verdict**

```bash
# The notional floor is really applied -- not silently zeroed.
infra/scripts/mutate-probe.sh --file cli/engine/flatten.py \
  --control 's/^def classify_balance/def classify_balance_DISABLED/' \
  --mutation 's/applicable = costmin if (costmin is not None and price is not None) else 0.0/applicable = 0.0/' \
  -- uv run pytest tests/test_engine_flatten.py::test_a_balance_over_ordermin_but_under_costmin_is_still_dust -q

# A margin row left in the final snapshot really is a residual.
infra/scripts/mutate-probe.sh --file cli/engine/flatten.py \
  --control 's/^def judge_final/def judge_final_DISABLED/' \
  --mutation 's/^        residuals.append(residual)$/        continue/' \
  -- uv run pytest tests/test_engine_flatten.py::test_a_residual_position_after_the_closes_exits_two -q

# `judge_final` skips only FLAT, never a LONG/SHORT whitelist: a side this code could not close from
# is exposure, and reading it as flat would exit 0 over an open position. The mutation restores the
# whitelist, scoped to `judge_final` so it cannot also move `margin_legs`'s own FLAT test.
infra/scripts/mutate-probe.sh --file cli/engine/flatten.py \
  --control 's/^def judge_final/def judge_final_DISABLED/' \
  --mutation '/^def judge_final/,/^def exit_code/ s/if row.side == "FLAT":/if row.side not in ("LONG", "SHORT"):/' \
  -- uv run pytest tests/test_engine_flatten.py::test_an_unrecognised_position_side_never_aborts_the_button_and_exits_two -q

# An unrecognised position side names its row instead of raising -- raising would abort the sweep
# before the cancel, with the kill file already latched and the engine already stopped.
infra/scripts/mutate-probe.sh --file cli/engine/flatten.py \
  --control 's/^def margin_legs/def margin_legs_DISABLED/' \
  --mutation 's/^        if side is None:$/        if False:/' \
  -- uv run pytest tests/test_engine_flatten.py::test_an_unrecognised_position_side_is_named_and_never_read_as_flat_or_aborted_on -q

# One leg's unreadable book never costs the whole sweep its cancel, its closes and its sales.
infra/scripts/mutate-probe.sh --file cli/engine/flatten.py \
  --control 's/^async def build_plan/async def build_plan_DISABLED/' \
  --mutation 's|^            logger.error("%s: no reference price.*$|            raise|' \
  -- uv run pytest tests/test_engine_flatten.py::test_a_book_read_failure_on_one_leg_never_aborts_the_plan_or_any_other_leg -q

# The margin leg fixes the side a shared pair is priced from. The mutation leaves the read COUNT at
# one, so only the price assertion can bite.
infra/scripts/mutate-probe.sh --file cli/engine/flatten.py \
  --control 's/^async def build_plan/async def build_plan_DISABLED/' \
  --mutation 's/^        wanted.setdefault(leg.symbol, leg.side)$/        wanted[leg.symbol] = leg.side/' \
  -- uv run pytest tests/test_engine_flatten.py::test_a_margin_and_a_spot_leg_on_one_pair_share_one_book_read_taken_on_the_margin_side -q

# The same test's other half, isolated: one book read per PAIR, never per leg. Doubling the loop
# leaves every price correct, so only the count assertion can bite. Pre-write reads are where a
# rate limit costs the cancel.
infra/scripts/mutate-probe.sh --file cli/engine/flatten.py \
  --control 's/^async def build_plan/async def build_plan_DISABLED/' \
  --mutation 's/^    for symbol, side in wanted.items():$/    for symbol, side in list(wanted.items()) * 2:/' \
  -- uv run pytest tests/test_engine_flatten.py::test_a_margin_and_a_spot_leg_on_one_pair_share_one_book_read_taken_on_the_margin_side -q

# A leg is sized against its OWN pair's constraints. Mis-keyed, 0.03 BTC meets BTC/EUR's 0.1 tick,
# floors to nothing and degrades to unpriced -- safe, and silently estimate-less.
infra/scripts/mutate-probe.sh --file cli/engine/flatten.py \
  --control 's/^async def build_plan/async def build_plan_DISABLED/' \
  --mutation 's/^        spot=\[size_leg(leg, constraints\[leg.symbol\], prices.get(leg.symbol)) for leg in spot_raw\],$/        spot=[size_leg(leg, constraints[sorted(constraints)[0]], prices.get(leg.symbol)) for leg in spot_raw],/' \
  -- uv run pytest tests/test_engine_flatten.py::test_each_leg_is_sized_with_the_price_and_the_constraints_of_its_own_pair -q

# `read_snapshot` composes three aborting reads and softens none of them: a snapshot carrying
# `positions=[]` because the venue answered `None` reaches exit 0 over open leverage.
infra/scripts/mutate-probe.sh --file cli/engine/flatten.py \
  --control 's/^async def read_snapshot/async def read_snapshot_DISABLED/' \
  --mutation 's/^        raise FlattenUnreachable("margin positions could not be read: the venue answered nothing")$/        rows = []/' \
  -- uv run pytest tests/test_engine_flatten.py::test_a_snapshot_read_that_answers_nothing_aborts_instead_of_becoming_an_empty_snapshot -q

# An empty answer is a real one, and the render says so in words -- a plan section that printed
# nothing reads the same as one that failed to print.
infra/scripts/mutate-probe.sh --file cli/engine/flatten.py \
  --control 's/^def render_plan/def render_plan_DISABLED/' \
  --mutation 's/^    if not plan.margin:$/    if False:/' \
  -- uv run pytest tests/test_engine_flatten.py::test_a_venue_that_answers_empty_is_a_plan_with_no_legs_that_says_so_in_words -q

# A top-of-book price of zero is refused rather than carried. Carried, it makes every notional read
# as nothing: every basket leg listed as dust, `judge_final` agreeing, exit 0 over a full spot book.
infra/scripts/mutate-probe.sh --file cli/engine/flatten.py \
  --control 's/^async def read_book_price/async def read_book_price_DISABLED/' \
  --mutation 's/^    if price <= 0.0:$/    if False:/' \
  -- uv run pytest tests/test_engine_flatten.py::test_a_non_positive_book_price_aborts_the_read_rather_than_pricing_a_leg_at_nothing -q

# The cancel's own failure really reaches the exit code.
infra/scripts/mutate-probe.sh --file cli/engine/flatten.py \
  --control 's/^def exit_code/def exit_code_DISABLED/' \
  --mutation 's/if result.post_write_failure is not None or not result.cancel_ok or residuals:/if result.post_write_failure is not None or residuals:/' \
  -- uv run pytest tests/test_engine_flatten.py::test_a_failed_cancel_exits_two_whatever_each_leg_answered -q

# The confirm is case-sensitive.
infra/scripts/mutate-probe.sh --file cli/engine/flatten.py \
  --control 's/^def matches_confirm/def matches_confirm_DISABLED/' \
  --mutation 's/return reply.strip() == CONFIRM_WORD/return reply.strip().upper() == CONFIRM_WORD/' \
  -- uv run pytest "tests/test_engine_flatten.py::test_only_the_exact_word_matches[flatten-False]" -q

# The confirm really reads its answer from the controlling terminal. `read_confirm` runs on the live
# path only -- every other test injects `prompt=` -- so the pty test is the single place it is
# executed at all, and an implementation that opened the wrong thing would reach an operator first.
infra/scripts/mutate-probe.sh --file cli/engine/flatten.py \
  --control 's/^def read_confirm/def read_confirm_DISABLED/' \
  --mutation 's|with open("/dev/tty", "r") as tty:|with open("/dev/null", "r") as tty:|' \
  -- uv run pytest tests/test_engine_flatten.py::test_the_confirm_reads_the_controlling_terminal_and_never_stdin -q

# The margin read really is scoped to MARGIN, so a spot holding cannot surface as a position row.
infra/scripts/mutate-probe.sh --file cli/engine/flatten.py \
  --control 's/^async def read_positions/async def read_positions_DISABLED/' \
  --mutation 's/"account_type": AccountType.MARGIN,/"account_type": AccountType.CASH,/' \
  -- uv run pytest tests/test_engine_flatten.py::test_the_position_read_is_scoped_to_margin_with_spot_reports_off -q

# A margin quantity that floors to nothing is named, not sent as a zero-quantity order.
infra/scripts/mutate-probe.sh --file cli/engine/flatten.py \
  --control 's/^def size_leg/def size_leg_DISABLED/' \
  --mutation 's/if qty <= 0.0:/if qty < 0.0:/' \
  -- uv run pytest tests/test_engine_flatten.py::test_a_margin_quantity_that_floors_to_zero_is_unclosable_here_and_named_as_such -q

# The printed estimate is the FLOORED leg's notional. Printed off the raw balance it reads above
# the very costmin the refusal beside it names. The lot step must stay COARSE in that test: at 1e-8
# the two products differ by less than `pytest.approx`'s default tolerance and the probe SURVIVES.
infra/scripts/mutate-probe.sh --file cli/engine/flatten.py \
  --control 's/^def size_leg/def size_leg_DISABLED/' \
  --mutation 's/estimate = qty \* price if price is not None else None/estimate = leg.quantity * price if price is not None else None/' \
  -- uv run pytest tests/test_engine_flatten.py::test_the_estimate_is_the_floored_quantity_s_notional_never_the_balance_s -q

# A price the tick floor erases degrades to unpriced -- the direction that SELLS -- instead of
# zeroing every notional and reading a live balance as dust with `judge_final` agreeing.
infra/scripts/mutate-probe.sh --file cli/engine/flatten.py \
  --control 's/^def classify_balance/def classify_balance_DISABLED/' \
  --mutation 's/^    return price if price > 0.0 else None$/    return price/' \
  -- uv run pytest tests/test_engine_flatten.py::test_a_price_the_tick_floor_leaves_at_nothing_degrades_to_unpriced_and_is_sold -q

# A rejected sub-ordermin margin closer really reaches the journal labelled, not as a bare EOrder
# string -- the label is what routes the operator to Kraken's settle-position action.
infra/scripts/mutate-probe.sh --file cli/engine/flatten.py \
  --control 's/^async def _send/async def _send_DISABLED/' \
  --mutation 's/if sized.leg.kind == "margin" and sized.qty < constraints.ordermin:/if False:/' \
  -- uv run pytest tests/test_engine_flatten.py::test_a_sub_ordermin_margin_row_is_sent_and_its_rejection_still_exits_two -q

# --- the async/book correction's own guards ----------------------------------------------------
# `Recorder.call` really awaits. Un-awaited, the fake's coroutine is journalled as a repr and the
# read that consumes it fails -- which is exactly what happened live, where the answer never came
# back at all.
infra/scripts/mutate-probe.sh --file cli/engine/flatten.py \
  --control 's/^    async def call/    async def call_DISABLED/' \
  --mutation 's/^            answer = await fn()$/            answer = fn()/' \
  -- uv run pytest tests/test_engine_flatten.py::test_the_full_sequence_calls_the_venue_in_the_order_the_design_fixes -q

# The book's side is CALLED, not read. Driven against a real offline `OrderBook`, where reading the
# attribute hands back the bound method -- the shape the old fake's plain lists hid.
infra/scripts/mutate-probe.sh --file cli/engine/flatten.py \
  --control 's/^async def read_book_price/async def read_book_price_DISABLED/' \
  --mutation 's/^        levels = list(read_side())$/        levels = list(read_side)/' \
  -- uv run pytest tests/test_engine_flatten.py::test_the_book_read_takes_its_side_from_the_real_order_book_type -q

# A side that is a plain sequence is NAMED, never a bare TypeError out of a function that promises
# to raise nothing.
infra/scripts/mutate-probe.sh --file cli/engine/flatten.py \
  --control 's/^async def read_book_price/async def read_book_price_DISABLED/' \
  --mutation 's/^    except TypeError as exc:$/    except ZeroDivisionError as exc:/' \
  -- uv run pytest tests/test_engine_flatten.py::test_a_book_whose_side_is_a_plain_sequence_is_named_rather_than_raising_a_traceback -q

# The command opens the loop. Called synchronously the coroutine is never awaited, `typer.Exit` gets
# a coroutine object where the code belongs, and the stub records no loop.
infra/scripts/mutate-probe.sh --file cli/engine/command.py \
  --control 's/raise typer.Exit(code=asyncio.run(run_flatten(/raise typer.Exit(code=asyncio.run(run_flatten_MISSING(/' \
  --mutation 's/raise typer.Exit(code=asyncio.run(run_flatten(client, state_dir=state_dir, execute=execute, echo=typer.echo)))/raise typer.Exit(code=run_flatten(client, state_dir=state_dir, execute=execute, echo=typer.echo))/' \
  -- uv run pytest tests/test_engine_flatten.py::test_the_command_opens_the_event_loop_every_venue_call_needs -q

# The offers guard compares KIND, not only existence. The mutation shadows `_Book`'s two methods
# with the plain lists they used to be -- every hasattr still passes, and only the kind check bites.
infra/scripts/mutate-probe.sh --file tests/test_engine_flatten.py \
  --control 's/^_BOOK_PLUMBING = frozenset/_BOOK_PLUMBING_DISABLED = frozenset/' \
  --mutation 's/^        self._asks = \[_Level(ask)\]$/        self._asks = [_Level(ask)]; self.bids = self._bids; self.asks = self._asks/' \
  -- uv run pytest tests/test_engine_flatten.py::test_no_stub_in_the_red_button_suite_offers_a_name_its_real_library_type_lacks -q

# The unattended pass's classifier really refuses the red button. Named tests, never a `-k` filter:
# a KILLED verdict over a filter says SOME collected test bites, and three tests carry the button's
# name today. The runbook task ran these five and got KILLED; that verdict is not reusable here --
# it describes the tree at that commit, and every commit since could have moved it. Re-run them.
# The control flips both of `classify_action`/`_classify_one`'s default-deny returns, so every
# command classifies autonomous; each mutation admits one spelling of the button as a read shape.
infra/scripts/mutate-probe.sh --file infra/scripts/ops_daily.py \
  --control 's/^    return Tier.PREPARED$/    return Tier.AUTONOMOUS/' \
  --mutation 's|^_READ_SHAPES = ($|_READ_SHAPES = (\n    _Shape(("zcrypto-flatten",), {"--execute": None}),|' \
  -- uv run pytest tests/test_ops_daily.py::test_the_red_button_is_never_autonomous -q

infra/scripts/mutate-probe.sh --file infra/scripts/ops_daily.py \
  --control 's/^    return Tier.PREPARED$/    return Tier.AUTONOMOUS/' \
  --mutation 's|^_READ_SHAPES = ($|_READ_SHAPES = (\n    _Shape(("zcrypto-flatten",), {"--execute": None}),|' \
  -- uv run pytest tests/test_ops_daily.py::test_no_runbook_command_carrying_a_destructive_token_is_ever_autonomous -q

# Twice over the wrapping walk: the host-wrapper shape moves its `sudo`, absolute-path and `ssh`
# rows, the in-container shape moves its `docker exec` and bare rows. Neither alone reaches all six.
infra/scripts/mutate-probe.sh --file infra/scripts/ops_daily.py \
  --control 's/^    return Tier.PREPARED$/    return Tier.AUTONOMOUS/' \
  --mutation 's|^_READ_SHAPES = ($|_READ_SHAPES = (\n    _Shape(("zcrypto-flatten",), {"--execute": None}),|' \
  -- uv run pytest tests/test_ops_daily.py::test_no_wrapping_of_the_red_button_reaches_autonomous -q

infra/scripts/mutate-probe.sh --file infra/scripts/ops_daily.py \
  --control 's/^    return Tier.PREPARED$/    return Tier.AUTONOMOUS/' \
  --mutation 's|^_READ_SHAPES = ($|_READ_SHAPES = (\n    _Shape(("zcrypto", "engine", "flatten"), {"--execute": None, "--state-dir": _PATH}),|' \
  -- uv run pytest tests/test_ops_daily.py::test_no_wrapping_of_the_red_button_reaches_autonomous -q

# The READ half of each wrapping pair is really observed -- without it the walk's refusals would be
# satisfied by a classifier that refuses everything. Breaking the `ssh` peel fails one row's read.
infra/scripts/mutate-probe.sh --file infra/scripts/ops_daily.py \
  --control 's/^    return Tier.PREPARED$/    return Tier.AUTONOMOUS/' \
  --mutation 's/tokens\[0\] == "ssh"/tokens[0] == "ssh_NEVER"/' \
  -- uv run pytest tests/test_ops_daily.py::test_no_wrapping_of_the_red_button_reaches_autonomous -q

# The image entrypoint override is really required, and really before the image.
infra/scripts/mutate-probe.sh --file infra/ansible/roles/engine/templates/zcrypto-flatten.sh.j2 \
  --control 's|^  --entrypoint zcrypto \\$|  --env ENTRYPOINT_OVERRIDE_REMOVED=1 \\|' \
  --mutation 's|--entrypoint zcrypto|--entrypoint sh|' \
  -- uv run pytest tests/test_engine_flatten_wrapper.py::test_the_rendered_invocation_overrides_the_image_entrypoint_before_the_image -q

# The kill file is really written before the unit is stopped. The mutation MOVES the stop ahead of
# the write rather than DELETING the write: deleting it leaves the real (unfaked) `chmod 0644
# "$KILL_FILE"` operating on a file that was never created, which kills the probe on that crash
# under `set -eu` before the ordering assertion is ever reached — a KILLED verdict that proves
# nothing about the ordering. Verify the inserted line lands after the `mkdir -p "$STATE_DIR/exec"`
# block: the insertion address is the first `  printf`, and the block above it carries none.
infra/scripts/mutate-probe.sh --file infra/ansible/roles/engine/templates/zcrypto-flatten.sh.j2 \
  --control 's/^  systemctl stop "\$UNIT"/  systemctl stop_DISABLED "$UNIT"/' \
  --mutation '/^  systemctl stop "\$UNIT"$/d
/^  printf/i\
  systemctl stop "$UNIT"' \
  -- uv run pytest tests/test_engine_flatten_wrapper.py::test_execute_writes_the_kill_file_before_it_stops_the_unit -q

# The still-active refusal really refuses.
# The control turns both indented refusals into a success, so the test's `returncode == 1` fails —
# a shell-portable break, unlike disabling `set -eu`, whose fatality on a bad option is dash's
# behaviour and not something a test may rely on.
infra/scripts/mutate-probe.sh --file infra/ansible/roles/engine/templates/zcrypto-flatten.sh.j2 \
  --control 's/^    exit 1$/    exit 0/' \
  --mutation 's/^  if systemctl is-active --quiet "\$UNIT"; then$/  if false; then/' \
  -- uv run pytest tests/test_engine_flatten_wrapper.py::test_execute_refuses_to_start_the_container_while_the_unit_is_still_active -q

# The widened structural guard really names the account-wide cancel.
infra/scripts/mutate-probe.sh --file tests/test_engine_executor.py \
  --control 's/^_VENUE_MUTATING_MODULES = .*/_VENUE_MUTATING_MODULES = frozenset()/' \
  --mutation 's/, ".cancel_all_orders"//' \
  -- uv run pytest tests/test_engine_executor.py::test_the_venue_mutating_names_have_exactly_one_module -q
```

For the last probe the mutation removes the name and the probe would still pass (no module names it today), so it is expected to report **SURVIVED**. That is the correct reading and the reason the guard was proven by construction in the earlier task instead: record the SURVIVED verdict and the construction proof together rather than inventing a fixture. Its control empties the module allowlist instead of the name tuple — emptying the tuple leaves the walk with nothing to match, so the probe would PASS under the control and `mutate-probe.sh` would refuse to score anything (exit 5). Every other probe must report `KILLED`.

- [ ] **Step 3: Adjust any sed that does not apply**

Two of the correction's pins carry no mutation probe, and the reason is what they are. `test_every_client_call_the_red_button_makes_needs_a_running_loop` and `test_a_client_call_inside_a_loop_answers_with_an_awaitable_the_module_must_await` assert about `KrakenSpotHttpClient` itself, not about anything in `cli/`: no mutation of this repo can move them, and they are not blind if they stay green under one. Each is the pin that goes red the day the adapter's shape changes under the design that assumes it. The second reaches Kraken's public listing endpoint and runs only under `ZCRYPTO_VENUE_CONTRACT=1`; the first needs no network, because with no running loop nothing can be scheduled onto one and no request can leave.

`mutate-probe.sh` exits 6 on a no-op sed. If an expression above misses because the implemented line differs from the plan's, **fix the sed to match the real line**, never the line to match the sed. Re-run until every probe reports a verdict.

- [ ] **Step 4: Confirm the tree is clean again**

Run: `git status --porcelain && uv run pytest tests/test_engine_flatten.py tests/test_engine_flatten_wrapper.py tests/test_engine_executor.py tests/test_ops_daily.py -q`
Expected: empty status, all green. `mutate-probe.sh` restores on every exit path; a non-empty status here means a restore failed and must be resolved before anything else.

- [ ] **Step 5: Record the verdicts**

No file changes. Carry the verdict table — probe, verdict, and the one SURVIVED with its reason — into the closeout entry and the PR body. **Never write a verdict from memory**; copy it from the run.

______________________________________________________________________

### Task 13: Closeout

Authored **now**, at the branch's end — never earlier (`.claude/rules/iterations-history.md`'s closeout-doc discipline). Re-verify every status claim against the full branch log before writing a word of it.

**Files:**

- Modify: `docs/open-topics/T0159-engine-flatten-the-red-button.md`
- Modify: `docs/open-topics/README.md`
- Modify: `docs/iterations-history-phase6.md`

- [ ] **Step 1: Read the whole branch before claiming anything**

Run: `git log --oneline develop..HEAD` and `git diff --stat develop..HEAD`
Read both in full. Every claim below must be a claim about what that diff actually contains.

- [ ] **Step 2: Load the skills that own the file mechanics**

Load `topic-ops` before touching either topic file, and `iteration-closeout` before writing the changelog entry. They own serials, the required shape, the partial procedure, index sync, and the entry format; do not improvise any of it.

- [ ] **Step 3: Update the topic**

`docs/open-topics/T0159-engine-flatten-the-red-button.md`:

- `status: open` → `status: partial` (the build sub-item is done; three human-gated ones remain).
- Add a `## Done so far` section written as the OUTCOME, not as a plan: the command, its exit-code contract, the host wrapper, the runbook section, and what the branch deliberately did NOT prove — no live venue call has been made from this code, and the reduce-only market close on margin remains unsent from this repository on any order type.
- **Remove** the two finished bullets from `## Suggested next steps` — the "write plan 00106 … execute … PR" one and the "the runbook section … lands with the code" one. A finished sub-item moves to `## Done so far` rewritten as its outcome; it is never edited in place under `## Suggested next steps`, where it still reads as pending.
- Keep the three human-gated bullets (the attended converge, the live read-only dry-run through the wrapper, drill B) mostly verbatim, with one addition: the converge bullet gains a clause that the same converge records `/usr/local/sbin/zcrypto-flatten` in `docs/reference/fleet.md` — a new permanent host artifact, and the converge is the only host-touching step that puts it there. No `ripe_when` is added: these wait on a person's decision, not on a measurable precondition, and a `ripe_when` that cannot be evaluated from data is worse than none.

`docs/open-topics/README.md`: move the T0159 bullet from `### Open` to `### Partially done` and rewrite it to say the command and the wrapper are built and merged, and that what remains is the attended converge, the live dry-run through the wrapper, and the drill.

- [ ] **Step 4: Append the iterations-history entry**

Append to `docs/iterations-history-phase6.md` (Phase 6 is execution — the subject-matter phase of this work) a new `## <YYYY-MM-DD> — <heading>` section with one bullet per thing that landed. Cover at least:

- the command, its default-is-a-dry-run polarity and why that direction was chosen;
- the exit-code contract, and specifically that a read failing after the first write is 2 and never 3;
- the one predicate serving both the dust classification and the residual verdict, so the two structurally cannot disagree;
- every book read being taken pre-write, including `BTC/EUR` whenever a leg routes through a `/BTC` pair, so the second spot pass never needs a read after the first write;
- the widened venue-mutating guard and the construction that proved it bites;
- the wrapper, the entrypoint override and why it is load-bearing, and the still-active refusal;
- the mutation-probe verdicts, copied from the runs, including the one SURVIVED and its reason;
- **what this did NOT prove**: no live venue call has been made, the five read shapes are unconfirmed against the real venue until the dry-run through the wrapper runs, and reduce-only market on margin is unproven live until the drill records a pass.

Name the CLASS of commits the entry covers ("every commit on this branch"), never an enumeration or a count.

**No decisions-log entry.** `.claude/rules/decisions-log.md`'s gate needs the decision to be about the subject matter — research direction, variants, the feature or model or universe to try. Everything decided on this branch is engineering and operations. Do not write one.

**No dataset-catalog sync.** This iteration introduces, relocates and retires no dataset.

- [ ] **Step 5: Run the gate and the reachable tests**

Run: `uv run pre-commit run -a` to green, re-staging what the hooks rewrite.
Run: `uv run pytest tests/test_engine_flatten.py tests/test_engine_flatten_wrapper.py tests/test_engine_executor.py tests/test_engine_command.py tests/test_nautilus_interface_pin.py tests/test_cli.py tests/test_cli_help_hygiene.py tests/test_internal_terms_not_operator_visible.py tests/test_code_prose_citations.py tests/test_ops_daily.py tests/test_infra_shell_templates_render.py tests/test_panel_regenerate.py tests/test_infra_alert_rules.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add docs/open-topics/T0159-engine-flatten-the-red-button.md docs/open-topics/README.md docs/iterations-history-phase6.md
git commit -m "docs(engine): flatten closeout -- the topic goes partial, the changelog entry, the owed live checks"
```

- [ ] **Step 7: Report, and stop**

The branch is finished. Report its state and wait: an attended session opens the PR only on the user's explicit word (`.claude/rules/branch-workflow.md`). Do not push a PR on your own.

______________________________________________________________________

## Self-Review

Run at the end of writing this plan, against the spec with fresh eyes.

**1. Spec coverage.**

| Spec element | Where it lands |
| --- | --- |
| D1 one host command, kill file first, unit stopped, one-off container, `--entrypoint zcrypto`, `--user`, `--state-dir`, `-it` | Task 10 (wrapper + render/behaviour tests); the `--execute` polarity in Tasks 8–9 |
| D1 dry run reads beside the running engine, wrapper says so | Task 10's dry-run branch and its printed lines |
| D2 one client from the two env vars, the seven methods, named-field parsing, key never logged | Tasks 1, 7, 9; `api_key_masked` asserted in Task 8's journal test |
| D3 orders / positions / balances / one listing / book at depth 1; EUR aliases; costmin from the committed table; `size_order` reuse | Tasks 1–4 |
| D4 side from `position_side`, quantity never above the report's, MARKET IOC reduce-only leverage 2 on margin; spot CASH no reduce-only; EUR-then-BTC pair choice; two passes; dust spot-only; `FLT-` ids; a margin row on an unlisted pair, and one carrying an unrecognised side, both named rather than aborted on | Tasks 2, 3, 4, 7, 8 |
| D2's one exception + D4's no-row-aborts rule, enumerated over every pre-write raising path | Global Constraints, "Every path that can raise before the first write"; Tasks 2, 4, 8 implement the two degrades |
| D5 the sequence and its ordering | Task 6 (gates), Task 7 (the write order test), Task 8 (`run_flatten`) |
| D6 the four exit codes, and the journal's contents and path | Task 8 |
| D7 the widened guard with its reason in the docstring; clean help | Task 5; Task 9 |
| D8.1 every named unit fixture | Tasks 1–8. Two fixtures appear twice on purpose — the post-cancel broken re-read and the fill during the confirm are pinned at `sweep` level in Task 7 (what reached the venue) and end to end in Task 8 (the exit code D8.1 names for them) |
| D8.2 the live read-only dry-run through the wrapper | Out of scope for the branch by construction (host-touching); registered in the topic at Task 13 and named as a live limit in the runbook at Task 11 |
| D8.3 drill B as the end-to-end proof | Named as a live limit in the runbook at Task 11; the drill itself stays the topic's |
| Runbook section, four parts, index row | Task 11 |
| Fable review floor, one branch, one PR | Global Constraints |

Two spec elements are deliberately not implemented on this branch because they cannot be: the live dry-run and the drill are host-touching and attended. Both are named where an operator meets them (the runbook) and registered where deferrals live (the topic) — never left only in prose.

**2. Placeholder scan.** No `TBD`, no "add error handling", no "similar to an earlier task", no test described without its body. Every code step carries the code. The one instruction that defers to judgement — "fix the sed to match the real line" in Task 12 — is a rule about which side to correct, not a missing detail.

**3. Type consistency.** `PairConstraints`, `PositionRow`, `BalanceRow`, `Leg`, `SizedLeg`, `Snapshot`, `Plan`, `LegOutcome`, `SweepResult`, `Recorder` are each defined once and used with the same field names throughout. `classify_balance(free, constraints, reference_price)` has one signature everywhere; `size_leg(leg, constraints, reference_price)` likewise; `sweep(client, rec, plan, listing, *, stamp)` and `run_flatten(client, *, state_dir, execute, …)` match their call sites in the tests. `_ACCOUNT` (the nautilus `AccountId`) reaches the client and `ACCOUNT_ID` (the string) reaches the journal — the fake normalises, so the assertions read the string form in both.

**4. What a reviewer should attack first.** In blast-radius order: the exit-code derivation (a wrong 0 tells an operator the book is flat when it is not), the side derivation and the quantity cap on a margin closer (a wrong side opens the other way), the wrapper's ordering and its still-active refusal (a second live client on one key), and the `--execute` polarity (an accidental invocation that sends). Everything else is Minor by construction.
