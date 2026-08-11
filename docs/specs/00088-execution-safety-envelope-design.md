# The execution safety envelope

The first of five specs that build [[T0018]]'s 6b executor. It adds **no capability**: the engine still submits nothing when this lands. What it adds is the chokepoint every future submission must pass, its revoke paths, and the proof that each one refuses — built while a mistake still costs nothing.

## Context — the transport is already live; only a missing call site stands between this repo and real money

Measured on `develop` at 2026-08-11, all four legs:

- `infra/ansible/roles/engine/templates/zcrypto.toml.j2` renders `exec_enabled = true` — in production, on the live engine host.
- `engine.env` carries the live Kraken trade key (`KRAKEN_SPOT_API_KEY` / `_SECRET`).
- `cli/engine/node.py` registers `KrakenLiveExecClientFactory` and sets `LiveExecEngineConfig(reconciliation=True)`.
- `grep -rnE 'submit_order|order_factory|OrderFactory|MarketOrder\(|LimitOrder\('` over `cli/` and `tests/` returns **0**.

So the deployed engine is an authenticated trading client that has never been told to trade. **There is today no structural difference between "the executor is half-built" and "the executor is live"** — no arming concept exists, and the first merge that adds a call site is also the merge that makes the engine capable of spending money. Every later sequencing choice is moot until that is false.

This spec makes it false. It is the only one of the five that **reduces net risk if it lands alone**, which is why it is first.

## Decisions

### D1 — Five specs, and this is the containment one

The build decomposes risk-first. Sizes are indicative, not commitments:

| Spec | Subject | Blast radius |
| --- | --- | --- |
| **00088** *(this one)* | arming interlock, kill-switch, venue gate, reduce-only-on-restart | none — shadow, submits nothing |
| 00089 | venue truth: instrument map, sizing, the `held` read, realized-state artifact, `zcrypto_exec_*` position families | none — read-only |
| 00090 | the rung-1 order path: maker-first state machine, submission, fill/fee ingestion | **real money, ~€10–30** |
| 00091 | weekly tracking-error report, cost recalibration from real fills | none — read-only |
| 00092 | rung-3 accumulation: [[T0119]]'s `target − held`, skip-or-carry, the full loop | **real money, ~€1,000** |

Two of five carry monetary blast radius, and both sit behind containment that was built and proven before they existed. **The four successors are registered in [[T0018]] by this branch** — a spec is not a registration, and a decomposition that lives only here is invisible at pick time.

Rejected: one iteration. The five have genuinely different evidence regimes — provable offline, provable read-only against the venue, provable only by spending money, provable only after fills exist, provable only after weeks of live operation — and folding them together would put the first `submit_order` in this project's history into the same reviewable diff as a reporting tool. Rejected: cutting 00090 first as a thin vertical slice. It reaches the venue soonest, but it arms a host that already holds the trade key before any revoke path exists.

### D2 — Two independent keys arm the engine, and a third, independent switch disarms it

**Armed ⟺ `exec_armed` is true in config AND the arm file exists.** Both default to closed.

- `exec_armed: bool = False` joins `EngineConfig` in `cli/config.py` beside the existing `exec_enabled`, and the role renders it **explicitly** (`exec_armed = false`) rather than relying on absence, so a converge diff shows it. Raising this key costs an engine converge: window-gated to the 4-hourly inter-cycle gap, canary-gated, pins recorded — deliberate, slow, and in git.
- The **arm file** is `<engine_state_dir>/exec/armed`. The compose file bind-mounts the state dir at the same path inside and outside the container, so a human creates or deletes it in seconds with no converge and no restart.

The three control files, named here because operators type them: `<engine_state_dir>/exec/armed`, `<engine_state_dir>/exec/kill`, `<engine_state_dir>/exec/restart-hold`. Only their **presence** is load-bearing; contents are informational (`restart-hold` carries the process start time so an operator can tell which restart it belongs to).

`exec_enabled` **keeps its current meaning** — "the exec transport is connected". It is already `true` in production, and silently re-meaning a live flag changes deployed behaviour without a diff that says so.

The asymmetry is the point: arming needs a slow recorded act *and* a fast human one, so no single accident arms the live trade path; disarming needs only deleting the file. After the rung-1 probe the operator removes the file and the engine rests genuinely disarmed even though config still permits it.

The **kill switch** is a third file, independent of both, and it **overrides** them: present ⟹ `none`, whatever else is true.

Rejected: config-only. Disarming would then need a converge window, leaving the kill file as the sole fast revoke — and the resting state after a probe would be "armed, stopped only by a kill file", which anyone tidying up could undo. Rejected: file-only. Nothing in git or the deploy record would gate arming, so one stray or restored file would arm a host that already holds the trade key.

### D3 — The gate is a cheap, side-effect-free predicate, called per submission, default closed

`cli/engine/execgate.py` exposes `ExecutionGate.evaluate(now) -> GateVerdict`, where `GateVerdict` carries a **level** — `none` | `reduce_only` | `full` — the input values that produced it, and **`reasons`, a tuple of every condition that restricted the level, not just the first**.

The plural is deliberate and the alternative was a real bug. Several conditions routinely apply at once — on the live host today, the arm file is absent *and* the restart hold is present — so a single-reason verdict would report whichever the implementation happened to check first, and an operator debugging a refusal would fix that one and still be refused. Reasons are emitted in a fixed declaration order so the output is deterministic and diffable; the level is the most restrictive that any applicable condition demands.

**Per submission, not per cycle.** This is the correction that motivates the design. A post-only order that rests and later crosses is a *second* submission decision taken minutes after cycle entry, when the arm file, the kill switch and the venue status may all have changed. A gate evaluated once at cycle entry would be bypassed by exactly the repricing path it exists to guard. So `evaluate()` is specified to be cheap (three `Path.exists()` calls and a cached venue read) and free of side effects, and 00090 calls it immediately before **every** submission.

**Default closed covers a returning reader, not only a raising one.** A venue reader that *returns* something unexpected — `None`, a wrong type — must refuse exactly like one that raises. The distinction matters because the caller in 00090 holds the live trade key: an `evaluate()` that propagates an `AttributeError` at a submission site is an unhandled exception, not a refusal, and unhandled exceptions do not have a safe direction.

**The gate returns a permission level; it does not judge orders.** Deciding whether a particular order is *reducing* requires knowing what is held, which does not exist until 00089. Keeping that out avoids inventing an intent type against no caller, and it draws the seam where the knowledge is.

**Default closed.** Any unreadable input, exception, timeout or unrecognised value resolves to `none`. There is no code path from an error to a permissive verdict.

Rejected: a cycle-entry check cached for the cycle. Cheaper, and wrong for the reason above. Rejected: passing a `SubmissionIntent` now. It would be a type with no producer, designed against zero examples.

### D4 — Venue status comes from Kraken's public REST endpoint, snapshotted with a 30-second bound

The [[T0105]] ruling requires the executor to check venue state before placing orders. **Nautilus cannot supply it** — verified in the installed adapter: `nautilus_trader/adapters/kraken/` carries only per-instrument `InstrumentStatus` / `MarketStatusAction`, refreshed by periodic instrument polling, with no system-wide status; a grep for `systemStatus|system_status|SystemStatus` across the adapter returns nothing. The `venue status system=online` line the fleet relies on today comes from our **own** capture WS client, not from the framework.

So `cli/engine/venue.py` reads Kraken's public `SystemStatus` endpoint, following the REST pattern `cli/ohlc/fetch.py` and `cli/trades/rest.py` already use against `https://api.kraken.com/0/public/`. No API key. Anything but `online` — and any error, timeout or unparseable payload — refuses.

**The snapshot is valid for 30 seconds.** Past that the next `evaluate()` re-reads, and a failed re-read refuses. The bound is reasoned, not taken from taste: the one observed maintenance transition (2026-08-06, 07:01:02Z) delivered `effective_time=None` on every transition — zero advance notice — with the status message arriving roughly 60 s ahead of feed silence, so a 30 s bound sits inside the only notice interval ever observed. It also caps public REST calls at ~2/min no matter how many orders a cycle submits, which a per-submission read would not.

Rejected: reading capture's continuous observation over a local transport. It reuses a proven observer on the same host and adds no external call, but it needs a new transport and makes the engine's ability to trade depend on capture's liveness. Rejected: the adapter's per-instrument status — it answers a narrower question, on a poll interval we do not control, and would not see a venue-wide halt.

### D5 — Execution outcomes get their own ledger; the concordance journal is not touched

`evaluate_gate` scores the Stage-6a streak off the concordance journal: six `cycle-HH.json` per UTC day, each `completed_at` in `[B, B+30 min]`, and a `failed-cycle-*` sidecar makes the day broken. The streak measured **30 days** on 2026-08-11 against a bar of 14, and it is the project's only currently-green light.

A refusal to trade must therefore never touch it. The research path genuinely succeeded — targets were computed correctly — so:

- `cycle-HH.json` keeps schema v1, its validation, its no-peek invariants and its snapshot-hash byte layout **unchanged**.
- Execution outcomes go to a new per-cycle artifact in the same day directory, with its own `schema_version`, recording the verdict, its inputs, and (in this spec, by construction) an empty submission list.
- A test pins the invariant directly: a day whose every execution artifact records a refusal still scores **clean** under `evaluate_gate`.

Rejected: reusing `failed-cycle-*`. It is the smallest change and it would reset the streak on every correct venue deferral, conflating "we deliberately did not trade" with "the cycle malfunctioned". Rejected: an execution section inside `CycleRecord` at schema v2. One artifact is tidier, but the snapshot content hash's byte layout is pinned *by* `schema_version`, so replay, compare and `evaluate_gate` would all have to straddle two versions — putting the machinery the streak rests on under the knife for a cosmetic gain.

### D6 — A restart latches `reduce_only`, and only a human clears it

On start the engine writes a restart-hold marker under the exec directory, unconditionally, carrying the process start time. While it exists the gate returns at most `reduce_only`. Only a human removing it restores `full`.

Restarts are routine here — converges, the supervision watchdog's `os._exit(1)`, the 02:25 reboot slot — and after any of them the engine's belief about what it holds is exactly what has not yet been re-established. Latching is the honest response.

**Later specs may narrow when it clears, never widen it.** Adding "and reconciliation agrees" as a further precondition is a legitimate 00089/00090 change; removing the human act so it clears itself is not.

Rejected: auto-clear on reconciliation agreement. It is the smoother operational answer, but neither the venue read nor the realized-state journal exists until 00089, so it would ship as untested prose in a spec whose entire purpose is provable containment. Rejected: clearing after N clean cycles. Buildable today, but it measures the research path's health, when the thing in doubt after a restart is our view of the position book.

### D7 — The kill switch is manual and latching in this spec

Present ⟹ `none`. A human creates it; a human removes it; **no code path clears it**.

No automatic trips land here. The conditions worth auto-tripping on — fill anomalies, reconciliation divergence, a drawdown breach — are all unobservable until 00089 and 00090, so building them now would ship guards whose defect cannot be constructed, which this project's rules treat as unproven by definition. The hooks land where their conditions exist.

Rejected: tripping on what *is* observable today, such as consecutive failed cycles or a persistently stale venue snapshot. Each is testable now, but it couples the kill switch to research-path health, so a data outage would latch the trade path off and require a human before the next probe.

### D8 — New families under a distinct prefix, admitted in the same change

Six gauges, named verbatim so the keep-list, the panels and the rules cannot drift from what is published:

| Metric | Meaning |
| --- | --- |
| `zcrypto_exec_gate_level` | `0 = none`, `1 = reduce_only`, `2 = full` — the encoding stated in the metric's own HELP text |
| `zcrypto_exec_armed` | both keys present (config **and** arm file) |
| `zcrypto_exec_kill_tripped` | the kill file is present |
| `zcrypto_exec_venue_ok` | the last venue read said `online` |
| `zcrypto_exec_venue_snapshot_age_seconds` | age of that read at publication |
| `zcrypto_exec_restart_hold` | the restart hold is present |

They are published through the existing pattern — built on the same registry the exporter serves and installed via `cycle.py::set_metrics_sink`, as `_CycleGauges` already does.

**The prefix is deliberate.** Existing engine families are `zcrypto_engine_*` and are all intent-side; a new prefix keeps intent-versus-execution unambiguous at `/metrics` level. The existing families are **not** renamed — they are live series, and a rename changes series identity under `increase()`.

Admission is part of this change, both directions of the trap: the keep-list `regex` in `infra/ansible/roles/capture/files/config.alloy` gains all six names (the engine is scraped there as job `engine_app`), and no name is admitted that is not published. A `config.alloy` edit ships only with `-e capture_alloy_digest=<currently-running>`; it is config-only, so no bake is owed.

Two alert rules, both on the `Engine` board:

- **`zcrypto_exec_armed` continuously 1 for more than 6 h** — arming is episodic through 00088–00091 (an attended probe window is short), so a 6 h arm means one was forgotten, which is exactly the failure this spec exists to prevent. **This rule is phase-appropriate, and that is stated rather than discovered later**: 00092's rung-3 loop arms the engine continuously, at which point a duration rule fires forever and must be replaced — most likely by "armed while no cycle has completed recently". Registered with the rest of the sequence in [[T0018]] so the replacement is owed work rather than an alert someone silences.
- **`zcrypto_exec_kill_tripped` is 1** — a deliberate state, but an invisible one is how it gets left on.

Alert summaries carry no internal traceability tokens, per `operator-facing-text.md`, and each names its runbook anchor.

**`zcrypto engine exec-status`** is the operator surface, and it belongs to this spec rather than being scope growth: `reasons` is the field that makes a refusal actionable, a gauge cannot carry a tuple of strings, and the deployment check below requires reading them on the host. It is also the only path that evaluates the gate **on demand** — see the freshness bound in the bounded claims.

**The published gauges reflect the last evaluation, not the current instant.** In this spec the gate is evaluated at process start and after each cycle completes, so a control file changed mid-cycle is honoured immediately by the *gate* (the next `evaluate()` reads the filesystem) but is not visible in *Grafana* until the next cycle. That is acceptable here because nothing submits — the functional guarantee is freshness at the submission site, which 00090 provides by calling `evaluate()` there — and unacceptable to paper over, so it is stated in the bounded claims and drilled through `exec-status` rather than through the gauge.

## Verification

- **Every refusal is constructed and seen to refuse.** One case per input, each flipping the verdict on its own: config false with the file present; config true with the file absent; both true with the kill file present; both true with venue `maintenance`; both true with the venue read raising; both true with the snapshot aged past the bound and the re-read failing; all clear but the restart hold present ⟹ `reduce_only`; all clear ⟹ `full`.
- **The multi-reason case is tested, because it is the live host's actual state.** With the arm file absent *and* the restart hold present, the verdict is `none` and `reasons` names **both**, in declaration order — the test asserts the tuple, not a substring, so an implementation that reports only the first condition fails.
- **Mutation probes** through `infra/scripts/mutate-probe.sh`: deleting any single check must flip at least one case. A guard whose removal breaks nothing is not a guard.
- **The streak invariant, tested through the real path.** `evaluate_gate` takes a list of `CycleOutcome` objects and never globs the journal, so asserting against it directly would prove nothing. The globbing lives in `cli/engine/command.py::_journal_artifacts`, which derives the hour from the filename's last dash-separated segment — meaning `exec-12.json` *would* parse as a valid boundary if any call site's glob matched it. Two tests, because they catch different regressions: a unit test that the shipped globs exclude the exec prefix, and an **integration** test driving the real report path over a synthetic day seeded with refusing execution records, asserting the gate output is byte-identical with and without them.
- **Series budget re-measured, not assumed** — the count is read against the <1k budget in the same change rather than carried from the 819 measured at the [[T0020]] rollout.
- **Live drill on the host, in two parts, because the two paths have different latencies.** The *gate* is drilled through `zcrypto engine exec-status`: create the kill file, confirm the verdict changes on the next invocation, remove it, confirm it changes back — seconds, not hours, and it proves the gate reads live filesystem state. The *publication path* is verified once at process start: immediately after the converge, `zcrypto_exec_gate_level` reads 0 with `zcrypto_exec_restart_hold` at 1 and `zcrypto_exec_armed` at 0 — the correct disarmed resting state, and a shape only a real startup evaluation can produce. Claiming a 0→1→0 gauge flip as a quick drill would be false: between cycle completions the gauge does not move.

## What this does NOT do — bounded claims

- **It does not restrain anything yet.** `reduce_only` has no consumer until 00090. This spec proves the verdict is *computed* correctly, never that it *stops* an order — that proof is owed at the first submission and belongs to 00090.
- **"Per-submission" is a property of the interface here, not an observed behaviour.** `evaluate()` is specified and tested as cheap, idempotent and side-effect-free so that calling it at every submission point is viable; that it *is* so called is 00090's obligation.
- **The gate is designed before the state machine exists.** Its inputs may be extended by 00090; its verdict semantics may not be widened. This is the known structural risk of building containment first, and it is accepted deliberately in exchange for the containment existing before the capability.
- **It does not check whether *this* pair is tradeable** — only whether the venue is. Per-instrument status is available from the adapter and is out of scope until an order needs it.
- **The gauges are as fresh as the last evaluation, which here means process start and each cycle completion — up to four hours old.** A kill switch engaged mid-cycle is honoured by the gate immediately and appears in Grafana late. This is stated rather than fixed because the alternatives are both worse at this stage: evaluating on every metrics scrape puts a network call in the scrape path, where a hanging endpoint stalls the whole `/metrics` endpoint, and a dedicated timer is new machinery inside a live engine process for observability convenience alone. 00090 revisits it because submissions evaluate the gate anyway, which makes a heartbeat nearly free.

## Out of scope

- Order submission, the state machine, the instrument map, venue-constraint sizing, the `held` read, fill/fee ingestion — 00089 and 00090.
- Automatic kill-switch trips (D7), reconciliation-based clearing of the restart hold (D6) — both named as later *narrowings*, both registered in [[T0018]] with the rest of the sequence.
- The nautilus version question. The repo pins 1.230.0 and PR #270's bump is blocked behind an attended probe; this spec touches no adapter behaviour and is indifferent to which of the two is pinned. The bump rides [[T0085]].
