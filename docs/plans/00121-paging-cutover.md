# The observability node, phase 3: the node pages the main channel, the direct-shipped streams move to it one sitting each, and Grafana Cloud's receivers move last — implementation plan

> Every value a rollout reading decides is a marked slot, `ROLLOUT:` inside double square brackets, listed at the end.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Paging moves from Grafana Cloud to the observability node `zcrypto-mon` in the spec's order. Once the gate holds, the node's four direct-stream dead-men are silenced and its two contact points move to the main channel, so both stacks page there. After rung 2's box, each direct-shipped log stream moves to the node's Loki in a sitting of its own, the engine's at the box's deferred disarm converge. Once every stream has moved and the node has paged the main channel for seven days, Grafana Cloud's receivers move to the shadow channel, the ops watchdog probes the node, and the tools' default stack becomes the node. Grafana Cloud keeps evaluating every shared rule until phase 4 retires its leg.

**Architecture:** Nine build tasks in three pull requests, with attended runsheets between them and two records pull requests. The first pull request is the cutover pull request the spec names: the gate, read from the tree and the ops journal and recorded (Task 1); the operator surfaces that say the node pages the shadow channel alone (Task 2); and the push skill's one sentence on the node's webhook (Task 3). The node's silences and its push to the main webhook follow. The second pull request merges on the hand-over day, after the box. It points both logship templates at the node's `logship` user and moves the guards that read Grafana Cloud's logship token, so the capture and ops compose files change by one comment line and the engine's renders byte-identical (Task 4). It also re-trues the direct-ship surfaces and adds the hand-over procedure (Task 5). The four sittings of that day follow. The third pull request flips the tools' default stack and the push script's default (Task 6), points the ops watchdog's probe at the node (Task 7), turns `grafana-cloud-dark` into the node-dark procedure and re-trues the surfaces that name Grafana Cloud as the pager (Task 8), and takes the skills to the node (Task 9). Grafana Cloud's push to the shadow webhook and the ops converge then follow.

**Tech Stack:** Grafana OSS on the node and Grafana Cloud, `infra/scripts/grafana-push.sh`, `grafana_auth.py`'s stack table, `grafana-query.py`, `ops_daily.py` and `grafana-compare.py`; Ansible (ansible-core 2.21, the `capture`, `ops`, `engine` and `mon` roles) through `infra/ansible/scripts/converge.sh`; the application log shipper `cli/logging/ship.py`, unchanged; pytest; `infra/scripts/mutate-probe.sh` for guard verdicts; Python 3.14 through `uv run`.

**Spec:** `docs/specs/00121-self-hosted-observability-design.md`, phase 3. It covers D19 (the gate), D22 (the sequence and its gate), D24 (the node-dark procedure), D25 (the rollback), D16's cutover clause (the ops watchdog's probe), D9's render clause, D20's ingest-dark and lost-lines proofs, the "Phase 3, the cutover" lines of "What changes in the repo, by phase" and "Proofs each phase owes", the invariants, and "What stays manual" (the silences in each stack's UI). Two owner rulings of 2026-10-08 settle the two points the spec left to this plan: the engine's hand-over converge and the dead-men's silences (Global Constraints). The measured basis this plan reads is the spec's, with phase 2's amendments on the records branch `docs/t0217-phase-2-records` (the log fan-out, the fleet on the node, the boundary reading). The plan's base is `develop` at `888d1d89e`, with the records branch at `71e1c9a37`, 26 commits ahead and unmerged. Phase 1 is `docs/plans/00121-mon-node.md` and phase 2 is `docs/plans/00121-dual-shipping.md`. Spec 00122's plan `docs/plans/00122-self-hosted-dead-man.md` shares this plan's engine converge (its R14). Phase 4 takes a plan of its own under the same serial. Every pull request's change-index row is keyed `00121` with no `iter`, as phases 1 and 2 were.

## Global Constraints

- **The gate comes first** (spec D19, D22). No receiver moves, and the cutover pull request does not open, until Task 1 has read all three parts of the gate. First, seven consecutive daily-pass journal entries from 2026-10-10, each carrying a `compare:` line that reads `0 differences` or whose differences that pull request explains. Second, drill-log entries `W1` to `W4`, each `pass`. Third, the measured-basis bullet with the boundary reading. A difference is fixed or explained in that pull request; one that is neither holds it for the owner.
- **The sequence is D22's.**
  - The node's four direct-stream dead-men are silenced before the node's two contact points move.
  - The node pages the main channel before any stream moves, which is D25's reason: a moved stream returns only by a revert and a restart.
  - The streams move after the box only, one sitting each. Their template change merges on the hand-over day, after the box closes.
  - Grafana Cloud's receivers move last: after every stream has moved and seven days after the node's receivers moved, with the probe re-pointed and the defaults flipped in the same step.
  - The node's three direct-stream burst rules (`zcrypto-engine-error-logs`, `zcrypto-capture-error-logs`, `zcrypto-ops-error-logs`) are blind on the node until their stream moves and take no silence there. Grafana Cloud's copies keep paging.
- **Through the box, Grafana Cloud is untouched** (the invariant). Its rules, receivers, watchdog URL and vault values stay as they are, and nothing from this work converges `zcrypto`. R2 to R4 touch the node alone and may run inside the box. The box runs Mon 2026-10-05 to Sun 2026-11-01 and may slip one week under its own rule.
- **One converge for the engine (the owner's ruling of 2026-10-08).** The engine's log-stream hand-over and spec 00122's move of the engine's dead-man check happen in one converge: the box's deferred disarm converge, inside its inter-cycle gap after the box closes (`infra/runbooks/engine-procedures.md#engine-rung-2-box` step 8 item 6, which is plan 00122's R14). The engine's hand-over task names that converge, and nothing else restarts the engine for it. Three things follow:
  - The primary's capture converge renders `/opt/zcrypto-capture/logship-secrets.env`, the file the engine reads at start. It runs earlier on the same day, so the four sittings fall on [[ROLLOUT: the hand-over day — the box's deferred disarm converge's day, Mon 2026-11-02 or a week later under the box's slip rule]], the engine's last.
  - The engine's compose template renders byte-identical (Task 4), so the converge's preview stays the one item 6 reads.
  - If the primary's capture sitting cannot finish before the day's last gap that item can use, the engine's hand-over stops and goes to the owner. No other restart is taken in its place.
- **Silences dated to their sitting (the owner's ruling of 2026-10-08).** Each of the node's four direct-stream dead-men takes a silence that ends at its own sitting's planned instant: `zcrypto-ops-poller-log-dead` at S1, `zcrypto-capture-log-dead-secondary` at S2, `zcrypto-capture-log-dead-primary` at S3, `zcrypto-engine-log-dead` at S4.
  - The silences are set in the node's UI before the node pages the main channel (R2).
  - At the hand-over, each is read back through the node's Alertmanager API and the instant it ended is recorded (R6 to R9, then R-records-2), so no silence outlives its stream.
  - A sitting that moves re-dates its silence's end in the node's UI before the old end passes, read back the same way.
  - A sitting that runs past its silence's end takes that dead-man's page from the node in the main channel. The page is read as the overrun, not as a fault.
- **Grafana Cloud's silences.** At each hand-over, Grafana Cloud's rules that read the moved stream are silenced in Grafana Cloud's UI (D22(3)), scoped to that stream. The dead-man is matched by `__alert_rule_uid__`. The burst rule is matched by its `__alert_rule_uid__` plus the stream's `host` and `container`, so its instances on a host or container not yet moved still page. Each ends at [[ROLLOUT: the Grafana Cloud silences' end — a day past retirement's planned start]]. The reason: after its receivers move, a dead-man Grafana Cloud fires reaches the shadow channel, and retirement's gate reads that channel for pages the node did not also send (D23).
- **The capture pair are restarted attended, one host at a time** (`.claude/rules/fleet-deploys.md`; `infra/runbooks/capture-daemon.md` step 4). The secondary goes first and the primary an hour later. The secondary's form is `-e capture_image_digest=<running> -e capture_alloy_digest=<running>`. The primary's is `--tags capture -e converge_primary=true` with the same two digests, never `--skip-tags engine` and never un-tagged. Both are the forms the dead-man cutover sitting ran on 2026-10-08 (plan 00122's R12). The capture restart is the converge's own `restart capture service` handler, which runs because Task 4 changes the rendered compose file. If the capture compose render reads `changed=false`, the restart is `sudo systemctl restart zcrypto-capture` by hand, in the same sitting.
- **The engine converges only inside the inter-cycle gap that `site.yml` computes from the boundary cycle's journal, under `infra/runbooks/engine-procedures.md`'s restart rules.** `-e '{"engine_window_override": …}'` is never passed without the owner's explicit approval, and a failed boundary is never retried.
- **`KRAKEN`, the whole-feed read of `https://status.kraken.com/api/v2/scheduled-maintenances.json`, is never piped through `head` or `tail`.** It is taken at planning and again immediately before every converge of `zcrypto-ops`, `zcrypto-red` and `zcrypto`. An empty or truncated feed is never evidence the window is clear. `zcrypto-mon` speaks to no venue, and its pushes and silences owe no read (`.claude/rules/fleet-deploys.md`; the invariant).
- **Each step's rollback stands beside it** (D25):
  - A receiver move is undone by one push per stack with the earlier webhook. Until a stream has moved, that is the whole rollback.
  - A moved stream returns only by reverting Task 4's commit, merging the revert, converging the stream's host in its hand-over form and restarting its shipper (the engine's inside a gap). The node's silence is then set again and Grafana Cloud's silences are ended.
  - The probe's re-point is undone by an ops converge with the admitted key `-e ops_grafana_watchdog_probe_url=https://zcrypto2026.grafana.net/api/health` until a revert merges.
  - The default flip is undone by reverting Task 6's commit.
- **Every push goes through `.claude/skills/zcrypto-grafana-push/SKILL.md`.** It starts from merged `develop` in a checkout that passes the skill's Step 2, after its open-PR hold. The node's push takes `infra/runbooks/mon.md#mon-push`'s form, and a push that moves a stack's contact points carries that stack's webhook in `GRAFANA_SLACK_WEBHOOK_URL`.
- **No secret appears in a command line, a log, a diff or a plan step, and no task prints one.**
  - A webhook or token reaches a command as an environment value read through `grafana_auth`, and a token reaches `curl` as a header on stdin (`-H @-`).
  - No container's environment is printed: a restart is proven by `.State.StartedAt` and `.RestartCount` alone.
  - A rendered file that carries a ping URL or a credential (the watchdog script, `logship-secrets.env`, `engine.env`) is read with `grep -c` for a host name and never printed.
  - No executor decrypts, prints or generates a vault value, and `ansible-inventory --host`, `--list` and `--graph --vars` are never run.
- **No executor step reaches a host, a venue, either Grafana, Slack, the dead-man service or the Linode Cloud Manager.** Every such step is an operator step, marked attended, with `W$` the workstation and `H$` the host.
- `infra/ansible/scripts/converge.sh` is never wrapped in `timeout`.
- No operator-read surface carries `Phase <N>`, `T<NNNN>`, `spec <NNNNN>` or `D<N>`; the surfaces are the runbook pages, the rule file's text, the Slack template, the skills and the healthchecks fixture's descriptions. Where provenance is wanted, it goes in an adjacent code comment.
- A comment or docstring carries a count of another file's contents only where a test holds that count.
- **A guard change records its `infra/scripts/mutate-probe.sh` verdict on the commit that makes it.**
  - The verdict is earned after the commit exists: the commit is made with the placeholder line `PROBE_VERDICT` in its message, and a message-only amend with the tree clean replaces that line with each probe's verdict.
  - The branch is unpushed while its tasks run, so the amend rewrites nothing a reader holds.
  - No entry of `infra/scripts/count-list.sh` counts a stack, a channel, a contact point, a webhook, `DEFAULT_STACK` or `COMPARISON_FROM` (the measured basis's read of its 49 entries), so no count moves in this phase.
- **Every commit is green over its changed files' consumers: the tests each task's consumer step names, never the full suite locally, which is CI's.**
  - A task that edits a page under `infra/runbooks/` also runs the runbook walkers: `tests/test_internal_terms_not_operator_visible.py`, `tests/test_runbook_internal_tokens.py`, `tests/test_runbook_triggers.py` and `tests/test_infra_alert_rules.py`, the last of which holds `test_every_runbook_cross_reference_resolves`.
  - A task that edits a skill runs `tests/test_guidance_guard.py` and `tests/test_guidance_refs_resolve.py`.
- **The commit gate runs before every commit.** The commit's files are staged by path, and then `uv run pre-commit run -a` runs clean. A run that rewrites files is re-run until clean, and the rewrites are staged.
- A new Markdown paragraph or list item is one line, with no column wrap and no filler blank lines. A universal word in a new runbook bullet (every, never, always, only, any, cannot) carries its `(set: …; count: …)` or `(no count command: …)` clause, or the bullet is worded without it.
- **Tasks 3 and 9 alone edit files under `.claude/`, each in a `claude` commit that carries no other file.**
  - A commit that grows the always-loaded set (a skill's `description`) carries the line `Ambient grows by N bytes: <reason>`, with N as `infra/scripts/guidance-guard.py` measures it.
  - `zcrypto-refine-rules` is loaded before each edit to a skill or to a top-level page under `infra/runbooks/`: the pages Tasks 2, 5 and 8 edit and the skills of Tasks 3 and 9.
  - No task edits `CLAUDE.md`.
- A commit message ends with this trailer, the placeholder replaced by the executing model's own name, followed by the executing session's `Claude-Session:` line where its harness supplies one:

```
Co-Authored-By: Claude <actual executing model> <noreply@anthropic.com>
```

## File structure

- `docs/open-topics/T0217-self-hosted-observability-stack.md`: the gate's findings bullet (Task 1); the readings, the state and the `ripe_when` the two records pull requests write (R-records-1, R-records-2).
- `infra/runbooks/mon.md`:
  - Task 2: `mon-push`'s *What it means* and step 2, where the node's webhook is the main channel's and the rollback's is the shadow channel's; `mon-patch-pass` step 6; `zcrypto-mon-reboot-pending`; `zcrypto-mon-grafana-error-logs`; `mon-dark`'s *What you are seeing*.
  - Task 5: a new `mon-stream-handover` procedure.
  - Task 8: `mon-dark`, `mon-push` step 1 and `mon-compare` step 3 after the flip.
- `infra/runbooks/hc.md`: the header and the sections whose sentences say the node's `zcrypto-hc` group pages the shadow channel (Task 2); `hc-dark` and `zcrypto-hc-service-down` once Grafana Cloud pages the shadow channel (Task 8).
- `infra/runbooks/engine.md`: `#zcrypto-engine-dark-with-exposure` step 1 gains the read of `zcrypto-mon-ingest-dark` first (Task 2), with its stack names re-trued after the flip (Task 8); `#zcrypto-engine-log-dead` step 4 (Task 5).
- `infra/runbooks/drills-telemetry.md`: the `W1` to `W4` sections' channel sentences (Task 2); drills C and C′ and the sections' Grafana Cloud lines once the node pages alone (Task 8).
- `infra/runbooks/engine-procedures.md`: step 8 item 6 names the hand-over the deferred disarm converge carries (Task 5).
- `infra/runbooks/observability.md`: the direct-ship sections `#zcrypto-logship`, `#zcrypto-capture-log-dead` and `#zcrypto-ops-log-plane` (Task 5); `grafana-cloud-dark` becomes `grafana-dark`, the node-dark procedure, with `#zcrypto-hcio-watchdog`, the header and the alloy-dark sections re-trued (Task 8).
- The other operator pages whose lines name Grafana Cloud as the stack a rule pages from, found by Task 8's sweep (`cache.md`, `zaccess.md` and the rest the sweep prints), and `infra/grafana/alerts.yaml`'s text where it says so (Task 8).
- `infra/ansible/group_vars/observed/vars.yml`: `mon_ingest_logship_user` (Task 4).
- The logship and compose files (Task 4):
  - `infra/ansible/roles/capture/templates/logship-secrets.env.j2` and `infra/ansible/roles/ops/templates/logship-secrets.env.j2`: the three `ZCRYPTO_LOKI_*` lines and their headers.
  - `roles/capture/tasks/main.yml` and `roles/ops/tasks/main.yml`: the render tasks' guards and the comments that name the old token.
  - `roles/capture/templates/compose.yaml.j2`, `roles/ops/templates/compose.yaml.j2` and `roles/engine/templates/compose.yaml.j2`: the guards, plus the capture and ops comment lines that name the token.
  - `infra/ops/README.md`: the guard's name.
- `infra/scripts/grafana-compare.py`: the comment on the seven direct-shipped rules (Task 5).
- The default flip (Task 6): `infra/scripts/grafana_auth.py` (`DEFAULT_STACK`); `infra/scripts/grafana-push.sh` (`GRAFANA_URL`'s default, the header and the render paragraph); `infra/scripts/ops_daily.py` (the comparison section's comment).
- The ops watchdog (Task 7): `infra/ansible/roles/ops/defaults/main.yml` (`ops_grafana_watchdog_probe_url`); `roles/ops/templates/grafana-watchdog.sh.j2` (the header); `roles/ops/templates/grafana-watchdog.timer.j2` (the description).
- `.claude/skills/zcrypto-grafana-push/SKILL.md`: line 20's webhook sentence (Task 3); Step 0, Steps 1, 3 and 4 and the description after the flip (Task 9). `.claude/skills/zcrypto-daily-ops/SKILL.md` and the other skills Task 9's sweep names (Task 9).
- Tests:
  - `tests/test_infra_compose_templates.py`: the guards' two branches under the new name, the logship files' literal lines, and no role reading Grafana Cloud's logship token (Task 4).
  - `tests/test_infra_mon_role.py`: the group vars' logship user (Task 4).
  - `tests/test_infra_converge_guards.py`: one comment (Task 4).
  - `tests/test_grafana_auth.py`, `tests/test_grafana_query.py`, `tests/test_ops_daily.py` and `tests/test_grafana_push_sh.py`: the default stack (Task 6).
  - `tests/test_grafana_auth.py`: the probe held to the default stack (Task 7).
- The records pull requests, not a task's: `docs/reference/deploy-log.jsonl`, `fleet-pins.md`'s `since` cells and `fleet.md`.

## Review Focus

Six classes, each held by the tests or reads of the tasks named beside it.

- **A stream pushed with a credential the edge refuses, or a guard keyed on a name the vault lacks.** Either way, the shipper's push fails and its lines are dropped and counted, or the compose renders without `--ship-logs`. The literal case holds both logship templates to `mon_ingest_loki_url`, `mon_ingest_logship_user` and `mon_ingest_logship_password`. The group-vars case holds `mon_ingest_logship_user` equal to the `mon` role's default and admitted on the Loki path alone. Task 4's Step 1 reads the vault key's name present. The sweep case holds no file under `infra/ansible/roles/` naming `logship_loki_token` (Task 4).
- **The engine restarted for its hand-over by anything but the deferred disarm converge, or a capture restart outside its attended sitting.**
  - The engine's compose renders byte-identical across Task 4, read in its Step 4, so no engine-tagged converge restarts the engine for this change.
  - The capture compose's one changed comment line makes its restart the hand-over converge's handler, in the sitting the rule licenses, and the merge waits for the hand-over day after the box.
  - The primary's capture converge is `--tags capture`, which renders the engine's file and reaches no engine task (Task 4, R8, R9).
- **A default that flips alone.** `DEFAULT_STACK`, the push script's `GRAFANA_URL` default and the ops watchdog's probe default are held to one value by tests. The push tests' Grafana Cloud URL is read from `grafana_auth.STACKS["cloud"]`, never from the script's default, which is the node's from Task 6, so the refusal and skip cases keep addressing Grafana Cloud (Tasks 6, 7).
- **A rule of the node-only groups reaching Grafana Cloud after the flip.** The host-keyed skip default and the refusal are unchanged and keep holding on every Grafana Cloud spelling. A push naming no stack now goes to the node and sends both node groups (Task 6).
- **A silence that outlives its stream, ends before it, or blinds a stream not yet moved.** The node's four end at their sittings and are read back expired with their instants. Grafana Cloud's are scoped to the moved stream's `host` and `container` (R2, R6 to R9, R-records-2).
- **An operator surface left saying the old pager, or a phase-4 line re-trued early.** Task 2 and Task 8 each run their sweep and class every hit. A line that says which stack pages, which channel a stack's page reaches, which URL the watchdog probes or which stack a tool reads by default is re-trued in the task that makes it false. A line on the Grafana Cloud leg's shipping, its keep-lists, its keep-alive, its retention or a past event is left to phase 4 or to history (Tasks 2, 5, 8, 9).

---

### Task 1: The gate — seven clean comparison days, four drills and the boundary reading, read and recorded

**Files:**
- Modify: `docs/open-topics/T0217-self-hosted-observability-stack.md` (one `## Findings so far` bullet: the gate as read, the seven entries by date with their `compare:` lines, each difference with its class, the four drill entries, and the boundary bullet)

**Interfaces:**
- Consumes:
  - the standing `ops-journal` branch's `docs/reference/ops-journal/2026-10.md`, each entry's `compare:` line (the daily-ops skill's step 7);
  - `docs/reference/drill-log.md`'s headings `## <date> — W<n> — pass`;
  - the spec's measured-basis bullet `The range-selector boundary, read on 2026-10-07`, which reads 5 on Grafana Cloud and 6 on the node;
  - `ops_daily.COMPARISON_FROM`;
  - `docs/reference/deploy-log.jsonl`'s `zcrypto-mon` rows;
  - R1's difference files under `.tmp/cutover/`.
- Produces: the gate's bullet in T0217, which the cutover pull request's body cites, and [[ROLLOUT: the gate's day — the seventh consecutive journal entry from 2026-10-10 whose compare line reads 0 differences or differences the pull request explains]].

**What this task decides, where the spec leaves it open:**
- **The seven are consecutive UTC days from 2026-10-10 on.** Each is a journal entry carrying the script's summary line. A `compare: failed` line, a day with no entry, or an entry with no `compare:` line breaks the run, and the count starts again from the next day (the daily-ops skill's step 1 paragraph; `mon.md#mon-compare`). Entries past October are read from the next month's file the same way.
- **A rebuild of the node restarts the seven** (D19). The deploy log records no bootstrap, so the read is every un-tagged `site.yml` row limited to `zcrypto-mon` since the primary's recreate, 2026-10-07T12:14:42Z, each checked against that day's journal entry. A rebuild named there restarts the count from the first day whose 00:00 UTC is 50 h after its converge.
- **The explanations admitted are D20's three, each read by R1 at the instant the difference names.**
  - The boundary sample: a value one sample apart on a node that reads a range, where a sample sits on the range's left edge. The node's 2.53.3 counts that sample and Grafana Cloud does not (the measured basis's 5 against 6).
  - An extra instance on the node of a rule with no `host` matcher, the node's leg being unfiltered.
  - A family Grafana Cloud's keep regex drops at the shipper, `only on mon` over a family absent from that role's keep block.
  - A difference in none of the three holds the pull request for the owner, to be fixed (a rule change with its dual push, which restarts no count) or explained in words the owner accepts.
- **What refuses:** fewer than seven; any of `W1` to `W4` without a `— pass` heading; the boundary bullet absent from the spec on `develop`; `COMPARISON_FROM` not set to 2026-10-10; or a difference no class admits. Each is a stop. Tasks 2 and 3 may be built on the branch ahead of the gate's day, but the pull request opens only after this task's commit.

- [ ] **Step 1: The preconditions on `develop`.** The records branch and R12's `COMPARISON_FROM` pull request are merged.

```bash
git fetch origin develop ops-journal
git grep -c 'The range-selector boundary, read on 2026-10-07' origin/develop -- docs/specs/00121-self-hosted-observability-design.md
git show origin/develop:docs/reference/drill-log.md | grep -cE '^## [0-9-]+ — W[1-4] — pass$'
git show origin/develop:infra/scripts/ops_daily.py | grep -cE '^COMPARISON_FROM.*= date\(2026, 10, 10\)$'
```

Expected: one line ending `:1`, then `4`, then `1`. Any other reading is a stop: the phase-2 records are not on `develop` yet.

- [ ] **Step 2: The journal.** `git show origin/ops-journal:docs/reference/ops-journal/2026-10.md | grep -E '^## 2026-10-|^compare:|compare: '` — Expected: from `## 2026-10-10` on, each entry heading followed by one `compare: <n> nodes × 24 instants, <k> differences` line. The seven consecutive ones are listed by date, and each `<k>` above 0 names a day R1 reads.
- [ ] **Step 3: The rebuild read.** `uv run python -c "import json; [print(r['ts'], r['tags'] or '<un-tagged>') for r in map(json.loads, open('docs/reference/deploy-log.jsonl')) if r.get('limit') == 'zcrypto-mon' and r['ts'] > '2026-10-07T12:14:42Z' and not r.get('tags') and r.get('playbook') == 'site.yml']"` — Expected: no line, or lines whose day's journal entry names no rebuild.
- [ ] **Step 4: R1's files.** For each day Step 2 named, `.tmp/cutover/compare-<day>.txt` exists and each difference line in it carries R1's class. Expected: every line classed. A line without a class is the stop above.
- [ ] **Step 5: The bullet.** One line in `## Findings so far`: the seven days and their lines, each difference and its class, the four drill headings with their dates, the boundary bullet's two readings, and R0's instant.
- [ ] **Step 6: The consumers** — `uv run pytest tests/test_open_topics_frontmatter.py tests/test_topics_index.py -q -p no:cacheprovider`; Expected: no failure.
- [ ] **Step 7: The commit gate.**
- [ ] **Step 8: Commit** — `docs(topics): T0217 records the cutover's gate — seven clean comparison days, the four drills and the boundary reading`, with the trailer; no guard changes, so no probe.
- [ ] **Step 9: The tree is clean** — `git status --porcelain`; Expected: empty.

---

### Task 2: The node pages the main channel — the operator surfaces that say it pages the shadow channel alone, and the exposure page's first read

**Files:**
- Modify: `infra/runbooks/mon.md`:
  - `mon-push`'s *What it means* sentence on a shell that exported the other stack's webhook.
  - Step 2: the push that moves the node's contact points carries `slack_webhook_url`, the main channel's, read through `grafana_auth.vault_var`, and the same push with `slack_shadow_webhook_url` is its rollback.
  - `mon-patch-pass` step 6 and `zcrypto-mon-reboot-pending`'s clause: "Until the node pages the main channel, that alert reaches the shadow channel alone, and this read is the one that brings a pending reboot to a person". The alert now pages the main channel, and the read stays as the pass's own.
  - `zcrypto-mon-grafana-error-logs`'s "A shadow channel that stays silent".
  - `mon-dark`'s *What you are seeing*: the node's copies in the main channel stop while Grafana Cloud's continue, in place of "the shadow channel is silent".
- Modify: `infra/runbooks/hc.md` (the header's "an alert fired in the shadow channel" and its sentence that the `zcrypto-hc` group pages the shadow channel; `hc-patch-pass` step 7's and `zcrypto-hc-reboot-pending`'s "Until the observability node pages the main channel" clauses; `zcrypto-hc-error-logs`'s channel lines)
- Modify: `infra/runbooks/engine.md`, `#zcrypto-engine-dark-with-exposure` step 1. A first read is added (D16, D20): when the page's links are under `https://zcrypto-mon.zhaow.me/`, read `zcrypto-mon-ingest-dark` there first. `uv run python infra/scripts/grafana-query.py --stack mon 'count(up{host!="zcrypto-mon"}) or on() vector(0)'` reading 0 is the node's edge or certificate, with every host absent at once (`mon.md#zcrypto-mon-ingest-dark`). The page's two halves are then read on Grafana Cloud's copy, `grafana-query.py` with no `--stack`, before the route split that follows.
- Modify: `infra/runbooks/drills-telemetry.md` (the `W1` to `W4` sections' sentences on the channel the node's pages reach in a re-run: the main channel, beside Grafana Cloud's copies until its receivers move)
- Test: none new; the runbook walkers.

**Interfaces:**
- Consumes: R3's push, which this task's text describes and which follows the pull request's merge; `zcrypto-mon-ingest-dark`, `for: 5m`, which W1's edge stop read paging at +11:24, ahead of the alloy-dark pair at +15:59 (T0217's W1 finding); the vault key names `slack_webhook_url` and `slack_shadow_webhook_url`.
- Produces: `mon.md#mon-push` step 2 in the form R3 runs.

**What this task decides, where the spec leaves it open:**
- **The sweep that finds the lines is `git grep -n -i -E 'shadow channel|until (the )?(observability )?node pages' -- infra/runbooks .claude infra/grafana infra/scripts docs/reference/fleet.md`.** At this plan's base it prints 26 runbook lines (15 in `drills-telemetry.md`, 6 in `mon.md`, 5 in `hc.md`). The push skill's line 20, which names the node's shadow webhook rather than the channel, is Task 3's. Each hit that says the node, or a group it alone evaluates, pages the shadow channel is re-trued here. A hit that says Grafana Cloud pages the main channel stays true until R10 and is Task 8's. The drill log is history and is not edited.
- **The exposure page's read is the node's because, from R3, both stacks send that page.** The node's copy is the one an ingest outage can raise, and its links name its host. After Task 6's flip, Task 8 swaps the stack names in the step.

- [ ] **Step 1: Load `zcrypto-refine-rules`** and read its *Before you write guidance*.
- [ ] **Step 2: The sweep**, kept as `.tmp/cutover/task2-sweep`, each hit classed.
- [ ] **Step 3: The edits.**
- [ ] **Step 4: The consumers** — `uv run pytest tests/test_internal_terms_not_operator_visible.py tests/test_runbook_internal_tokens.py tests/test_runbook_triggers.py tests/test_infra_alert_rules.py tests/test_ops_daily.py tests/test_drill_log.py tests/test_infra_hc_role.py tests/test_infra_mon_role.py -q -p no:cacheprovider`; Expected: no failure.
- [ ] **Step 5: The commit gate.**
- [ ] **Step 6: Commit** — `docs(runbooks): the node pages the main channel — its push's webhook, the node-only groups' channel, and the exposure page reads ingest-dark first`, with the trailer; no guard changes.
- [ ] **Step 7: The tree is clean.**

---

### Task 3: The push skill's sentence on the node's webhook

**Files:**
- Modify: `.claude/skills/zcrypto-grafana-push/SKILL.md` (line 20's "a shell that exported the node's shadow webhook then leaves Grafana Cloud's receivers where they point" becomes a shell that exported the other stack's webhook; nothing else)

**Interfaces:**
- Consumes: Task 2's `mon-push` step 2.
- Produces: a push skill true from R3.

- [ ] **Step 1: Load `zcrypto-refine-rules`.**
- [ ] **Step 2: The edit**, in the body, outside the always-loaded set.
- [ ] **Step 3: The consumers** — `uv run pytest tests/test_guidance_guard.py tests/test_guidance_refs_resolve.py tests/test_grafana_push_sh.py -q -p no:cacheprovider`.
- [ ] **Step 4: The commit gate.**
- [ ] **Step 5: Commit** — `claude(skills): a routine push leaves either stack's receivers where they point, whichever channel's webhook the shell holds`, with the trailer; a `claude` commit carrying no other file.
- [ ] **Step 6: The tree is clean.**

Then the cutover pull request opens through the `open-pr` skill over Tasks 1 to 3. Its body cites Task 1's bullet under a `## Gate` section, and each difference with its explanation. A different agent reads the branch, and `merge-pr` merges it. The Rollout's R2 to R4 follow from merged `develop`.

---

### Task 4: The logship files push to the node's Loki as its `logship` user, and the guards that read Grafana Cloud's logship token move to the node's

**Files:**
- Modify: `infra/ansible/group_vars/observed/vars.yml` (`mon_ingest_logship_user: logship` beside `mon_ingest_fleet_user`; the header's "the user it admits on both" re-trued to the two users, `logship` on the Loki path alone)
- Modify: `infra/ansible/roles/capture/templates/logship-secrets.env.j2` and `infra/ansible/roles/ops/templates/logship-secrets.env.j2`:
  - The three lines below replace the `grafana_loki_url`, `grafana_loki_user` and `logship_loki_token` lines.
  - The header's Grafana Cloud sentences are re-trued: the access policy `zcrypto-app-logship`, "the URL and USERNAME are properties of the Grafana Cloud stack", and "the same values alloy-secrets.env.j2 renders". The password is the node's `logship` user's, which the edge admits on the Loki path alone, so revoking it leaves the `fleet` user's ingest untouched.
  - The `ZCRYPTO_SHIP_LOGS` line and its comment stay.
- Modify: `infra/ansible/roles/capture/tasks/main.yml` and `infra/ansible/roles/ops/tasks/main.yml`: each `render the logship secrets env file` task takes `when: mon_ingest_logship_password is defined`, and the ops task's comment naming `logship_loki_token is defined` is re-trued. These render tasks notify nothing; the capture role's comment, "a credential rotation must never restart live capture", stays true.
- Modify: `infra/ansible/roles/capture/templates/compose.yaml.j2`: its two `{% if logship_loki_token is defined %}` guards become `{% if mon_ingest_logship_password is defined %}`, and the comment line "Guarded by the SAME `logship_loki_token is defined`" is re-trued. The rendered file then differs by that one comment line, and the converge's `restart capture service` handler is the attended restart.
- Modify: `infra/ansible/roles/ops/templates/compose.yaml.j2`: the three guards and the comment's "`logship_loki_token is defined` condition", re-trued. The render notifies nothing, and the recreate is by hand.
- Modify: `infra/ansible/roles/engine/templates/compose.yaml.j2`: the three guards alone. No comment there names the token, so the rendered file is byte-identical.
- Modify: `infra/ops/README.md` (line 38's "guarded by `logship_loki_token is defined`")
- Test: `tests/test_infra_compose_templates.py`:
  - The guard's two branches render under `mon_ingest_logship_password`: `test_renders_valid_yaml_without_logship_token`, `test_renders_valid_yaml_with_logship_token` and `test_engine_logship_guard_moves_environment_and_entrypoint_together`, the variable and the comments re-trued.
  - New: `test_the_logship_files_push_to_the_nodes_loki_as_its_logship_user`, which holds each template's three `ZCRYPTO_LOKI_*` lines to the literal below and reads no `grafana_loki_` or `logship_loki_token` name in either template.
  - New: `test_no_role_reads_grafana_clouds_logship_token`, under which no file below `infra/ansible/roles/` names `logship_loki_token`.
- Test: `tests/test_infra_mon_role.py`: `test_the_fleets_ingest_names_are_the_nodes_public_name_its_two_authenticated_paths_and_its_fleet_user` holds the group vars' `mon_` keys to a dict gaining `mon_ingest_logship_user` equal to the role default. A new assertion reads that user admitted on `/loki/api/v1/push` and absent from `/api/v1/write`, through `role_render.users`.
- Test: `tests/test_infra_converge_guards.py` (the comment at :1960, "the ops host defines `logship_loki_token`", re-trued to the new name; the assertions unchanged)

**Interfaces:**
- Consumes:
  - `mon_ingest_logship_password` in `infra/ansible/group_vars/observed/vault.yml` (phase 1's P2; T0085's node credentials) and `mon_ingest_loki_url` in the group vars (phase 2's Task 1).
  - The `mon` role's default `mon_ingest_logship_user: logship` and its edge include, which admits `logship` on `/loki/api/v1/push` alone (`infra/ansible/roles/mon/tasks/main.yml`'s `edge_basic_auth_routes`).
  - Phase 1's R6, which pushed through `cli/logging/ship.py`'s handler as `logship` to `https://zcrypto-mon.zhaow.me/loki/api/v1/push` and was accepted.
  - `cli/__main__.py`'s `_LOKI_ENV_NAMES`, unchanged.
  - The engine role's `preflight — refuse to restart the engine without its logship secrets`, unchanged.
- Produces, for Task 5 and the hand-over day:
  - after each host's sitting, the logship files `/etc/zcrypto-ops/logship-secrets.env` and `/opt/zcrypto-capture/logship-secrets.env` naming the node, rendered by `--tags ops` and by the capture-role converges;
  - the capture compose's rendered change (one comment line);
  - the ops compose's rendered change (one comment line);
  - the engine compose byte-identical;
  - `logship_loki_token` read by no role, so phase 4 removes it from the vault with no consumer left.

**What this task decides, where the spec leaves it open:**
- **The guards move here, not in phase 4.** The spec's phase-3 line names the two logship templates and the engine's compose template, whose one `logship` name is its guard. The capture and ops compose templates and the two render tasks carry the same guard on the same token. D23 removes `logship_loki_token` from the vault at retirement, and a guard still reading it would then silently render compose without `--ship-logs`. Moving them here lets the attended capture restart that D22(3) already owes carry the capture compose's one-line change. In phase 4 that change would be a capture restart of its own.
- **The engine's compose template changes in its three guards alone, so its rendered file is byte-identical** and the deferred disarm converge's preview stays item 6's. Step 4 reads it identical before the commit.
- **`mon_ingest_logship_user` is a group var for the reason phase 2 made `mon_ingest_fleet_user` one:** a role's defaults are invisible to another role's template.

The template lines, determined by the group and vault names:

```
ZCRYPTO_LOKI_URL={{ mon_ingest_loki_url }}
ZCRYPTO_LOKI_USERNAME={{ mon_ingest_logship_user }}
ZCRYPTO_LOKI_PASSWORD={{ mon_ingest_logship_password }}
```

The group var:

```yaml
mon_ingest_logship_user: logship
```

- [ ] **Step 1: The vault key's name, then the failing tests.** `grep -c '^mon_ingest_logship_password:' infra/ansible/group_vars/observed/vault.yml`, a key name alone; Expected: `1`. A `0` is a stop for the owner, since no executor writes a vault line. Then the cases above.
- [ ] **Step 2: Run them and read the failure** — `uv run pytest tests/test_infra_compose_templates.py tests/test_infra_mon_role.py -q -p no:cacheprovider`. Expected:
  - the literal case fails on both templates;
  - the sweep case fails, naming the seven files that read the token (the two logship templates, the three compose templates and the two render tasks' files);
  - the group-vars case fails on the missing key;
  - the guard-branch cases fail, since the renamed variable is not yet what the templates read.
- [ ] **Step 3: The group var, the two templates, the two tasks, the three compose templates, the README line and the comments the Files entries quote.**
- [ ] **Step 4: The engine's render, unchanged; the capture's, one comment line.** Before the commit, against `HEAD`'s copy:

```bash
mkdir -p .tmp/cutover && git show HEAD:infra/ansible/roles/engine/templates/compose.yaml.j2 > .tmp/cutover/engine-compose.base.j2
uv run python - <<'PY'
import sys
from pathlib import Path
sys.path.insert(0, "tests")
import test_infra_compose_templates as t
ctx = {**t.ENGINE_CONTEXT, "logship_loki_token": "x", "mon_ingest_logship_password": "x"}
render = lambda text: t._ENV.from_string(text).render(**ctx)
base = render(Path(".tmp/cutover/engine-compose.base.j2").read_text())
head = render(Path("infra/ansible/roles/engine/templates/compose.yaml.j2").read_text())
print("identical" if base == head else "differs")
PY
git diff -U0 -- infra/ansible/roles/capture/templates/compose.yaml.j2 infra/ansible/roles/ops/templates/compose.yaml.j2
```

Expected: `identical`; the diff shows each file's guards and one comment line, and nothing else. `differs` is a stop: the deferred disarm converge's preview would name the compose file, so item 6's preview line is re-trued in Task 5 before the pull request opens, and the engine restart is unchanged either way.

- [ ] **Step 5: Run the tests** — Expected: no failure.
- [ ] **Step 6: The consumers** — every test file `grep -rl --exclude='*vault*' 'logship\|compose.yaml.j2\|group_vars/observed' tests/ | sort` names: `tests/test_infra_compose_templates.py`, `tests/test_infra_converge_guards.py`, `tests/test_infra_mon_role.py`, `tests/test_infra_alloy_series.py`, `tests/test_logging_ship_handler.py` and `tests/test_obs_metrics.py` among them at this plan's base.
- [ ] **Step 7: The commit gate.**
- [ ] **Step 8: Commit** — `feat(infra): the applications' own log push goes to the node's Loki as its logship user, and no role reads Grafana Cloud's logship token`, with `PROBE_VERDICT` and the trailer.
- [ ] **Step 9: The tree is clean.**
- [ ] **Step 10: Prove the guards with one probe per guard, then record their verdicts by a message-only amend.** Mutations:
  - the capture template's URL line back to `{{ grafana_loki_url }}`;
  - the ops template's user line bound to `mon_ingest_fleet_user`;
  - the password line back to `logship_loki_token`;
  - the ops compose template's first guard back to `logship_loki_token`;
  - the engine compose's second guard back to `logship_loki_token`;
  - the group var's value `fleet`;
  - the group var removed;
  - the capture render task's `when:` back to the old name.

  Each run ends `mutate-probe: KILLED (control proven, tree restored byte-identically)`.

---

### Task 5: The direct-ship surfaces and the hand-over procedure

**Files:**
- Modify: `infra/runbooks/mon.md`, a new section `mon-stream-handover — PROCEDURE: handing a direct-shipped log stream to the node`, in the page's procedure shape:
  - *What you are seeing*: nothing fired, and a sitting moves one stream; or Grafana Cloud's dead-man for a stream pages because an unplanned restart moved it early.
  - *What it means*: each shipper reads its push credentials from its logship file when its container starts, so a start after the change reaches the host moves its stream. The engine reads the primary's capture file. The node's dead-man for each stream is silenced until its sitting, and Grafana Cloud's dead-man for a moved stream pages within its six-hour range unless silenced.
  - *What to do*, per stream: the converge and restart form of its host; the stream read by value on the node, the rule's own query; the shipper's two counters; the stream gone from Grafana Cloud; the node's dead-man `inactive`, then its silence ended and read back; Grafana Cloud's rules that read the stream silenced, scoped to its `host` and `container`.
  - *Rollback*.
  - *Retire when*: `grafana_auth.py`'s `STACKS` holds one stack.
- Modify: `infra/runbooks/engine-procedures.md`, step 8 item 6. The converge's restart starts the engine on the logship file the primary's capture converge rendered earlier that day, which hands the engine's log stream to the node; its reads are `mon.md#mon-stream-handover`'s, taken after disarm step 3's. The preview line stands unless Task 4's Step 4 read `differs`.
- Modify: `infra/runbooks/observability.md`:
  - The header's sentence on the direct-ship path, "push their own logs to Loki", which names the node's Loki once each stream has moved.
  - `#zcrypto-logship` step 6's "a fresh Loki line", read on the node once the stream has moved.
  - `#zcrypto-capture-log-dead`.
  - `#zcrypto-ops-log-plane` steps 3 and 4: "A rotated Loki token" becomes the node's `logship` password, and the converge re-renders the file.
  - In each of those sections, a Grafana Cloud dead-man for a stream already moved routes to `mon.md#mon-stream-handover`.
- Modify: `infra/runbooks/engine.md` (`#zcrypto-engine-log-dead` step 4's "the host's push path or Grafana Cloud", re-trued to the node's edge and Loki)
- Modify: `infra/scripts/grafana-compare.py` (the comment above `DIRECT_SHIPPED_RULES`, "which reaches the node only at the cutover", re-trued: the seven read a stream that reached the node at its hand-over and Grafana Cloud no longer, so they stay outside the comparison)
- Test: none new; the runbook walkers, and `tests/test_grafana_compare.py` for the comment.

**Interfaces:**
- Consumes:
  - Task 4's files.
  - The seven rules and their selectors (`infra/grafana/alerts.yaml`). Each dead-man is `sum by (host) (count_over_time({host=…, container=…, level=~".+"} [6h])) or on() vector(0)` with `for: 0s` and `noDataState: Alerting`; each burst rule is `sum by (host, container, level, msg)` over the same stream's `ERROR|CRITICAL` lines.
  - The shipper's counters `zcrypto_logship_shipped_lines_total` and `zcrypto_logship_dropped_lines_total`, under the jobs `liquidations_app`, `capture_app` and `engine_app` (the read `observability.md#zcrypto-logship` step 6 already uses).
- Produces: `mon.md#mon-stream-handover`, which R6 to R9 follow and engine-procedures' item 6 cites.

- [ ] **Step 1: Load `zcrypto-refine-rules`.**
- [ ] **Step 2: The sweep** — `git grep -n -i -E 'logship|ship-logs|direct-ship|push their own logs' -- infra/runbooks infra/ops/README.md`, each hit read for a sentence that names Grafana Cloud's Loki or its token as the push's destination; kept as `.tmp/cutover/task5-sweep`.
- [ ] **Step 3: The section, item 6's clause, the re-trued lines and the comment.**
- [ ] **Step 4: The consumers** — `uv run pytest tests/test_internal_terms_not_operator_visible.py tests/test_runbook_internal_tokens.py tests/test_runbook_triggers.py tests/test_infra_alert_rules.py tests/test_grafana_compare.py tests/test_code_prose_citations.py tests/test_prose_chars.py -q -p no:cacheprovider`; Expected: no failure.
- [ ] **Step 5: The commit gate.**
- [ ] **Step 6: Commit** — `docs(runbooks): a direct-shipped stream's hand-over to the node, one sitting each, and the engine's at the box's deferred disarm converge`, with the trailer.
- [ ] **Step 7: The tree is clean.**

Then the second pull request opens over Tasks 4 and 5, is read by a different agent and is reviewed ahead of the hand-over day. `merge-pr` merges it on [[ROLLOUT: the hand-over day …]], after the box, before that day's first converge (R5).

---

### Task 6: The tools' default stack is the node, and a push that names no stack goes to it

**Files:**
- Modify: `infra/scripts/grafana_auth.py` (`DEFAULT_STACK = "mon"`; its comment, "the one that pages", stays true)
- Modify: `infra/scripts/grafana-push.sh`:
  - `export GRAFANA_URL="${GRAFANA_URL:-https://zcrypto-mon.zhaow.me}"`.
  - The header's "With no GRAFANA_URL it goes to Grafana Cloud and leaves out the rule groups the observability node alone evaluates" is re-trued: with none it goes to the node, which takes every group, and a push addressed to Grafana Cloud leaves those groups out.
  - The render paragraph (D9): the node runs no image renderer, so a dashboard is verified by reading each panel's query by value and looking at the panel.
  - The host-keyed skip default and the refusal are unchanged.
- Modify: `infra/scripts/ops_daily.py` (the comment above the `## Comparison` section, "a difference is a finding for the cutover pull request", cut to what stays true: the line is not a verdict and `exit_code` never reads it)
- Test: `tests/test_grafana_auth.py` (the table test renamed `test_the_table_holds_the_two_stacks_and_reads_the_node_when_none_is_named`, asserting `DEFAULT_STACK == "mon"`, `stack() is STACKS["mon"]` and `GRAFANA_URL == STACKS["mon"].url`, and Grafana Cloud's row unchanged)
- Test: `tests/test_grafana_query.py` (`test_no_stack_named_reads_grafana_cloud_with_its_token` becomes `test_no_stack_named_reads_the_node_with_its_token`; a case `--stack cloud` reads Grafana Cloud's URL with `grafana_sa_token`; the usage string unchanged)
- Test: `tests/test_ops_daily.py` (`test_the_pass_reads_grafana_cloud_when_no_stack_is_named` becomes `test_the_pass_reads_the_node_when_no_stack_is_named`; the named case reads `--stack cloud`; the comparison's due-ness cases unchanged, since they read the table's length)
- Test: `tests/test_grafana_push_sh.py`:
  - `_cloud_url()` reads `grafana_auth.STACKS["cloud"].url`, loaded as `tests/test_grafana_auth.py` loads the module, in place of the script's default.
  - `_cloud_url_forms()` loses its `"the default"` entry, which no longer spells Grafana Cloud.
  - `test_a_push_that_names_no_stack_sends_no_rule_of_the_observability_node` becomes `test_a_push_that_names_no_stack_goes_to_the_node_and_sends_both_of_its_groups`: `GRAFANA_URL=""` sends `r3` and `r4`, and the first line ends `skip-groups=<none>`.
  - New: `test_the_scripts_default_stack_is_the_tools_default_stack`, holding the script's `GRAFANA_URL` default equal to `grafana_auth.STACKS[grafana_auth.DEFAULT_STACK].url`.

**Interfaces:**
- Consumes: the stack table and its two rows; the push script's host-keyed `skip_default` and its refusal (`grafana-push.sh:53-73`); every importer of `grafana_auth.GRAFANA_URL` and `DEFAULT_STACK` (`grafana-query.py`, `ops_daily.py`, `grafana-compare.py`, `ops-postverify.sh` through `grafana-query.py`).
- Produces: a workstation whose unnamed reads and pushes go to the node, which Task 9's skills and R10 rely on.

**What this task decides, where the spec leaves it open:**
- **The skip default needs no edit.** It is keyed to the host the push addresses, so moving the URL default moves it: an unnamed push skips nothing, and a push to any Grafana Cloud spelling still skips both node groups and refuses otherwise. That is the "push script's defaults" D22(4) flips.
- **The comparison keeps running until retirement** (`comparison_due` reads the table's length). Its line keeps landing in the journal and nothing waits on it.

- [ ] **Step 1: Write the failing tests.**
- [ ] **Step 2: Run them and read the failure** — `uv run pytest tests/test_grafana_auth.py tests/test_grafana_query.py tests/test_ops_daily.py tests/test_grafana_push_sh.py -q -p no:cacheprovider`. Expected:
  - the default cases fail on `cloud`;
  - the new equality case passes, both defaults still naming Grafana Cloud;
  - the rewired `_cloud_url()` cases pass unchanged.
- [ ] **Step 3: The constant, the script's default, its header and render paragraph, and the comment.**
- [ ] **Step 4: Run the tests** — Expected: no failure.
- [ ] **Step 5: The consumers** — every test file `grep -rl --include='test_*.py' 'grafana_auth\|grafana-query\|grafana-push\|ops_daily\|ops-daily\|grafana-compare\|ops-postverify' tests/ | sort` names, with `tests/test_scripts_have_tests.py`, `tests/test_code_prose_citations.py` and `tests/test_prose_chars.py`.
- [ ] **Step 6: The commit gate.**
- [ ] **Step 7: Commit** — `feat(grafana): the tools read and push to the observability node when no stack is named`, with `PROBE_VERDICT` and the trailer.
- [ ] **Step 8: The tree is clean.**
- [ ] **Step 9: Prove the guards, then record their verdicts by a message-only amend.** Mutations:
  - `DEFAULT_STACK` back to `"cloud"`;
  - the script's default back to Grafana Cloud's URL, with `DEFAULT_STACK` `"mon"`;
  - the `*.grafana.net)` skip default emptied;
  - the refusal's `exit 1` removed;
  - `_cloud_url()`'s source back to the script's default, which the push cases then read as the node's and fail.

---

### Task 7: The ops watchdog probes the stack that pages

**Files:**
- Modify: `infra/ansible/roles/ops/defaults/main.yml` (`ops_grafana_watchdog_probe_url: "https://zcrypto-mon.zhaow.me/api/health"`; the comment above it re-trued)
- Modify: `infra/ansible/roles/ops/templates/grafana-watchdog.sh.j2` (the header's "healthchecks.io half: probes the Grafana Cloud stack", re-trued: the dead-man service's half, probing the Grafana that pages)
- Modify: `infra/ansible/roles/ops/templates/grafana-watchdog.timer.j2` (`Description=Every-5-minutes Grafana Cloud probe for the mutual watchdog`, re-trued without the vendor)
- Test: `tests/test_grafana_auth.py` (new: `test_the_ops_watchdog_probes_the_stack_that_pages`, which holds the ops default equal to `f"{ga.STACKS[ga.DEFAULT_STACK].url}/api/health"`)

**Interfaces:**
- Consumes: Task 6's `DEFAULT_STACK`; the edge, which passes `/api/health` to Grafana, answered without a login (spec D4; the measured basis's anonymous-surface read); the ops role's unconditional watchdog block (`roles/ops/tasks/main.yml`, the `install the grafana-watchdog pinger` block), which renders under `--tags ops` with no digest; `converge.sh`'s admitted key `ops_grafana_watchdog_probe_url` (`tests/test_converge_sh.py`).
- Produces: R10's ops converge; the clone's check `zcrypto-grafana-watchdog` reading the node's health, whose description ("The ops timer probing Grafana every 5 min …") stays true, so the fixture is not re-fetched.

**What this task decides, where the spec leaves it open:**
- **The probe moves to the node alone; Grafana Cloud is not probed twice over.** D16 calls the re-pointed probe "a second prober off the node", and D22(4) re-points it with Grafana Cloud's receivers. After R10, Grafana Cloud pages only the shadow channel, and its death is read there.

- [ ] **Step 1: Write the failing test.**
- [ ] **Step 2: Run it** — `uv run pytest tests/test_grafana_auth.py -q -p no:cacheprovider`; Expected: the new case fails on Grafana Cloud's URL.
- [ ] **Step 3: The default, the header and the description.**
- [ ] **Step 4: Run the test** — Expected: no failure.
- [ ] **Step 5: The consumers** — `uv run pytest tests/test_infra_shell_templates_render.py tests/test_count_list.py tests/test_converge_sh.py tests/test_grafana_auth.py -q -p no:cacheprovider`, and every file `grep -rl --include='test_*.py' 'grafana-watchdog\|ops/defaults' tests/` names.
- [ ] **Step 6: The commit gate.**
- [ ] **Step 7: Commit** — `feat(infra): the ops watchdog probes the observability node's health, the stack that pages`, with `PROBE_VERDICT` and the trailer.
- [ ] **Step 8: The tree is clean.**
- [ ] **Step 9: Prove the guard** — mutations: the default back to Grafana Cloud's URL; its path changed to `/api/search`. Each is KILLED, and the verdict is recorded by a message-only amend.

---

### Task 8: The node-dark procedure, and the surfaces that name Grafana Cloud as the pager

**Files:**
- Modify: `infra/runbooks/observability.md`:
  - `grafana-cloud-dark` becomes `grafana-dark`, its anchor and heading `grafana-dark — PROCEDURE: while the Grafana that pages is down`, re-pointed per D24.
  - *What you are seeing*: the clone's `zcrypto-grafana-watchdog` check, now probing `https://zcrypto-mon.zhaow.me/api/health`, with its two routes; and the node's own check `zcrypto-mon`, `mon.md#mon-dark`.
  - *What it means*, part 1: the exposure rule is unevaluated where it pages, so the engine's dead-man check and the hand read are its cover.
  - *What it means*, part 2: until the Grafana Cloud leg retires, Grafana Cloud's rules still evaluate and page the shadow channel, which is read for the outage's minutes.
  - *What it means*, part 3, the hole stated plainly: the node and the dead-man node dark together page nothing in the main channel, and Grafana Cloud's `zcrypto-hcio-watchdog` reads `999` in the shadow channel alone.
  - *What to do*: step 1's probe URL; step 2's dead-man read; step 5 gains D20's check after an outage, that a lost nightly `pull complete` line can fire the archive-pull dead-men for a day.
  - *Retire when* re-trued.
  - The page header (lines 3 and 5) and `#zcrypto-hcio-watchdog`'s probe target, its `/fail` route lines and its link are re-trued. The alloy-dark sections' "absent from Grafana Cloud" lines become absent on the stack that paged.
  - The `grafana-cloud-dark` citations in `drills-telemetry.md` are re-pointed in the same commit.
- Modify: `infra/runbooks/mon.md`:
  - `mon-dark`: "The fleet is still watched: Grafana Cloud's rules page the main channel throughout" becomes the shadow channel until the leg retires; Grafana Cloud's `zcrypto-hcio-watchdog` is in the shadow channel and the clone's `zcrypto-grafana-watchdog` in the main channel; steps 2 and 5's reads take `--stack cloud`.
  - `mon-push`: a push naming no stack goes to the node; step 1's line keeps its explicit URL; *What it means* names Grafana Cloud's push as the second.
  - `mon-compare` step 3's re-read takes `--stack cloud` second.
- Modify: `infra/runbooks/hc.md` (`hc-dark`'s "Grafana Cloud's rules page the main channel throughout" and the service's death through Grafana Cloud's `zcrypto-hcio-watchdog`, which now reaches the main channel from the node's copy; `zcrypto-hc-service-down`)
- Modify: `infra/runbooks/engine.md` (`#zcrypto-engine-dark-with-exposure` step 1's stack names after the flip: the ingest-dark read with no `--stack`, the halves on Grafana Cloud with `--stack cloud`)
- Modify: `infra/runbooks/drills-telemetry.md` (drill C′, "Grafana Cloud dark", re-pointed at the Grafana that pages, with its probe override's restore reading the new default; drill C's and the `W` sections' Grafana Cloud lines by the cut below)
- Modify: the other hits of the sweep below in class (a), and `infra/grafana/alerts.yaml`'s summaries or comments where they say Grafana Cloud pages
- Test: none new; the runbook walkers, and `tests/test_infra_alert_rules.py` and `tests/test_ops_daily.py` (the fixture's `Runbook:` anchors, of which none names `grafana-cloud-dark` at this plan's base).

**Interfaces:**
- Consumes: Tasks 6 and 7; D24; the measured W2 and W3 figures in `mon-dark`; the clone's checks `zcrypto-mon` and `zcrypto-grafana-watchdog` (spec 00122 D8).
- Produces: `observability.md#grafana-dark`, the node-dark procedure phase 4 narrows by its Grafana Cloud clause.

**What this task decides, where the spec leaves it open:**
- **The cut between this phase and phase 4.** The sweep is the measured basis's: `git grep -n -i -E 'main channel|shadow channel|grafana cloud' -- infra/runbooks .claude docs/reference/fleet.md docs/reference/fleet-pins.md infra/grafana/alerts.yaml infra/scripts/ops_daily.py`. It printed 107 lines at this plan's base, and Task 2 and Task 5 have re-trued some since. Each hit falls in one of two classes:
  - (a) It says which stack evaluates or pages a rule the reader is working, which channel a stack's page reaches, which URL the watchdog probes, or which stack a tool reads with no `--stack`. It is re-trued here.
  - (b) It is about the Grafana Cloud leg's shipping, its keep-lists, its keep-alive, its retention, a past event, or why a rule's `execErrState` is `OK`. It is left to phase 4 or to history.

  The commit message gives each class's count.
- **The anchor is renamed,** since a heading that names Grafana Cloud over a procedure for the node is false. History (the drill log, archived topics, the specs and plans) keeps the old anchor in its text.
- **A rule summary the sweep changes takes the dual push after the merge** (R10's last step). None is expected: the summaries the measured basis lists (`zcrypto-alloy-dark-hc`, `zcrypto-mon-ingest-dark`, `zcrypto-hcio-watchdog`) describe what reads a series, not where the page goes.

- [ ] **Step 1: Load `zcrypto-refine-rules`.**
- [ ] **Step 2: The sweep**, kept as `.tmp/cutover/task8-sweep`, each hit classed (a) or (b).
- [ ] **Step 3: The procedure, the rename and its citations, and the class (a) lines.**
- [ ] **Step 4: The consumers** — `uv run pytest tests/test_internal_terms_not_operator_visible.py tests/test_runbook_internal_tokens.py tests/test_runbook_triggers.py tests/test_infra_alert_rules.py tests/test_ops_daily.py tests/test_drill_log.py tests/test_code_prose_citations.py -q -p no:cacheprovider`; Expected: no failure, `test_every_runbook_cross_reference_resolves` among them.
- [ ] **Step 5: The commit gate.**
- [ ] **Step 6: Commit** — `docs(runbooks): the node-dark procedure, and the pages that named Grafana Cloud as the pager name the node`, with the trailer.
- [ ] **Step 7: The tree is clean.**

---

### Task 9: The skills take the node as the pager

**Files:**
- Modify: `.claude/skills/zcrypto-grafana-push/SKILL.md`:
  - Step 0's invocation is the node's push, `mon-push` step 1's line, and Grafana Cloud's push is named beside it with `GRAFANA_URL=https://zcrypto2026.grafana.net` and `grafana_sa_token`, its first line reading `skip-groups=zcrypto-mon zcrypto-hc`.
  - The dual-period paragraph: the node's push first, then Grafana Cloud's, from the one checkout.
  - Step 1 and Step 3's `--stack mon` clauses invert: the skipped groups and the node rows are read with no `--stack`, and a shared rule's Grafana Cloud reading takes `--stack cloud`.
  - Step 3's render is replaced, per D9, by a read of each new or changed panel's query by value and a look at the panel.
  - Step 4's prune is unchanged in substance.
  - The `description` reads "to the observability node and, until its leg retires, Grafana Cloud".
- Modify: `.claude/skills/zcrypto-daily-ops/SKILL.md` (the pass reads the node, the stack that pages, and `--stack cloud` reads Grafana Cloud's state; the clauses that name "the cutover" as ahead, its step 1 paragraph on the seven days and the rationalisation row's "a finding for the cutover pull request", re-trued: the comparison's line is still recorded until the table holds one stack, and nothing waits on it)
- Modify: the other skills' lines in class (a) of Task 8's sweep (`.claude/skills/zcrypto-bump-alloy/SKILL.md` line 43, "Grafana Cloud holds no `host="zcrypto-mon"` … series: the two nodes' are read with … `--stack mon`", becomes a read with no stack named), each found by the same sweep over `.claude/`

**Interfaces:**
- Consumes: Tasks 6 to 8.
- Produces: skills true from R10's merge.

- [ ] **Step 1: Load `zcrypto-refine-rules`** and read its *Before you write guidance*; each sentence lands on a ground it names.
- [ ] **Step 2: The edits.**
- [ ] **Step 3: The consumers** — `uv run pytest tests/test_internal_terms_not_operator_visible.py tests/test_daily_ops_skill.py tests/test_guidance_guard.py tests/test_guidance_refs_resolve.py tests/test_grafana_push_sh.py -q -p no:cacheprovider`.
- [ ] **Step 4: The commit gate**, and `infra/scripts/guidance-guard.py`'s measure of the description's growth.
- [ ] **Step 5: Commit** — `claude(skills): the push, the daily pass and the Alloy bump take the observability node as the stack that pages`, with `Ambient grows by N bytes: <reason>` where the description grew, and the trailer; a `claude` commit carrying no other file.
- [ ] **Step 6: The tree is clean.**

Then the third pull request opens over Tasks 6 to 9, once S4 is read and seven days have passed since R3's instant. A different agent reads it, and `merge-pr` merges it immediately before R10, in R10's sitting.

---

## Rollout (attended)

**Operator steps (attended).** Nothing below is an executor step: each reaches the node, Grafana Cloud, Slack, the dead-man service or a fleet host, or decides a venue-facing converge.

- **Conventions.** `W$` is the workstation at the repository root and `H$` a shell on the named host (`ssh hp` for ops, `ssh red`, `ssh zcrypto`, `ssh mon`). `.tmp/cutover/` holds what a later step reads back. It is disposable, so each reading goes into T0217 by the records pull request that follows it.
- **Converges.** Every converge goes through `infra/ansible/scripts/converge.sh` from merged `develop`, which previews, asks for the typed `--limit` and appends its deploy-log line, and is never wrapped in `timeout`. A preview naming anything beyond the files a step names holds that step.
- **Running digests.** A digest a converge is handed is read off its container immediately before (`docker inspect <container> --format '{{.Config.Image}}'`, the `sha256:…` after the `@`, never `.Image`) and matched against `docs/reference/fleet-pins.md`.
- **`KRAKEN`** is `curl -fsS https://status.kraken.com/api/v2/scheduled-maintenances.json | jq .`, read whole and judged by `.claude/rules/fleet-deploys.md`'s test.
- **`AUDIT`** is `uv run python infra/scripts/deploy-log-audit.py maintenance --venue-facing --since "$(cat .tmp/cutover/r0-instant)"`, which must print `rows inside an API-impacting window 0 of …` over the rows this phase appended.
- **The node's API.** `MON_TOKEN="$(uv run python -c 'import sys; sys.path.insert(0, "infra/scripts"); import grafana_auth as g; print(g.token("mon"))')"` is held in the one shell that reads the node's API and is unset after. Its two reads:
  - `rules`: `printf 'Authorization: Bearer %s\n' "$MON_TOKEN" | curl -fsS -H @- https://zcrypto-mon.zhaow.me/api/prometheus/grafana/api/v1/rules`.
  - `silences`: `printf 'Authorization: Bearer %s\n' "$MON_TOKEN" | curl -fsS -H @- https://zcrypto-mon.zhaow.me/api/alertmanager/grafana/api/v2/silences`. Whether the Editor token reads the silences endpoint is unread: the measured basis read it refused only on the Alertmanager status. A `403` makes each silence read the owner's, in the node's UI under Alerting → Silences, its matchers, state and end copied into the same file.

**The hand-over reads, used by every sitting below**, over one stream's `<host>`, `<container>`, `<job>`, its node dead-man `<uid>` and Grafana Cloud's rules that read it. Before PR 3 merges, Grafana Cloud is `grafana-query.py` with no `--stack`; after, `--stack cloud`.

1. **The stream on the node by the rule's own query:** `uv run python infra/scripts/grafana-query.py --stack mon --loki 'sum by (host) (count_over_time({host="<host>", container="<container>", level=~".+"} [6h]))'`; Expected: one row above 0, read once the shipper has logged after its restart.
2. **The shipper's counters on the node**: `uv run python infra/scripts/grafana-query.py --stack mon 'increase(zcrypto_logship_shipped_lines_total{host="<host>", job="<job>"}[15m])' 'increase(zcrypto_logship_dropped_lines_total{host="<host>", job="<job>"}[15m])'`; Expected: above 0, then 0.
3. **The stream gone from Grafana Cloud**, from five minutes after the restart: `--loki 'sum(count_over_time({host="<host>", container="<container>"}[5m]))'`; Expected: `(no series)`.
4. **The node's dead-man inactive, then its silence ended:** `rules | jq -r '.data.groups[].rules[] | select(.uid == "<uid>") | "\(.uid) \(.state) \(.health)"'`; Expected: `<uid> inactive ok`. Then, where the silence's end is still ahead, the owner expires it in the node's UI. Then `silences | jq -c '.[] | select(any(.matchers[]; .name == "__alert_rule_uid__" and .value == "<uid>")) | {id, state: .status.state, endsAt}' | tee .tmp/cutover/silence-<uid>.json`; Expected: `"state":"expired"`, with `endsAt` the instant it ended.
5. **Grafana Cloud's silences:** the owner silences, in Grafana Cloud's UI, the dead-man by `__alert_rule_uid__=<its uid>` and the burst rule by `__alert_rule_uid__=<its uid>`, `host="<host>"` and `container="<container>"`, each ending at [[ROLLOUT: the Grafana Cloud silences' end …]], and copies each silence's id into `.tmp/cutover/cloud-silences`.

**The rollback of a moved stream** is `mon.md#mon-stream-handover`'s: Task 4's commit reverted on a branch and merged; the host converged in its sitting's form, which renders the old file and, on a capture host, restarts capture through the handler; the shipper restarted (the poller by `docker compose up -d`, the engine inside a gap under `engine-procedures.md`'s restart rules); the node's silence set again; Grafana Cloud's silences expired. On `zcrypto` the one file serves both shippers, so the revert returns the capture daemon's stream as well at its restart.

**Preconditions.** On `develop`:
- the records branch `docs/t0217-phase-2-records`, with the drill-log entries `W1` to `W4`, the boundary bullet, T0217's phase-2 state and the `hc` edge's cookieless-`HEAD` route (`/checks/*`, `/cloaked/*`, cookie `sessionid`, its commit `276301e95`);
- R12's pull request (`COMPARISON_FROM = date(2026, 10, 10)`).

**R0. The operands, read once.**
- `git switch develop && git pull --ff-only && git status --porcelain` reads empty.
- `mkdir -p .tmp/cutover`; `date -u +%Y-%m-%dT%H:%M:%SZ | tee .tmp/cutover/r0-instant`.
- `KRAKEN` at planning.
- `uv run python infra/scripts/ops-daily.py report --stack mon --since 24h | tee .tmp/cutover/r0-mon-report`. Its `## Alerts firing` lists the four direct-stream dead-men, firing on the node by design. Every other row there is resolved first, or named in R3's announcement as a page the main channel will take from the node at its policy's repeat interval.

**R1. The differences, if the seven entries count any** (before Task 1's Step 4). For each day Task 1's Step 2 names, `W$ uv run python infra/scripts/grafana-compare.py --day <day> | tee .tmp/cutover/compare-<day>.txt` runs while both stacks still hold that day (Grafana Cloud keeps 14). Each difference line is re-read by `mon.md#mon-compare` step 3 at its instant, on both stacks, and its class is written beside it in the file: [[ROLLOUT: R1's differences — each line's rule, instant and class, or none]]. A run outside a pass counts for no day of the seven; this one reads the lines a pass prints only as a count.

**R2. The node's four silences, before its receivers move** (the owner's ruling of 2026-10-08; spec D22(1)). The owner, signed in on the node, opens each dead-man's silence form at `https://zcrypto-mon.zhaow.me/alerting/silence/new` with the one matcher `__alert_rule_uid__=<uid>`. Each silence ends at its sitting's planned instant: [[ROLLOUT: the four sittings' planned instants on the hand-over day — S1 the poller, S2 the secondary's capture, S3 the primary's an hour after S2, S4 the engine's gap]]. Its comment names the sitting.

| silence | rule | ends at |
|---|---|---|
| 1 | `zcrypto-ops-poller-log-dead` | S1's instant |
| 2 | `zcrypto-capture-log-dead-secondary` | S2's instant |
| 3 | `zcrypto-capture-log-dead-primary` | S3's instant |
| 4 | `zcrypto-engine-log-dead` | S4's instant |

Then `silences | jq -r '.[] | select(.status.state == "active") | "\(.matchers | map("\(.name)=\(.value)") | join(",")) \(.endsAt) \(.id)"' | tee .tmp/cutover/r2-silences`. Expected: four lines, one per uid, each with its end. Nothing else active, unless the owner names it. Rollback: each silence expired in the UI.

**R3. The node pages the main channel** (spec D22(2); after the cutover pull request merges).
1. The announcement goes to the main channel first: from now both stacks page there, duplicates are accepted, and a copy's links name its stack's host.
2. The push skill's Step 2 holds pass:

```
W$ git switch develop && git pull --ff-only && git status --porcelain
W$ git fetch origin develop && git merge-base --is-ancestor origin/develop HEAD && git status --porcelain -- infra/grafana
W$ gh pr list -L 100 --json number,body --jq '.[] | select(.body | test("## Grafana push")) | .number'
```

3. `mon-push` step 2's push runs with the main webhook:

```
W$ GRAFANA_URL=https://zcrypto-mon.zhaow.me GRAFANA_SKIP_RULE_GROUPS= \
     GRAFANA_SLACK_WEBHOOK_URL="$(uv run python -c 'import sys; sys.path.insert(0, "infra/scripts"); from grafana_auth import vault_var; print(vault_var("slack_webhook_url"))')" \
     GRAFANA_SA_TOKEN="$(uv run python -c 'import sys; sys.path.insert(0, "infra/scripts"); import grafana_auth as g; print(g.token("mon"))')" \
     PATH="$PWD/.venv/bin:$PATH" ./infra/scripts/grafana-push.sh
W$ date -u +%Y-%m-%dT%H:%M:%SZ | tee .tmp/cutover/r3-instant
```

Its first line reads `stack=https://zcrypto-mon.zhaow.me` and `skip-groups=<none>`. It prints no `GRAFANA_SLACK_WEBHOOK_URL not set` line, reads the template back byte-identical and reports no orphan. A first line naming another stack is a stop: nothing was sent to the node.

4. The owner, signed in on the node, presses the test of each contact point, `metrics` and `logs`, under Alerting → Contact points. Expected: two test messages in the main channel and none in the shadow channel.
5. `uv run python infra/scripts/ops-daily.py report --stack mon --since 1h` prints no `Rules not evaluating` section.

The instant is [[ROLLOUT: R3's instant — the node's receivers on the main channel, from which its seven days count]]. Rollback (D25): the same push with `vault_var("slack_shadow_webhook_url")`, and the two tests read in the shadow channel.

**R4. One page from the node in the main channel, with working links** (the spec's phase-3 proof after step 2).
1. The proof is the first real page the node sends to the main channel after R3. Grafana Cloud's copy beside it carries `zcrypto2026.grafana.net` links; the node's carries `zcrypto-mon.zhaow.me` links.
2. The owner opens its three links on Slack for macOS: the panel (`/d/…`), the rule (`/alerting/…`) and the silence form (`/alerting/silence/new?…`). Each lands on its page under `https://zcrypto-mon.zhaow.me/`, signed in, and none on `/login?redirectTo=…`. The silence form is closed without saving.
3. The route is the node's edge. The `mon` role's include renders `edge_head_paths: [/d/*, /alerting/*]` with `edge_session_cookie: grafana_session`, which answers a cookieless `HEAD` with `200`. The clone's edge renders its own route over `/checks/*` and `/cloaked/*` with `sessionid`, and a page from the clone's integration is not this proof. Read from the workstation with the page's panel link:
   - `curl -sS -I -o /dev/null -w '%{http_code}\n' '<the panel link>'` reads `200`, the edge's answer to a `HEAD` with no session.
   - `curl -sS -o /dev/null -w '%{http_code} %{redirect_url}\n' '<the panel link>'` reads `302` to the node's `/login`, Grafana's own answer to a `GET` with no session.
4. No node copy of the four silenced dead-men reached the main channel.
5. R4 waits for a page. Until one comes, the hand-over day may still open, and R10 may not.

The reading is [[ROLLOUT: R4's page — its rule, its time and where its three links landed]].

**R-records-1. The node pages the main channel: one pull request.** From `develop`:
- T0217's `## Findings so far` gains R0's instant, R2's four silences (uid, id, end), R3's instant, the two contact-point tests and R4's page.
- Its `ripe_when` becomes the date [[ROLLOUT: the hand-over day …]], the streams' earliest day, with the check `date -u +%F`.
- `uv run python infra/scripts/topics-index.py` re-renders the index.
- `uv run pytest tests/test_open_topics_frontmatter.py tests/test_topics_index.py -q -p no:cacheprovider` passes.
- The commit is `docs(topics): T0217 — the node pages the main channel beside Grafana Cloud, its four direct-stream dead-men silenced to their sittings`.
- The pushes write no deploy-log row.

**R5. The hand-over day, planned and opened** (on [[ROLLOUT: the hand-over day …]], after the box).
- `KRAKEN` at planning.
- The four planned instants are re-read against R2's ends. A day or an instant that moved re-dates its silence in the node's UI first, read back by `silences`.
- The second pull request merges through `merge-pr` before the first converge.
- `git switch develop && git pull --ff-only`.
- The day's announcement in the main channel names the four sittings, the capture gaps and the engine's converge.
- The engine's gap is the one `engine-procedures.md#engine-rung-2-box` step 8 item 6 takes, after S3.
- If S3 cannot finish before the day's last gap that item can use, S4's hand-over is the owner's to rule (Global Constraints).

**R6. S1 — the poller on ops.**
1. `KRAKEN` immediately before.
2. `W$ infra/ansible/scripts/converge.sh site.yml --limit zcrypto-ops --tags ops -e ops_image_digest=sha256:<running-ops>`, the digest read off `zcrypto-ops-liquidations`. The preview names `logship-secrets.env` and the liquidations `compose.yaml` changed (both `no_log`, so the changed-files report is the signal) and nothing else. With the running digest, no `liquidations_decision` is asked.
3. `H$ cd /etc/zcrypto-ops && sudo docker compose up -d`.
4. `sudo docker inspect zcrypto-ops-liquidations --format 'img={{.Config.Image}} restarts={{.RestartCount}} started={{.State.StartedAt}}'` reads the same digest, 0 restarts and a `started` after the converge. A `started` that did not move is a stop, and the recreate is then `sudo docker compose up -d --force-recreate liquidations`, read the same way. The poller's seconds of downtime are a gap in a stream nothing backfills.
5. The hand-over reads over `ops`, `liquidations`, `liquidations_app`, `zcrypto-ops-poller-log-dead`, and Grafana Cloud's `zcrypto-ops-poller-log-dead` and `zcrypto-ops-error-logs`.

**R7. S2 — the secondary's capture daemon.**
1. `KRAKEN` immediately before.
2. `W$ infra/ansible/scripts/converge.sh site.yml --limit zcrypto-red -e capture_image_digest=sha256:<running-capture> -e capture_alloy_digest=sha256:<running-alloy>`. The preview names `logship-secrets.env` and the capture `compose.yaml` changed and nothing else, Alloy's files unchanged. The handler `restart capture service` runs.
3. `zcrypto-capture`'s `StartedAt` moved and `RestartCount` 0; Alloy's `StartedAt` unmoved.
4. The capture gap the restart books is read on the pulled copy by the rollout-image skill's verify-by-outcome.
5. The hand-over reads over `zcrypto-red`, `capture`, `capture_app`, `zcrypto-capture-log-dead-secondary`, and Grafana Cloud's `zcrypto-capture-log-dead-secondary` and `zcrypto-capture-error-logs` scoped to `host="zcrypto-red"`.

**R8. S3 — the primary's capture daemon**, an hour after S2, away from a 4-hourly boundary and from any engine restart.
1. `KRAKEN` immediately before.
2. `W$ infra/ansible/scripts/converge.sh site.yml --limit zcrypto --tags capture -e converge_primary=true -e capture_image_digest=sha256:<running-capture> -e capture_alloy_digest=sha256:<running-alloy>`, never `--skip-tags engine`. The same preview and reads as S2, on `zcrypto-capture`. `zcrypto-engine`'s `StartedAt` is unmoved.
3. `H$ sudo grep -c 'zcrypto-mon.zhaow.me' /opt/zcrypto-capture/logship-secrets.env` reads `1`, a count: the file the engine reads at its next start names the node.
4. The hand-over reads over `zcrypto`, `capture`, `capture_app`, `zcrypto-capture-log-dead-primary`, and Grafana Cloud's `zcrypto-capture-log-dead-primary` and `zcrypto-capture-error-logs` scoped to `host="zcrypto"`.

From here, an engine restart for any reason moves the engine's stream. Such a restart is not taken for it (the owner's ruling), and an unplanned one is `mon.md#mon-stream-handover`'s early case.

**R9. S4 — the engine, at the box's deferred disarm converge** (the owner's ruling of 2026-10-08). This converge is `infra/runbooks/engine-procedures.md#engine-rung-2-box` step 8 item 6 and plan 00122's R14, and nothing else restarts the engine for the hand-over.
1. `KRAKEN` immediately before.
2. Inside the inter-cycle gap, under the procedure's restart rules and the position read it names: `W$ infra/ansible/scripts/converge.sh site.yml --limit zcrypto --tags engine -e converge_primary=true -e engine_image_digest=sha256:<running> -e cache_proxy_image_digest=sha256:<running>`, each digest read off `zcrypto-engine` and `zcrypto-cache-proxy`.
3. The preview names exactly what item 6 reads: `render the engine zcrypto.toml`, the one line `exec_armed = true` → `exec_armed = false`, and `render the engine secrets env file`, `changed` with its diff hidden. `render the engine compose file` is not changed, per Task 4's Step 4. Anything else holds the converge.
4. The procedure's disarm step 3 reads its three reasons, and plan 00122's R14 reads the engine's check moved on the clone.
5. The hand-over reads over `zcrypto`, `engine`, `engine_app`, `zcrypto-engine-log-dead`, and Grafana Cloud's `zcrypto-engine-log-dead` and `zcrypto-engine-error-logs`.

The four sittings' readings are [[ROLLOUT: S1 to S4 — each stream's readings on the node, its silence's ended instant, and Grafana Cloud's silences' ids]].

**R10. Grafana Cloud's receivers move last, the probe moves to the node, and the defaults flip** (spec D22(4)).
- **Preconditions:** S1 to S4 read, R4's page seen, and R3's instant plus seven days passed with the node's receivers on the main channel throughout. The announcement in the main channel says Grafana Cloud's copies leave it.
- **The merge:** the third pull request merges through `merge-pr`, then `git switch develop && git pull --ff-only`.
- **Grafana Cloud's receivers to the shadow channel.** The push skill's Step 2 holds pass, then:

```
W$ GRAFANA_URL=https://zcrypto2026.grafana.net \
     GRAFANA_SLACK_WEBHOOK_URL="$(uv run python -c 'import sys; sys.path.insert(0, "infra/scripts"); from grafana_auth import vault_var; print(vault_var("slack_shadow_webhook_url"))')" \
     GRAFANA_SA_TOKEN="$(uv run python -c 'import sys; sys.path.insert(0, "infra/scripts"); import grafana_auth as g; print(g.token("cloud"))')" \
     PATH="$PWD/.venv/bin:$PATH" ./infra/scripts/grafana-push.sh
```

  Its first line reads `stack=https://zcrypto2026.grafana.net` and `skip-groups=zcrypto-mon zcrypto-hc`, and it reports `ORPHAN (live, of skipped group …)` for none. The owner presses the test of Grafana Cloud's `metrics` and `logs` contact points in Grafana Cloud's UI: two test messages in the shadow channel, none in the main channel. Rollback: the same push with `vault_var("slack_webhook_url")`.
- **The probe:**
  1. `KRAKEN` immediately before.
  2. `W$ infra/ansible/scripts/converge.sh site.yml --limit zcrypto-ops --tags ops`. The preview names `/usr/local/sbin/zcrypto-grafana-watchdog` and the watchdog timer unit changed and nothing else.
  3. `H$ sudo grep -c 'zcrypto-mon.zhaow.me/api/health' /usr/local/sbin/zcrypto-grafana-watchdog` reads `1`, a count: the script carries a ping URL and is never printed.
  4. `H$ sudo systemctl start zcrypto-grafana-watchdog.service && sudo journalctl -u zcrypto-grafana-watchdog.service -n 5 --no-pager -o cat` shows no `curl:` line.
  5. After the next tick, `W$ uv run python infra/scripts/grafana-query.py 'hc_check_up{name="zcrypto-grafana-watchdog"}'` reads `1`: the clone's check is green against the node.

  Rollback: `converge.sh site.yml --limit zcrypto-ops --tags ops -e ops_grafana_watchdog_probe_url=https://zcrypto2026.grafana.net/api/health` until Task 7's revert merges.
- **The daily pass reads the node.**
  - `W$ uv run python -c 'import sys; sys.path.insert(0, "infra/scripts"); import grafana_auth as g; print(g.DEFAULT_STACK, g.GRAFANA_URL)'` reads `mon https://zcrypto-mon.zhaow.me`.
  - `W$ uv run python infra/scripts/ops-daily.py report --since 1h` prints no `## Sources that could not be read` naming a Grafana source, and its `## Alerts firing` equals `--stack mon`'s.
  - Rollback: Task 6's commit reverted.
- **The dual push:** where Task 8 changed `infra/grafana/alerts.yaml`'s text, the dual push of Task 9's skill follows, the node's first.

The day is [[ROLLOUT: R10's day — Grafana Cloud's receivers moved to the shadow channel]].

**R-records-2. The cutover's records: one pull request.** From `develop`:
- The deploy-log rows of R6 to R10.
- `docs/reference/fleet-pins.md`'s `since` cells for the containers the sittings restarted: the liquidations poller, both capture daemons, and the engine, which plan 00122's records may already carry from the same converge.
- `docs/reference/fleet.md`'s Services and Telemetry labels: the three direct shippers push to the node's Loki as `logship`, the node pages the main channel, Grafana Cloud pages the shadow channel, and the ops watchdog probes the node.
- T0217:
  - `## Findings so far` gains each sitting's readings and the four silences as read back, each uid with its `expired` state and the instant it ended. They come from `.tmp/cutover/silence-<uid>.json`, read in the sitting, since how long the node lists an expired silence is unread.
  - It also gains Grafana Cloud's silences' ids and ends, and R10's readings.
  - `## Done so far` gains this phase: the plan, the three pull requests, R3, the four sittings and R10.
  - `## Suggested next steps` is cut to phase 4.
  - `status: partial` stays.
  - `ripe_when` becomes the date [[ROLLOUT: R10's day …]] plus seven days, retirement's earliest day under D23, the check `date -u +%F`. The gate's second half, nothing in the shadow channel that the node did not also page, is named in the next steps.
- `uv run python infra/scripts/topics-index.py`.
- `AUDIT`, its count 0.
- `uv run pytest tests/test_deploy_log.py tests/test_deploy_log_audit.py tests/test_fleet_contracts.py tests/test_pins_converged.py tests/test_open_topics_frontmatter.py tests/test_topics_index.py -q -p no:cacheprovider`.
- The commit is `chore(fleet): the observability node pages the main channel, the direct-shipped streams ship to it, and Grafana Cloud pages the shadow channel`, its message carrying every slot's reading, with the trailer.

## Resolution

It settles what the spec left to this phase:
- the cutover pull request is the first of three, and its gate is Task 1's reads;
- the engine's hand-over is the box's deferred disarm converge, shared with plan 00122's R14, the owner's ruling;
- the node's four silences end at their sittings and are read back, the owner's ruling;
- Grafana Cloud's silences are scoped to the moved stream and outlast retirement's start;
- the guards on Grafana Cloud's logship token move with the templates;
- `grafana-cloud-dark` becomes `grafana-dark`;
- the line between the operator surfaces this phase re-trues and phase 4's.

It does not deliver phase 4, which takes from this plan:
- `logship_loki_token`, read by no role after Task 4, free to leave the vault with the other Grafana Cloud values;
- Grafana Cloud's silences, deleted with its rules;
- the shadow channel's read for retirement's gate;
- `observability.md#grafana-dark`'s clause on Grafana Cloud's shadow-channel pages, and the hole it states while both nodes are dark, which that phase's plan answers or carries;
- the class (b) lines of Task 8's sweep;
- the skills' dual-period clauses, `GRAFANA_SKIP_RULE_GROUPS`, the stack table's second row and `mon.md`'s `mon-compare`, `mon-push` dual wording and `mon-stream-handover`, each of which retires with the table.

## Slots the rollout fills

- `[[ROLLOUT: the gate's day — the seventh consecutive journal entry from 2026-10-10 whose compare line reads 0 differences or differences the pull request explains]]` (Task 1) — Task 1's Step 2, into T0217 and the cutover pull request's body.
- `[[ROLLOUT: R1's differences — each line's rule, instant and class, or none]]` (R1; Task 1) — R1's files, into Task 1's bullet.
- `[[ROLLOUT: the hand-over day — the box's deferred disarm converge's day, Mon 2026-11-02 or a week later under the box's slip rule]]` (Global Constraints; Task 5; R5; R-records-1) — the box's own rule at its close.
- `[[ROLLOUT: the four sittings' planned instants on the hand-over day — S1 the poller, S2 the secondary's capture, S3 the primary's an hour after S2, S4 the engine's gap]]` (R2; R5) — set at R2, re-dated at R5 if the day moved.
- `[[ROLLOUT: R3's instant — the node's receivers on the main channel, from which its seven days count]]` (R3; R10) — into R-records-1.
- `[[ROLLOUT: R4's page — its rule, its time and where its three links landed]]` (R4) — into R-records-1.
- `[[ROLLOUT: the Grafana Cloud silences' end — a day past retirement's planned start]]` (Global Constraints; the hand-over reads) — set in S1, carried by S2 to S4.
- `[[ROLLOUT: S1 to S4 — each stream's readings on the node, its silence's ended instant, and Grafana Cloud's silences' ids]]` (R6 to R9) — into R-records-2.
- `[[ROLLOUT: R10's day — Grafana Cloud's receivers moved to the shadow channel]]` (R10; R-records-2) — T0217's `ripe_when`, plus seven days.
