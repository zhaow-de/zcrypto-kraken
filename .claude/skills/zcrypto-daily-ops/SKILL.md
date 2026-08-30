---
name: zcrypto-daily-ops
description: Run the daily proactive operations pass — read the fleet, follow the runbook for whatever fired, remediate within the two tiers, write the journal entry and post the summary. Human-triggered, once a day.
disable-model-invocation: false
---

# zcrypto-daily-ops

## What this is

The proactive half of day-2 operations. Alerts fire at you; this pass goes looking. It reads what fired, what the logs said, whether the dead-men are alive and their descriptions still resolve, whether the fleet's own series are present and fresh, what was deployed, and which reminders are due — then follows the runbook for anything that fired, fixes what it may, and leaves a journal entry so a quiet day is distinguishable from a day nobody looked.

**Every ssh/sudo step runs in the main loop, never in a dispatched subagent** — the permission gate blocks it there and the step dies where nobody sees the prompt.

## 1. Read

```bash
uv run python infra/scripts/ops-daily.py report --since 24h
```

Exit **0** all-clear · **1** attention · **2** a source could not be read. **Exit 2 is the first finding**, and the report names which source: a source that cannot be reached is a finding about that source, never a gap to pass over. `(no series)` is a FAIL, never a zero.

## 2. Follow the runbook, per alert that fired

Every rule carries `Runbook: infra/runbooks/<file>#<uid>` and the report prints it. Open the section and work it in order — *What you are seeing* → *What it means* → *What to do*. Then classify what happened:

- **expected** — a deploy in the window explains it; the report lists the window's deploys.
- **transient** — it self-resolved and the cause is identified.
- **needs a fix** — a defect in code or config.
- **needs a human** — anything the next section puts in the prepared tier.

## 3. Classify before acting, then remediate

**Before running any *What to do* step, classify the one command you are about to run:**

```bash
uv run python infra/scripts/ops-daily.py classify --host <the alert's host, from the report> "<the command>"
```

Exit **0** autonomous · **3** prepared. **`prepared` means prepare the action and stop.** If the classifier itself errors, treat that as prepared too: an unclassifiable step and an unrunnable classifier both mean nobody has judged this action.

**The classifier is default-deny over an enumerated table of command shapes, so `prepared` also means *not yet enumerated*** — a diagnostic a runbook gained after the table was written is refused exactly like a destructive one. That is the safe direction and never a reason to widen the table in the moment: prepare the step, then add the shape and its fixture through the normal fix branch.

**The host comes from the report's `Alert.host`, never from the step.** One runbook body serves all four Alloy hosts, and the same restart is routine on ops and attended on the capture pair.

**Autonomous** — everything read-only, wherever it runs; telemetry-only actions on **ops, the NAS or zaccess only** (restart Alloy, re-arm a timer); and a code fix taken the normal way — fix branch, tests, subagent review, PR, merged on CI green — **when the fix is off the protected paths**.

**Prepared, then the user's word** — any restart or converge of a capture daemon or the engine; anything touching the venue account (the arm file, the kill file, orders); deleting data; running `grafana-push.sh` after a merged rule fix, since it changes what pages; and a fix landing on the capture write path, the live trade path, canonical data, or anything a host converges. **Deploying any fix to a host is a converge — always attended.**

## 4. Read the dashboards numerically

The verdict tiles' own PromQL is what the report's fleet checks already ran. Read those; no pixels.

## 5. Evaluate the due reminders

The report's `## Reminders` section is the trigger — an **OWED** line is work, not decoration: open the section it names (`reference-data.md#refdata-sweep-due`, `ops.md#healable-threshold-rederivation-due`) and do it. The sweep's due-ness is computed from the register's last re-confirmation row plus the monthly cadence; the healable line says only whether the counter moved in the window — the count itself is still that section's step 1, from the ledger.

**Slack's scheduled message is a convenience ping, never the check.** Its scheduling cannot be listed or verified from this side, so "no message arrived" means nothing and a message that did arrive adds nothing the report did not already say. A reminder source the report could not read is exit 2, like any other.

## 6. Rewrite any dead-man description the report faults

The report's `## Dead-men` section prints one `- description:` line per **defect**, each naming its check: a description with no `Runbook: infra/runbooks/<file>#<anchor>` link, one whose link resolves to no anchor in the file it names, or one carrying repo-internal vocabulary — on a surface read from a phone with nothing open. **One check can produce several lines** — a missing link plus two internal tokens is three — so count the distinct check names before writing a number into the entry.

**This is not an alert.** Nothing fired, so there is no runbook section to open; no command is run, so there is nothing to classify; and it does not move the verdict — a day whose only finding is a description is still `all-clear`, by design. What it needs is a hand rewrite, which no repo change can make: the descriptions are hand-written in healthchecks.io.

**The fix is a hand rewrite of that check's description in healthchecks.io**, with the admin key (`healthchecks_api_key` in the vault — the read-only key the report reads with cannot write). Give it the `Runbook:` link and drop the vocabulary; send the description field and nothing else, so the check's own schedule and grace period are untouched; then read it back. The finding clears on the next pass.

**If it is not fixed, say so in the entry, with the check named.** The line reprints every day until someone rewrites it, and a finding nobody names reads as a new one each morning.

## 7. Write the journal entry

Append to `docs/reference/ops-journal/<YYYY-MM>.md` on the standing `ops-journal` branch, in the shape its README fixes: `## <YYYY-MM-DD> — <all-clear | attention | incident>`, then the paragraph `ops-daily.py report --journal-entry` prints, with the actions taken and their tier written in. Commit.

At a month change: open the finished month's PR, merge it on CI green, delete the branch, and re-cut `ops-journal` from `develop`. No review, no word — the second standing exception in `branch-workflow.md`.

## 8. Post the summary

The entry's paragraph, to `#zcrypto`. If no Slack tool is reachable, say so in the entry rather than dropping it.

## 9. Re-arm tomorrow

A scheduled message fires once. Schedule tomorrow's trigger before finishing, the way `refdata-sweep-due` does.

**With no Slack tool, the chain stops here and the entry must say so** — the next pass has nothing to trigger it. A session-local scheduler is not a substitute: it dies with the session, and this reminder has to outlive it.

**The recovery, because this is not terminal**: MCP tools bind at SESSION START, so enabling a Slack connector mid-pass does nothing for the pass in flight — a NEW session gets them. The Slack half is safely run late: post the entry's paragraph and schedule the trigger from the next session, then re-true the entry. That is what 2026-08-30 did.

## Failure modes — catch yourself

| The impulse | The reality |
|---|---|
| "The runbook says restart the daemon, so restart it" | The tier governs, not the runbook. Classify first; `prepared` stops you. |
| "No series came back, so it is zero" | `(no series)` is a FAIL. An empty query is not an observation. |
| "Nothing fired, so there is nothing to write" | The all-clear entry is the product. A missing entry reads as a day nobody looked. |
| "The classifier errored, I will judge it myself" | An unrunnable classifier is a prepared action. |
| "Exit 2, but the rest of the report looks fine" | Exit 2 means something was not seen. Report it first. |
| "I will restart Alloy on the capture host, it is only telemetry" | The capture pair's Alloy goes through `zcrypto-bump-alloy`, attended. |
