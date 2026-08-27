# Spec 00101 — the idle data socket: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship spec `00101` Option A hardened — `ws_idle_timeout_ms=0` on the engine's Kraken data client, pinned by tests proven to bite, with the operator paragraph landing in the same change — so the disarmed engine stops spending 27 % of the per-IP Cloudflare connection budget it shares with the L2 capture primary.

**Architecture:** One config literal in `cli/engine/node.py::_data_client_config`. Three guards around it: an interface pin on the adapter semantics the decision rests on (`0` disables, `None` silently means 10000), a builder-level `== 0` pin, and an opt-in keyless probe that runs a data-only node against the live venue and counts idle timeouts — parametrised so the defect and the fix are measured on the same fixture. The runbook gains one KNOWN LIMITATION section. Nothing on the executor, the exec client, or any other config field moves.

**Tech Stack:** Python 3.14 via `uv`; `nautilus-trader` at the pinned 2.x wheel (Rust-backed Kraken adapter, config surface read from `.venv/.../nautilus_trader/adapters/kraken/__init__.pyi`); pytest; `infra/scripts/mutate-probe.sh` for guard proofs.

## Global Constraints

- `ws_idle_timeout_ms` is the literal `0`. `None` reads back as `10000` and reinstates the loop — spec D1. No test may accept `None` as "off".
- No other field on `KrakenDataClientConfig` changes: `heartbeat_interval_secs` stays at the adapter default (30) — spec D1.
- No executor change, no subscription of any kind, no log-level suppression — spec D3, D4.
- The restore-to-default rule is stated in `_data_client_config`'s docstring — spec D5.
- The runbook section lands in the SAME change as the code — spec D6, `spec-plan-locations.md`.
- Every guard is proven on a fixture where defect and correct behaviour differ, and the suite keeps a true positive — `agent-ops.md`.
- A network-touching test is gated on `ZCRYPTO_LIVE_VENUE_TESTS=1`, never on reachability — `CLAUDE.md`.
- No new `T<NNNN>` topics. Residuals go to spec D7 and T0155's body.
- Model ceiling for every implementer and task reviewer in this plan: **Opus**. Fable was authorised for the cold spec+plan review only.
- Every commit carries `Co-Authored-By:` and, after its review, `Reviewed-by:` — `commit-messages.md`. Stage by explicit path.
- Branch: `feat/t0155-idle-data-socket`, cut from `8f6370c7` on `deploy/v2-capture-secondary`. Its PR targets that branch, not `develop`, for the same reason the hygiene PR did.

---

### Task 1: Pin the adapter semantics the whole decision rests on

**Files:**
- Modify: `tests/test_nautilus_interface_pin.py` — the function `test_the_kraken_client_configs_accept_the_arguments_we_pass` and one new test beside it

**Interfaces:**
- Consumes: `KrakenDataClientConfig(ws_idle_timeout_ms=...)` and its `.ws_idle_timeout_ms` property (present in the adapter stub)
- Produces: the guarantee later tasks lean on — that `0` and `None` mean what spec D1 says they mean on THIS pinned wheel

- [ ] **Step 1: Add the kwarg to the acceptance test and write the semantics test**

In `test_the_kraken_client_configs_accept_the_arguments_we_pass`, change the data-client construction to:

```python
    KrakenDataClientConfig(
        product_type=KrakenProductType.SPOT,
        environment=KrakenEnvironment.LIVE,
        ws_idle_timeout_ms=0,
    )
```

Directly below that test, add:

```python
# The two values spec 00101 D1 rests on, measured here rather than remembered: `0` disables the
# idle timer, and `None` is NOT "off" -- it silently falls back to the adapter default and reinstates
# the reconnect loop. A future upstream change to either reading would pass every other test.
def test_ws_idle_timeout_zero_disables_and_none_means_the_default():
    from nautilus_trader.adapters.kraken import KrakenDataClientConfig, KrakenEnvironment, KrakenProductType

    off = KrakenDataClientConfig(product_type=KrakenProductType.SPOT, environment=KrakenEnvironment.LIVE, ws_idle_timeout_ms=0)
    assert off.ws_idle_timeout_ms == 0, "0 must read back as 0 -- that is the literal the engine ships"

    fallback = KrakenDataClientConfig(product_type=KrakenProductType.SPOT, environment=KrakenEnvironment.LIVE, ws_idle_timeout_ms=None)
    assert fallback.ws_idle_timeout_ms == 10000, (
        f"None must read back as the adapter default (10000), not as off: {fallback.ws_idle_timeout_ms!r}"
    )
    assert fallback.ws_idle_timeout_ms != off.ws_idle_timeout_ms, "if these ever coincide, None has become a valid 'off' and D1's literal-0 rule is moot"
```

- [ ] **Step 2: Run both tests — expect PASS (an interface pin is green from the start by construction)**

Run: `uv run pytest tests/test_nautilus_interface_pin.py -k "accept_the_arguments or idle_timeout" -v`
Expected: 2 passed. An interface pin asserts the library, not our code, so it cannot be red first; its bite is proven in the next step instead.

- [ ] **Step 3: Prove the pin bites — it must fail if the kwarg is renamed or the fallback changes**

Run, from the repo root (clean tree required; the script refuses otherwise):

```bash
bash infra/scripts/mutate-probe.sh \
  --file tests/test_nautilus_interface_pin.py \
  --control 's/ws_idle_timeout_ms=0,/ws_idle_timeout_ms=0, bogus_kwarg=1,/' \
  --mutation 's/assert fallback.ws_idle_timeout_ms == 10000/assert fallback.ws_idle_timeout_ms == 0/' \
  -- uv run pytest tests/test_nautilus_interface_pin.py -k "accept_the_arguments or idle_timeout" -q
```

Expected: `mutate-probe: KILLED (control proven, tree restored byte-identically)`. The control shows the acceptance test rejects an unknown kwarg (so a rename would be caught); the mutation shows the semantics test refuses a world where `None` means off.

- [ ] **Step 4: Commit**

```bash
git add tests/test_nautilus_interface_pin.py
git commit -m "test(engine): pin the two idle-timeout readings spec 00101 rests on

\`ws_idle_timeout_ms=0\` must read back as 0 and \`None\` must read back as the adapter default
(10000), not as off. Both are the measured basis of spec 00101 D1; either reading changing
upstream would pass every other test and silently reinstate the reconnect loop.

Co-Authored-By: <the authoring model> <noreply@anthropic.com>"
```

---

### Task 2: The one-line change, pinned at the builder

**Files:**
- Modify: `cli/engine/node.py` — `_data_client_config` (return value and docstring)
- Modify: `tests/test_engine_node.py` — `test_the_builder_is_given_the_production_client_and_engine_configs`

**Interfaces:**
- Consumes: `_record_assembly(...)` and `recorder.named("add_data_client")[0]["config"]`, both already in the test file
- Produces: the shipped config; `data_client["config"].ws_idle_timeout_ms == 0` as the property every later step assumes

- [ ] **Step 1: Write the failing assertion**

In `test_the_builder_is_given_the_production_client_and_engine_configs`, after `assert isinstance(data_client["config"], KrakenDataClientConfig)`, add:

```python
    # spec 00101 D1: the idle timer is OFF on the data client. Asserted as the literal 0, because
    # None reads back as 10000 (pinned in test_nautilus_interface_pin.py) and would reinstate the
    # ~14.8 s reconnect loop that spends 27 % of the per-IP Cloudflare connection budget shared with
    # the capture primary. heartbeat_interval_secs stays at the adapter default: the heartbeat is
    # what still catches a dead peer (<= 3 intervals) and what keeps Kraken's ~60 s inactivity close
    # at bay.
    assert data_client["config"].ws_idle_timeout_ms == 0
    assert data_client["config"].heartbeat_interval_secs == 30
```

- [ ] **Step 2: Run it — expect FAIL**

Run: `uv run pytest tests/test_engine_node.py -k the_builder_is_given_the_production_client -q`
Expected: 1 failed, `assert 10000 == 0` — the config does not set the knob yet, so it reads the fallback.

- [ ] **Step 3: Make the change and state the two rules in the docstring**

In `cli/engine/node.py`, replace `_data_client_config` with:

```python
def _data_client_config() -> KrakenDataClientConfig:
    """The Kraken data client. The adapter loads the venue's instrument universe itself on connect;
    nothing here selects it, and `test_engine_node.py`'s live instrument-arrival test is what proves
    the twelve `INSTRUMENT_IDS` still land in the Cache.

    `product_type` and `environment` are stated rather than inherited. Both equal the library's
    defaults today, so nothing moves; they are the two fields that select WHICH Kraken venue this
    engine reaches, and an upstream default flip would otherwise land on the live trade path with
    nothing red anywhere. `test_nautilus_interface_pin.py` pins both enums.

    `ws_idle_timeout_ms=0` is spec 00101 D1, and the value is the LITERAL zero: `None` reads back
    as the adapter default (10000) and reinstates a ~14.8 s reconnect loop on an unsubscribed socket
    -- 40 connection attempts per rolling 10 min against a per-IP Cloudflare budget of ~150 that this
    host shares with the L2 capture primary. Disarmed, nothing is subscribed, so the timer can only
    ever detect the absence of data it was never sent; a dead peer is still caught by the heartbeat
    at <= 3 intervals. D5: if a standing subscription ever lands (spec 00101 D3), restore this to
    the adapter default in the same change -- a permanently-subscribed client is the shape that
    default assumes."""
    return KrakenDataClientConfig(
        product_type=KrakenProductType.SPOT,
        environment=KrakenEnvironment.LIVE,
        ws_idle_timeout_ms=0,
    )
```

- [ ] **Step 4: Run it — expect PASS**

Run: `uv run pytest tests/test_engine_node.py -k the_builder_is_given_the_production_client -q`
Expected: 1 passed.

- [ ] **Step 5: Prove the pin bites against the fallback shape, not merely against absence**

```bash
bash infra/scripts/mutate-probe.sh \
  --file cli/engine/node.py \
  --control 's/        ws_idle_timeout_ms=0,/        ws_idle_timeout_ms=0, product_type=None,/' \
  --mutation 's/        ws_idle_timeout_ms=0,/        ws_idle_timeout_ms=None,/' \
  -- uv run pytest tests/test_engine_node.py -k the_builder_is_given_the_production_client -q
```

Expected: `KILLED (control proven, tree restored byte-identically)`. The mutation is the exact regression D1 names — someone writing `None` for "off" — and the pin must refuse it.

- [ ] **Step 6: Commit**

```bash
git add cli/engine/node.py tests/test_engine_node.py
git commit -m "feat(engine): the data client's idle timer is off, and the builder pins the literal

spec 00101 D1. Disarmed, nothing is subscribed on the Kraken data socket, so the 10 s idle timer
only ever measured the absence of data it was never sent -- one reconnect per 14.8 s, 40 per
rolling 10 min, 27 % of the per-IP Cloudflare connection budget this host shares with the L2
capture primary. The literal 0 is asserted at the builder because None reads back as 10000.
heartbeat_interval_secs is pinned unchanged: it is what still catches a dead peer.

Co-Authored-By: <the authoring model> <noreply@anthropic.com>"
```

---

### Task 3: The keyless probe — defect and fix measured on one fixture

**Files:**
- Modify: `tests/test_engine_node.py` — one new module constant `_IDLE_SOCKET_PROBE` beside `_INSTRUMENT_ARRIVAL_PROBE`, and one new parametrised test beside `test_the_twelve_instruments_are_in_the_cache_when_the_strategy_starts`

**Interfaces:**
- Consumes: `_node_builder`, `EngineConfig(exec_enabled=False)`, `_kraken_public_reachable()`, the `ZCRYPTO_LIVE_VENUE_TESTS` opt-in — all already in the file
- Produces: the measured proof that `0` stops the loop on a live socket AND that the harness would have caught the loop (the `10000` row must reproduce it)

- [ ] **Step 1: Add the probe script**

Beside `_INSTRUMENT_ARRIVAL_PROBE`, add:

```python
# A data-only node, run for a fixed window with the idle timer forced to argv[2], counting the two
# lines the reconnect loop emits. The override goes through `_data_client_config` itself, so the
# probe exercises the same construction path the engine ships -- argv[2]=10000 must REPRODUCE the
# loop (that is what proves this harness bites) and argv[2]=0 must not. Nautilus's Rust logger
# writes to stdout; the counts are taken from the captured stream after the window.
_IDLE_SOCKET_PROBE = """
import os, sys, threading, time
from pathlib import Path

from cli.config import EngineConfig
from cli.engine import node as node_mod
from nautilus_trader.adapters.kraken import KrakenDataClientConfig, KrakenEnvironment, KrakenProductType

root = Path(sys.argv[1])
idle_ms = int(sys.argv[2])
window_s = float(sys.argv[3])

node_mod._data_client_config = lambda: KrakenDataClientConfig(
    product_type=KrakenProductType.SPOT, environment=KrakenEnvironment.LIVE, ws_idle_timeout_ms=idle_ms,
)
live = node_mod._node_builder(
    EngineConfig(store_dir=root / "store", journal_dir=root / "journal", exec_enabled=False)
).build()


def stopper():
    time.sleep(window_s)
    sys.stdout.flush()
    os._exit(0)


threading.Thread(target=stopper, daemon=True).start()
live.run()
"""
```

- [ ] **Step 2: Add the parametrised test**

Beside `test_the_twelve_instruments_are_in_the_cache_when_the_strategy_starts`, add:

```python
@pytest.mark.parametrize(
    "idle_ms,window_s,max_timeouts,why",
    [
        (10000, 70, None, "the adapter default MUST reproduce the loop -- otherwise this harness proves nothing"),
        (0, 180, 0, "spec 00101 D1: the shipped value holds a silent unsubscribed socket open, through three of Kraken's ~60 s inactivity windows"),
    ],
)
def test_the_idle_socket_probe_separates_the_loop_from_the_fix(tmp_path, idle_ms, window_s, max_timeouts, why):
    # Opt-in, not reachability-gated, for the same reason as the instrument-arrival test above: a
    # skip on an unreachable venue would read as coverage. Set ZCRYPTO_LIVE_VENUE_TESTS=1 to run it;
    # the closeout runs it deliberately. Keyless: the data client is public and the node is
    # exec_enabled=False, so no credentials are read.
    if os.environ.get("ZCRYPTO_LIVE_VENUE_TESTS") != "1":
        pytest.skip("needs a live venue: set ZCRYPTO_LIVE_VENUE_TESTS=1 to run it")
    if not _kraken_public_reachable():
        pytest.fail("ZCRYPTO_LIVE_VENUE_TESTS=1 was set but Kraken's public endpoint is unreachable")
    env = os.environ.copy()
    env.pop("KRAKEN_SPOT_API_KEY", None)
    env.pop("KRAKEN_SPOT_API_SECRET", None)
    result = subprocess.run(
        [sys.executable, "-c", _IDLE_SOCKET_PROBE, str(tmp_path), str(idle_ms), str(window_s)],
        capture_output=True,
        text=True,
        timeout=window_s + 60,
        env=env,
    )
    out = result.stdout + result.stderr
    timeouts = out.count("Read idle timeout")
    reconnects = out.count("websocket::client: Reconnecting")
    connected = out.count("CONNECTED")
    detail = f"exit={result.returncode} timeouts={timeouts} reconnects={reconnects} connected={connected}\n--- tail ---\n{out[-3000:]}"
    assert connected >= 1, f"the socket never connected, so the window measured nothing: {detail}"
    if max_timeouts is None:
        # the defect row: at the default the loop fires roughly every 14.8 s, so a 70 s window sees
        # several -- require at least two so one stray line cannot pass the harness
        assert timeouts >= 2 and reconnects >= 2, f"{why}: {detail}"
    else:
        assert timeouts <= max_timeouts and reconnects == 0, f"{why}: {detail}"
```

- [ ] **Step 3: Run the gated test with the venue — expect both rows to PASS, for opposite reasons**

Run: `ZCRYPTO_LIVE_VENUE_TESTS=1 uv run pytest tests/test_engine_node.py -k idle_socket_probe -v`
Expected: 2 passed, ~4.5 min wall clock. The `10000` row passing means the loop reproduced (≥ 2 timeouts in 70 s); the `0` row passing means 0 timeouts and 0 reconnects across 180 s with ≥ 1 `CONNECTED`. If the `10000` row FAILS, stop: the harness cannot see the defect and the `0` row's green is worthless.

- [ ] **Step 4: Run it without the opt-in — expect SKIP, never a silent pass**

Run: `uv run pytest tests/test_engine_node.py -k idle_socket_probe -v`
Expected: 2 skipped with the message naming the env var.

- [ ] **Step 5: Commit**

```bash
git add tests/test_engine_node.py
git commit -m "test(engine): a keyless probe measures the idle loop and its fix on one fixture

Opt-in (ZCRYPTO_LIVE_VENUE_TESTS=1), data-only, no credentials read. The adapter-default row
must REPRODUCE the loop (>= 2 idle timeouts in 70 s) -- that is the harness proving it bites --
and the shipped value must hold the socket open across 180 s with zero timeouts and zero
reconnects. Measured at write time: <paste the two rows' timeouts/reconnects/connected counts>.

Co-Authored-By: <the authoring model> <noreply@anthropic.com>"
```

---

### Task 4: The operator paragraph lands with the code

**Files:**
- Modify: `infra/runbooks/engine.md` — one new section before `## engine-probe-window — PROCEDURE`
- Modify: `infra/runbooks/README.md` — one index row beside the two `engine-*` PROCEDURE rows

**Interfaces:**
- Consumes: the runbook's section shape (`<a name>`, `## <anchor> — KIND`, `### What you are seeing / What it means / What to do`) and its admission rule (procedures for a signal, and accepted limitations)
- Produces: spec D6 on the operating surface; the "stop the engine" sentence carries the owner's approval of spec 00101

- [ ] **Step 1: Add the section**

Immediately before the line `<a name="engine-probe-window"></a>` in `infra/runbooks/engine.md`, insert:

```markdown
<a name="engine-data-socket-idle"></a>

## engine-data-socket-idle — KNOWN LIMITATION

### What you are seeing

Nothing fires this. You are reading `docker logs zcrypto-engine` on the engine host — because a real reconnect line caught your eye, or because a Kraken outage is in progress and you are deciding whether the engine is making it worse.

### What it means

The engine's Kraken **data** socket is idle by design while disarmed: nothing is subscribed between intents, the executor subscribes quotes per intent, and the socket's idle timer is OFF (`ws_idle_timeout_ms=0`, spec `00101`). Its lines therefore mean:

- **`Read idle timeout: no data received for 10.0s`** — the timer has been turned back on. That is a config regression, not a venue event: the literal `0` was replaced (writing `None` does it, silently). Nothing to do on the host; fix the config and redeploy.
- **`Reconnecting` → `Reconnect succeeded`** at INFO, without a preceding idle-timeout line — a real drop. Read it against `zcrypto_capture_reconnects_total{host="zcrypto"}` on the capture dashboard: both moving means the venue or the host's network moved; the engine alone moving is the engine's problem.
- **`Heartbeat timeout: no frame received`** — a dead peer, caught by the heartbeat at three intervals (≤ 90 s). Expect a reconnect to follow.

None of these lines reaches Loki — the engine ships only the `zcrypto` logger — so this is the only place they can be read.

**Why the socket's behaviour is capture's problem.** Kraken's edge rate-limits connection attempts to ~150 per rolling 10 minutes **per IP**, and bans the IP for 10 minutes on breach. The engine host is the L2 capture primary; `ws.kraken.com`, `ws-auth.kraken.com` and `api.kraken.com` resolve to the same edge. So a retry storm from the engine's two sockets can take the capture daemon's ability to reconnect with it — and L2 is unbackfillable. The engine's failure backoff (≈ 0.7 → 5 s, ~30 attempts per 150 s per socket, no knob to change it) crosses that limit at roughly six minutes into a fast-failing outage.

### What to do

- **A Kraken outage in progress and both engine sockets retrying** (`Reconnecting` lines every few seconds, `Reconnect attempt N failed`): **stop the engine** — `sudo docker stop zcrypto-engine` on the host — before the retry count nears 150 in ten minutes. A ban self-renews only while something keeps retrying; the capture daemon's own reconnect needs the budget more than the disarmed engine does. Start it again once `zcrypto_capture_reconnects_total{host="zcrypto"}` stops moving, and read the next `cycle-<HH>.json` for `completed_at` inside `[B, B+30 min]` as the all-clear.
- **A single `Reconnecting`/`Reconnect succeeded` pair** with the venue quiet — note it and move on; the heartbeat did its job.
- **Any `Read idle timeout` line at all** — the knob regressed. Find the change to `cli/engine/node.py::_data_client_config` and redeploy; the builder test that pins it (`test_engine_node.py`) will say which value was written.
```

- [ ] **Step 2: Add the index row**

In `infra/runbooks/README.md`, directly above the `engine-probe-window` row, add:

```markdown
- [`engine-data-socket-idle`](engine.md#engine-data-socket-idle) — KNOWN LIMITATION: the engine's data socket is idle by design while disarmed; what its reconnect lines mean, why they only exist in `docker logs`, and when to stop the engine during a Kraken outage so its retries cannot cost the capture primary its reconnect budget.
```

- [ ] **Step 3: Verify the guards that read these files**

Run: `uv run pytest tests/test_code_prose_citations.py tests/test_internal_terms_not_operator_visible.py -q`
Expected: all passed — the section cites `spec 00101` in prose, which the runbook may (it is read with the repo open), and no plan-task number appears.

Run: `uv run pre-commit run mdformat --files infra/runbooks/engine.md infra/runbooks/README.md`
Expected: Passed, or a rewrite you re-stage.

- [ ] **Step 4: Commit**

```bash
git add infra/runbooks/engine.md infra/runbooks/README.md
git commit -m "docs(runbooks): what the engine's idle data socket's lines mean, and when to stop it

spec 00101 D6, landing with the code it describes. The section is a KNOWN LIMITATION because
nothing fires it: an operator arrives from docker logs on the host, which is the only place the
Rust-side socket lines exist. The outage response -- stop the engine before its two sockets'
retries spend the per-IP budget the capture primary needs -- carries the owner's approval of
spec 00101.

Co-Authored-By: <the authoring model> <noreply@anthropic.com>"
```

---

### Task 5: Verify what the diff can reach, and review before push

**Files:** none modified

- [ ] **Step 1: The tests the change reaches, and the full commit gate**

Run: `uv run pytest tests/test_engine_node.py tests/test_nautilus_interface_pin.py tests/test_engine_command.py tests/test_code_prose_citations.py tests/test_internal_terms_not_operator_visible.py -q`
Expected: all passed, the two probe rows skipped (no opt-in set).

Run: `uv run pre-commit run -a`
Expected: every hook Passed or Skipped; re-stage and re-run if any hook rewrote a file.

- [ ] **Step 2: Review each commit with a subagent other than its author (Opus ceiling), amend `Reviewed-by:` in the same turn**

Run: `bash infra/scripts/review-trailer-audit.sh deploy/v2-capture-secondary`
Expected: `PASS — every code-kind commit ... carries a Reviewed-by trailer.`

---

### Task 6: Closeout — the topic, the history entry, no decisions-log entry

**Files:**
- Modify: `docs/open-topics/T0155-engine-data-socket-reconnects-every-14s-when-idle.md` — `## Done so far` and `## Suggested next steps`, frontmatter `ripe_when`
- Modify: `docs/open-topics/README.md` — the T0155 bullet
- Modify: `docs/iterations-history-phase6.md` — append the entry

**Interfaces:**
- Consumes: the commits above (cite them by hash copied from `git log`, never from memory)
- Produces: T0155 still `partial` (the converge is still owed), with the code half recorded as done and the remainder narrowed to the attended converge; the iter-146 entry

- [ ] **Step 1: Re-true T0155**

Under `## Done so far`, append one bullet recording that spec `00101` is implemented on this branch — the literal `0`, the three guards and what each was proven against, the runbook section — with the commit hashes. Rewrite `**Remainder — implement spec 00101 (A, hardened).**` to `**Remainder — converge spec 00101.**` naming the attended, canary-gated engine converge before the first armed probe pass, and the post-converge reads from spec `00101` § Verification (idle-timeout count 0 in the first hour and at 24 h; reconnects per rolling 10 min ≈ 0 from 40; the next `cycle-<HH>.json` inside `[B, B+30 min]`). Set `ripe_when` to `"the next attended, canary-gated engine converge — spec 00101 is implemented and reviewed on feat/t0155-idle-data-socket; only its delivery is owed"`. Status stays `partial`. Refresh the README bullet's last sentence to match.

- [ ] **Step 2: Append the history entry**

Append to `docs/iterations-history-phase6.md`:

```markdown
## 2026-08-27 — the engine's idle data socket stops spending a connection budget it shares with capture (iter-146)

- **One literal, three guards, one runbook section — spec `00101`.** `ws_idle_timeout_ms=0` on the engine's Kraken data client. Disarmed, nothing is subscribed, so the adapter's 10 s idle timer measured the absence of data it was never sent and reconnected every 14.8 s — 40 attempts per rolling 10 minutes, 27 % of the per-IP Cloudflare budget (~150, 10-minute ban) that the engine host shares with the L2 capture primary and with its own REST order path. The heartbeat, unchanged at 30 s, still catches a dead peer at ≤ 90 s and keeps Kraken's ~60 s inactivity close at bay.
- **The value is pinned as the literal, because `None` means 10000.** An interface pin measures both readings on the pinned wheel; the builder test asserts `== 0` and was proven to refuse `None`; an opt-in keyless probe runs a data-only node against the live venue in two rows — the adapter default MUST reproduce the loop, the shipped value must not — so the harness is shown to bite before its green is believed.
- **The decision was challenged before it shipped, and the option space is recorded.** Fourteen options across four lenses, every claim refuted adversarially: every sentinel-subscription form is equivalent on the stakes and re-arms the trigger; every other knob is A in disguise or not viable; dropping either client breaks the boundary concordance. B stays available on its own armed evidence, re-scoped as an executor change. Two of the topic's own claims fell — the mid-order quote-delay story, and a 1 s backoff floor that was the successful-reconnect step, not failure pacing.
- **What A does not fix is recorded where it will be read, not deferred.** The two-socket outage loop has no adapter knob; the only lever is upstream after the pin moves. Rust-side socket lines never reach Loki. Both live in spec `00101` D7, the runbook section, and [[T0155]]'s body — no new topic, per the standing rule.
- **The converge is still owed.** [[T0155]] stays `partial`; it closes at the next attended, canary-gated engine converge, verified by the idle-timeout count reading 0 at one hour and at 24 h.
```

- [ ] **Step 3: No decisions-log entry, and say so**

This is an engineering decision about a transport knob, not a subject-matter research decision (`decisions-log.md`'s gate). Nothing is appended to `docs/research/14.phase6-decisions.md`; the closeout commit message states that.

- [ ] **Step 4: Commit the closeout**

```bash
git add docs/open-topics/T0155-engine-data-socket-reconnects-every-14s-when-idle.md docs/open-topics/README.md docs/iterations-history-phase6.md
git commit -m "docs(engine): iter-146 closeout -- spec 00101 implemented, its converge still owed

T0155 stays partial: the code half is done and reviewed on this branch; the attended,
canary-gated engine converge is the remainder. No decisions-log entry: a transport knob is an
engineering decision, not a subject-matter one.

Co-Authored-By: <the authoring model> <noreply@anthropic.com>"
```

---

## Self-review

**Spec coverage.** D1 → Task 2 (literal, heartbeat unchanged, docstring). D2 → Tasks 1 and 2 (pins proven against `None` and against a kwarg rename). D3, D4 → Global Constraints (nothing touches the executor, no subscription, no `component_levels`). D5 → Task 2's docstring. D6 → Task 4, same change. D7 → Task 6's history entry and T0155 body; no new topics. Verification § → Task 1 step 3, Task 2 step 5, Task 3 (keyless ≥ 180 s at `0`; the true positive is Task 3's `10000` row — a real reconnect is shown to still log). Deploy § → out of this plan by design: the converge is attended and governed by `capture-deploys.md`; Task 6 records it as the owed remainder.

**Placeholder scan.** The only angle-bracketed items are the two the plan cannot know at write time — the authoring model's name in each trailer, and Task 3's measured counts, which the commit message tells the implementer to paste from the run.

**Type consistency.** `data_client["config"]` is the `KrakenDataClientConfig` instance in every task; `.ws_idle_timeout_ms` and `.heartbeat_interval_secs` are properties on it per the adapter stub; `_IDLE_SOCKET_PROBE`'s argv contract (`root`, `idle_ms`, `window_s`) matches the test's `subprocess.run` argument list.
