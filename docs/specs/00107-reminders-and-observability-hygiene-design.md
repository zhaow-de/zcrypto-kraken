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
- **Healable re-derivation**: whether `zcrypto_reconcile_healable_gap_seconds_total` **increased** in the window. The runbook's own step 1 says to count qualifying days from the ledger and never from Grafana Cloud, because Cloud retains ~14 days and every event predates its window — so the pass does **not** attempt the count. It answers the only question it can answer honestly: *has a new healable-gap event landed since you last looked?* If the counter moved, the recount is owed and the runbook section is named; if it did not, nothing is. **A reset in the window is its own state**: the counter is re-emitted from the ledger's totals every cycle, so a ledger correction or rebuild that lowers the total is a reset, and `increase()` then reports the whole post-reset value as movement — the hazard `zcrypto-reconcile-healable-gap-rate` guards with `resets()` over this same counter and window. The reminder mirrors that guard: on a reset it names the reset, owes the ledger recount, and never quotes the number.

This keeps the instrument **pure-HTTP**. An `ssh`-plus-`sudo` read for the ledger would have given it its first host dependency and a new class of unreadable source, to answer a question the counter already answers. The trigger is also more correct event-driven than calendar-driven: the re-derivation is gated on qualifying days accruing, not on time passing.

### D4 — the three capture lines are INFO, and the reconnect counter is the signal

`segment_writer.py:364` (`dropping late event`), `:510` and `:544` (`dropping replayed event`) become `logger.info`. They record an expected consequence of a normal reconnect, at roughly 600 lines per event; as WARNING they were ~1200 a day of noise competing with real findings, and they made the daily pass's WARNING channel meaningless.

Nothing depends on them being WARNING, verified: the capture log-dead rules select `level=~".+"` (INFO still matches, and capture emits ~578 INFO lines a day per host besides these), and the error rules select `ERROR|CRITICAL`. The daily pass filters `WARNING|ERROR|CRITICAL`, so after this change these stop reaching it — which is the point.

**The handle is not lost**, which was the objection this decision had to answer: `zcrypto_capture_reconnects_total` is a scraped counter that moved 2 and 1 in the window, and it is a better instrument than counting log lines ever was. A comment at each site says so, because the next editor's instinct on seeing "dropping" at INFO will be to raise it back.

### D5 — the descriptions are checked, not generated

For each of the ten checks the pass already fetches, two assertions: the description carries a `Runbook: infra/runbooks/<file>#<anchor>` that resolves against a real anchor, and it carries no internal token (`Phase <N>`, `T<NNNN>`, `iter-<N>`, `spec <NNNNN>` in the bare or the backticked spelling, `WP<N>`). Violations are findings in the report, named per check.

The literal `Runbook: ` prefix is part of the first assertion, not decoration: a description that merely mentions a runbook path in passing has not been given the link an operator follows from a phone, and accepting one would report as checked a description that carries no link at all. The bare decision number (`D5`) that `operator-facing-text.md` also bans is deliberately **not** in the token set: this check detects without repairing, so a false positive costs a finding line in every daily report until a human rewrites a description that was never wrong.

Rejected: descriptions-as-code with a renderer and a push script, mirroring `alerts.yaml` + `grafana-push.sh`. The hole found was **undetected drift**, and a source file does not close that better — the tokens would have been written into the file too. It would also make a third copy of content the dead-man map in `observability.md` already holds. Detection is what was missing; generation is the upgrade if drift proves recurring rather than one-off.

The cost, accepted: this detects but cannot repair. With ten checks and a daily report naming the offender, a human rewrite is proportionate.

### D6 — the belief that made the gap invisible is corrected where it lives

[[T0103]]'s archive says the reminder "cannot be deleted through the API, so it will land in `#zcrypto` on the day". Observation disproves it. The archived file is re-trued in place, and the memo's "armed OUTSIDE the repo" note gains what this iteration measured: that the arming cannot be verified from this side at all, which is why D1 moves the load off it.

**And on every operating surface that still names Slack as the trigger, in this same change** — a ruling recorded only in a spec is invisible at execution time. Three of them, each going false the moment D1 lands, each to name the report's `## Reminders` section instead: `infra/runbooks/reference-data.md`'s opening sentence and its `#refdata-sweep-due` section, which tell the operator they are here because a scheduled Slack message came due; `infra/runbooks/ops.md#healable-threshold-rederivation-due`, which calls itself "a calendar trigger with no metric behind it" when the counter it now reads is exactly that metric; and `.claude/skills/zcrypto-daily-ops/SKILL.md`'s step 5, which evaluates the Slack inbox rather than the report the pass just produced.

## Verification

- The level change is proven by a test that fails against `logger.warning` — the guard sees the defect it names, on all three sites.
- `read_reminders()` is proven against the **real** register (its parse must find `2026-08-04` in the committed file, not a fixture shaped to the parser) and against a fixture where the counter moved, one where it did not, and one where it reset, so the trigger discriminates rather than always firing — and a correction is never read as an event.
- The description assertions are proven by a fixture carrying an internal token and one carrying a dead runbook link, **plus the true positive that today's ten real descriptions all pass** — a check that refuses everything is not a check.
- The runbook anchors the instrument itself prints are guarded **in kind, not by instance**: every `infra/runbooks/<file>#<anchor>` in the module's own source resolves against the anchors that exist, and the guard fails if it finds none to check. Pinning them literal-against-literal in a test only re-states the constant, so a rename made while editing those very sections — D6 edits both — would send a paged operator to a fragment that scrolls nowhere with the suite still green.
- Every guard mutation-probed through `infra/scripts/mutate-probe.sh`.
- The pass is re-run live and its exit code read, before and after.

## Out of scope

- A descriptions-as-code push mechanism (D5), and a metric/alert for due-ness (D2) — both **dropped**, not deferred: no topic tracks either, and each is reopened only if its named condition arrives (drift recurring; the pass proving insufficient).
- The capture-image rollout that carries D4 to the hosts — not this iteration's, and not registered by it: the attended rollout [[T0037]]'s `ripe_when` already owes carries the digest, and the pass's `## Logs` count is the evidence of the gap until it lands.
- Any change to reconnect behaviour. The reconnects are normal; the bursts are their expected consequence, and 2–3 a day across two hosts is not a fault.
- The capture WARNING bursts as a phenomenon to explain further. D4 explains them; the memo's `noisy warning` idea is discharged by this spec rather than left owing a second data point.
