# The observability node, phase 3: the node pages the main channel, the direct-shipped streams move to it one sitting each, and Grafana Cloud's receivers move last — implementation plan

> Every value a rollout reading decides is a marked slot, `ROLLOUT:` inside double square brackets, listed at the end.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Paging moves from Grafana Cloud to the observability node `zcrypto-mon` in the spec's order. Once the gate holds, the node's four direct-stream dead-men are silenced and its two contact points move to the main channel, so both stacks page there. After rung 2's box, each direct-shipped log stream moves to the node's Loki in a sitting of its own, the engine's at the box's deferred disarm converge. Once every stream has moved and the node has paged the main channel for seven days, Grafana Cloud's receivers move to the shadow channel, the ops watchdog probes the node, and the tools' default stack becomes the node. Grafana Cloud keeps evaluating every shared rule until phase 4 retires its leg.

**Architecture:** Nine build tasks in three pull requests, with attended runsheets between them and two records pull requests. The first pull request is the cutover pull request the spec names: the gate, read from the tree and the ops journal and recorded (Task 1); the operator surfaces that say the node pages the shadow channel alone or carries its webhook, or that the comparison still gates the cutover (Task 2); and the push skill's one sentence on the node's webhook, with the daily-ops skill's comparison clauses (Task 3). The node's silences and its push to the main webhook follow. The second pull request merges on the hand-over day, after the box. It points both logship templates at the node's `logship` user and moves the guards that read Grafana Cloud's logship token, so the capture and ops compose files change by one comment line and the engine's renders byte-identical (Task 4). It also re-trues the direct-ship surfaces and adds the hand-over procedure (Task 5). The four sittings of that day follow. The third pull request flips the tools' default stack and the push script's default (Task 6), points the ops watchdog's probe at the node (Task 7), turns `grafana-cloud-dark` into the node-dark procedure and re-trues the surfaces that name Grafana Cloud as the pager (Task 8), and takes the skills to the node (Task 9). Grafana Cloud's push to the shadow webhook and the ops converge then follow.

**Tech Stack:** Grafana OSS on the node and Grafana Cloud, `infra/scripts/grafana-push.sh`, `grafana_auth.py`'s stack table, `grafana-query.py`, `ops_daily.py` and `grafana-compare.py`; Ansible (ansible-core 2.21, the `capture`, `ops`, `engine` and `mon` roles) through `infra/ansible/scripts/converge.sh`; the application log shipper `cli/logging/ship.py`, unchanged; pytest; `infra/scripts/mutate-probe.sh` for guard verdicts; Python 3.14 through `uv run`.

**Spec:** `docs/specs/00121-self-hosted-observability-design.md`, phase 3. It covers D19 (the gate), D22 (the sequence and its gate), D24 (the node-dark procedure), D25 (the rollback), D16's cutover clause (the ops watchdog's probe), D9's render clause, D20's ingest-dark and lost-lines proofs, the "Phase 3, the cutover" lines of "What changes in the repo, by phase" and "Proofs each phase owes", the invariants, and "What stays manual" (the silences in each stack's UI). Two owner rulings of 2026-10-08 settle the two points the spec left to this plan: the engine's hand-over converge and the dead-men's silences (Global Constraints); the owner's ruling of 2026-10-09 makes that converge the November nautilus bump's engine re-pin as well. The measured basis this plan reads is the spec's, with phase 2's amendments on the records branch `docs/t0217-phase-2-records` (the log fan-out, the fleet on the node, the boundary reading). The plan's base is `develop` at `888d1d89e`. The records branch is unmerged and still moving, so every reading this plan gives at its base was taken on `develop` at `888d1d89e` alone, and the records reach `develop` before Task 1 (its Step 1). Phase 1 is `docs/plans/00121-mon-node.md` and phase 2 is `docs/plans/00121-dual-shipping.md`. Spec 00122's plan `docs/plans/00122-self-hosted-dead-man.md` shares this plan's engine converge (its R14). Phase 4 takes a plan of its own under the same serial. Every pull request's change-index row is keyed `00121` with no `iter`, as phases 1 and 2 were.

## Global Constraints

- **The gate comes first** (spec D19, D22). No receiver moves, and the cutover pull request does not open, until Task 1 has read all three parts of the gate. First, seven consecutive daily-pass journal entries from 2026-10-10, each carrying a `compare:` line that reads `0 differences` or whose differences that pull request explains. Second, drill-log entries `W1` to `W4`, each `pass`. Third, the measured-basis bullet with the boundary reading. A difference is fixed or explained in that pull request; one that is neither holds it for the owner.
- **The sequence is D22's.**
  - The node's four direct-stream dead-men are silenced before the node's two contact points move.
  - The node pages the main channel before any stream moves, which is D25's reason: a moved stream returns only by a revert and a restart.
  - The streams move after the box only, one sitting each. Their template change merges on the hand-over day, after the box closes.
  - Grafana Cloud's receivers move last: after every stream has moved and seven days after the node's receivers moved, with the probe re-pointed and the defaults flipped in the same step.
  - The node's three direct-stream burst rules (`zcrypto-engine-error-logs`, `zcrypto-capture-error-logs`, `zcrypto-ops-error-logs`) are blind on the node until their stream moves and take no silence there. Grafana Cloud's copies keep paging.
- **Through the box, Grafana Cloud is untouched** (the invariant). Its rules, receivers, watchdog URL and vault values stay as they are, and nothing from this work converges `zcrypto`. R2 to R4 touch the node alone and may run inside the box. The box runs Mon 2026-10-05 to Sun 2026-11-01. It was entered on its first day, so its pre-entry slip clause is spent, and it is never extended (`docs/research/14.phase6-decisions.md`'s time-box ruling).
- **One converge for the engine (the owner's rulings of 2026-10-08 and 2026-10-09).** The engine's log-stream hand-over, spec 00122's move of the engine's dead-man check and the November nautilus bump's engine re-pin happen in one converge: the box's deferred disarm converge, inside its inter-cycle gap after the box closes (`infra/runbooks/engine-procedures.md#engine-rung-2-box` step 8 item 6, which is plan 00122's R14), passing the bump's engine digest, whose own `zcrypto engine preflight` passes, and no `engine_preflight_override` (R9). It is also the first engine converge from a `develop` that carries the rung-3 loop, which renders the comment lines plan 00092's R2 preview reads as already rendered. The engine's hand-over task names that converge, and nothing else restarts the engine for it. Three things follow:
  - The primary's capture converge renders `/opt/zcrypto-capture/logship-secrets.env`, the file the engine reads at start. It runs earlier on the same day, so the four sittings fall on [[ROLLOUT: the hand-over day — the box's deferred disarm converge's day, Mon 2026-11-02 as that item names it]], the engine's last.
  - The engine's compose template renders byte-identical (Task 4), so the converge's preview stays the one item 6 reads, its compose line the re-pin's digest alone, which Task 5 writes into item 6.
  - If the primary's capture sitting cannot finish before the day's last gap that item can use, the engine's hand-over stops and goes to the owner. No other restart is taken in its place.
- **Silences dated to their sitting (the owner's ruling of 2026-10-08).** Each of the node's four direct-stream dead-men takes a silence that ends at its own sitting's planned finish, after that sitting's read 4, since the dead-man fires on the node until its stream arrives: `zcrypto-ops-poller-log-dead` at S1, `zcrypto-capture-log-dead-secondary` at S2, `zcrypto-capture-log-dead-primary` at S3, `zcrypto-engine-log-dead` at S4.
  - The silences are set in the node's UI before the cutover pull request merges, so before `mon-push` step 2 carries the main webhook and the node pages the main channel (R2).
  - At the hand-over, each is read back through the node's Alertmanager API and the instant it ended is recorded (R6 to R9, then R-records-2), so no silence outlives its stream.
  - A sitting that moves re-dates its silence's end in the node's UI before the old end passes, read back and kept by R2's appended read-back.
  - A sitting that runs past its silence's end takes that dead-man's page from the node in the main channel. The page is read as the overrun, not as a fault.
  - A rebuild of the node between R2 and S4 takes spec D22's amendment of 2026-10-08 over the rows of R2's table whose sitting has not run, each set again with its matcher and its end as last set or re-dated, which R2's file holds, and read back by R2's read-back. Task 2 writes that re-set into drill W3's *Induce*, the rebuild procedure `mon.md#mon-dark` step 4 sends a lost node through, ahead of its push step; a rebuild between R2 and the cutover pull request's merge takes the re-set from this bullet, that W3 not yet on `develop`.
- **Grafana Cloud's silences.** At each hand-over, Grafana Cloud's rules that read the moved stream are silenced in Grafana Cloud's UI (D22(3)), scoped to that stream. The dead-man is matched by `__alert_rule_uid__`. The burst rule is matched by its `__alert_rule_uid__` plus the stream's `host` and `container`, so its instances on a host or container not yet moved still page. Every matcher is an equality. Each ends at [[ROLLOUT: the Grafana Cloud silences' end — the instant spec D25's amendment of 2026-10-08 names]]: retirement's planned start, 00:00 UTC on R10's day plus three, the first UTC day on which D23's amendment of 2026-10-08, counting two days from Grafana Cloud's push at R10, allows retirement whatever that push's hour. Retirement's first act, the deletion of Grafana Cloud's rules by uid, falls inside that end, between D23's gate opening at R10's push instant plus two days and the end, so a later start of the rest of retirement lapses no silence and owes no re-date (spec D23's amendment of 2026-10-08). S1 sets it against R10's planned day, which R5 sets. Whenever R10's planned day moves, each end is re-dated in Grafana Cloud's UI before it passes (spec D25's amendment of 2026-10-08), by the next step R-records-1 writes into T0217, read from the hand-over day on, when T0217's date trigger has fired; R10 reads each end against its actual day and re-dates what a slip missed; `cloud silences` is the read-back of each setting and each re-date. The reason: after its receivers move, a dead-man Grafana Cloud fires reaches the shadow channel, and retirement's gate reads that channel for pages the node did not also send, the fleet's rules' own pages alone (D23 and its amendments of 2026-10-08): a page Grafana Cloud raises on its own evaluation error, on a rule whose `execErrState` is `Alerting`, does not count, and a dead-man's page on a moved stream does. From R-records-2 on, T0217's next steps carry that end.
- **The capture pair are restarted attended, one host at a time** (`.claude/rules/fleet-deploys.md`; `infra/runbooks/capture-daemon.md` step 4). The secondary goes first and the primary an hour after the deploy-log row of the secondary's capture converge (R8). The secondary's form is `-e capture_image_digest=<running> -e capture_alloy_digest=<running>`. The primary's is `--tags capture -e converge_primary=true` with the same two digests, never `--skip-tags engine` and never un-tagged. Both are the forms the dead-man cutover sitting ran on 2026-10-08 (plan 00122's R12). Each carries the Alloy digest, with which the capture role copies its `config.alloy` over a deployed copy that differs from the repo's and reloads Alloy, a change `.claude/skills/zcrypto-rollout-image/SKILL.md` ships by the bump-alloy skill's `--tags alloy` form. So each sitting takes the Alloy read first, the host's deployed copy against the repo's, `H$ sudo sha256sum /etc/zcrypto-capture/alloy/conf/config.alloy` against `W$ sha256sum infra/ansible/roles/capture/files/config.alloy`, and where the two differ runs that form before the capture converge, with its reads (`.claude/skills/zcrypto-bump-alloy/SKILL.md`, *The capture secondary, then the primary*): `--limit zcrypto-red --tags alloy -e capture_alloy_digest=<alloy_image_digest>` on the secondary, `--limit zcrypto --tags alloy -e converge_primary=true -e capture_alloy_digest=<alloy_image_digest>` on the primary. The two then read equal, and the capture converge's preview names no Alloy file. On the hand-over day they differ unless a converge has landed the file by then: the capture keep regex changed on `develop` by merge `5b75499a7`, after both hosts' converges of 2026-10-08. The capture restart is the converge's own `restart capture service` handler, which runs because Task 4 changes the rendered compose file. If the capture compose render reads `changed=false`, the restart is `sudo systemctl restart zcrypto-capture` by hand, in the same sitting.
- **The engine converges only inside the inter-cycle gap that `site.yml` computes from the boundary cycle's journal, under `infra/runbooks/engine-procedures.md`'s restart rules.** `-e '{"engine_window_override": …}'` is never passed without the owner's explicit approval, and a failed boundary is never retried.
- **`KRAKEN`, the whole-feed read of `https://status.kraken.com/api/v2/scheduled-maintenances.json`, is never piped through `head` or `tail`.** It is taken at planning and again immediately before every converge of `zcrypto-ops`, `zcrypto-red` and `zcrypto`. An empty or truncated feed is never evidence the window is clear. `zcrypto-mon` speaks to no venue, and its pushes and silences owe no read (`.claude/rules/fleet-deploys.md`; the invariant).
- **Each step's rollback stands beside it** (D25):
  - A receiver move is undone by one push per stack with the earlier webhook. Until a stream has moved, that is the whole rollback. From the first hand-over on, a moved stream's dead-man and burst rule page from the node alone, Grafana Cloud holding none of its lines and its copies being silenced, so the node's receivers leave the main channel only after the next bullet has returned every moved stream. That order binds Task 2's `mon-push` step 2, Task 5's `mon-stream-handover` *Rollback*, R3's and R10's rollbacks, and the probe's and the defaults' below.
  - A moved stream returns only with every other stream already moved, so no single-stream rollback exists: the capture template serves both capture daemons and the engine, and the rollback is Task 4's commit reverted on a branch and merged, after which each host's next render returns its logship file to Grafana Cloud whichever stream was meant. Each stream already moved then takes its sitting again: its host converged in its hand-over form (on a capture host the handler restarts capture), its shipper restarted (the poller by `docker compose up -d`, the engine inside a gap under `engine-procedures.md`'s restart rules), the node's silence on its dead-man set again, and Grafana Cloud's two silences on it expired. On `zcrypto` the one file serves both shippers, so the primary's capture converge returns the engine's stream too at the engine's next start. The streams return to a Grafana Cloud whose receivers page the main channel: after R10 this rollback starts with R10's receiver rollback, Grafana Cloud's push with `slack_webhook_url`.
  - The probe's re-point is undone by an ops converge with the admitted key `-e ops_grafana_watchdog_probe_url=https://zcrypto2026.grafana.net/api/health` until a revert merges.
  - The default flip and the probe are undone together, by one pull request reverting Tasks 6 to 9, each task's commit by a revert commit of its own: Task 7's test holds the probe to the default stack, and Tasks 8 and 9 write the node as the stack a read with no `--stack` reaches (`engine.md`'s exposure step, `mon-push` and the skills' reads among them) and Grafana Cloud as paging the shadow channel. An ops converge then renders the reverted probe on the host.
  - The probe and the default stack follow the stack that pages the main channel. Before Grafana Cloud's push at R10 that revert runs alone (R10). After it, the revert, and the override until the revert merges, run only after R10's receiver rollback has put Grafana Cloud's receivers back on the main channel. A read that fails on the node's default after R10 fails the same with `--stack mon`, so it is the node's to repair and is never answered by the revert.
- **Every push goes through `.claude/skills/zcrypto-grafana-push/SKILL.md`.** It starts from merged `develop` in a checkout that passes the skill's Step 2, after its open-PR hold. The node's push takes `infra/runbooks/mon.md#mon-push`'s form, and a push that moves a stack's contact points carries that stack's webhook in `GRAFANA_SLACK_WEBHOOK_URL`.
- **No secret appears in a command line, a log, a diff or a plan step, and no task prints one.**
  - A webhook or token reaches a command as an environment value read through `grafana_auth`, and a token reaches `curl` as a header on stdin (`-H @-`).
  - No container's environment is printed: a restart is proven by `.State.StartedAt` and `.RestartCount` alone.
  - A rendered file that carries a ping URL or a credential (the watchdog script, `logship-secrets.env`, `engine.env`) is read with `grep -c` for a host name and never printed.
  - No executor decrypts, prints or generates a vault value, and `ansible-inventory --host`, `--list` and `--graph --vars` are never run.
- **No executor step reaches a host, a venue, either Grafana, Slack, the dead-man service or the Linode Cloud Manager.** Every such step is an operator step, marked attended, with `W$` the workstation and `H$` the host.
- `infra/ansible/scripts/converge.sh` is never wrapped in `timeout`.
- No operator-read surface carries `Phase <N>`, `T<NNNN>`, `spec <NNNNN>` or `D<N>`; the surfaces are the runbook pages, the rule file's text, the Slack template, the skills and the healthchecks fixture's descriptions. Where provenance is wanted, it goes in an adjacent code comment. A runbook page carries no plan task number either (`tests/test_code_prose_citations.py`), so a form or a rollback of these Global Constraints that a page takes, the capture-pair forms among them, is worded there without one.
- A comment or docstring carries a count of another file's contents only where a test holds that count.
- **A guard change records its `infra/scripts/mutate-probe.sh` verdicts in a commit of its own, right after the commit that makes it.**
  - The verdicts are earned after that commit exists, since the script refuses a dirty tree, and are never written by an amend (the implementer contract): the probes' commit changes no file (`git commit --allow-empty`), is a `test` commit of the proven commit's scope, and its message names `infra/scripts/mutate-probe.sh` and the proven commit's hash, then carries each probe's verdict line.
  - No entry of `infra/scripts/count-list.sh` counts a stack, a channel, a contact point, a webhook, `DEFAULT_STACK` or `COMPARISON_FROM` (read at this plan's base over its 48 entries, `grep -cE '^\s+emit "' infra/scripts/count-list.sh`), so no count moves in this phase.
- **The pager sweep** is this plan's own read, `git grep -n -i -E 'main channel|shadow channel|\bcloud\b' -- infra/runbooks .claude docs/reference/fleet.md docs/reference/fleet-pins.md infra/grafana/alerts.yaml infra/scripts/ops_daily.py`, which printed 135 lines at this plan's base. `\bcloud\b` takes a line that says "Cloud" alone beside a read with no `--stack`, which Task 6's flip moves to the node without a word changing. Task 8 runs it outside `.claude/` and Task 9 under it. Each hit falls in one of two classes:
  - (a) It says which stack evaluates or pages a rule the reader is working, which channel a stack's page reaches, which URL the watchdog probes, or which stack a read with no `--stack` means. It is re-trued in the task that makes it false: a read that means Grafana Cloud takes `--stack cloud`, and one that means the stack that pages stays as it is.
  - (b) It is about the Grafana Cloud leg's shipping, its keep-lists, its keep-alive, its retention, a past event, or why a rule's `execErrState` is `OK`, or it names no Grafana stack (the Linode Cloud Manager, its Cloud Firewall). It is left to phase 4 or to history.
  - At this plan's base the hits that carry a read with no `--stack` are `drills-telemetry.md` lines 535, 606, 632 and 634, `engine-procedures.md` 388, `hc.md` 31, 51 and 144, `mon.md` 71, 98 and 101, `observability.md` 377, the push skill's 38 and the rollout-image skill's 107, with the bump-alloy skill's 205 and 215, whose reads sit in the list under 205 and in 215's words. Each is classed by what its read means.
- **Every commit is green over its changed files' consumers, never the full suite locally, which is CI's.** `CONSUMERS <paths>` is `(set -o pipefail; mkdir -p .tmp && infra/scripts/consumers.sh <paths> | tee .tmp/consumers.out | grep -E '^tests/test_[^/]+\.py$' | sort -u | xargs -r uv run pytest -q -p no:cacheprovider)`, the implementer contract's reader list run whole, its `<paths>` the files the commit changes (`git diff --name-only HEAD`) and any a step adds; with no path `consumers.sh` exits 2, and the pipeline fails with it. Every commit that changes a file runs it beside the tests its task's consumer step names, and each path whose block in `.tmp/consumers.out` reads `# (none` is named in the task's report.
  - A task that edits a page under `infra/runbooks/` also runs `WALKERS`, the tests that read every top-level page there: `uv run pytest tests/test_internal_terms_not_operator_visible.py tests/test_runbook_internal_tokens.py tests/test_runbook_triggers.py tests/test_infra_alert_rules.py tests/test_ops_daily.py tests/test_guidance_guard.py tests/test_count_list.py tests/test_guidance_refs_resolve.py tests/test_code_prose_citations.py -q -p no:cacheprovider`. `tests/test_infra_alert_rules.py` holds `test_every_runbook_cross_reference_resolves`, `tests/test_ops_daily.py` classifies every runbook command, `tests/test_guidance_guard.py` and `tests/test_count_list.py` read each page's universals and count names, `tests/test_guidance_refs_resolve.py` resolves each guidance path a page cites, and `tests/test_code_prose_citations.py` refuses a page's plan task number that carries no serial. A test that reads one page by name runs beside them in the task that edits that page: `tests/test_engine_draftplan.py` reads `engine-procedures.md`'s `engine-rung-2-box` section.
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
  - Task 2: `mon-push` step 2, where the node's webhook is the main channel's, with its rollback; `mon-secrets` step 1; `mon-patch-pass` step 6; `zcrypto-mon-reboot-pending`; `zcrypto-mon-grafana-error-logs`; `mon-dark`'s *What you are seeing*; `zcrypto-mon-ingest-dark` step 1; and the clauses that hold the cutover ahead, false from the cutover pull request's merge: `mon-compare`'s *What it means* last sentence and steps 2 and 4, and `mon-dark`'s *What it means* clause on the seven days.
  - Task 5: a new `mon-stream-handover` procedure; `mon-secrets` step 4; `mon-compare`'s clause on the seven direct-stream rules.
  - Task 8: `mon-dark`, `mon-push` step 1 and `mon-compare` step 3 after the flip; the planned stops of the node's Grafana, its edge or the node, and the header's sentence on a converge of the node that takes Grafana down.
- `infra/runbooks/hc.md`: the header and the sections whose sentences say the node's `zcrypto-hc` group or its Alloy-dark rule pages the shadow channel (Task 2); `hc-dark` and `zcrypto-hc-service-down` once Grafana Cloud pages the shadow channel, and `hc-keys` step 5's announcement (Task 8).
- `infra/runbooks/engine.md`: `#zcrypto-engine-dark-with-exposure` step 1 gains the read of `zcrypto-mon-ingest-dark` first (Task 2), with its stack names re-trued after the flip (Task 8); `#zcrypto-engine-log-dead`'s early case, step 4 and step 6 (Task 5).
- `infra/runbooks/drills-telemetry.md`: the `W1` to `W4` sections' channel sentences, drill W3's push step, the silence re-set ahead of it and its two clauses on the comparison's count (Task 2); drills C and C′, the sections' Grafana Cloud lines once the node pages alone, and the W1 to W3 announcements of the watchdog's page (Task 8).
- `infra/runbooks/engine-procedures.md`: step 8 item 6 names the hand-over the deferred disarm converge carries (Task 5).
- `infra/runbooks/observability.md`: the direct-ship sections, by heading `zcrypto-logship`, `zcrypto-capture-log-dead` and `zcrypto-ops-log-plane` (Task 5); `grafana-cloud-dark` becomes `grafana-dark`, the node-dark procedure, with `#zcrypto-hcio-watchdog`, the header and the alloy-dark sections re-trued (Task 8).
- `infra/runbooks/ops-node.md`: the keep-alive section's link to `grafana-cloud-dark` and its sentence on what pages a dark Grafana Cloud (Task 8).
- The other operator pages whose lines the pager sweep classes (a), and `infra/grafana/alerts.yaml`'s text where it says Grafana Cloud pages (Task 8).
- `docs/open-topics/T0085-final-pre-golive-steps.md`: the two Slack webhook entries (Task 2); the ingest pairs' entry on the `logship` password and the recreate list's logship entry (Task 5).
- `README.md`, `cli/__main__.py` and `infra/docker/Dockerfile`: the `--ship-logs` help and comment's destination; `infra/grafana/alerts.yaml`: the comment on the capture daemon's direct push (Task 5).
- `infra/ansible/group_vars/observed/vars.yml`: `mon_ingest_logship_user` (Task 4).
- The logship and compose files (Task 4):
  - `infra/ansible/roles/capture/templates/logship-secrets.env.j2` and `infra/ansible/roles/ops/templates/logship-secrets.env.j2`: the three `ZCRYPTO_LOKI_*` lines and their headers.
  - `roles/capture/tasks/main.yml` and `roles/ops/tasks/main.yml`: the render tasks' guards and the comments that name the old token.
  - `roles/capture/templates/compose.yaml.j2`, `roles/ops/templates/compose.yaml.j2` and `roles/engine/templates/compose.yaml.j2`: the guards, plus the capture and ops comment lines that name the token.
  - `infra/ops/README.md`: the guard's name (Task 4); the poller's direct-ship destination (Task 5).
- `infra/scripts/grafana-compare.py`: the comment on the seven direct-shipped rules (Task 5).
- `infra/scripts/ops_daily.py`: the comment above the `## Comparison` section (Task 2).
- The default flip (Task 6): `infra/scripts/grafana_auth.py` (`DEFAULT_STACK`); `infra/scripts/grafana-push.sh` (`GRAFANA_URL`'s default, the header's two paragraphs, the render paragraph and the comment above the refusal); `infra/grafana/alerts.yaml` (the comments over the two node-only groups); `infra/nas/README.md` (its push section's stack and token).
- The ops watchdog (Task 7): `infra/ansible/roles/ops/defaults/main.yml` (`ops_grafana_watchdog_probe_url`, and the keep-alive's comment below it); `roles/ops/templates/grafana-watchdog.sh.j2` (the header); `roles/ops/templates/grafana-watchdog.service.j2` and `grafana-watchdog.timer.j2` (the two descriptions).
- `.claude/skills/zcrypto-grafana-push/SKILL.md`: line 20's webhook sentence (Task 3); Step 0, Steps 1, 3 and 4 and the description after the flip (Task 9). `.claude/skills/zcrypto-daily-ops/SKILL.md`: the comparison's clauses that hold the cutover ahead (Task 3); the stack the pass reads (Task 9). The other skills the pager sweep names (Task 9).
- Tests:
  - `tests/test_infra_compose_templates.py`: each logship guard's whole branch under the new name, the render tasks' `when:`, the logship files' literal lines, no role reading Grafana Cloud's logship token, and the module comment's guard name (Task 4).
  - `tests/test_infra_mon_role.py`: the group vars' logship user (Task 4).
  - `tests/test_infra_converge_guards.py`: one comment (Task 4).
  - `tests/test_grafana_auth.py`, `tests/test_grafana_query.py`, `tests/test_ops_daily.py` and `tests/test_grafana_push_sh.py`: the default stack (Task 6).
  - `tests/test_grafana_auth.py`: the probe held to the default stack (Task 7).
- The records pull requests, not a task's: `docs/reference/deploy-log.jsonl`, `fleet-pins.md`'s `since` cells and the engine's re-pinned row, and `fleet.md`.

## Review Focus

Six classes, each held by the tests or reads of the tasks named beside it.

- **A stream pushed with a credential the edge refuses, or a guard keyed on a name the vault lacks.** Either way, the shipper's push fails and its lines are dropped and counted, or the compose renders without `--ship-logs`. The literal case holds each logship template's non-comment lines whole: `mon_ingest_loki_url`, `mon_ingest_logship_user`, `mon_ingest_logship_password` and `ZCRYPTO_SHIP_LOGS=1`, the flag without which the capture image's ENTRYPOINT omits `--ship-logs`. The group-vars case holds `mon_ingest_logship_user` equal to the `mon` role's default and admitted on the Loki path alone. R5's `logship` push reads the vault key before any shipper presents it. The branch case renders the capture, ops and engine compose templates, eight guards between them, with `mon_ingest_logship_password` alone defined and reads each service's whole true branch, then with nothing defined its whole false branch; the render-task case holds both `render the logship secrets env file` tasks' `when:` to that name; Step 10 renames each of the ten to a name no context defines. The sweep case holds no file under `infra/ansible/roles/` naming `logship_loki_token`, and Step 10 puts the name into a comment that only that case reads (Task 4).
- **The engine restarted for its hand-over by anything but the deferred disarm converge, or a capture restart outside its attended sitting.**
  - The engine's compose renders byte-identical across Task 4, read in its Step 4, so no engine-tagged converge restarts the engine for this change.
  - The capture compose's one changed comment line makes its restart the hand-over converge's handler, in the sitting the rule licenses, and the merge waits for the hand-over day after the box.
  - The primary's capture converge is `--tags capture`, which renders the engine's file and reaches no engine task (Task 4, R8, R9).
- **A default that flips alone.** `DEFAULT_STACK`, the push script's `GRAFANA_URL` default and the ops watchdog's probe default are held to one value by tests. The push tests' Grafana Cloud URL is read from `grafana_auth.STACKS["cloud"]`, never from the script's default, which is the node's from Task 6, so the refusal and skip cases keep addressing Grafana Cloud (Tasks 6, 7).
- **A rule of the node-only groups reaching Grafana Cloud after the flip.** The host-keyed skip default and the refusal are unchanged and keep holding on every Grafana Cloud spelling. A push naming no stack now goes to the node and sends both node groups (Task 6).
- **A silence that outlives its stream, ends before it, or blinds a stream not yet moved.** The node's four end at their sittings and are read back expired with their instants. Grafana Cloud's take the matchers the Global Constraints' *Grafana Cloud's silences* bullet names (R2, R6 to R9, R10, R-records-2).
- **An operator surface left saying the old pager, or a phase-4 line re-trued early.** Task 2 runs its sweep, and Tasks 8 and 9 the pager sweep, each hit classed. A line that says which stack pages, which channel a stack's page reaches, which URL the watchdog probes or which stack a tool reads by default is re-trued in the task that makes it false. A line on the Grafana Cloud leg's shipping, its keep-lists, its keep-alive, its retention or a past event is left to phase 4 or to history (Tasks 2, 5, 8, 9).

---

### Task 1: The gate — seven clean comparison days, four drills and the boundary reading, read and recorded

**Files:**
- Modify: `docs/open-topics/T0217-self-hosted-observability-stack.md` (one `## Findings so far` bullet: the gate as read, the seven entries by date, each beside the day it compared, with their `compare:` lines, each difference with its class, the four drill entries, and the boundary bullet)

**Interfaces:**
- Consumes:
  - the standing `ops-journal` branch's `docs/reference/ops-journal/2026-10.md`, each entry's `compare:` line (the daily-ops skill's step 7);
  - `docs/reference/drill-log.md`'s headings `## <date> — W<n> — pass`;
  - the spec's measured-basis bullet `The range-selector boundary, read on 2026-10-07`, which reads 5 on Grafana Cloud and 6 on the node;
  - `ops_daily.COMPARISON_FROM`;
  - `docs/reference/deploy-log.jsonl`'s `zcrypto-mon` rows;
  - R0 and R1, run before this task's Step 4 in the workstation checkout at the repository root (the Rollout's conventions), where R1's difference files `.tmp/cutover/compare-<compared day>.txt` sit; Step 4 reads them there.
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

- [ ] **Step 1: The preconditions on `develop`.** The records branch and plan 00123's R12 pull request, which sets `COMPARISON_FROM`, are merged.

```bash
git fetch origin develop ops-journal
git grep -c 'The range-selector boundary, read on 2026-10-07' origin/develop -- docs/specs/00121-self-hosted-observability-design.md
git show origin/develop:docs/reference/drill-log.md | grep -cE '^## [0-9-]+ — W[1-4] — pass$'
git show origin/develop:infra/scripts/ops_daily.py | grep -cE '^COMPARISON_FROM.*= date\(2026, 10, 10\)$'
```

Expected: one line ending `:1`, then `4`, then `1`. Any other reading is a stop: the phase-2 records are not on `develop` yet.

- [ ] **Step 2: The journal.** `git show origin/ops-journal:docs/reference/ops-journal/2026-10.md | grep -E '^## 2026-10-|^compare:|compare: '` — Expected: from `## 2026-10-10` on, each entry heading followed by one `compare: <n> nodes × 24 instants, <k> differences` line. The seven consecutive ones are listed by date. An entry dated D carries the comparison of D − 1, the day the pass hands its runner (`ops_daily.read_comparison`, `now.date() - timedelta(days=1)`), so each `<k>` above 0 names its compared day, D − 1, which R1 reads.
- [ ] **Step 3: The rebuild read.** `uv run python -c "import json; [print(r['ts'], r['tags'] or '<un-tagged>') for r in map(json.loads, open('docs/reference/deploy-log.jsonl')) if r.get('limit') == 'zcrypto-mon' and r['ts'] > '2026-10-07T12:14:42Z' and not r.get('tags') and r.get('playbook') == 'site.yml']"` — Expected: no line, or lines whose day's journal entry names no rebuild.
- [ ] **Step 4: R1's files.** For each compared day Step 2 named, `.tmp/cutover/compare-<compared day>.txt` exists in R1's checkout and each difference line in it carries R1's class. Expected: every line classed. A line without a class is the stop above.
- [ ] **Step 5: The bullet.** One line in `## Findings so far`: the seven entries, each beside the day it compared and its line, each difference and its class, the four drill headings with their dates, and the boundary bullet's two readings; R0's instant is R-records-1's.
- [ ] **Step 6: The consumers** — `uv run pytest tests/test_open_topics_frontmatter.py tests/test_topics_index.py -q -p no:cacheprovider`; Expected: no failure.
- [ ] **Step 7: The commit gate.**
- [ ] **Step 8: Commit** — `docs(topics): T0217 records the cutover's gate — seven clean comparison days, the four drills and the boundary reading`, with the trailer; no guard changes, so no probe.
- [ ] **Step 9: The tree is clean** — `git status --porcelain`; Expected: empty.

---

### Task 2: The node pages the main channel — the operator surfaces that say it pages the shadow channel alone, and the exposure page's first read

**Files:**
- Modify: `infra/runbooks/mon.md`:
  - Step 2: the push that moves the node's contact points carries `slack_webhook_url`, the main channel's, read through `grafana_auth.vault_var`. Its rollback, the same push with `slack_shadow_webhook_url`, keeps the Global Constraints' order, which the step states in its own words: while Grafana Cloud's receivers are on the main channel and no direct-shipped stream has moved to the node, that push alone; once Grafana Cloud's receivers are on the shadow channel, Grafana Cloud's push with `slack_webhook_url` first; and once a stream has moved, not before each moved stream has returned to Grafana Cloud with Grafana Cloud's silences on it expired, so that a stack whose rules read each stream pages the main channel throughout.
  - `mon-patch-pass` step 6 and `zcrypto-mon-reboot-pending`'s clause: "Until the node pages the main channel, that alert reaches the shadow channel alone, and this read is the one that brings a pending reboot to a person". The alert now pages the main channel, and the read stays as the pass's own.
  - `zcrypto-mon-grafana-error-logs`: *What it means*' "both minted from the one shadow webhook"; step 3's "Both contact points carry the one shadow webhook" and its re-mint command, which vaults `slack_webhook_url`, the key step 2 names, and writes it to the contact points of each stack that pages the main channel: the node's by `mon-push` step 2, and, while Grafana Cloud's receivers page the main channel too, Grafana Cloud's by the push skill's Step 0 line with `GRAFANA_SLACK_WEBHOOK_URL` set to the new value, since both stacks then carry that webhook; and step 4's "A shadow channel that stays silent".
  - `mon-secrets` step 1's test of the `metrics` contact point, which reaches the main channel.
  - `mon-dark`'s *What you are seeing*: the node's copies in the main channel stop while Grafana Cloud's continue, in place of "the shadow channel is silent".
  - `zcrypto-mon-ingest-dark` step 1, which names a TLS error and a timeout: a refused connection names Caddy, not listening on 443, the edge fault drill W1's last leg induced.
  - The clauses that hold the cutover ahead, false from this pull request's merge: `mon-compare`'s *What it means* last sentence, the seven days that gate the cutover; its step 2's "a finding for the cutover pull request, fixed or explained there"; its step 4's "where the cutover's seven days are read from"; and `mon-dark`'s *What it means* clause on the seven days counting again after a rebuild. Each is re-trued to what stays true: the comparison's line is recorded until the table holds one stack, a difference is read by step 3, and nothing waits on it.
- Modify: `infra/scripts/ops_daily.py`'s comment above the `## Comparison` section, "a difference is a finding for the cutover pull request", cut to what stays true from this pull request's merge: the line is not a verdict and `exit_code` never reads it.
- Modify: `infra/runbooks/hc.md` (the header's "an alert fired in the shadow channel" and its sentence that the `zcrypto-hc` group pages the shadow channel; `hc-dark`'s "`zcrypto-alloy-dark-hc` pages the shadow channel"; `hc-patch-pass` step 7's and `zcrypto-hc-reboot-pending`'s "Until the observability node pages the main channel" clauses)
- Modify: `infra/runbooks/engine.md`, `#zcrypto-engine-dark-with-exposure` step 1. A first read is added (D16, D20): when the page's links are under `https://zcrypto-mon.zhaow.me/`, read `zcrypto-mon-ingest-dark` there first. `uv run python infra/scripts/grafana-query.py --stack mon 'count(up{host!="zcrypto-mon"}) or on() vector(0)'` reading 0, or failing to connect, a refused connection, a TLS error or a timeout, since the read travels the same edge, is the node's edge or certificate, with every host absent at once (`mon.md#zcrypto-mon-ingest-dark` step 1). The page's two halves are then read on Grafana Cloud's copy, `grafana-query.py` with no `--stack`, before the route split that follows.
- Modify: `infra/runbooks/drills-telemetry.md` (the `W1` to `W4` sections' sentences on the channel the node's pages reach in a re-run: the main channel, beside Grafana Cloud's copies until its receivers move; drill W3's *Induce* step 4, whose "with the shadow webhook" goes, so that it cites `mon-push` step 2 and names no webhook of its own; and, ahead of that push, the Global Constraints' rebuild re-set: while a silence on a direct-stream dead-man whose stream has not moved was live at the loss, each such silence is set again in the node's UI with its matcher and its end as last set or re-dated, and read back by `mon_get /api/alertmanager/grafana/api/v2/silences` (`mon-patch-pass` step 5's `mon_get`), the step named as outside the must-hold "No UI step between the rebuild and the first evaluated rule", since that dead-man fires at the first evaluation after the push and pages the main channel; and W3's two clauses that keep a rebuild restarting the comparison's count, its *Operator action*'s "the seven days are counted again as `mon-dark` counts them" and its *Record*'s "the day whose comparison restarts", re-trued with `mon-dark`'s clause)
- Modify: `docs/open-topics/T0085-final-pre-golive-steps.md`'s two Slack webhook entries: `slack_webhook_url`, re-minted, reaches the contact points of whichever stack pages the main channel, by that stack's push carrying it, the node's being `mon-push`'s *A push that mints or moves the node's two contact points*, and while both stacks page it both; `slack_shadow_webhook_url` reaches the contact points of whichever stack pages the shadow channel, by that stack's push carrying it.
- Test: none new; `WALKERS`.

**Interfaces:**
- Consumes: R3's push, which this task's text describes and which follows the pull request's merge; `zcrypto-mon-ingest-dark`, `for: 5m`, which W1's edge stop read paging at +11:24, ahead of the alloy-dark pair at +15:59 (`docs/reference/drill-log.md`'s W1 entry); the vault key names `slack_webhook_url` and `slack_shadow_webhook_url`.
- Produces: `mon.md#mon-push` step 2 in the form R3 runs.

**What this task decides, where the spec leaves it open:**
- **The sweep that finds the lines is `git grep -n -i -E 'shadow channel|shadow webhook|slack_shadow_webhook_url|until (the )?(observability )?node pages' -- infra/runbooks .claude infra/grafana infra/scripts docs/reference/fleet.md docs/open-topics/T0085-final-pre-golive-steps.md`.** At this plan's base it prints 31 lines: 16 in `drills-telemetry.md`, 8 in `mon.md`, 5 in `hc.md`, the push skill's line 20, which is Task 3's, and T0085's `slack_shadow_webhook_url` entry. Each hit that says the node, or a group it alone evaluates, pages the shadow channel, or that names the shadow webhook as the node's, is re-trued here. A hit that says Grafana Cloud pages the main channel stays true until R10 and is Task 8's. The drill log is history and is not edited.
- **The exposure page's read is the node's because, from R3, both stacks send that page.** The node's copy is the one an ingest outage can raise, and its links name its host. After Task 6's flip, Task 8 swaps the stack names in the step.
- **The comparison's clauses that hold the cutover ahead are re-trued in this pull request, not the third,** since they go false when it merges. `git grep -n -i -E 'cutover pull request|cutover.s seven days|seven days the cutover|cutover is gated|seven consecutive days' -- infra/runbooks infra/scripts .claude/skills` prints 8 lines at this plan's base: `mon.md` 57, 69, 73 and 91 and `ops_daily.py` 1199, which are this task's, and the daily-ops skill's 21, 96 and 119, which are Task 3's. Two more lines carry the clause in words that pattern misses, `drills-telemetry.md` 705 and 709 at this plan's base, in drill W3; they are this task's, named in its `drills-telemetry.md` entry.

- [ ] **Step 1: Load `zcrypto-refine-rules`** and read its *Before you write guidance*.
- [ ] **Step 2: The sweep**, kept as `.tmp/cutover/task2-sweep`, each hit classed.
- [ ] **Step 3: The edits.**
- [ ] **Step 4: The consumers** — `WALKERS`, then `uv run pytest tests/test_drill_log.py tests/test_infra_hc_role.py tests/test_infra_mon_role.py tests/test_open_topics_frontmatter.py tests/test_topics_index.py -q -p no:cacheprovider`; Expected: no failure from either.
- [ ] **Step 5: The commit gate.**
- [ ] **Step 6: Commit** — `docs(runbooks): the node pages the main channel — its push's webhook, the node-only groups' channel, the exposure page reads ingest-dark first, and a comparison difference gates nothing once the gate is read`, with the trailer; no guard changes.
- [ ] **Step 7: The tree is clean.**

---

### Task 3: The push skill's sentence on the node's webhook, and the daily pass's comparison once the gate is read

**Files:**
- Modify: `.claude/skills/zcrypto-grafana-push/SKILL.md` (line 20's "a shell that exported the node's shadow webhook then leaves Grafana Cloud's receivers where they point" becomes a shell that exported the other stack's webhook; nothing else)
- Modify: `.claude/skills/zcrypto-daily-ops/SKILL.md` (the clauses that hold the cutover ahead, which go false when the cutover pull request merges: step 1's paragraph on the seven days the cutover waits for and its rebuild restart, step 7's "since the cutover's seven days are read from the journal", and the rationalisation row's "a finding for the cutover pull request"; re-trued in Task 2's words for `mon-compare`: the comparison's line is recorded until the table holds one stack, and nothing waits on it)

**Interfaces:**
- Consumes: Task 2's `mon-push` step 2 and its `mon-compare` steps.
- Produces: a push skill true from R3, and a daily-ops skill true from the cutover pull request's merge.

- [ ] **Step 1: Load `zcrypto-refine-rules`.**
- [ ] **Step 2: The edits**, in the two bodies, outside the always-loaded set.
- [ ] **Step 3: The consumers** — `uv run pytest tests/test_guidance_guard.py tests/test_guidance_refs_resolve.py tests/test_grafana_push_sh.py tests/test_daily_ops_skill.py -q -p no:cacheprovider`.
- [ ] **Step 4: The commit gate.**
- [ ] **Step 5: Commit** — `claude(skills): a routine push leaves either stack's receivers where they point, whichever channel's webhook the shell holds, and the daily pass's comparison gates nothing once the gate is read`, with the trailer; a `claude` commit carrying no other file.
- [ ] **Step 6: The tree is clean.**

Then the cutover pull request opens through the `open-pr` skill over Tasks 1 to 3. Its body cites Task 1's bullet under a `## Gate` section, and each difference with its explanation. A different agent reads the branch. The Rollout's R2 runs once the pull request is open and before `merge-pr` merges it, since a rebuild or a key replacement that follows the merged `mon-push` step 2 mints the main webhook; R3 and R4 follow from merged `develop`.

---

### Task 4: The logship files push to the node's Loki as its `logship` user, and the guards that read Grafana Cloud's logship token move to the node's

**Files:**
- Modify: `infra/ansible/group_vars/observed/vars.yml` (`mon_ingest_logship_user: logship` beside `mon_ingest_fleet_user`; the header's "the user it admits on both" re-trued to the two users, `logship` on the Loki path alone)
- Modify: `infra/ansible/roles/capture/templates/logship-secrets.env.j2` and `infra/ansible/roles/ops/templates/logship-secrets.env.j2`:
  - The first three lines below replace the `grafana_loki_url`, `grafana_loki_user` and `logship_loki_token` lines.
  - The header's Grafana Cloud sentences are re-trued: the access policy `zcrypto-app-logship`, "the URL and USERNAME are properties of the Grafana Cloud stack", and "the same values alloy-secrets.env.j2 renders". The password is the node's `logship` user's, which the edge admits on the Loki path alone, so revoking it leaves the `fleet` user's ingest untouched.
  - The `ZCRYPTO_SHIP_LOGS=1` line, the fourth below, and its comment stay.
- Modify: `infra/ansible/roles/capture/tasks/main.yml` and `infra/ansible/roles/ops/tasks/main.yml`: each `render the logship secrets env file` task takes `when: mon_ingest_logship_password is defined`, and the ops task's comment naming `logship_loki_token is defined` is re-trued. These render tasks notify nothing; the capture role's comment, "a credential rotation must never restart live capture", stays true.
- Modify: `infra/ansible/roles/capture/templates/compose.yaml.j2`: its two `{% if logship_loki_token is defined %}` guards become `{% if mon_ingest_logship_password is defined %}`, and the comment line "Guarded by the SAME `logship_loki_token is defined`" is re-trued. The rendered file then differs by that one comment line, and the converge's `restart capture service` handler is the attended restart.
- Modify: `infra/ansible/roles/ops/templates/compose.yaml.j2`: the three guards and the comment's "`logship_loki_token is defined` condition", re-trued. The render notifies nothing, and the recreate is by hand.
- Modify: `infra/ansible/roles/engine/templates/compose.yaml.j2`: the three guards alone. No comment there names the token, so the rendered file is byte-identical.
- Modify: `infra/ops/README.md` (the guard's name, `logship_loki_token`, in the `ZCRYPTO_LOG_HOST` row's "guarded by `logship_loki_token is defined`" and in the *Two log paths* paragraph's "when `logship_loki_token` is vaulted")
- Test: `tests/test_infra_compose_templates.py`:
  - `test_renders_valid_yaml_without_logship_token`, `test_renders_valid_yaml_with_logship_token` and `test_engine_logship_guard_moves_environment_and_entrypoint_together` take `mon_ingest_logship_password`, the variable and the comments re-trued. The two valid-YAML families read only that a render parses, which either branch does, so they hold no guard's name.
  - The module comment over the contexts, "outside the `logship_loki_token is defined` guard", re-trued to the new name.
  - New: the branch case and the render-task case below. A guard or a `when:` that reads any other name renders its false branch with the node's password defined, and fails them.
  - New: `test_the_logship_files_push_to_the_nodes_loki_as_its_logship_user`, which holds each template's non-comment lines, whole and in order, to the four below and reads no `grafana_loki_` or `logship_loki_token` name in either template. The fourth, `ZCRYPTO_SHIP_LOGS=1`, is the capture daemon's only way to ship: its image's ENTRYPOINT adds `--ship-logs` when the flag is set, and the capture compose bakes none in.
  - New: `test_no_role_reads_grafana_clouds_logship_token`, under which no file below `infra/ansible/roles/` names `logship_loki_token`.
- Test: `tests/test_infra_mon_role.py`: `test_the_fleets_ingest_names_are_the_nodes_public_name_its_two_authenticated_paths_and_its_fleet_user` holds the group vars' `mon_` keys to a dict gaining `mon_ingest_logship_user` equal to the role default. A new assertion reads that user admitted on `/loki/api/v1/push` and absent from `/api/v1/write`, through `role_render.users`.
- Test: `tests/test_infra_converge_guards.py` (the comment "the ops host defines `logship_loki_token`", re-trued to the new name; the assertions unchanged)

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
- **The engine's compose template changes in its three guards alone, so its rendered file is byte-identical** and the deferred disarm converge's preview stays item 6's, its compose line the re-pin's digest alone (Task 5). Step 4 reads it identical before the commit.
- **`mon_ingest_logship_user` is a group var for the reason phase 2 made `mon_ingest_fleet_user` one:** a role's defaults are invisible to another role's template.

Each template's non-comment lines, the first three determined by the group and vault names and the fourth unchanged:

```
ZCRYPTO_LOKI_URL={{ mon_ingest_loki_url }}
ZCRYPTO_LOKI_USERNAME={{ mon_ingest_logship_user }}
ZCRYPTO_LOKI_PASSWORD={{ mon_ingest_logship_password }}
ZCRYPTO_SHIP_LOGS=1
```

The group var:

```yaml
mon_ingest_logship_user: logship
```

The branch case and the render-task case, in `tests/test_infra_compose_templates.py`. The capture service ships through its image's own ENTRYPOINT, which reads `ZCRYPTO_SHIP_LOGS` from the logship file, so its true branch carries no `--ship-logs` of its own:

```python
_LOGSHIP_GUARDS = [
    (CAPTURE_TEMPLATE, CAPTURE_CONTEXT, "capture", "/opt/zcrypto-capture/logship-secrets.env", False),
    (OPS_TEMPLATE, OPS_CONTEXT, "liquidations", "/etc/zcrypto-ops/logship-secrets.env", True),
    (ENGINE_TEMPLATE, ENGINE_CONTEXT, "engine", "/opt/zcrypto-capture/logship-secrets.env", True),
]


def _logship_branch(service: dict, logship_file: str) -> tuple[bool, bool, bool]:
    paths = [e["path"] if isinstance(e, dict) else e for e in service.get("env_file", [])]
    return (
        "ZCRYPTO_LOG_HOST" in service["environment"],
        logship_file in paths,
        "--ship-logs" in service.get("entrypoint", []),
    )


@pytest.mark.parametrize(
    ("template", "context", "service", "logship_file", "ships_by_entrypoint"), _LOGSHIP_GUARDS, ids=["capture", "ops", "engine"]
)
def test_every_logship_guard_renders_its_whole_branch_on_the_nodes_password(
    template, context, service, logship_file, ships_by_entrypoint
):
    on = _render(template, {**context, "mon_ingest_logship_password": "x"})["services"][service]
    off = _render(template, context)["services"][service]
    assert _logship_branch(on, logship_file) == (True, True, ships_by_entrypoint)
    assert _logship_branch(off, logship_file) == (False, False, False)


@pytest.mark.parametrize("role", ["capture", "ops"])
def test_the_logship_file_renders_on_the_nodes_password(role):
    tasks = yaml.safe_load((REPO / f"infra/ansible/roles/{role}/tasks/main.yml").read_text())
    (render,) = [t for t in tasks if t.get("name") == "render the logship secrets env file"]
    assert render["when"] == "mon_ingest_logship_password is defined"
```

- [ ] **Step 1: The failing tests**, the cases above. The vault key whose name they read is T0085's ingest-pairs entry's `mon_ingest_logship_password` in `group_vars/observed/vault.yml`, a file no executor reads (the implementer contract); R5's `logship` push reads it before any shipper presents it.
- [ ] **Step 2: Run them and read the failure** — `uv run pytest tests/test_infra_compose_templates.py tests/test_infra_mon_role.py -q -p no:cacheprovider`. Expected:
  - the literal case fails on both templates;
  - the sweep case fails, naming the seven files that read the token (the two logship templates, the three compose templates and the two render tasks' files);
  - the group-vars case fails on the missing key;
  - the branch case fails on capture, ops and engine, and the render-task case on both roles, each still reading `logship_loki_token`;
  - `test_engine_logship_guard_moves_environment_and_entrypoint_together` fails, its true branch unrendered;
  - the two valid-YAML families pass, since either branch parses.
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

Expected: `identical`; the diff shows each file's guards and one comment line, and nothing else. `differs` is the engine template changed beyond its three guards, a guard reading another name or a line the render carries edited: the template is put right and Step 4 is run again, and item 6's preview line is never re-trued for it.

- [ ] **Step 5: Run the tests** — Expected: no failure.
- [ ] **Step 6: The consumers** — `CONSUMERS` over the task's files, with `tests/test_logging_ship_handler.py` and `tests/test_obs_metrics.py`; Expected: no failure.
- [ ] **Step 7: The commit gate.**
- [ ] **Step 8: Commit** — `feat(infra): the applications' own log push goes to the node's Loki as its logship user, and no role reads Grafana Cloud's logship token`, with the trailer.
- [ ] **Step 9: The tree is clean.**
- [ ] **Step 10: Prove the guards with one probe per guard, then record their verdicts in the probes' commit (Global Constraints).** Each run's control is `'1,$d'`, the file emptied, and each mutation is anchored to one line. A renamed guard or `when:` takes `logship_probe_unset`, a name no context defines, so the branch and render-task cases kill it and the sweep case cannot. The capture template's flag deleted is the literal case's alone to kill, and the token named in a YAML comment on the ops tasks' first line the sweep case's alone, since the render-task case reads that file as YAML:

```bash
probe() { infra/scripts/mutate-probe.sh --file "$1" --control '1,$d' --mutation "$2" -- uv run pytest tests/test_infra_compose_templates.py tests/test_infra_mon_role.py -q -p no:cacheprovider; }
probe infra/ansible/roles/capture/templates/logship-secrets.env.j2 's/^ZCRYPTO_LOKI_URL={{ mon_ingest_loki_url }}$/ZCRYPTO_LOKI_URL={{ grafana_loki_url }}/'
probe infra/ansible/roles/ops/templates/logship-secrets.env.j2 's/^ZCRYPTO_LOKI_USERNAME={{ mon_ingest_logship_user }}$/ZCRYPTO_LOKI_USERNAME={{ mon_ingest_fleet_user }}/'
probe infra/ansible/roles/ops/templates/logship-secrets.env.j2 's/^ZCRYPTO_LOKI_PASSWORD={{ mon_ingest_logship_password }}$/ZCRYPTO_LOKI_PASSWORD={{ logship_loki_token }}/'
probe infra/ansible/roles/capture/templates/logship-secrets.env.j2 '/^ZCRYPTO_SHIP_LOGS=1$/d'
probe infra/ansible/roles/ops/tasks/main.yml '1i # logship_loki_token'
probe infra/ansible/group_vars/observed/vars.yml 's/^mon_ingest_logship_user: logship$/mon_ingest_logship_user: fleet/'
probe infra/ansible/group_vars/observed/vars.yml '/^mon_ingest_logship_user: logship$/d'
for role in capture ops engine; do
  t="infra/ansible/roles/$role/templates/compose.yaml.j2"
  for n in $(grep -n '^{% if mon_ingest_logship_password is defined %}$' "$t" | cut -d: -f1); do
    probe "$t" "${n}s/mon_ingest_logship_password/logship_probe_unset/"
  done
done
for role in capture ops; do
  probe "infra/ansible/roles/$role/tasks/main.yml" 's/^  when: mon_ingest_logship_password is defined$/  when: logship_probe_unset is defined/'
done
```

  Expected: seventeen runs, the guards' eight among them, two in the capture template and three in each of the ops and engine templates, each ending `mutate-probe: KILLED (control proven, tree restored byte-identically)`.

---

### Task 5: The direct-ship surfaces and the hand-over procedure

**Files:**
- Modify: `infra/runbooks/mon.md`, a new section `mon-stream-handover — PROCEDURE: handing a direct-shipped log stream to the node`, in the page's procedure shape:
  - *What you are seeing*: nothing fired, and a sitting moves one stream; or Grafana Cloud's dead-man for a stream pages because an unplanned restart moved it early; or a read of Grafana Cloud's rules, the daily pass's while it reads Grafana Cloud by default among them, lists the dead-man of a stream whose sitting has run as `firing` with no page in Slack, its silence holding the notification and not the rule's state while the silence lasts; or Grafana Cloud's dead-man for a stream whose sitting has run pages, its silence having ended before the Grafana Cloud leg retired.
  - *What it means*: each shipper reads its push credentials from its logship file when its container starts, so a start after the change reaches the host moves its stream. The engine reads the primary's capture file. The node's dead-man for each stream is silenced until its sitting, and Grafana Cloud's dead-man for a moved stream pages within its six-hour range unless silenced.
  - *What to do*, per stream, by case: in a sitting, the converge and restart form of its host, then the six reads; in the early case, the six reads alone, its restart having been taken, the sitting's remaining steps; for a stream whose sitting has run, no step, its reads being the node's, `ops-daily.py report --stack mon` among them, but for a Grafana Cloud page whose silence has ended, while Grafana Cloud's receivers are still on the main channel, read 5's two silences set again to end at 00:00 UTC on the third day after the day their move is now planned for, and once they have left it, the owner's to rule, since read 5's end has then passed. The host forms: the poller's, `infra/ansible/scripts/converge.sh site.yml --limit zcrypto-ops --tags ops -e ops_image_digest=sha256:<running>` from the workstation, the digest read off `zcrypto-ops-liquidations`, then on ops `cd /etc/zcrypto-ops && sudo docker compose up -d`, then `sudo docker inspect zcrypto-ops-liquidations --format 'img={{.Config.Image}} restarts={{.RestartCount}} started={{.State.StartedAt}}'` reading the same digest, 0 restarts and a `started` after the converge, a `started` that did not move being recreated by `sudo docker compose up -d --force-recreate liquidations` and read the same way; a capture daemon's, the Global Constraints' capture-pair forms; the engine's, a converge inside an inter-cycle gap under `engine-procedures.md`'s restart rules, on the hand-over day step 8 item 6's. The six reads, numbered as the section carries them, are over one stream's `<host>`, `<container>`, `<job>`, its node dead-man `<uid>` and Grafana Cloud's rules that read it, each Grafana Cloud read naming `--stack cloud` and each read of the node's API taking `mon_get` as `mon-patch-pass` step 5 defines it:
    1. **The stream on the node by the rule's own query:** `uv run python infra/scripts/grafana-query.py --stack mon --loki 'sum by (host) (count_over_time({host="<host>", container="<container>", level=~".+"} [6h]))'`; Expected: one row above 0, read once the shipper has logged after its restart.
    2. **The shipper's counters on the node**: `uv run python infra/scripts/grafana-query.py --stack mon 'increase(zcrypto_logship_shipped_lines_total{host="<host>", job="<job>"}[15m])' 'increase(zcrypto_logship_dropped_lines_total{host="<host>", job="<job>"}[15m])'`; Expected: above 0, then 0.
    3. **The stream gone from Grafana Cloud**, from five minutes after the restart: `uv run python infra/scripts/grafana-query.py --stack cloud --loki 'sum(count_over_time({host="<host>", container="<container>"}[5m]))'`; Expected: `(no series)`.
    4. **The node's dead-man inactive, then its silence ended:** `mon_get /api/prometheus/grafana/api/v1/rules | jq -r '.data.groups[].rules[] | select(.uid == "<uid>") | "\(.uid) \(.state) \(.health)"'`; Expected: `<uid> inactive ok`. Then, where the silence's end is still ahead, it is expired in the node's UI. Then `mon_get /api/alertmanager/grafana/api/v2/silences | jq -c '.[] | select(any(.matchers[]; .name == "__alert_rule_uid__" and .value == "<uid>")) | {id, state: .status.state, matchers, endsAt}'`; Expected: `"state":"expired"`, its one matcher `"isEqual":true` and `"isRegex":false`, with `endsAt` the instant it ended.
    5. **Grafana Cloud's silences:** in Grafana Cloud's UI, the dead-man silenced by `__alert_rule_uid__=<its uid>` and the burst rule by `__alert_rule_uid__=<its uid>`, `host=<host>` and `container=<container>`, each matcher an equality, each ending at 00:00 UTC on the third day after the day Grafana Cloud's receivers leave the main channel, as planned until they have, and each silence's id kept. Then the read-back, `uv run python -c 'import sys; sys.path.insert(0, "infra/scripts"); import grafana_auth as g; print("Authorization: Bearer " + g.token("cloud"))' | curl -fsS -H @- https://zcrypto2026.grafana.net/api/alertmanager/grafana/api/v2/silences | jq -c '.[] | select(.status.state == "active") | {id, matchers, endsAt}'`; Expected: each id just kept appears once with its end and exactly its silence's matchers, each `"isEqual":true` and `"isRegex":false`: the dead-man's `__alert_rule_uid__` alone, the burst rule's `__alert_rule_uid__`, `host` and `container` with the stream's values; no second active line carries the same matchers.
    6. **The burst rule's pipeline on the node:** the burst rule's expression as `infra/grafana/alerts.yaml` holds it under its uid, with `level=~"ERROR|CRITICAL"` widened to `level=~".+"`, its selector narrowed to `host="<host>"` and `container="<container>"`, and its `or on() vector(0)` dropped, read by `uv run python infra/scripts/grafana-query.py --stack mon --loki '<that expression>'`; Expected: rows, each carrying a `msg` label, read inside the expression's 15-minute range once the shipper has logged after its restart.
  - *Rollback*: the Global Constraints' rollback of a moved stream, which `mon.md` words without a task number, as the change that pointed both logship templates at the node reverted on a branch and merged; all moved streams return together to a Grafana Cloud whose receivers page the main channel, so that once they page the shadow channel, `mon-push` step 2's Grafana Cloud push with `slack_webhook_url` comes first.
  - *Retire when*: `grafana_auth.py`'s `STACKS` holds one stack.
- Modify: `infra/runbooks/engine-procedures.md`, step 8 item 6. The converge's restart starts the engine on the logship file the primary's capture converge rendered earlier that day, which hands the engine's log stream to the node; its reads are `mon.md#mon-stream-handover`'s, taken after disarm step 3's. The converge is also the November nautilus bump's engine re-pin (the owner's ruling of 2026-10-09): in place of disarm step 2's running digest, whose image predates `zcrypto engine preflight` and answers rc 2, it passes the bump's engine digest as `.claude/skills/zcrypto-rollout-image/SKILL.md`'s *Engine converges* takes a candidate, so the candidate's own preflight passes and no `engine_preflight_override` rides beside it. The item's preview gains, beside the lines it names: `render the engine compose file` and `install the engine flatten wrapper`, each `changed` on the engine image's digest line alone; the preflight block's two asserts, `engine preflight — refuse …` and `engine provenance — refuse …`, each printing `All assertions passed`, and its override task `skipping`; the two renders beside a live file that each engine converge makes and removes, `engine preflight — render the candidate configuration beside the live one` and `render the cache proxy config beside its live copy`, `changed` with their diffs hidden; and a render the bump's own merge changed, as its rollout names it. The hand-over adds no line there, Task 4's Step 4 holding the engine's compose render unchanged and the logship file being the capture converge's; the page words the item without a skill's phase number or a task number.
- Modify: `infra/runbooks/mon.md`:
  - `mon-secrets` step 4: a changed `logship` password reaches the three application shippers through `mon-stream-handover`'s per-stream forms, their logship files rendered by the role converges and their containers recreated, since `--tags alloy` renders neither logship file and `env_file` is read at create. Its rotation is a sitting shaped like the hand-over day's.
  - `mon-compare`'s *What it means* clause that the seven direct-stream rules' stream "reaches the node at the cutover and not before", re-trued as the script's comment is.
- Modify: `infra/runbooks/observability.md`. Its direct-ship sections are named here by heading, and none of the three headings is an anchor: a link to one takes one of its anchors (`zcrypto-logship-lines-dropped`, `zcrypto-capture-log-dead-primary`, `zcrypto-ops-poller-log-dead` and their siblings).
  - The header's sentence on the direct-ship path, "push their own logs to Loki", which names the node's Loki once each stream has moved.
  - `zcrypto-logship` step 3's "`logship_loki_token`, vaulted, rendered into `logship-secrets.env`", which becomes `mon_ingest_logship_password`, and step 6's "a fresh Loki line", read on the node once the stream has moved.
  - `zcrypto-capture-log-dead`, its step 5's forms among it: the Global Constraints' capture-pair forms, the Alloy read and its `--tags alloy` form included, the primary's `--tags capture -e converge_primary=true` with both running digests in place of `--skip-tags engine`.
  - `zcrypto-ops-log-plane` steps 3 and 4: "A rotated Loki token" becomes the node's `logship` password, and the converge re-renders the file.
  - The early case, in each of the four dead-men's sections (`zcrypto-capture-log-dead` for two, `zcrypto-ops-log-plane` for the poller's, and `engine.md`'s below): the rule's own query read with `--stack mon` above 0 is a stream already moved, and a Grafana Cloud page or `firing` read for it routes to `mon.md#mon-stream-handover`, whose *What you are seeing* separates a stream an unplanned restart moved early from one whose sitting has run.
- Modify: `infra/runbooks/engine.md`, `#zcrypto-engine-log-dead`: the early case ahead of step 1, so that a Grafana Cloud page after the engine's stream moved reaches `mon.md#mon-stream-handover` before step 4 reads the silenced capture dead-man as "engine alone"; step 4's "the host's push path or Grafana Cloud", re-trued to the node's edge and Loki; step 6's all-clear read with `--stack mon` once the stream has moved.
- Modify: `infra/ops/README.md`'s two sentences that name Grafana Cloud Loki as the poller's direct-ship destination, in the *Two log paths* paragraph and the *Ops log streams* paragraph, which name the node's Loki once the poller's stream has moved.
- Modify: `docs/open-topics/T0085-final-pre-golive-steps.md`'s ingest-pairs entry: the `logship` password reaches the application shippers by `mon-secrets` step 4's per-stream forms, beside the node's converge; and its recreate list's "logship token → both capture hosts" (line 73 at this plan's base), which from Task 4 is the node's `logship` password.
- Modify: `infra/scripts/grafana-compare.py` (the comment above `DIRECT_SHIPPED_RULES`, "which reaches the node only at the cutover", re-trued: the seven read a stream that reached the node at its hand-over and Grafana Cloud no longer, so they stay outside the comparison)
- Modify: the direct push's destination outside the runbooks, which Step 2's second sweep finds. Re-trued here, each to the Loki `ZCRYPTO_LOKI_URL` names: `README.md`'s and `cli/__main__.py`'s `--ship-logs` help, "Also ship logs to Grafana Cloud Loki", and `infra/docker/Dockerfile`'s comment on `ZCRYPTO_SHIP_LOGS`; and `infra/grafana/alerts.yaml`'s comment in `zcrypto-capture-error-logs`, "pushed straight to Grafana Cloud Loki", a comment no push carries. At this plan's base that sweep prints 37 lines: 26 are Task 4's (its seven role files' 19, `infra/ops/README.md`'s two guard-name lines, four in `tests/test_infra_compose_templates.py` and one in `tests/test_infra_converge_guards.py`); 7 are this task's (the four just named, T0085's line 73, `infra/ops/README.md`'s line 198 and `observability.md`'s `zcrypto-logship` step 3); and 4 are left as they are: `roles/capture/files/config.alloy`'s line 184 and `roles/ops/files/config.alloy`'s lines 238 and 322, since an edit to a `config.alloy` arms its role's drift assert on every host the file serves until each is converged (spec D14), and T0085's line 19, whose rotation scope names a Grafana Cloud credential until phase 4 revokes it.
- Test: none new; `WALKERS`, `tests/test_engine_draftplan.py` for item 6's section, `tests/test_grafana_compare.py` for the comment, `tests/test_logging_cli.py`, `tests/test_cli_help_hygiene.py` and `tests/test_docker_build_context.py` for the help and the Dockerfile, and the test files that read `alerts.yaml` for its comment.

**Interfaces:**
- Consumes:
  - Task 4's files.
  - The seven rules and their selectors (`infra/grafana/alerts.yaml`). Each dead-man is `sum by (host) (count_over_time({host=…, container=…, level=~".+"} [6h])) or on() vector(0)` with `for: 0s` and `noDataState: Alerting`; each burst rule is `sum by (host, container, level, msg)` over the same stream's `ERROR|CRITICAL` lines.
  - The shipper's counters `zcrypto_logship_shipped_lines_total` and `zcrypto_logship_dropped_lines_total`, under the jobs `liquidations_app`, `capture_app` and `engine_app` (the read the `zcrypto-logship` section's step 6 already uses).
- Produces: `mon.md#mon-stream-handover`, which R6 to R9 follow and engine-procedures' item 6 cites.

- [ ] **Step 1: Load `zcrypto-refine-rules`.**
- [ ] **Step 2: The sweeps**, kept as `.tmp/cutover/task5-sweep`. First `git grep -n -i -E 'logship|ship-logs|direct-ship|push their own logs' -- infra/runbooks infra/ops/README.md`, each hit read for a sentence that names Grafana Cloud's Loki or its token as the push's destination. Then the tree outside history, `git grep -n -i -E 'Cloud Loki|straight to Grafana Cloud|directly to Grafana Cloud|logship_loki_token|logship token' -- ':!docs/specs' ':!docs/plans' ':!docs/research' ':!*archive*' ':!*vault*' ':!*.sops.*' ':!infra/ansible/files/*_ed25519'`, each hit classed as the Files entry on the direct push's destination classes it.
- [ ] **Step 3: The section, item 6's clause, the re-trued lines and the comment.**
- [ ] **Step 4: The consumers** — `WALKERS`, then `uv run pytest tests/test_engine_draftplan.py tests/test_grafana_compare.py tests/test_logging_cli.py tests/test_cli_help_hygiene.py tests/test_docker_build_context.py tests/test_prose_chars.py tests/test_open_topics_frontmatter.py tests/test_topics_index.py -q -p no:cacheprovider`, and `CONSUMERS` over the task's files; Expected: no failure from any.
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
  - The header's token sentence, "Obtain it with `grafana_auth.py`'s `vault_var("grafana_sa_token")`", re-trued to the token of the stack the push addresses: `grafana_auth.token("mon")` for the node, the default, and `token("cloud")` for Grafana Cloud.
  - The render paragraph (D9): the node runs no image renderer, so a dashboard is verified by reading each panel's query by value and looking at the panel.
  - The comment above the refusal, "a rule of one that fires on no data would page the main channel", re-trued: it would page from Grafana Cloud for good, wherever its receivers point.
  - The host-keyed skip default and the refusal are unchanged.
- Modify: `infra/grafana/alerts.yaml`'s comments over the `zcrypto-mon` and `zcrypto-hc` groups, "grafana-push.sh leaves this group out of a push that names no stack", re-trued to a push addressed to Grafana Cloud; comments alone, which no push carries.
- Modify: `infra/nas/README.md`'s *Grafana dashboard + alerts* section, which runs the push with Grafana Cloud's token and no `GRAFANA_URL`: its opening paragraph's "onto the already-live Grafana Cloud instance" re-trued to the stacks the push addresses, the node when none is named, and *Deploy* steps 1 and 3, the token and the run, replaced by one step citing the push skill's Step 0, which names each stack's URL and token; step 2, the webhook's contract, stays.
- Test: `tests/test_grafana_auth.py` (the table test renamed `test_the_table_holds_the_two_stacks_and_reads_the_node_when_none_is_named`, asserting `DEFAULT_STACK == "mon"`, `stack() is STACKS["mon"]` and `GRAFANA_URL == STACKS["mon"].url`, and Grafana Cloud's row unchanged; `test_token_reads_the_named_stacks_token_var_from_its_own_file` reads `ga.token("cloud")` and then `ga.token()`, expecting `("grafana_sa_token", ga.VAULT_FILE)` and then the node's `(token_var, vault_file)`)
- Test: `tests/test_grafana_query.py` (`test_no_stack_named_reads_grafana_cloud_with_its_token` becomes `test_no_stack_named_reads_the_node_with_its_token`; a case `--stack cloud` reads Grafana Cloud's URL with `grafana_sa_token`; the usage string unchanged)
- Test: `tests/test_ops_daily.py` (`test_the_pass_reads_grafana_cloud_when_no_stack_is_named` becomes `test_the_pass_reads_the_node_when_no_stack_is_named`; the named case reads `--stack cloud`; the due-ness case `one stack in the table` patches the table to `{"mon": STACKS["mon"]}`, the table retirement leaves, since a one-stack table that lacks the default stack makes `main` refuse the unnamed default; the other due-ness cases unchanged)
- Test: `tests/test_grafana_push_sh.py`:
  - `_cloud_url()`'s body is the one line `return _GA.STACKS["cloud"].url`, `_GA` being the module loaded as `tests/test_grafana_auth.py` loads it, in place of the script's default.
  - `_cloud_url_forms()`'s `"the default"` entry, now Grafana Cloud's plain URL, is renamed `"the plain URL"`, and `_RUNNABLE_SPELLINGS`' filter names the new key, so the refusal keeps its plainest spelling.
  - `test_a_push_that_names_no_stack_sends_no_rule_of_the_observability_node` becomes `test_a_push_that_names_no_stack_goes_to_the_node_and_sends_both_of_its_groups`: `GRAFANA_URL=""` sends `r3` and `r4`, and the first line ends `skip-groups=<none>`. Its recorded paths keep the node's host, since `_Stack.recorded()` strips the stub's URL alone, so it asserts `("POST", f"{_GA.STACKS['mon'].url}/api/v1/provisioning/alert-rules")` in `_rule_calls` for each of `r3` and `r4`.
  - New: `test_the_scripts_default_stack_is_the_tools_default_stack`, holding the script's `GRAFANA_URL` default equal to `grafana_auth.STACKS[grafana_auth.DEFAULT_STACK].url`.

**Interfaces:**
- Consumes: the stack table and its two rows; the push script's host-keyed `skip_default` and its refusal (`grafana-push.sh:53-73`); every importer of `grafana_auth.GRAFANA_URL` and `DEFAULT_STACK` (`grafana-query.py` and `ops_daily.py`, and `ops-postverify.sh` through `grafana-query.py`); `grafana-compare.py` reads the table's rows alone and is unmoved by the default.
- Produces: a workstation whose unnamed reads and pushes go to the node, which Task 9's skills and R10 rely on.

**What this task decides, where the spec leaves it open:**
- **The skip default needs no edit.** It is keyed to the host the push addresses, so moving the URL default moves it: an unnamed push skips nothing, and a push to any Grafana Cloud spelling still skips both node groups and refuses otherwise. That is the "push script's defaults" D22(4) flips.
- **The comparison keeps running until retirement** (`comparison_due` reads the table's length). Its line keeps landing in the journal and nothing waits on it.

- [ ] **Step 1: Write the failing tests.**
- [ ] **Step 2: Run them and read the failure** — `uv run pytest tests/test_grafana_auth.py tests/test_grafana_query.py tests/test_ops_daily.py tests/test_grafana_push_sh.py -q -p no:cacheprovider`. Expected:
  - the default cases fail on `cloud`: the table, token, query and pass cases, the one-stack due-ness case, and the push case that names no stack, which still skips both node groups;
  - the new equality case passes, both defaults still naming Grafana Cloud;
  - the rewired `_cloud_url()` cases pass unchanged.
- [ ] **Step 3: The constant; the script's default, its header's two paragraphs, its render paragraph and the comment above its refusal; the two `alerts.yaml` comments; and the NAS README's push section.**
- [ ] **Step 4: Run the tests** — Expected: no failure.
- [ ] **Step 5: The consumers** — `CONSUMERS` over the task's files and the five scripts that reach a stack through the table, `infra/scripts/grafana-query.py`, `infra/scripts/ops_daily.py`, `infra/scripts/ops-daily.py`, `infra/scripts/grafana-compare.py` and `infra/scripts/ops-postverify.sh`, with `tests/test_scripts_have_tests.py`, `tests/test_code_prose_citations.py` and `tests/test_prose_chars.py`.
- [ ] **Step 6: The commit gate.**
- [ ] **Step 7: Commit** — `feat(grafana): the tools read and push to the observability node when no stack is named`, with the trailer.
- [ ] **Step 8: The tree is clean.**
- [ ] **Step 9: Prove the guards, then record their verdicts in the probes' commit (Global Constraints).** Each mutation is anchored to one line: the refusal's `exit 1` is the script's one at ten spaces of indent, and the skip default's value appears once. Each run's control is `'1,$d'`, the file emptied, but the test file's, which collects nothing emptied and passes, so its control appends a failing module line:

```bash
probe() { infra/scripts/mutate-probe.sh --file "$1" --control "$2" --mutation "$3" -- uv run pytest tests/test_grafana_auth.py tests/test_grafana_query.py tests/test_ops_daily.py tests/test_grafana_push_sh.py -q -p no:cacheprovider; }
probe infra/scripts/grafana_auth.py '1,$d' 's/^DEFAULT_STACK = "mon"$/DEFAULT_STACK = "cloud"/'
probe infra/scripts/grafana-push.sh '1,$d' 's|^export GRAFANA_URL="${GRAFANA_URL:-https://zcrypto-mon.zhaow.me}"$|export GRAFANA_URL="${GRAFANA_URL:-https://zcrypto2026.grafana.net}"|'
probe infra/scripts/grafana-push.sh '1,$d' 's/skip_default="zcrypto-mon zcrypto-hc"/skip_default=""/'
probe infra/scripts/grafana-push.sh '1,$d' '/^          exit 1$/d'
probe tests/test_grafana_push_sh.py '$a assert False' 's/^    return _GA.STACKS\["cloud"\].url$/    return _GA.STACKS["mon"].url/'
```

  Expected: five runs, each ending `mutate-probe: KILLED (control proven, tree restored byte-identically)`. The last points `_cloud_url()` at the node's row, the URL the script's default now names, so the push cases address the node and fail.

---

### Task 7: The ops watchdog probes the stack that pages

**Files:**
- Modify: `infra/ansible/roles/ops/defaults/main.yml` (`ops_grafana_watchdog_probe_url: "https://zcrypto-mon.zhaow.me/api/health"`; the comment above it re-trued; and the keep-alive's comment below it, "the unauthenticated `/api/health` probe above has run for months without preventing hibernation", re-trued to the probe ops ran against Grafana Cloud until it moved to the node)
- Modify: `infra/ansible/roles/ops/templates/grafana-watchdog.sh.j2` (the header's "healthchecks.io half: probes the Grafana Cloud stack", re-trued: the dead-man service's half, probing the Grafana that pages)
- Modify: `infra/ansible/roles/ops/templates/grafana-watchdog.timer.j2` (`Description=Every-5-minutes Grafana Cloud probe for the mutual watchdog`, re-trued without the vendor)
- Modify: `infra/ansible/roles/ops/templates/grafana-watchdog.service.j2` (`Description=Grafana Cloud availability probe gating the zcrypto-grafana-watchdog dead-man`, re-trued without the vendor)
- Test: `tests/test_grafana_auth.py` (new: `test_the_ops_watchdog_probes_the_stack_that_pages`, which holds the ops default equal to `f"{ga.STACKS[ga.DEFAULT_STACK].url}/api/health"`)

**Interfaces:**
- Consumes: Task 6's `DEFAULT_STACK`; the edge, which passes `/api/health` to Grafana, answered without a login (spec D4; the measured basis's anonymous-surface read); the ops role's unconditional watchdog block (`roles/ops/tasks/main.yml`, the `install the grafana-watchdog pinger` block), which renders under `--tags ops` with no digest; `converge.sh`'s admitted key `ops_grafana_watchdog_probe_url` (`tests/test_converge_sh.py`).
- Produces: R10's ops converge; the clone's check `zcrypto-grafana-watchdog` reading the node's health, whose description ("The ops timer probing Grafana every 5 min …") stays true, so the fixture is not re-fetched.

**What this task decides, where the spec leaves it open:**
- **The probe moves to the node alone; Grafana Cloud is not probed twice over.** D16 calls the re-pointed probe "a second prober off the node", and D22(4) re-points it with Grafana Cloud's receivers. After R10, Grafana Cloud pages only the shadow channel and no check reads its death, so retirement's gate reads its rules evaluating (R-records-2).

- [ ] **Step 1: Write the failing test.**
- [ ] **Step 2: Run it** — `uv run pytest tests/test_grafana_auth.py -q -p no:cacheprovider`; Expected: the new case fails on Grafana Cloud's URL.
- [ ] **Step 3: The default, the header and the two descriptions.**
- [ ] **Step 4: Run the test** — Expected: no failure.
- [ ] **Step 5: The consumers** — `uv run pytest tests/test_infra_shell_templates_render.py tests/test_count_list.py tests/test_converge_sh.py tests/test_grafana_auth.py tests/test_internal_terms_not_operator_visible.py -q -p no:cacheprovider`, the last for each unit's `Description=`, and `CONSUMERS` over the task's files.
- [ ] **Step 6: The commit gate.**
- [ ] **Step 7: Commit** — `feat(infra): the ops watchdog probes the observability node's health, the stack that pages`, with the trailer.
- [ ] **Step 8: The tree is clean.**
- [ ] **Step 9: Prove the guard, then record the verdicts in the probes' commit (Global Constraints):**

```bash
probe() { infra/scripts/mutate-probe.sh --file infra/ansible/roles/ops/defaults/main.yml --control '1,$d' --mutation "$1" -- uv run pytest tests/test_grafana_auth.py -q -p no:cacheprovider; }
probe 's|^ops_grafana_watchdog_probe_url: "https://zcrypto-mon.zhaow.me/api/health"$|ops_grafana_watchdog_probe_url: "https://zcrypto2026.grafana.net/api/health"|'
probe 's|^ops_grafana_watchdog_probe_url: "https://zcrypto-mon.zhaow.me/api/health"$|ops_grafana_watchdog_probe_url: "https://zcrypto-mon.zhaow.me/api/search"|'
```

  Expected: two runs, each ending `mutate-probe: KILLED (control proven, tree restored byte-identically)`.

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
  - Each link to `grafana-cloud-dark` outside history is re-pointed in the same commit: `drills-telemetry.md`'s three (lines 49, 102 and 156 at this plan's base), the page's own two (its header and `#zcrypto-hcio-watchdog`), and `ops-node.md`'s in `zcrypto-ops-grafana-keepalive-stale`'s *What it means*, whose "what reaches you is the healthchecks.io dead-man" is class (a), since from R10 the dead-man probes the node and no check probes Grafana Cloud.
  - `#zcrypto-hcio-watchdog`, the runbook the clone's `zcrypto-grafana-watchdog` check names, reads a `/fail` page inside an announced stop of the node as that stop's.
- Modify: `infra/runbooks/mon.md`:
  - `mon-dark`: "The fleet is still watched: Grafana Cloud's rules page the main channel throughout" becomes the shadow channel until the leg retires; Grafana Cloud's `zcrypto-hcio-watchdog` is in the shadow channel and the clone's `zcrypto-grafana-watchdog` in the main channel; steps 2 and 5's reads take `--stack cloud`.
  - `mon-push`: a push naming no stack goes to the node; step 1's line keeps its explicit URL; *What it means* names Grafana Cloud's push as the second.
  - `mon-compare` step 3's re-read takes `--stack cloud` second.
- Modify: `infra/runbooks/hc.md` (`hc-dark`'s "Grafana Cloud's rules page the main channel throughout" and the service's death through Grafana Cloud's `zcrypto-hcio-watchdog`, which now reaches the main channel from the node's copy; `zcrypto-hc-service-down`)
- Modify: `infra/runbooks/engine.md` (`#zcrypto-engine-dark-with-exposure` step 1's stack names after the flip: the ingest-dark read with no `--stack`, reading 0 or failing to connect for the edge, as Task 2 wrote it; with the edge clear, the halves read on the node with no `--stack`, and with it dark, on Grafana Cloud with `--stack cloud`)
- Modify: `infra/runbooks/drills-telemetry.md` (drill C′, "Grafana Cloud dark", re-pointed at the Grafana that pages, with its probe override's restore reading the new default; drill C's and the `W` sections' Grafana Cloud lines by the cut below, drill W2's two reads of Grafana Cloud among them, the Cloud leg's `count_over_time` and the lines-lost count's first, each taking `--stack cloud`)
- Modify, for the clone's `zcrypto-grafana-watchdog`, which from R10 probes the node's `/api/health` every five minutes and pings `/fail` on a failed probe: each procedure that stops the node's Grafana, its edge or the node itself announces that page in the main channel beforehand. At this plan's base they are `mon.md`'s `mon-store-restart` step 1, `mon-patch-pass` step 3, `zcrypto-mon-reboot-pending` step 1, `mon-secrets` step 3 and `zcrypto-mon-retention-by-size` step 3, `hc.md`'s `hc-keys` step 5, and the announcements of drills W1 (legs 3 and 4), W2 and W3 in `drills-telemetry.md`, W1's count of the pages its announcement names among them. The three converge steps among them announce the page when their preview queues a handler that stops or restarts Grafana, Prometheus or Loki, since a store's restart stops Grafana around it, and `mon.md`'s header says the same once for a converge of the node outside these steps, `mon-token-rotate` step 1 and `mon-patch-pass` step 4 among them.
- Modify: the pager sweep's other class (a) hits outside `.claude/`, and `infra/grafana/alerts.yaml`'s summaries or comments where they say Grafana Cloud pages
- Test: none new; `WALKERS`, among them `tests/test_infra_alert_rules.py` and `tests/test_ops_daily.py` (the fixture's `Runbook:` anchors, of which none names `grafana-cloud-dark` at this plan's base).

**Interfaces:**
- Consumes: Tasks 6 and 7; D24; the measured W2 and W3 figures in `mon-dark`; the clone's checks `zcrypto-mon` and `zcrypto-grafana-watchdog` (spec 00122 D8).
- Produces: `observability.md#grafana-dark`, the node-dark procedure phase 4 narrows by its Grafana Cloud clause.

**What this task decides, where the spec leaves it open:**
- **The cut between this phase and phase 4** is the pager sweep's two classes (Global Constraints), run over its paths outside `.claude/`; Task 2 and Task 5 have re-trued some of its hits by then. The commit message gives each class's count.
- **The anchor is renamed,** since a heading that names Grafana Cloud over a procedure for the node is false. History (the drill log, T0158's record of what landed, archived topics, the specs and plans) keeps the old anchor in its text.
- **A rule summary the sweep changes takes the dual push after the merge** (R10's last step). None is expected: at this plan's base the sweep's one summary hit is `zcrypto-alloy-dark-hc`'s, which names what reads the service, not where the page goes.

- [ ] **Step 1: Load `zcrypto-refine-rules`.**
- [ ] **Step 2: The pager sweep**, kept as `.tmp/cutover/task8-sweep`, each hit outside `.claude/` classed (a) or (b).
- [ ] **Step 3: The procedure, the rename and its citations, and the class (a) lines.**
- [ ] **Step 4: The consumers** — `WALKERS`, then `uv run pytest tests/test_drill_log.py -q -p no:cacheprovider`; Expected: no failure from either, `test_every_runbook_cross_reference_resolves` among them.
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
- Modify: `.claude/skills/zcrypto-daily-ops/SKILL.md` (the pass reads the node, the stack that pages, and `--stack cloud` reads Grafana Cloud's state; its comparison clauses are Task 3's)
- Modify: the pager sweep's (Global Constraints) class (a) hits under `.claude/` in the other skills. At this plan's base they are the bump-alloy skill's line 43, "Grafana Cloud holds no `host="zcrypto-mon"` … series: the two nodes' are read with … `--stack mon`", which becomes a read with no stack named; its per-host reads under line 205's "In Cloud" and line 215's "read on Cloud and on the node", each taken on both stacks while the table holds two, the node with no `--stack` and Grafana Cloud with `--stack cloud`; and the rollout-image skill's line 107, whose read of a new family on the Grafana Cloud leg's keep-list takes `--stack cloud`.

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

- **Conventions.** `W$` is the workstation at the repository root and `H$` a shell on the named host (`ssh hp` for ops, `ssh red`, `ssh zcrypto`, `ssh mon`). `.tmp/cutover/` holds what a later step reads back. A sitting that writes into it opens with `mkdir -p .tmp/cutover`, since a `tee` into a missing directory prints its error, writes nothing and lets the sitting go on. It is disposable, so each reading goes into T0217 by the records pull request that follows it.
- **Converges.** Every converge goes through `infra/ansible/scripts/converge.sh` from merged `develop`, which previews, asks for the typed `--limit` and appends its deploy-log line, and is never wrapped in `timeout`. A preview naming anything beyond the files a step names holds that step.
- **Running digests.** A digest a converge is handed is read off its container immediately before (`docker inspect <container> --format '{{.Config.Image}}'`, the `sha256:…` after the `@`, never `.Image`) and matched against `docs/reference/fleet-pins.md`.
- **`KRAKEN`** is `curl -fsS https://status.kraken.com/api/v2/scheduled-maintenances.json | jq .`, read whole and judged by `.claude/rules/fleet-deploys.md`'s test.
- **`AUDIT`** is `uv run python infra/scripts/deploy-log-audit.py maintenance --venue-facing --since "$(cat .tmp/cutover/r0-instant)"`, which must print `rows inside an API-impacting window 0 of …` over the rows this phase appended.
- **The node's API** is read by `mon_get <path>`, the function `infra/runbooks/mon.md#mon-patch-pass` step 5 defines, pasted from there into the workstation shell; it reads the node's token through `grafana_auth` on each call, so no shell holds one. Each stack's tools token reads the silences endpoint (200 on both, read on 2026-10-08).
- **Grafana Cloud's API.** `cloud silences` is `mon.md#mon-stream-handover` read 5's read-back, which Task 5 writes. Run at a re-date and at R10, its Expected is held over every id `.tmp/cutover/cloud-silences` holds under its first line, beside read 5's own: each appears once, active, with the end it was last set or re-dated to. A re-date rewrites that first line to the new planned day, and one that mints a new id in the UI replaces the old id in that file.

**The hand-over reads** are `mon.md#mon-stream-handover`'s six, which Task 5 writes whole and every sitting below takes from that section, over one stream's `<host>`, `<container>`, `<job>`, its node dead-man `<uid>` and Grafana Cloud's rules that read it. A sitting keeps two of their outputs: read 4's silence line, its command followed by `| tee .tmp/cutover/silence-<uid>.json`, which R-records-2 reads; and read 5's silence ids, each copied into `.tmp/cutover/cloud-silences`, whose first line S1 writes as the R10 planned day their end was dated from. Read 5's end is [[ROLLOUT: the Grafana Cloud silences' end …]].

**The rollback of a moved stream** is the Global Constraints' and `mon.md#mon-stream-handover`'s *Rollback*: Task 4's commit reverted returns every stream already moved, and each of them takes its sitting again.

**The daily pass from S1 until Task 6's flip** reads Grafana Cloud when it names no stack, so its `## Alerts firing` lists each moved stream's Grafana Cloud dead-man, `firing` under its silence: `mon-stream-handover`'s case of a stream whose sitting has run, no step, its reads being `--stack mon`'s. Its `## Logs` and the journal line's `logs` clause count Grafana Cloud's Loki, which from each sitting lacks the moved stream's lines; the node's count, which holds them, is `ops-daily.py report --stack mon`'s `## Logs`.

**Preconditions.** On `develop`:
- the records branch `docs/t0217-phase-2-records`, with the drill-log entries `W1` to `W4`, the boundary bullet, T0217's phase-2 state and the `hc` edge's cookieless-`HEAD` route (`/checks/*`, `/cloaked/*`, cookie `sessionid`, its commit `276301e95`);
- plan 00123's R12 pull request (`COMPARISON_FROM = date(2026, 10, 10)`).

**R0. The operands, read once.**
- `git switch develop && git pull --ff-only && git status --porcelain` reads empty.
- `mkdir -p .tmp/cutover`; `date -u +%Y-%m-%dT%H:%M:%SZ | tee .tmp/cutover/r0-instant`.
- `KRAKEN` at planning.
- `uv run python infra/scripts/ops-daily.py report --stack mon --since 24h | tee .tmp/cutover/r0-mon-report`. Its `## Alerts firing` lists the four direct-stream dead-men, firing on the node by design. Every other row there is resolved first, or named in R3's announcement as a page the main channel will take from the node at its policy's repeat interval.

**R1. The differences, if the seven entries count any** (before Task 1's Step 4). An entry dated D carries the comparison of D − 1, the day the pass hands its runner (`ops_daily.read_comparison`). For each entry Task 1's Step 2 names, its compared day is run again while both stacks still hold it (Grafana Cloud keeps 14):

```
W$ day="$(date -u -d '<entry date> -1 day' +%F)" && uv run python infra/scripts/grafana-compare.py --day "$day" | tee ".tmp/cutover/compare-$day.txt"
```

Each difference line is re-read by `mon.md#mon-compare` step 3 at its instant, on both stacks, and its class is written beside it in the file: [[ROLLOUT: R1's differences — each line's rule, instant and class, or none]]. A run outside a pass counts for no day of the seven; this one reads the lines a pass prints only as a count.

**R2. The node's four silences, before the cutover pull request merges** (the owner's ruling of 2026-10-08; spec D22(1)). The owner, signed in on the node, opens each dead-man's silence form at `https://zcrypto-mon.zhaow.me/alerting/silence/new` with the one matcher `__alert_rule_uid__=<uid>`. Each silence ends at its sitting's planned finish, after that sitting's read 4, S4's at the close of the inter-cycle gap item 6 takes: [[ROLLOUT: the four sittings' planned finishes on the hand-over day — S1 the poller, S2 the secondary's capture, S3 the primary's an hour after S2, S4 the close of the engine's gap]]. Its comment names the sitting.

| silence | rule | ends at |
|---|---|---|
| 1 | `zcrypto-ops-poller-log-dead` | S1's finish |
| 2 | `zcrypto-capture-log-dead-secondary` | S2's finish |
| 3 | `zcrypto-capture-log-dead-primary` | S3's finish |
| 4 | `zcrypto-engine-log-dead` | S4's finish |

Then R2's read-back, `mon_get /api/alertmanager/grafana/api/v2/silences | jq -c '.[] | select(.status.state == "active") | {id, matchers, endsAt}' | tee .tmp/cutover/r2-silences`. Expected: four lines, one per uid, each with its one matcher `__alert_rule_uid__`, `"isEqual":true` and `"isRegex":false`, and its end. Nothing else active, unless the owner names it. A later re-date of one of the four, by a sitting that moves (Global Constraints) or at R5, is read back by the same line with `tee -a` in place of `tee`, so the file's last line for a uid holds its end as last set or re-dated. Rollback: each silence expired in the UI.

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

The instant is [[ROLLOUT: R3's instant — the node's receivers on the main channel, from which its seven days count]]. Rollback (D25): the same push with `vault_var("slack_shadow_webhook_url")`, and the two tests read in the shadow channel, until S1; from S1 on, in the Global Constraints' order, every moved stream returned first.

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
- T0217's `## Findings so far` gains R0's instant, R2's four silences (uid, id, end as last set), R3's instant, the two contact-point tests and R4's page.
- Its `ripe_when` becomes the date [[ROLLOUT: the hand-over day …]], the streams' earliest day, with the check `date -u +%F`.
- Its `## Suggested next steps` gains the re-date that spec D25's amendment of 2026-10-08 owes on a slip of Grafana Cloud's receiver move, read from the hand-over day on, when that date trigger has fired: until this plan's R10 has run, on the day before the end Grafana Cloud's silences carry, as `mon.md#mon-stream-handover` read 5's read-back prints it, R10's planned day is moved and each end re-dated in Grafana Cloud's UI to 00:00 UTC on the new day plus three, then read back the same way.
- `uv run python infra/scripts/topics-index.py` re-renders the index.
- `uv run pytest tests/test_open_topics_frontmatter.py tests/test_topics_index.py -q -p no:cacheprovider` passes.
- The commit is `docs(topics): T0217 — the node pages the main channel beside Grafana Cloud, its four direct-stream dead-men silenced to their sittings`.
- The pushes write no deploy-log row.

**R5. The hand-over day, planned and opened** (on [[ROLLOUT: the hand-over day …]], after the box).
- `KRAKEN` at planning.
- The four planned finishes are re-read against R2's ends. A finish that moved re-dates its silence in the node's UI first, read back and kept by R2's read-back with `tee -a`.
- R10's planned day is set, [[ROLLOUT: R10's planned day — the day planned for Grafana Cloud's push, no earlier than the hand-over day or R3's instant plus seven days]], from which S1 dates Grafana Cloud's silences' end.
- The node's delivery, read again before any stream moves to it: R3 step 4's contact-point test, its Expected unchanged. A missing message holds the day, since from S1 a moved stream pages from the node alone.
- The `logship` pair, read before any shipper presents it: phase 1's R6 push, the first command of that step in `docs/plans/00121-mon-node.md`, reading `shipped 1 dropped 0`. A refusal holds the day: the vaulted password and the node's hash disagree, and `mon.md#mon-secrets` steps 2 and 3 replace both.
- The second pull request merges through `merge-pr` before the first converge.
- `git switch develop && git pull --ff-only`.
- The bump's engine image, read before any sitting: `<bump>`, [[ROLLOUT: the November bump's engine digest — the image built from `develop` after the nautilus bump's merge, as `zcrypto-rollout-image`'s *Engine converges* takes a candidate, pulled on `zcrypto`]], present on `zcrypto`, and S4's command from R9 step 2 run early with `--check`, as `zcrypto-rollout-image`'s Phase 3 says, its preflight read as that phase's item 9 reads it. An image not ready, or a refusal, opens no sitting and leaves the day to the owner, since S4 takes no other digest (the owner's ruling of 2026-10-09).
- Each capture host's Alloy runs the digest committed for it: `H$ sudo docker inspect grafana-alloy --format '{{.Config.Image}}'` on `zcrypto-red` and on `zcrypto`, against `alloy_image_digest` in `infra/ansible/group_vars/observed/alloy.yml`. A host off it holds the day for the owner: an Alloy wave is open there, and the sittings' `--tags alloy` form would recreate Alloy.
- The day's announcement in the main channel names the four sittings, the capture gaps, the engine's converge, R10's planned day and Grafana Cloud's silences' end.
- The engine's gap is the one `engine-procedures.md#engine-rung-2-box` step 8 item 6 takes, after S3.
- If S3 cannot finish before the day's last gap that item can use, S4's hand-over is the owner's to rule (Global Constraints).

**R6. S1 — the poller on ops.**
1. `KRAKEN` immediately before.
2. `mon.md#mon-stream-handover`'s poller form: its converge from `W$`, then its recreate and its `docker inspect` read on `H$`. The preview names `logship-secrets.env` and the liquidations `compose.yaml` changed (both `no_log`, so the changed-files report is the signal) and nothing else. With the running digest, no `liquidations_decision` is asked. The poller's seconds of downtime are a gap in a stream nothing backfills.
3. `mon.md#mon-stream-handover`'s six reads over `ops`, `liquidations`, `liquidations_app`, `zcrypto-ops-poller-log-dead`, and Grafana Cloud's `zcrypto-ops-poller-log-dead` and `zcrypto-ops-error-logs`.

**R7. S2 — the secondary's capture daemon.**
1. `KRAKEN` immediately before each converge below.
2. The Global Constraints' Alloy read on `zcrypto-red`, and where the two copies differ, its `--tags alloy` form there first.
3. `W$ infra/ansible/scripts/converge.sh site.yml --limit zcrypto-red -e capture_image_digest=sha256:<running-capture> -e capture_alloy_digest=sha256:<running-alloy>`. The preview names `logship-secrets.env` and the capture `compose.yaml` changed and nothing else, Alloy's files unchanged. The handler `restart capture service` runs.
4. `zcrypto-capture`'s `StartedAt` moved and `RestartCount` 0; Alloy's `StartedAt` unmoved.
5. The capture gap the restart books is read on the pulled copy by the rollout-image skill's verify-by-outcome.
6. `mon.md#mon-stream-handover`'s six reads over `zcrypto-red`, `capture`, `capture_app`, `zcrypto-capture-log-dead-secondary`, and Grafana Cloud's `zcrypto-capture-log-dead-secondary` and `zcrypto-capture-error-logs` scoped to `host="zcrypto-red"`.

**R8. S3 — the primary's capture daemon**, its converges started no earlier than an hour after the deploy-log row of R7's capture converge was written, away from a 4-hourly boundary and from any engine restart. A row's `ts` is stamped at its run's end, and `capture-daemon.md` step 4's count pairs capture rows on the two hosts 3600 s apart or less.
1. `KRAKEN` immediately before each converge below.
2. The Global Constraints' Alloy read on `zcrypto`, and where the two copies differ, its `--tags alloy` form there first.
3. `W$ infra/ansible/scripts/converge.sh site.yml --limit zcrypto --tags capture -e converge_primary=true -e capture_image_digest=sha256:<running-capture> -e capture_alloy_digest=sha256:<running-alloy>`, never `--skip-tags engine`. The same preview and reads as S2, on `zcrypto-capture`. `zcrypto-engine`'s `StartedAt` is unmoved.
4. `H$ sudo grep -c 'zcrypto-mon.zhaow.me' /opt/zcrypto-capture/logship-secrets.env` reads `1`, a count: the file the engine reads at its next start names the node.
5. `mon.md#mon-stream-handover`'s six reads over `zcrypto`, `capture`, `capture_app`, `zcrypto-capture-log-dead-primary`, and Grafana Cloud's `zcrypto-capture-log-dead-primary` and `zcrypto-capture-error-logs` scoped to `host="zcrypto"`.

From here, an engine restart for any reason moves the engine's stream. Such a restart is not taken for it (the owner's ruling), and an unplanned one is `mon.md#mon-stream-handover`'s early case.

**R9. S4 — the engine, at the box's deferred disarm converge** (the owner's rulings of 2026-10-08 and 2026-10-09). This converge is `infra/runbooks/engine-procedures.md#engine-rung-2-box` step 8 item 6, plan 00122's R14 and the November nautilus bump's engine re-pin, and nothing else restarts the engine for the hand-over.
1. `KRAKEN` immediately before.
2. Inside the inter-cycle gap, under the procedure's restart rules and the position read it names: `W$ infra/ansible/scripts/converge.sh site.yml --limit zcrypto --tags engine -e converge_primary=true -e engine_image_digest=sha256:<bump> -e cache_proxy_image_digest=sha256:<running>`, `<bump>` R5's, never the digest `zcrypto-engine` runs, and the proxy's digest read off `zcrypto-cache-proxy`; no `engine_preflight_override` is passed.
3. The preview is the one item 6 names, as `develop` reads it after R5's pull, the re-pin's lines Task 5 writes there among them. Anything beyond item 6's preview holds the converge.
4. The procedure's disarm step 3 reads its three reasons, plan 00122's R14 reads the engine's check moved on the clone, and `zcrypto-rollout-image`'s Phase 5 reads the re-pin by outcome, the deploy-log row's `preflight` among it. A rollback of the re-pin is that skill's Phase 4, the owner's to take.
5. `mon.md#mon-stream-handover`'s six reads over `zcrypto`, `engine`, `engine_app`, `zcrypto-engine-log-dead`, and Grafana Cloud's `zcrypto-engine-log-dead` and `zcrypto-engine-error-logs`.

The four sittings' readings are [[ROLLOUT: S1 to S4 — each stream's readings on the node, its silence's ended instant, and Grafana Cloud's silences' ids]].

**R10. Grafana Cloud's receivers move last, the probe moves to the node, and the defaults flip** (spec D22(4)).
- **Preconditions:** `KRAKEN` at planning. S1 to S4 read, R4's page seen, and R3's instant plus seven days passed with the node's receivers on the main channel throughout. The announcement in the main channel says Grafana Cloud's copies leave it.
- **The node's delivery, read before the merge:** R3 step 4's contact-point test of the node, its Expected unchanged. A missing message holds the merge, and with it Grafana Cloud's push, the probe and the defaults.
- **The merge:** the third pull request merges through `merge-pr`, then `git switch develop && git pull --ff-only`. R10's remaining steps follow in the same sitting. An R10 held after the merge and before Grafana Cloud's push takes the Global Constraints' revert of the default flip before any converge of `zcrypto-ops` from `develop` that runs the ops role, `--tags ops` or un-tagged.
- **Grafana Cloud's receivers to the shadow channel.** The push skill's Step 2 holds pass, then:

```
W$ GRAFANA_URL=https://zcrypto2026.grafana.net \
     GRAFANA_SLACK_WEBHOOK_URL="$(uv run python -c 'import sys; sys.path.insert(0, "infra/scripts"); from grafana_auth import vault_var; print(vault_var("slack_shadow_webhook_url"))')" \
     GRAFANA_SA_TOKEN="$(uv run python -c 'import sys; sys.path.insert(0, "infra/scripts"); import grafana_auth as g; print(g.token("cloud"))')" \
     PATH="$PWD/.venv/bin:$PATH" ./infra/scripts/grafana-push.sh
W$ date -u +%Y-%m-%dT%H:%M:%SZ | tee .tmp/cutover/r10-instant
```

  Its first line reads `stack=https://zcrypto2026.grafana.net` and `skip-groups=zcrypto-mon zcrypto-hc`, and it reports `ORPHAN (live, of skipped group …)` for none. The owner presses the test of Grafana Cloud's `metrics` and `logs` contact points in Grafana Cloud's UI: two test messages in the shadow channel, none in the main channel. Rollback: the same push with `vault_var("slack_webhook_url")`.
- **Grafana Cloud's silences read against R10's actual day:** `cloud silences`, each end read against 00:00 UTC on R10's actual day plus three (the Global Constraints); an end that differs, the owner moves to it in Grafana Cloud's UI, rewriting `.tmp/cutover/cloud-silences`' first line to R10's day, then `cloud silences`, its Expected.
- **The probe:**
  1. `KRAKEN` immediately before.
  2. `W$ infra/ansible/scripts/converge.sh site.yml --limit zcrypto-ops --tags ops`. The preview names `/usr/local/sbin/zcrypto-grafana-watchdog` and the watchdog's service and timer units changed and nothing else.
  3. `H$ sudo grep -c 'zcrypto-mon.zhaow.me/api/health' /usr/local/sbin/zcrypto-grafana-watchdog` reads `1`, a count: the script carries a ping URL and is never printed.
  4. `H$ sudo systemctl start zcrypto-grafana-watchdog.service && sudo journalctl -u zcrypto-grafana-watchdog.service -n 5 --no-pager -o cat` shows no `curl:` line.
  5. After the next tick, `W$ uv run python infra/scripts/grafana-query.py 'hc_check_up{name="zcrypto-grafana-watchdog"}'` reads `1`: the clone's check is green against the node.

  Rollback: `converge.sh site.yml --limit zcrypto-ops --tags ops -e ops_grafana_watchdog_probe_url=https://zcrypto2026.grafana.net/api/health` until the Global Constraints' revert of the default flip merges, after R10's receiver rollback (Global Constraints).
- **The daily pass reads the node.**
  - `W$ uv run python -c 'import sys; sys.path.insert(0, "infra/scripts"); import grafana_auth as g; print(g.DEFAULT_STACK, g.GRAFANA_URL)'` reads `mon https://zcrypto-mon.zhaow.me`.
  - `W$ uv run python infra/scripts/ops-daily.py report --since 1h` prints no `## Sources that could not be read` naming a Grafana source, and its `## Alerts firing` equals `--stack mon`'s.
  - Rollback: none of its own. A source the node's default cannot read fails the same with `--stack mon` and is the node's to repair, `mon.md#mon-token-rotate` for a refused token; the revert of the default flip runs only with R10's receiver rollback (Global Constraints).
- **The dual push:** where Task 8 changed `infra/grafana/alerts.yaml`'s text, the dual push of Task 9's skill follows, the node's first.

The day is [[ROLLOUT: R10's day — Grafana Cloud's receivers moved to the shadow channel]].

**R-records-2. The cutover's records: one pull request.** From `develop`:
- The deploy-log rows of R6 to R10.
- `docs/reference/fleet-pins.md`'s `since` cells for the containers the sittings restarted: the liquidations poller, both capture daemons, and the engine, whose row S4 re-pins to `<bump>` with the replaced digest its rollback operand (`zcrypto-rollout-image`'s Phase 5), which plan 00122's records or the November rollout's may already carry from the same converge.
- `docs/reference/fleet.md`'s Services and Telemetry labels: the three direct shippers push to the node's Loki as `logship`, the node pages the main channel, Grafana Cloud pages the shadow channel, and the ops watchdog probes the node.
- T0217:
  - `## Findings so far` gains each sitting's readings and the four silences as read back, each uid with its `expired` state and the instant it ended. They come from `.tmp/cutover/silence-<uid>.json`, read in the sitting, since how long the node lists an expired silence is unread.
  - It also gains Grafana Cloud's silences' ids and ends, and R10's readings, its push instant from `.tmp/cutover/r10-instant` among them.
  - `## Done so far` gains this phase: the plan, the three pull requests, R3, the four sittings and R10.
  - `## Suggested next steps` is cut to phase 4 and lists the Resolution's phase-4 items, the hole first: from R10 the observability node and the dead-man node dark together page nothing in the main channel. Grafana Cloud's silences' end is named there: retirement's planned start, 00:00 UTC on R10's day plus three (the Global Constraints), with retirement's first act inside it: Grafana Cloud's rules deleted by uid, each confirmed 404, between D23's gate opening at R10's push instant plus two days and that end (spec D23's amendment of 2026-10-08), each written there as its UTC instant, the first from `.tmp/cutover/r10-instant`, so the deletion is planned inside them.
  - `status: partial` stays.
  - `ripe_when` becomes the date [[ROLLOUT: R10's day …]] plus two days, the day D23's gate opens at R10's push instant plus two days, so that retirement's first act falls inside Grafana Cloud's silences' end, the check `date -u +%F`. The gate's second half, nothing in the shadow channel that the node did not also page, is named in the next steps as D23's amendments of 2026-10-08 read it: over the fleet's rules' own pages alone, a page Grafana Cloud raises there on its own evaluation error, on a rule whose `execErrState` is `Alerting`, being no page the node did not also send. The read is per message: the template marks an evaluation error on a message's first alert alone (`infra/grafana/notification-templates/zcrypto-slack.tmpl`, the `zcrypto.errctx` block at `$i` 0). A silent shadow channel counts only from a Grafana Cloud read evaluating: its rules' `lastEvaluation` through `/api/prometheus/grafana/api/v1/rules` with `grafana_auth.token("cloud")`, inside the groups' 60 s interval of the read.
- `uv run python infra/scripts/topics-index.py`.
- `AUDIT`, its count 0.
- `uv run pytest tests/test_deploy_log.py tests/test_deploy_log_audit.py tests/test_fleet_contracts.py tests/test_pins_converged.py tests/test_open_topics_frontmatter.py tests/test_topics_index.py -q -p no:cacheprovider`.
- The commit is `chore(fleet): the observability node pages the main channel, the direct-shipped streams ship to it, and Grafana Cloud pages the shadow channel`, its message carrying every slot's reading, with the trailer.

## Resolution

It settles what the spec left to this phase:
- the cutover pull request is the first of three, and its gate is Task 1's reads;
- the engine's hand-over is the box's deferred disarm converge, shared with plan 00122's R14, and the November nautilus bump's engine re-pin on the bump's own digest, the owner's rulings of 2026-10-08 and 2026-10-09;
- the node's four silences end at their sittings and are read back, the owner's ruling;
- Grafana Cloud's silences are scoped to the moved stream, their end retirement's planned start, 00:00 UTC on R10's day plus three (spec D25's and D23's amendments of 2026-10-08), re-dated before the end passes on a slip of R10 by T0217's next step and read at R10 against its actual day, and retirement's first act, the deletion of Grafana Cloud's rules, falls inside that end (spec D23's amendment of 2026-10-08);
- the order of the rollbacks once a stream has moved (Global Constraints);
- the guards on Grafana Cloud's logship token move with the templates;
- `grafana-cloud-dark` becomes `grafana-dark`;
- the line between the operator surfaces this phase re-trues and phase 4's.

It does not deliver phase 4, which takes from this plan:
- `logship_loki_token`, read by no role after Task 4, free to leave the vault with the other Grafana Cloud values, and with them the comment in `group_vars/observed/vault.yml` that names `logship-secrets.env.j2` as the reader of `grafana_loki_url` and `grafana_loki_user`, false from Task 4 and left there because no executor prints that file;
- the comments in `roles/capture/files/config.alloy` (lines 184-186 at this plan's base) and `roles/ops/files/config.alloy` (238-239 and 321-323) that name Grafana Cloud as the capture daemon's and the poller's direct-push destination, left because an edit to a `config.alloy` arms its role's drift assert on every host the file serves until each is converged (spec D14), and T0085's rotation scope naming `logship_loki_token`, a Grafana Cloud credential until phase 4 revokes it;
- the deletion of Grafana Cloud's rules by uid as retirement's first act, inside its silences' end, the silences, matching nothing once the rules are gone, running out at their own end (spec D23's amendment of 2026-10-08), and the deletion lasting only while no push reaches Grafana Cloud: until the stack table holds one row a push goes to both stacks, and `grafana-push.sh` creates each rule whose GET does not answer 200;
- the shadow channel's read for retirement's gate, over the fleet's rules' own pages alone, a page Grafana Cloud raises on its own evaluation error, on a rule whose `execErrState` is `Alerting`, not counting (spec D23's amendment of 2026-10-08), read per message, since the template marks that error on a message's first alert alone (`zcrypto-slack.tmpl`, the `zcrypto.errctx` block at `$i` 0), and from a Grafana Cloud read evaluating (R-records-2);
- `observability.md#grafana-dark`'s clause on Grafana Cloud's shadow-channel pages, and the hole it states while both nodes are dark, which that phase's plan answers or carries;
- the class (b) lines of the pager sweep;
- the skills' dual-period clauses, `GRAFANA_SKIP_RULE_GROUPS`, the stack table's second row and `mon.md`'s `mon-compare`, `mon-push` dual wording and `mon-stream-handover`, each of which retires with the table.

## Slots the rollout fills

- `[[ROLLOUT: the gate's day — the seventh consecutive journal entry from 2026-10-10 whose compare line reads 0 differences or differences the pull request explains]]` (Task 1) — Task 1's Step 2, into T0217 and the cutover pull request's body.
- `[[ROLLOUT: R1's differences — each line's rule, instant and class, or none]]` (R1; Task 1) — R1's files, into Task 1's bullet.
- `[[ROLLOUT: the hand-over day — the box's deferred disarm converge's day, Mon 2026-11-02 as that item names it]]` (Global Constraints; Task 5; R5; R-records-1) — `engine-procedures.md#engine-rung-2-box` step 8 item 6, read at R-records-1.
- `[[ROLLOUT: the four sittings' planned finishes on the hand-over day — S1 the poller, S2 the secondary's capture, S3 the primary's an hour after S2, S4 the close of the engine's gap]]` (Global Constraints; R2; R5) — set at R2, re-dated at R5 if a finish moved.
- `[[ROLLOUT: the November bump's engine digest — the image built from `develop` after the nautilus bump's merge, as `zcrypto-rollout-image`'s *Engine converges* takes a candidate, pulled on `zcrypto`]]` (R5; R9) — read at R5 and passed in S4, into R-records-2.
- `[[ROLLOUT: R3's instant — the node's receivers on the main channel, from which its seven days count]]` (R3; R10) — into R-records-1.
- `[[ROLLOUT: R4's page — its rule, its time and where its three links landed]]` (R4) — into R-records-1.
- `[[ROLLOUT: the Grafana Cloud silences' end — the instant spec D25's amendment of 2026-10-08 names]]` (Global Constraints; the hand-over reads; R10) — 00:00 UTC on R10's day plus three (the Global Constraints), set in S1 against R10's planned day, carried by S2 to S4, re-dated before the end passes on a slip of R10 by T0217's next step from R-records-1, and read at R10 against its actual day.
- `[[ROLLOUT: R10's planned day — the day planned for Grafana Cloud's push, no earlier than the hand-over day or R3's instant plus seven days]]` (R5; the hand-over reads) — set at R5, into the day's announcement and `.tmp/cutover/cloud-silences`' first line, moved by a re-date, and into R-records-2.
- `[[ROLLOUT: S1 to S4 — each stream's readings on the node, its silence's ended instant, and Grafana Cloud's silences' ids]]` (R6 to R9) — into R-records-2.
- `[[ROLLOUT: R10's day — Grafana Cloud's receivers moved to the shadow channel]]` (R10; R-records-2) — plus two days, T0217's `ripe_when`; plus three, the end R10 reads Grafana Cloud's silences against.
