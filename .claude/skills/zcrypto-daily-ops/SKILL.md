---
name: zcrypto-daily-ops
description: Run the daily proactive operations pass — read the fleet, follow the runbook for whatever fired, remediate within the two tiers, write the journal entry and post the summary. Human-triggered, once a day.
disable-model-invocation: false
---

# zcrypto-daily-ops

**Every ssh/sudo step runs in the main loop, never in a dispatched subagent** — the permission gate blocks it there and the step dies where nobody sees the prompt.

## 1. Read

```bash
uv run python infra/scripts/ops-daily.py report --since 24h
```

Run it from a checkout at `develop`'s tip, never from the `ops-journal` worktree — its scripts are `develop`'s only at the month-change re-cut; the journal entry is written in the `ops-journal` worktree, the report is not. Exit **0** all-clear · **1** attention · **2** a source could not be read. **Exit 2 is the first finding**, and the report names which source: a source that cannot be reached is a finding about that source, never a gap to pass over. `(no series)` is a FAIL, never a zero.

## 2. Follow the runbook, per alert that fired

Every rule carries `Runbook: infra/runbooks/<file>#<uid>` and the report prints it. Open the section and work it in order — *What you are seeing* → *What it means* → *What to do*. Then classify what happened:

- **expected** — a deploy in the window explains it; the report lists the window's deploys.
- **transient** — it self-resolved and the cause is identified.
- **needs a fix** — a defect in code or config.
- **needs a human** — anything the next section puts in the prepared tier.

## 3. Classify before acting, then remediate

**Before running any *What to do* step, classify the one command you are about to run:**

```bash
uv run python infra/scripts/ops-daily.py classify --host <one host the alert names, from the report> "<the command>"
```

**`--host` is also where a read is resolved**: before answering `autonomous` for a `cat` or a `grep`, the classifier asks that host what the command's file operands really name, so a link under a read-safe root pointing outside it — and a host it could not reach — read `prepared`.

Exit **0** autonomous · **3** prepared. **`prepared` means prepare the action and stop.** If the classifier itself errors, treat that as prepared too: an unclassifiable step and an unrunnable classifier both mean nobody has judged this action.

**The classifier is default-deny over an enumerated table of command shapes, so `prepared` also means *not yet enumerated*** — a diagnostic a runbook gained after the table was written is refused exactly like a destructive one. That is the safe direction and never a reason to widen the table in the moment: prepare the step, then add the shape and its fixture through the normal fix branch.

**The host comes from the report's `Alert.hosts`, never from the step.** One runbook body serves all four Alloy hosts, and the same restart is routine on ops and attended on the capture pair. **A rule firing on several hosts is classified once PER HOST** — the report names every host with a firing instance, the tier can differ between them, and the silence the capture runbook prescribes is created and deleted per host too.

**Done is an outcome, never a merge.** A fix whose effect needs a converge is not done when it merges: the entry names it as owed to an attended converge.

**Autonomous** — everything read-only, wherever it runs; telemetry-only actions on **ops, the NAS or zaccess only** (restart Alloy, re-arm a timer); and a code fix taken the normal way — fix branch, tests, subagent review, PR, merged on CI green — **when the fix is off the protected paths**.

**Prepared, then the user's word** — any restart or converge of a capture daemon or the engine; anything touching the venue account (the arm file, the kill file, orders); deleting data; running `grafana-push.sh` after a merged rule fix, since it changes what pages; and a fix landing on the capture write path, the live trade path, canonical data, or anything a host converges. **Deploying any fix to a host is a converge — always attended.**

## 4. Read the dashboards numerically

The verdict tiles' own PromQL is among what the report's fleet checks already ran. Read those; no pixels.

**The `soak verdict` row is the soak instrument's daily reading, and none of its states is a host action.** It is `soak-check`'s panel over the journal, not the gate's soak verdict the NAS gate metrics carry. The report runs `zcrypto engine soak-check` over a store derived from the newest journaled 240 snapshots and reduces the payload to this one row; nothing is classified, because there is no command to run. `soak verdict could not be read` (exit 2) is a finding about a SOURCE only when its value names one — the journal mount `/mnt/zhao-crypto/engine-journal`, a record or store read under it, or the workstation's canonical dataset, `data/ohlc-full` in the main checkout — and then the check is that mount and that directory, never a fleet host. Any other value names this reader or the instrument, and is handed to `zcrypto-marco` the way a `void:` row is. `FAIL … void: <reasons>` is a finding about the INSTRUMENT — a self-test that ran and failed, a degenerate window, a null with no power — and so is a value saying `only N metric(s) decided`, a panel too undecided to reach the threshold: the book was not judged that day, the verdicts a void payload also carries are never read, and the entry says so and hands it to `zcrypto-marco`. A value is read in that order — `void:`, then `NOT CURRENT`, then the decided count, and only then the outside count. `FAIL` with three or more metrics outside the band, and none of those before it, is a finding about the BOOK: hand it to `zcrypto-marco`, the same day to the owner once the engine is armed. A `FAIL` whose value says `NOT CURRENT` is a finding about the instrument's WINDOW — its last scored cycle is stamped more than twelve hours before the pass, or something other than the journal ended it, the store running out first or the run's clock — so the panel beside it judged an older book. One failed boundary cycle is the usual cause: `soak-check` scores the longest contiguous run, so it keeps scoring the run before the gap until the newer one is longer, and the row says `NOT CURRENT` on every pass until then. A stamp falling a further day behind each pass while the mount holds no `failed-cycle-*.json` is the pull to the mount stalled or the engine journaling nothing: the report's archive-pull alerts and `engine cycle age` say which. Hand it to `zcrypto-marco` on the first such pass and name it as standing on the later ones. A `PASS` row's `outside:` list is narration, not a finding: one metric outside a 90% band is the count chance expects, and a `skipped` self-test flag is narrated the same way.

## 5. Evaluate the due reminders

The report's `## Reminders` section is the trigger — an **OWED** line is work, not decoration: open the section it names (`reference-data.md#refdata-sweep-due`, `ops.md#healable-threshold-rederivation-due`) and do it. The healable line says only whether the counter moved in the window — the count itself is still that section's step 1, from the ledger.

**Slack's scheduled message is a convenience ping, never the check.** Its scheduling cannot be listed or verified from this side, so "no message arrived" means nothing and a message that did arrive adds nothing the report did not already say. A reminder source the report could not read is exit 2, like any other.

**The nightly data-gated run is read from its file, not from the report.** `infra/scripts/data-gated-run.py`, fired by the `zcrypto-data-gated-tests.timer` user unit (`infra/systemd/`), runs the whole suite from the main checkout — the one with `data/`, where every test that skips in CI for want of a dataset runs for real — and writes `.local/data-gated-runs/latest.json` **in that checkout**: `.local/` is per-checkout, so read the main checkout's copy by absolute path, never a relative one from wherever the pass is running, or an unwritten path reads exactly like a night that did not run. It is `FAIL data-gated tests: <why>` — a row in the entry's paragraph in the shape of the report's fleet-check rows, and the verdict is `attention` — when the file is absent, when `finished` is more than 26 h before the pass (nightly, with two hours of slack), or when `ok` is false: a non-zero `exit_code`, `counts.failed` or `counts.errors` above zero, `data_gated_skipped` non-empty — tests that skipped because their dataset was not there, the one night this run exists to catch, and `data_present: false` is the same finding before pytest started — or `error` set: a run that could not read its own summary, a timeout or a usage error, a failure of the runner rather than of a test. The row names the ids the `failed` and `errors` lists carry and the sites `data_gated_skipped` carries. A failing test goes the normal fix-branch way (autonomous: nothing here touches a host); an absent or stale file means the timer did not fire — `systemctl --user list-timers zcrypto-data-gated-tests.timer` and `journalctl --user -u zcrypto-data-gated-tests.service -n 50` on the workstation say why, read from the main loop like any other host step. `counts.skipped` is recorded so a rise can be read, and beyond the data-gated ones is not a finding on its own: the suite's own gates — the live-venue opt-in, root's permission bypass — decide what else skips.

## 5b. Evaluate the live topics' triggers

Take the Open and Partially-done bullets of `docs/open-topics/README.md` — the rendered index carries each live topic's trigger — and run the one check each trigger names, for the four shapes this pass can decide from repo state and its own reading:

- **a date** — compare with today, unless the trigger's own text says the date is a handle for a check this
  pass cannot run: `T0150` names the oldest `cycle-<HH>.json` on the engine host as its test, so it is named
  unevaluated.
- **another topic's resolution** — run the check the trigger carries, against the topic's own definitions: a change-index cell is a parse of a PR body, not the spec listing — open the topic and the spec listing before reading a cell or a word match as fired.
- **an alert** — the report already says whether it fired; a trigger naming one is answered by the section you have just read.
- **a file being touched** — `git -C <main checkout> log --name-only --since=<the last journal entry's date> --format= develop`
  against the paths the trigger names in backticks. Report it only when one of them is in that list: a
  standing line saying a topic waits is wallpaper within a week, and the daily pass is the backstop here,
  not the primary reader — `open-pr`'s rider clause is what keeps these from being written at all.

A milestone, an evaluation statement, or an activity no repo path records is not this pass's to decide: name it unevaluated rather than guessing. A fired trigger goes into the journal entry's `follow-ups` line by serial (`follow-ups none` stays the all-clear form) and is handed to `zcrypto-marco`; the topic itself is edited by whoever takes the work, through `topic-ops`.

## 6. Rewrite any dead-man description the report faults

The report's `## Dead-men` section prints one `- description:` line per **defect**, each naming its check: a description with no `Runbook: infra/runbooks/<file>#<anchor>` link, one whose link resolves to no anchor in the file it names, or one carrying repo-internal vocabulary — on a surface read from a phone with nothing open. **One check can produce several lines** — a missing link plus two internal tokens is three — and the journal paragraph's `description finding(s)` clause counts those lines, not the checks. Let that number stand as printed; the entry's own prose is where the distinct checks are named.

**This is not an alert.** Nothing fired, so there is no runbook section to open; no command is run, so there is nothing to classify; and it does not move the verdict — a day whose only finding is a description is still `all-clear`, by design. What it needs is a hand rewrite, which no repo change can make: the descriptions are hand-written in healthchecks.io.

**The fix is a hand rewrite of that check's description in healthchecks.io**, with the admin key (`healthchecks_api_key` in `infra/ansible/group_vars/capture_host/vault.yml`, not the default `all/` vault — the read-only key the report reads with cannot write). Give it the `Runbook:` link and drop the vocabulary; send the description field and nothing else, so the check's own schedule and grace period are untouched; then read it back. The finding clears on the next pass.

**If it is not fixed, say so in the entry, with the check named.** The line reprints every day until someone rewrites it, and a finding nobody names reads as a new one each morning.

## 7. Write the journal entry

Append to `docs/reference/ops-journal/<YYYY-MM>.md` on the standing `ops-journal` branch, in the shape its README fixes: `## <YYYY-MM-DD> — <all-clear | attention | incident>`, then the paragraph `ops-daily.py report --journal-entry` prints, with the actions taken and their tier written in. An action left prepared, or a finding the pass could not clear, is recorded in the entry AND routed where work lives — a decision to a `T<NNNN>` through `topic-ops`, a doing handed to `zcrypto-marco` for the memo queue — and the entry names where it went; the journal is not a backlog. Commit.

At a month change: open the finished month's PR, merge it on CI green, delete the branch, and re-cut `ops-journal` from `develop`. No review and no word while the PR carries journal files alone — a month of all-clear entries has nothing a second reader could check, and a gate there is a place the routine stalls; `merge-pr`'s gate holds the exemption to exactly that, so a PR that also carries a script or a role fix takes the read like any other.

## 8. Post the summary

The entry's paragraph, to `#zcrypto`. If no Slack tool is reachable, say so in the entry rather than dropping it.

## 9. Re-arm tomorrow

A scheduled message fires once. Schedule tomorrow's trigger before finishing, the way `refdata-sweep-due` does. **The Slack message is the convenience; the named hand-off is the trigger** — the pass is re-armed only when something that outlives this session carries tomorrow's.

**With no Slack tool, the entry says so AND the re-trigger goes to a carrier that outlives the session**: hand it to `zcrypto-marco` for the memo queue, the way 5b hands a fired trigger, or schedule a routine through `/schedule`; the entry names which. A session-local scheduler is not a substitute: it dies with the session, and this reminder has to outlive it.

**The recovery, because this is not terminal**: MCP tools bind at session start, and a plugin reload (`/reload-plugins`) re-binds them into the running session — try that before deferring the Slack half. Failing that, the Slack half is safely run late: post the entry's paragraph and schedule the trigger from the next session, then re-true the entry.

## Failure modes — catch yourself

| The impulse | The reality |
|---|---|
| "Nothing fired, so there is nothing to write" | The all-clear entry is the product. A missing entry reads as a day nobody looked. |
| "I will restart Alloy on the capture host, it is only telemetry" | The capture pair's Alloy goes through `zcrypto-bump-alloy`, attended. |
| "No nightly file, so there is nothing to report" | An absent or stale `latest.json` is the FAIL row: the timer did not fire, and the data-gated family ran nowhere that night. |
