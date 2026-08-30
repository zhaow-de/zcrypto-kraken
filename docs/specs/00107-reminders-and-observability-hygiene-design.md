# 00107 — the signals that were silently absent: reminders, log levels, and the descriptions no test can reach

Three findings from the first real daily pass (2026-08-30, `iter-156`), each an instance of the same failure: **a signal that was missing, and nothing noticed.** A reminder that never arrived, a WARNING stream that meant nothing, and an operator-visible surface outside every guard.

| # | component | what it buys |
| --- | --- | --- |
| A | reminders as the daily pass's sixth read — `read_reminders()` in `infra/scripts/ops_daily.py` | due-ness is computed from repo and metric state every day, so a lost Slack message costs nothing |
| B | three `logger.warning` → `logger.info` in `cli/capture/segment_writer.py` | ~1200 expected lines a day stop competing with real findings, and the pass's WARNING channel becomes meaningful |
| C | two assertions on the healthchecks descriptions the pass already fetches | the one operator-visible surface no repo test can reach gains a daily check |

## The measured basis

Read 2026-08-30 against the live stack.

**The reminder.** [[T0103]]'s healable-gap reminder, scheduled for 2026-08-27, **never landed** — `#zcrypto` read across that whole UTC day holds two messages, neither of them it. The archived topic asserts it "cannot be deleted through the API, so it will land in `#zcrypto` on the day". That is false as stated, and because the re-arm step lived *inside* the message, the re-derivation is currently owned by nothing. [[T0105]]'s 2026-08-05 reminder did land, so the mechanism works — this is one lost message, not a broken design. **The structural fact is worse than the incident**: the Slack MCP exposes `slack_schedule_message` but no way to list or verify scheduled messages, so an arming that fails to exist is undetectable from this side. "Armed outside the repo" cannot be checked; it can only be relied upon.

**The log lines.** The capture WARNING volume arrives in bursts, not continuously: two buckets in 24 h — 08-29 13:00 (`zcrypto` 600, `zcrypto-red` 601) and 08-30 05:00 (`zcrypto` 601, secondary none). Three `logger.warning` sites produce them (`segment_writer.py:364`, `:510`, `:544`), and the code comment at `:361` names the cause: *a reconnect's trade snapshot replays prints from before the boundary*. The counters confirm it exactly — `increase(zcrypto_capture_reconnects_total[24h])` reads **2 on `zcrypto` and 1 on `zcrypto-red`**, matching the burst counts one-for-one. Resubscribes, resubscribe errors and desyncs are all **0**, so these are not the desync-recovery replay the rollout skill attributes those lines to. Integrity is intact: `increase(zcrypto_capture_gap_seconds_total[24h])` is **0** on both hosts and the gate streak reads 50.

**The descriptions.** All three healthchecks descriptions that existed before 2026-08-30 carried internal tokens — `Phase-6`, `spec 00050`, `T0083` — on a surface read from a phone with nothing open, which `operator-facing-text.md` governs. They survived because that rule is enforced by a test over git-tracked files and these live hand-written in a SaaS.

## Decisions

### D1 — repo-side due-ness is load-bearing; Slack is a convenience ping

The daily routines stop depending on a Slack message arriving. The pass computes due-ness itself, every day, from state it can read. A lost or never-created reminder then costs nothing, where today it costs the whole check.

Rejected: re-arming alone (restores a trigger that can vanish again undetected), and belt-and-braces (keeps a mechanism whose health nobody can verify while implying it is covered — the worse half of both).

The reminder is still re-armed, as a convenience — by the runbook step that already does it, the next time the section runs. It is no longer the thing the check rests on, so the lost 2026-08-27 message is not replaced out of band.

### D2 — due-ness lives in the instrument, not in a test

`ops_daily.py` gains `read_reminders()`, a sixth source beside alerts, logs, dead-men, verdict and deploys. It reports; it does not block.

**Not a pytest guard.** A test that goes red because a calendar date passed is a bad test: it turns CI red for something that is not a code defect, on a repo where red CI blocks merges — so the pressure becomes "make the test pass" rather than "do the sweep". The suite also never runs against the calendar; the pass runs daily.

**Not a metric and alert rule.** That is the strongest form and needs a textfile exporter on a host plus a pushed rule — converge-shaped work for two reminders on a monthly cadence. Revisit if the pass proves insufficient.

### D3 — each reminder is read from the source that actually knows

- **Refdata sweep**: the last row of `docs/reference/kraken-snapshot-register.md`'s `## Re-confirmation log` table (`#1 (monthly, 2026-08-04)`) plus the monthly cadence [[T0113]] defines. Pure repo, no network. Reports `due in N days` or `OVERDUE by N days`.
- **Healable re-derivation**: whether `zcrypto_reconcile_healable_gap_seconds_total` **increased** in the window. The runbook's own step 1 says to count qualifying days from the ledger and never from Grafana Cloud, because Cloud retains ~14 days and every event predates its window — so the pass does **not** attempt the count. It answers the only question it can answer honestly: *has a new healable-gap event landed since you last looked?* If the counter moved, the recount is owed and the runbook section is named; if it did not, nothing is. The movement is reported as the scraped, extrapolated figure `increase()` returns — never as the ledger's delta, which it is not: the range vector is extrapolated to its boundaries, and step 1 of the runbook exists precisely because Cloud cannot answer this question. **A reset in the window is its own state**: the counter is re-emitted from the ledger's totals every cycle, so a ledger correction or rebuild that lowers the total is a reset, and `increase()` then reports the whole post-reset value as movement — the hazard `zcrypto-reconcile-healable-gap-rate` guards with `resets()` over this same counter and window. The reminder mirrors that guard: on a reset it names the reset, owes the ledger recount, and never quotes the number.

This keeps the instrument **pure-HTTP**. An `ssh`-plus-`sudo` read for the ledger would have given it its first host dependency and a new class of unreadable source, to answer a question the counter already answers. The trigger is also more correct event-driven than calendar-driven: the re-derivation is gated on qualifying days accruing, not on time passing.

### D4 — the three capture lines are INFO, and the reconnect counter is the signal

`segment_writer.py:364` (`dropping late event`), `:510` and `:544` (`dropping replayed event`) become `logger.info`. They record an expected consequence of a normal reconnect, at roughly 600 lines per event; as WARNING they were ~1200 a day of noise competing with real findings, and they made the daily pass's WARNING channel meaningless.

No alert rule depends on them being WARNING, verified on every rule over either host: the capture log-dead rules select `level=~".+"` (INFO still matches, and capture emits ~578 INFO lines a day per host besides these), and the error rules select `ERROR|CRITICAL`. The daily pass filters `WARNING|ERROR|CRITICAL`, so after this change these stop reaching it — which is the point for capture. Where the same lines mean something else, two paragraphs down.

**The handle is not lost for capture**, which was the objection this decision had to answer: `zcrypto_capture_reconnects_total` is a scraped counter that moved 2 and 1 in the window, and it is a better instrument than counting log lines ever was. A comment at each site says so, because the next editor's instinct on seeing "dropping" at INFO will be to raise it back.

**`SegmentWriter` is shared, and the second consumer does lose something — named here, and accepted.** The two liquidations writers (`cli/liquidations/coinalyze.py`, the live poller, and the shelved `cli/liquidations/recorder.py`, both `dedup_key="event_id"`) log the same two `dropping replayed event` lines, and there the drop is *not* expected reconnect noise: spec 00055's bucket watermark filters re-submissions at source, so a drop that still fires means the watermark regressed. The reconnect counter is capture's alone — nothing in `cli/liquidations/` emits it, `SegmentWriter` increments no counter at either drop site, and the rules over `host="ops"` select `ERROR|CRITICAL` or `level=~".+"` — so the daily pass's `## Logs` count was the only automated surface those lines had there.

What replaces it: `tests/test_liquidations_coinalyze.py::test_poll_cycle_second_cycle_is_silent_no_dedup_drops` asserts the drop does not fire and runs in CI on every PR, and this change is what makes it *keep* biting — captured at `logging.WARNING` it would have gone vacuous the moment the level dropped, so re-levelling it is part of D4, not housekeeping beside it. What is genuinely given up is detection of a **runtime-only** watermark regression, one no code change caused. That costs no data — the writer's dedup and the late-event floor are the second and third of spec 00055's three mechanisms and are untouched — and it is still readable from raw INFO logs. Accepted, not deferred: no topic tracks it, and it is reopened only if a watermark regression ever reaches production.

### D5 — the descriptions are checked, not generated

For each of the ten checks the pass already fetches, two assertions: the description carries a `Runbook: infra/runbooks/<file>#<anchor>` that resolves against a real anchor, and it carries no internal token (`Phase <N>`, `T<NNNN>`, `iter-<N>`, `spec <NNNNN>` in the bare or the backticked spelling, `WP<N>`). Violations are findings in the report, named per check.

The literal `Runbook: ` prefix is part of the first assertion, not decoration: a description that merely mentions a runbook path in passing has not been given the link an operator follows from a phone, and accepting one would report as checked a description that carries no link at all. It is also **the link the prefix introduces that is resolved**, not the first path anywhere in the text — a description carrying a passing mention ahead of its real link would otherwise be judged on the mention, and pass while the link an operator taps goes nowhere. The bare decision number (`D5`) that `operator-facing-text.md` also bans is deliberately **not** in the token set: this check detects without repairing, so a false positive costs a finding line in every daily report until a human rewrites a description that was never wrong.

**A description finding is a report line and a journal clause — never the exit code.** The verdict stays `all-clear` / exit 0 unless something else fires. That is exactly what "a finding line in every daily report" above prices, and it is the shape D2 already gives an owed reminder: it reports, it does not block. The check detects without repairing and the descriptions live in a SaaS no repo change can touch, so an escalation would not clear when the branch merges, when CI goes green, or on any later pass — only when a human logs into healthchecks.io. Until then every day's entry would read `attention`, and the all-clear entry that is the journal's whole product would be gone for the duration. It would also invert the severity ordering against D2, where an OWED refdata sweep — real overdue work on externally-owned facts — leaves the exit code at 0.

**Visibility is therefore the entire guarantee, and it is asserted in both places the finding must reach**: a `description:` line under `## Dead-men` in the markdown, and a clause of the journal paragraph. A finding that reached neither would be the silent gap this whole iteration exists to close.

**A source the pass could not READ is untouched by this.** Healthchecks.io unreachable, or the runbook files unreadable, stays `unreadable` → exit 2 like every other read: not seeing is not the same as seeing a defect, and the two must not be blurred.

Rejected: descriptions-as-code with a renderer and a push script, mirroring `alerts.yaml` + `grafana-push.sh`. The hole found was **undetected drift**, and a source file does not close that better — the tokens would have been written into the file too. It would also make a third copy of content the dead-man map in `observability.md` already holds. Detection is what was missing; generation is the upgrade if drift proves recurring rather than one-off.

The cost, accepted: this detects but cannot repair. With ten checks and a daily report naming the offender, a human rewrite is proportionate.

The remedy, stated so the pass has one: rewrite that check's description in healthchecks.io with the admin key, and the finding clears on the next pass. Nothing fired, so there is no alert to follow and no runbook section to open; no command is run, so there is no tier to classify. That imperative lands on the daily pass's own skill in this same change — a ruling recorded only here is invisible at execution time.

### D6 — the belief that made the gap invisible is corrected where it lives

[[T0103]]'s archive says the reminder "cannot be deleted through the API, so it will land in `#zcrypto` on the day". Observation disproves it. The archived file is re-trued in place, and the memo's "armed OUTSIDE the repo" note gains what this iteration measured: that the arming cannot be verified from this side at all, which is why D1 moves the load off it.

**And on every operating surface that still names Slack as the trigger, in this same change** — a ruling recorded only in a spec is invisible at execution time. Three of them, each going false the moment D1 lands, each to name the report's `## Reminders` section instead: `infra/runbooks/reference-data.md`'s opening sentence and its `#refdata-sweep-due` section, which tell the operator they are here because a scheduled Slack message came due; `infra/runbooks/ops.md#healable-threshold-rederivation-due`, which calls itself "a calendar trigger with no metric behind it" when the counter it now reads is exactly that metric; and `.claude/skills/zcrypto-daily-ops/SKILL.md`'s step 5, which evaluates the Slack inbox rather than the report the pass just produced.

**And one more belief, falsified by the same measurement that licenses D4, on the capture-rollout path**: `.claude/skills/zcrypto-rollout-image/SKILL.md` tells an operator that `dropping late event` lines right after a start are healthy **resubscribe** replay. Resubscribes, resubscribe errors and desyncs all read 0 in the window; reconnects read 2 and 1 and match the bursts one-for-one. It is *reconnect* replay, and after D4 it is INFO. The sentence is re-trued there, and in [[T0037]], whose parked-residual argument rests on that same drop being a bare WARNING that the rollout skill documents as noise — after D4 the trace is expected-consequence noise by design, which is the argument for the detector, not against it.

## Verification

- The level change is proven by a test that fails against `logger.warning` — the guard sees the defect it names, on all three sites.
- `read_reminders()` is proven against the **real** register (its parse must find `2026-08-04` in the committed file, not a fixture shaped to the parser) and against a fixture where the counter moved, one where it did not, and one where it reset, so the trigger discriminates rather than always firing — and a correction is never read as an event.
- The description assertions are proven by a fixture carrying an internal token and one carrying a dead runbook link, **plus the true positive that today's ten real descriptions all pass** — a check that refuses everything is not a check.
- A description finding's **visibility** is pinned in both places it must reach, and its **exit-code neutrality** with them: one test asserts the finding line under `## Dead-men`, the clause in the journal paragraph, and `exit_code == 0` together, and the mutations that suppress either surface — or that escalate the finding to attention, the plausible "fix" on seeing a finding under an all-clear headline — are each proven to trip it.
- The runbook anchors the instrument itself prints are guarded **in kind, not by instance**: every `infra/runbooks/<file>#<anchor>` in the module's own source resolves against the anchors that exist, and the guard fails if it finds none to check. Pinning them literal-against-literal in a test only re-states the constant, so a rename made while editing those very sections — D6 edits both — would send a paged operator to a fragment that scrolls nowhere with the suite still green.
- Every guard mutation-probed through `infra/scripts/mutate-probe.sh`.
- The pass is re-run live and its exit code read, before and after.

## Out of scope

- A descriptions-as-code push mechanism (D5), and a metric/alert for due-ness (D2) — both **dropped**, not deferred: no topic tracks either, and each is reopened only if its named condition arrives (drift recurring; the pass proving insufficient).
- The bake gate's own Slack reminder (`zcrypto-rollout-image`, Phase 2, scheduled at the computed gate-open time) — the same unverifiable arming the structural finding above names, on the unbackfillable capture pair. **Dropped, not deferred**: that rollout is attended and its gate-open time is computed and stated for the user's word in the same session, so a ping that never armed cannot hide the gate the way the missing message hid the sweep. Reopened only if a rollout is ever left to cross a session boundary on that ping alone.
- The capture-image rollout that carries D4 to the hosts — not this iteration's, and not registered by it: the attended rollout [[T0037]]'s `ripe_when` already owes carries the digest, and the pass's `## Logs` count is the evidence of the gap until it lands.
- Any change to reconnect behaviour. The reconnects are normal; the bursts are their expected consequence, and 2–3 a day across two hosts is not a fault.
- The capture WARNING bursts as a phenomenon to explain further. D4 explains them, and that discharges the second data point the day-one pass's routing left owing — the owing is recorded in the memo's own Block A ledger entry, not in a `## NEW IDEAS` item (there is none: the sentence naming an idea to append to describes an append that never happened), so that ledger entry is where the discharge is written.
