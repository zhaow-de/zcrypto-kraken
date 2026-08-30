# 00105 — the go-live drill program: implementation plan

Spec: `docs/specs/00105-go-live-drill-program-design.md`. Branch `feat/t0049-drill-program`, cut from `develop` after PR #352 ([[T0157]] / spec `00104`) merged — `infra/runbooks/observability.md`, `engine.md` and the PROCEDURE kind all exist there now, so no task here creates them.

## Goal

Every go-live drill scenario has an induction instrument, a derived bound and a recording shape before anyone needs one at 03:00; the telemetry tier is **executed**, not just written; and the two gaps no rehearsal can close — the dark-with-exposure alert and the Grafana-dark procedure — are built.

## Global constraints

- **A drill that induces a fault runs in the main loop, never in a subagent or workflow** — the permission gate blocks ssh/sudo there and the step dies where nobody sees the prompt (`agent-ops.md`).
- **Never induce a fault on live capture outside an attended window, and never inside a published Kraken maintenance window** — read `https://status.kraken.com/api/v2/scheduled-maintenances.json` at planning time and again immediately before each induction (`fleet-deploys.md`). The **primary's capture daemon and its Alloy are not touched by any task here.**
- **The owner's 2026-08-29 authorization ([[T0158]]) IS this iteration's attended window, and it covers exactly one class**: every Alloy action, and any container / unit / timer start–stop the loop reverts itself. A **converge** is outside it and stays a human step, as does anything that reboots or powers off a host. An induction the class does not cover **stops the chain where it stands** — revert what is already induced, record why, and hand back; never proceed past it, and never widen a named instrument into a heavier one.
- **Every induction is reverted and verified BY VALUE before the next one starts.** A drill that leaves the fleet degraded is an incident, not a drill.
- **Bounds are derived, never guessed**: a Grafana rule's `for` plus its group's evaluation interval; a healthchecks check's timeout plus grace, quoted from the check itself. The management API takes a **check name**; `capture-redundant`, `capture`, `ops`, `nas`, `engine` are node **tags** and resolve to nothing there — `observability.md`'s dead-man map is the tag→daemon table, and a lookup that returns nothing is never repaired by reaching for the adjacent check.
- **A drill result lives in `docs/reference/drill-log.md` and in its runbook section.** A result that lives only in a report or a PR body is not recorded (`open-topics.md`).
- Every commit reviewed by a subagent other than its author; **Fable floor for anything touching the capture path or the live trade path** (`spec-plan-locations.md`).

## Tasks

### Task 1 — the drill log and its guard, red first

Write `tests/test_drill_log.py` asserting only what D2 specifies: every `##` heading matches `<YYYY-MM-DD> — <scenario id> — <pass | fail | partial>`, and dates within the file do not decrease. Create `docs/reference/drill-log.md` with its header and no entries.

**Verify**: the test is seen RED against a deliberately malformed heading before the file is made valid — a guard is unproven until the defect it names trips it. Then green on the empty log.

### Task 2 — `infra/runbooks/drills-telemetry.md`

Sections C, C′, I, J′, K, O, P+R, Q in the seven-part PROCEDURE shape (D1), plus one section stating when the **proven** tier (F, H, J, L, M, N, T) is re-verified — only when the code path it proved changes, citing the incident or drill that proved it — and recording that **N is due now** ([[T0048]] changed the Alloy path after the 2026-07-15/16 incident that proved it). That section also carries the two dropped items with their reasons: the reboot-window overlap check (both capture hosts are attended-reboot since [[T0027]]) and drills for [[T0039]]'s phantom-splice guard and [[T0043]]'s lost-trades detector (code guards with tests, not fleet failure scenarios).

**Verify**: every bound in the file is derived from a quoted `for` + interval or timeout + grace, with the source named; no section exceeds the README's shape; `uv run pytest tests/test_infra_alert_rules.py tests/test_code_prose_citations.py --deselect tests/test_infra_alert_rules.py::test_the_index_routes_to_every_section_and_only_to_real_ones`. **The deselect is load-bearing and temporary**: that test fails on any `<a name=…>` no index row routes to, and the rows land in Task 4 — deleting the anchors to make it green is the wrong repair, since Task 4's rows and every cross-file citation resolve through them.

### Task 3 — `infra/runbooks/drills-order-path.md`

Sections A1, A2, B, D, E (with E′), F2, G, in the same seven parts, fitted around `engine-procedures.md#engine-probe-window`. Each names the four enhancements it waits on where relevant, and G carries the [[T0018]] by-value reading `zcrypto_exec_external_events_total{disposition="matched"}`, discharged into `docs/reference/adapter-verification/<version>.md`: **1** expected, **2** under a fill race — either proves Kraken echoes `cl_ord_id` across a restart. **0 has two causes and the section must carry both**, per spec D4: Kraken did not echo `cl_ord_id`, **or** the ack never reached the external stream — nautilus's routing of a strategy-issued cancel on an EXTERNAL-tagged order, unmeasured in the repo and an engine-side defect on the live trade path. The section names the two artefacts that tell them apart — the `canceling adopted resting order` log line (`executor.py`) and the row's `events` — and forbids recording either cause without them. A2's `matched`-reads-0 caveat is stated where it belongs.

**Verify**: a cold reviewer dry-reads every command against the probe procedure — every command resolves, every expected ledger value names its field (spec Verification); `uv run pytest tests/test_infra_alert_rules.py tests/test_code_prose_citations.py --deselect tests/test_infra_alert_rules.py::test_the_index_routes_to_every_section_and_only_to_real_ones` (same temporary deselect as Task 2; the rows land in Task 4).

### Task 4 — index every anchor this branch creates

**Runs after Task 6**, not in numeric order: the index must route to anchors that already exist, and Tasks 5 and 6 create two of them. Add the two drill files to `infra/runbooks/README.md` under their own `###` headings with a row per section, **and** rows for `engine.md#zcrypto-engine-dark-with-exposure` (Task 5) and `observability.md#grafana-cloud-dark` (Task 6) under those files' existing headings. Enumerate the target list from the files themselves — every `<a name=…>` the branch added — rather than from this sentence.

**Verify**: `uv run pytest tests/test_infra_alert_rules.py` in full — no deselect from here on. It asserts both directions: a row pointing at an anchor its named file does not define, and an anchor no row routes to. The second is what Tasks 2, 3, 5 and 6 deferred to here, so a green run is this task's whole point.

### Task 5 — `zcrypto-engine-dark-with-exposure`

Add the critical rule to `infra/grafana/alerts.yaml`: `zcrypto_exec_position` non-zero at last sight AND the engine's scrape absent, pinned against `up{job="engine_app",host="zcrypto"}` — the job is scraped on both capture hosts and reads 0 on `zcrypto-red` by design, so the host label is load-bearing. Runbook section in `engine.md`, response is B. **The section's bound quotes the rule's own `for` and its group's evaluation interval** (spec Verification) — the page is read on a phone with real exposure open, and without the bound the responder cannot tell five minutes dark from an hour before deciding to flatten.

Two durable claims go false when this rule lands, and re-tensing them is part of the task, not a follow-up: the `alerts.yaml` comment above `zcrypto-engine-cycle-stale` that says "Deliberately no such rule exists today … Revisit only if arming stops being episodic" becomes the record of why the **unscoped** rule is still refused and what this one pins instead; and `NOT_A_FAULT_SIGNAL`'s `zcrypto_exec_position` entry in `tests/test_infra_alert_rules.py`, whose comment reasons the execution gauges are attended-window instruments nothing pages on, must now say that the bare value stays no fault while non-zero **with the engine's scrape gone** pages. Neither breaks a test, which is exactly why nothing else would catch them.

**Verify**: `uv run pytest tests/test_infra_alert_rules.py tests/test_dashboards_cover_metrics.py tests/test_internal_terms_not_operator_visible.py tests/test_code_prose_citations.py --deselect tests/test_infra_alert_rules.py::test_the_index_routes_to_every_section_and_only_to_real_ones` (same temporary deselect as Task 2 — this task's `engine.md` anchor is indexed in Task 4) — the rule must carry a resolving runbook link, its summary must hold no internal token, and `test_dashboards_cover_metrics.py` refuses half a `__dashboardUid__`/`__panelId__` pointer and an unquoted `__panelId__`, which aborts the whole push. The push and the first-sample-by-value read are Task 11.

### Task 6 — `observability.md#grafana-cloud-dark`

The PROCEDURE section: for the duration, the dead-man domain plus the daily pass's direct healthchecks read, `docker logs` on hosts, `exec-status` on the engine host. On return: the rules blind to a condition already present at first sample, re-verified by value. Its permanent-loss-per-plane statement (drill C) and its page bound (drill C′) are measured in Task 10, so this task lands the section with each carrying a literal, greppable marker — **`PENDING-DRILL-C`** and **`PENDING-DRILL-C-PRIME`** — on the line the value belongs on. Task 10 names this file and both markers, so the fill is an instruction there and not an inference; a marker surviving to the PR means the one procedure written for a Grafana-dark outage is missing the two numbers it exists to supply.

**Verify**: `uv run pytest tests/test_infra_alert_rules.py tests/test_code_prose_citations.py --deselect tests/test_infra_alert_rules.py::test_the_index_routes_to_every_section_and_only_to_real_ones` (same temporary deselect as Task 2 — this task's anchor is indexed in Task 4); `grep -c 'PENDING-DRILL' infra/runbooks/observability.md` returns 2, so Task 10 has an exact target count to drive to 0.

### Task 7 — the master-plan artifact line

Add `docs/reference/drill-log.md` by name to the master plan's Stage-6b **Artifacts:** line in `docs/research/00.master-plan.md`, which today names "ops drill log" and points at nothing.

**No repo-`README.md` row.** The root README has three top-level sections — Requirements, Usage, Configuration — and `readme-usage.md` scopes it to CLI subcommands and their options; it describes no runbook tree, and minting a top-level section for one would also regenerate the mdformat TOC. Discoverability is already owned: `infra/runbooks/README.md` is the runbook index (Task 4) and the master-plan artifact line is the drill log's.

**Verify**: `grep -n 'drill-log.md' docs/research/00.master-plan.md` names the path on the Stage-6b Artifacts line; `uv run pre-commit run -a` clean — the master plan is mdformat-managed, so the edit must survive the reformat rather than be reflowed away.

### Task 8 — mutation probe on the drill-log guard

**Runs after Task 10**, not in numeric order, and on a **committed clean tree**: `mutate-probe.sh` mutates `docs/reference/drill-log.md`, and while that file holds only the header Task 1 wrote there is no `##` heading to malform — every sed would no-op and the script would exit 6 rather than prove anything. After Task 10 the log holds Task 9's entry and one per executed drill, so both of D2's assertions have something to bite on. The script also refuses a dirty worktree (its restore is `git checkout --`), so commit first.

There is no `-k` filter to prove and `--collect-only` is not one of its arguments — it parses `--sandbox|--file|--control|--mutation|--` and exits 2 on anything else. The guard is one file, so the probe command selects it whole. Two runs, each with the same control, which must fail before either verdict counts:

```
infra/scripts/mutate-probe.sh --file docs/reference/drill-log.md \
  --control 's/^## .*/## not a heading/' \
  --mutation '0,/^## /s/^## \([0-9]\{4\}\)-/## \1/' \
  -- uv run pytest tests/test_drill_log.py
infra/scripts/mutate-probe.sh --file docs/reference/drill-log.md \
  --control 's/^## .*/## not a heading/' \
  --mutation '0,/^## /s/^## [0-9]\{4\}/## 9999/' \
  -- uv run pytest tests/test_drill_log.py
```

The first drops the hyphen after the year in the first heading — the malformed heading spec Verification names. The second is the one D2's other assertion owns and Task 1's red phase never reached: `9999-…` still **matches** the shape, so only the dates-do-not-decrease assertion can move, and it moves because the next entry's date is now lower.

**Verify**: KILLED both times with the control proven and the tree restored byte-identically. Then re-run each mutation by hand and **read which assertion failed** — a red exit can be the guard tripping on the wrong thing: run 1 must fail on the heading shape and run 2 on the date ordering. `git status --porcelain` empty afterwards.

### Task 9 — execute J′ (workstation-only, no host access)

Read `engine_healthcheck_url` through `grafana_auth.vault_var` from `group_vars/engine_host/vault.yml`; `curl <url>/fail` **from the workstation** — never from the engine host, whose only copies sit beside the trade key; engine disarmed. Read the native page and `zcrypto-hcio-watchdog` by value; write the drill-log entry; then a success ping to clear it.

**Verify**: the entry records the **two machine timestamps** D2 asks for — `zcrypto-hcio-watchdog`'s rule `activeAt` and the Slack message — and marks the third, the device reading, as [[T0158]]'s human step; a phone reading is not takeable from an autonomous run, and an entry that silently omits it reads as a complete measurement. The check is green again, read by value.

### Task 10 — execute the telemetry tier on ops, the NAS and the secondary

In the main loop, one at a time, each **reverted and verified by value before the next starts**. Every instrument is written out below because the letters resolve to nothing an implementer can see: the archived `T0049` matrix glosses **R** as "secondary host loss" and **N** as "NAS archive-pull stall", and neither gloss is the induction — R is one `systemctl stop` of one unit, never a reboot or a power-off, and N is one `docker stop`. **Never widen an instrument to match a gloss**: anything heavier than what is written here falls outside the owner's authorization in Global constraints and stops the chain.

1. **K** — `docker stop grafana-alloy` on ops; `zcrypto-alloy-dark-ops` must fire within its `for` + interval. Restart it and verify the restart recipe by value. **Q's metrics path is read here**, before the restore: D3 rides Q's metrics path on K, and every induction in this chain is reverted before the next starts — so a Q reading deferred to the end of the chain has nothing firing to read and costs a second, unplanned Alloy stop.
2. **O** — stop the ops **panel-materialize** timer past its check's timeout + grace, quoted from that check by NAME. D3's O is specifically about the timer that has **no** staleness rule — whether its dead-man catches it alone, a missing rule if not — so any other ops timer measures the wrong thing. `observability.md`'s dead-man map routes the `ops`/`panel` row to the section owning that unit; the map records **tags**, so resolve the check's display name on the hc.io dashboard before quoting anything from it. Its dead-man must page; then start the timer and confirm the next ping lands.
3. **I** — a throwaway capture container on ops from the pinned digest with a tmpfs data dir a few hundred MiB wide, and a throwaway healthchecks check as its dead-man, **created with `channels` naming the Slack integration explicitly** — an API-created check inherits NO integrations ([[T0085]]), and an unchannelled one breaches in silence, which would be recorded as a FAIL of the dead-man domain that never happened. The withheld ping must page the throwaway check. **Q's healthchecks-native path is read here.** Delete the throwaway check and container afterwards.
4. **Q-logs** — the third receiver, and the one path with an induction of its own: one failing invocation inside the liquidations container on ops, so `zcrypto-ops-error-logs` fires on the `logs` receiver. It runs **here, before C-ops**, because that line reaches Loki through the ops Alloy — once C-ops has disconnected it the reading is impossible. Record `activeAt` and the Slack message timestamp. Q's three paths are complete at this point; the device timestamp on each is [[T0158]]'s human step and is marked as owed, never omitted.
5. **C-ops** — `docker network disconnect` the ops Alloy container for 2 h. `zcrypto-alloy-dark-ops` fires, and `zcrypto-hcio-watchdog` with it as an expected side effect (the ops Alloy is the hc.io scrape). **Not** the Grafana watchdog: it `curl`s Grafana from the host rather than through Alloy and keeps pinging success. Reconnect, then read what backfilled per plane — the remote-write WAL against `loki.write`'s absence of one — and which rules misfired on return.
6. **C-secondary** — the same disconnect on `zcrypto-red`'s Alloy container for 2 h; `zcrypto-alloy-dark-capture-secondary` must fire. Only the telemetry shipper is touched; the secondary's capture daemon keeps running.
7. **C′-staleness** — on ops, stop `zcrypto-grafana-watchdog.timer` past its check's timeout + grace (600 s + 600 s per D3, re-quoted from the check itself immediately before). The `zcrypto-grafana-watchdog` check must page natively and `zcrypto-hcio-watchdog` fire with it. Start the timer. C′'s **`/fail` route is a converge and is not in this task.**
8. **Fill `infra/runbooks/observability.md#grafana-cloud-dark`** here, while C and C′ are freshly measured — Task 6 landed that section with two markers on the lines the values belong on. Replace `PENDING-DRILL-C` with the permanent-loss-per-plane statement for a 12 h outage and `PENDING-DRILL-C-PRIME` with the page bound. A marker that survives leaves the only procedure written for a Grafana-dark outage missing the two numbers it exists to supply.
9. **N** — on the NAS, `sudo /usr/local/bin/docker stop zcrypto-archive-pull`, held past `zcrypto-nas-archive-pull-stalled`'s no-clean-line window plus its `for` and interval; that rule must fire on the `logs` receiver. Stopping the **container** is the induction: the dead-man matches a clean `zcrypto archive pull` line from ANY channel inside it, so silencing one channel leaves it green. Restore with `docker compose up -d archive-pull` from `/volume1/docker/zcrypto-archive` and read one `pull complete … failed=0` line back before moving on. **N has no section of its own** — D3 records its re-run in the proven-tier section Task 2 wrote, so that section is the amendment this step lands. `docker` on that host is `/usr/local/bin/docker`, needs `sudo`, and is not on a non-interactive ssh `PATH` — called bare it prints nothing and reads as "no containers" rather than "command not found".
10. **R** — `systemctl stop zcrypto-capture` on `zcrypto-red`, and nothing heavier. **P is not in this task** (its restore is a converge).
    - **Preconditions, every one of them immediately before the stop.** `up{job="capture_app",host="zcrypto"}==1` read **by value** and both capture-silence rules Normal — the primary is provably whole before the secondary goes dark, and a "read by value" that names no series can be satisfied by reading anything at all. **No converge, reboot or published Kraken maintenance touching the primary inside the window**: a converge restarts live capture (`fleet-deploys.md`), and one overlap with both hosts silent is permanent, unbackfillable L2 loss — the reconciler heals a silent primary from a live secondary and never the reverse, so it books to `residual_gap_seconds_total` and nothing recovers it. Hard cap = **`zcrypto-capture-red`**'s timeout + grace + one evaluation, quoted from that check via the management API.
    - **Must fire**: hc.io `zcrypto-capture-red` by staleness, inside the cap. `zcrypto-alloy-dark-capture-secondary` must stay **quiet** — Alloy is up, and a firing there says the induction hit the wrong thing.
    - **After the restore, the primary is proved whole a second time, and that read closes the entry**: no `minted`/`would_mint` record for the window's hours, row counts and hashes intact, `residual_gap_seconds_total` unchanged before and after. The reconciler books hour H only at the first `:12`/`:42` tick after H+2, so until that tick this read is **pending, not clean** — R's entry stays open until then and is never recorded `pass` on the pre-stop read alone.

**Verify**: each drill gets its `drill-log.md` entry and its section amendment **before the next starts**, committed as it lands; the Kraken maintenance feed is read immediately before each induction; every revert verified by value; `grep -c 'PENDING-DRILL' infra/runbooks/observability.md` returns 0 after step 8; R's entry carries the post-restore reading, not just the pre-stop one. **The chain is longer than one sitting** — C's two halves are 2 h each, and O, C′, N and R each hold for their own derived window — so plan it across sittings: the only safe stopping point is the boundary **between** drills, with nothing induced and the last revert verified.

### Task 11 — Grafana push, from MERGED `develop` only

After the PR merges — Task 12 opens and merges it, so this task is the **last** one to run despite its number: push `zcrypto-engine-dark-with-exposure`, orphan report clean, first sample read **by value** before anything is pruned (`fleet-deploys.md`).

**Verify**: the first sample is read by VALUE, not by the rule's presence in the orphan report; the rule's inputs already exist, so a no-data page here is the push landing before the read, not a missing metric. Nothing is pruned in this task.

### Task 12 — closeout

Append the `iter-<N>` entry to `docs/iterations-history-phase6.md`; run `infra/scripts/review-trailer-audit.sh develop` and resolve what it reports; **bring [[T0158]] current in this same PR** — `ripe_when` re-cut to the order-path tier at rung 1, the executed drills' results in `## Done so far`, `## Suggested next steps` trimmed to P, C′'s `/fail` route and Q's phone reading with their `(autonomous)`/`(human)` tags; open the PR into `develop` and merge on CI green.

**Verify**: `uv run pre-commit run -a` clean, and green on the tests this diff can reach — the full suite is CI's on the PR, and no data-gated family is in this diff's reach. `review-trailer-audit.sh` reports no code-kind commit without its trailer; the [[T0158]] edits land in **this** PR, not a later one — a `status` correct over a stale body is still drift (`open-topics.md`).

## What this plan does not do

The order-path tier is written and parked, never run — rung 1 has not opened and the engine has never been armed. The four enhancements it needs (`00106` flatten, `rest-hold`, cancel-on-stop, re-cancel-on-reconnect) are each their own spec and PR at the Fable floor, and none is built here. **P** (its restore is a secondary converge) and **C′'s `/fail` route** (a converge) stay attended and are not in Task 10; both are registered as [[T0158]]'s `(human)` next steps, alongside Q's device timestamps, and Task 12 brings that topic current.
