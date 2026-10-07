# One Alloy version across the fleet: a shared `alloy` tag, the apt Alloys held at the fleet's version, and one wave — implementation plan

> Every value a rollout reading decides is a marked slot, `ROLLOUT:` inside double square brackets, listed at the end.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every host of the inventory's `observed` group runs the Alloy version one committed file names, `infra/ansible/group_vars/observed/alloy.yml`, and reaches it by one converge, `--tags alloy`: the container roles bring their container to the fleet's digest and read the image it runs, the apt roles hold and pin the package at the fleet's deb version and restart a process that predates the binary, and `converge.sh` refuses an `alloy` run that would land nothing. A bump moves to a version only when the image registry and the apt index both carry it, the record and its count show a host off the version, and the observability node pages a split fleet. The first wave brings the fleet's three versions to one inside rung 2's box, the capture pair dual-shipping to the node with it. The capture role's share of the tag, the NAS's Alloy-only form and plan 00121's Task 7 are on this branch already and are task-reviewed here, not rebuilt.

**Architecture:** Twenty-one tasks on this branch, once it has merged `develop`, merged as one pull request, then an attended wave. A review task first pays the debt of the twelve commits built outside a plan. Then the fleet file and its operands; one walk of `site.yml`, the inventory and the roles' task files in `infra/scripts/alloy-version.py`, which every tag test and `converge.sh` read; the three container roles' refusal of an operand that is not the digest committed for the host, their recreate and their image read, ops and the cache nodes joining the tag; the NAS writing its own Alloy pin line; a shared role, `alloy_apt`, whose two task files the access and mon roles import under the tag; `converge.sh`'s refusal and the fleet-wide tag tests; the gate and the count; the node's split rule; plan 00121's Task 8 in the tag form; the runbook and reference pages; the rule and the two skills in `claude` commits of their own; the amendments spec 00121 and plan 00121 owe; and, after the gate's live reading, the fleet file at its target. The Rollout records the gate's fixtures, reads the gate, opens the pull request, merges it on the wave's day and runs the wave host by host in spec D12's order, each host's verification the only gate to the next.

**Tech Stack:** Grafana Alloy (the fleet's container pin v1.19.2, `grafana/alloy@sha256:b8ec653c4423…`; the node's apt `1.20.1-1`, the bridgehead's `1.20.0-1`; the target the gate reads, 1.20.1 at the readings of 2026-10-05), Ansible (ansible-core 2.21.4; the `capture`, `ops`, `cache`, `nas`, `access` and `mon` roles, a new shared `alloy_apt` role), the apt module's `allow_downgrade` and `allow_change_held_packages`, apt preferences, `dpkg_selections`, Docker Compose 5.5.1 on the container hosts and 2.20.1 on the NAS, Docker Hub's tag listing and registry API, apt.grafana.com's `Packages` index, Prometheus and Grafana on the node, pytest, `infra/scripts/mutate-probe.sh` for guard verdicts, Python 3.14 through `uv run`.

**Spec:** `docs/specs/00123-one-alloy-version-design.md` at the commit this plan is read at: D1 to D18 as the owner's rulings of 2026-10-05 and 2026-10-06 settle them, "What changes in the repo", "What this asks of plans 00121 and 00122", the invariants, the measured basis and "Not confirmed here". Plan 00121, `docs/plans/00121-dual-shipping.md`, supplies Task 7's text (Task 1 reviews against it), Task 8's text (Task 13 carries it), the per-host proof, the dry-start form and R7 to R9. Plan 00122, `docs/plans/00122-self-hosted-dead-man.md` on `develop`, takes a requirement from Task 8 and is not edited.

## Global Constraints

- No executor step reaches a host, a registry, an apt repository, a venue, Grafana Cloud, the observability node, the NAS, Slack or healthchecks.io; each such step is an operator step of the Rollout, attended, `W$` the workstation at the repository root and `H$` a shell on the named host. An executor's one network read is a GitHub release asset for a dry-start, the form plan 00121's executors used.
- `ansible-playbook` is never run by an executor in any form, `--syntax-check`, `--check` and `--list-tasks` included: this workstation is the fleet host `zcrypto-ops`. A role's YAML is proven by the tests' walk and the commit gate's `ansible-lint`. `infra/ansible/scripts/converge.sh` runs in the Rollout alone, from merged `develop`, and is never wrapped in `timeout`.
- The primary takes only `--tags alloy -e converge_primary=true` with `capture_alloy_digest`: the fleet's `<alloy_image_digest>` in its wave, or the previous digest beside `-e '{"alloy_override": "<reason>"}'` in spec D16's one-host rollback (Task 17's form, the Rollout's stop conditions); never a whole-role, `--skip-tags engine` or un-tagged run. Nothing of this package touches the engine role, the engine play or the engine's config while rung 2's box holds: no task edits `roles/engine/`, `roles/cache_link/` or the engine play of `site.yml`, and `tests/test_capture_alloy_tag.py::test_an_alloy_run_on_the_capture_and_engine_plays_runs_the_alloy_part_beside_the_always_pre_tasks` keeps holding what the primary's run selects.
- The NAS's puller, `archive-pull`, is never restarted or recreated by the narrow form: `tests/test_nas_alloy_tag.py`'s exclusion and parity cases hold it, and Task 7 changes them only where spec D6 and the exclusion allowlist of spec D5's *Guards* say.
- A guard is proven by `infra/scripts/mutate-probe.sh`, one probe at a time, in-repo on the committed tree, each with a control that must fail the probe and a mutation whose verdict is recorded; every run ends `mutate-probe: KILLED (control proven, tree restored byte-identically)`. The commit is made with the line `PROBE_VERDICT` in its message, and a message-only amend with the tree clean replaces it with each probe's command and verdict; the branch is unpushed while the tasks run, so the amend rewrites nothing a reader holds. A mutation that makes a `that:` or a `when:` always true writes the string `"true"`, never the YAML boolean `true`: the cases hand each conditional to Ansible's templating as a string (`tests/test_infra_converge_guards.py::truthy`), which refuses a boolean with a `TypeError` before any assertion reads it, a KILLED for a reason no case holds — every `made "true"` of Tasks 4 to 8, and Task 1's re-run of `b5f1a96d2`'s fourth and seventh probes. Likewise a mutation whose named form would raise before its case's assertion reads it is written so that the assertion is what fails, as Task 3's `include_role` arm and Task 11's registry-alone target and failed apt index are.
- A real vaulted file — any `vault.yml` under `infra/ansible/`, `infra/ansible/files/zaccess_ca.key.vault` and `infra/ansible/vault-password.sops.yaml` — is never read, printed, grepped, diffed or copied by an executor, so a recursive grep given `infra/` carries `--exclude='*vault*' --exclude='*.sops.*'` (the consumer greps of Tasks 3, 8, 10 and 13); `ansible-inventory` is never run. No secret appears in a command line, a log, a diff or a plan step.
- No container's environment is printed: every `docker inspect` here names its fields, each one of `.Config.Image`, `.State.StartedAt`, `.Created`, `.RestartCount` or `.Name`, never `.Config.Env`, `{{json .Config}}`, `docker exec … env` or `docker compose config`.
- `tests/test_internal_terms_not_operator_visible.py`'s surfaces — the runbook pages, the rule annotations, the role task names and messages it walks — carry no `Phase <N>`, `T<NNNN>`, `iter-<N>`, `spec <NNNNN>`, `D<N>` or `WP<N>`; a provenance token goes in an adjacent code comment.
- Python 3.14 through `uv run` (`.python-version`); PEP 758's `except A, B:` is valid syntax.
- The commit gate, before every commit: the commit's files staged by path, its new files among them, then `uv run pre-commit run -a` until clean, its rewrites staged. Conventional Commits. A `.claude/` change rides a `claude(...)` commit carrying no other file (Tasks 16, 17 and 18), and `zcrypto-refine-rules` is loaded before each edit to the rule, a skill or a top-level page under `infra/runbooks/` (Tasks 12, 14, 16, 17 and 18), every guidance line landing on one of its four grounds with the check that enforces it named in the line.
- Every commit is green over its consumers: the task's own tests, and every test file `grep -rl` names for each script, role, template or config the task changes, the data-gated ones among them, never the full suite locally. A task that edits a page under `infra/runbooks/` also runs `tests/test_internal_terms_not_operator_visible.py`, `tests/test_runbook_internal_tokens.py`, `tests/test_runbook_triggers.py`, `tests/test_guidance_guard.py` and `tests/test_guidance_refs_resolve.py`; any other task that adds or edits text `tests/test_internal_terms_not_operator_visible.py` walks — an Ansible task name or `msg`/`fail_msg`, a string literal under `infra/scripts/`, an output line of a shell script under `infra/` — runs that file too; and one that changes a role's task or handler file runs `tests/test_infra_converge_guards.py`, whatever its grep names.
- A new Markdown paragraph or list item is one line; an existing file keeps its form. A universal word (every, never, always, only, any, cannot) in a new list item of a runbook page, the rule, `docs/reference/fleet.md` or `docs/reference/fleet-pins.md` carries its `(set: …; count: …)` or `(no count command: …)`, or the item is worded without it.
- A code comment, task name or task message a task's edit falsifies is re-trued in that task's commit, and its Files entry names it. An operator page — a runbook, `infra/nas/README.md`, `infra/ops/README.md`, `docs/reference/fleet.md` — and a `.claude/` file that a code task falsifies is re-trued by Tasks 14 to 18, one place per page, since the package merges as one pull request and no page is read from this branch before it; each of those tasks lists the lines.
- Every reviewer — Task 1's, each task's, the branch's — runs on Opus, the model passed explicitly.
- The dry-start form is the dry-start form of plan 00121's Global Constraints, `docs/plans/00121-dual-shipping.md`, against the release binary of the version the fleet file names when the task runs, unless the step names another, with one change: the copy also points every loopback address it dials — each scrape `__address__`, each `redis_addr` and each URL on `127.0.0.1` — at `127.0.0.1:9`, a closed port, as the form points each `*_URL`, since this workstation is `zcrypto-ops` and a loopback port there can be a live service (the liquidations poller's metrics on `9103`, a Valkey on `6379`); the form's Expected then admits, on the cache config, `Couldn't connect to redis instance` lines and no other `level=error` line, uncounted, their number set by when the exporters' scrapes land. The release zip stores `alloy-linux-amd64` without its execute bit, so every unzip of it here is followed by `chmod +x` on the binary — the dry-starts and the validates of Task 8's Step 4, Task 13's Step 4 and Task 20's Step 2.
- A commit message ends with this trailer, the placeholder replaced by the executing model's own name, followed by the executing session's `Claude-Session:` line where its harness supplies one:

```
Co-Authored-By: Claude <actual executing model> <noreply@anthropic.com>
```

## File structure

- `infra/ansible/group_vars/observed/alloy.yml` (new): the fleet's three values (Task 2; its comment's gate named by Task 11; moved to the gate's reading by Task 20).
- `infra/ansible/host_vars/nas/vars.yml`: `nas_alloy_image`, held equal to the NAS's committed digest, the fleet file's unless the NAS's hold file names another (Task 2's test; moved by Task 20).
- `infra/ansible/scripts/converge.sh`: `alloy_override`, `alloy_deb_version` beside it (Task 2); the `alloy` reach refusal (Task 10); the `TAGNAMES` comment (Task 3).
- `infra/scripts/alloy-version.py` (new) and `tests/test_alloy_version.py` (new): `reaches` (Task 3), `off-fleet` and `gate` (Task 11); `tests/fixtures/alloy_version/` (new, Task 11, recorded by the Rollout's P1).
- `infra/ansible/roles/capture/tasks/main.yml` (Tasks 4 and 13), `roles/ops/tasks/main.yml` (Task 5), `roles/cache/tasks/main.yml` (Task 6): the fleet-digest refusal, the recreate, the image read; ops and cache the tag, the fail-fast; the three roles' `templates/alloy-compose.yaml.j2` and `handlers/main.yml`, their comments re-trued for the recreate (the same tasks).
- `infra/ansible/roles/nas/tasks/main.yml`: the `ALLOY_IMAGE=` line and the post-recreate image read (Task 7).
- `infra/ansible/roles/alloy_apt/tasks/main.yml` and `postcondition.yml` (new, Task 8); `roles/access/tasks/main.yml` and `.pre-commit-config.yaml`'s `ansible-lint` entry (Task 8); `roles/mon/tasks/main.yml` and `handlers/main.yml` (Task 9).
- `tests/test_capture_alloy_tag.py` (Tasks 3, 4, 5, 6, 8, 9, 10), `tests/test_nas_alloy_tag.py` (Tasks 3, 7), `tests/test_ops_alloy_tag.py` (new, Task 5), `tests/test_cache_alloy_tag.py` (new, Task 6), `tests/test_alloy_container_recreate.py` (new, Task 4, widened by Tasks 5 and 6), `tests/test_infra_alloy_apt.py` (new, Task 8), `tests/test_access_alloy_tag.py` (new, Task 8), `tests/test_mon_alloy_tag.py` (new, Task 9), `tests/test_infra_mon_role.py` (Task 9), `tests/test_infra_converge_guards.py` (Task 9), `tests/test_alloy_tag.py` (new, Task 10), `tests/test_converge_sh.py` (Tasks 2, 10), `tests/test_fleet_contracts.py` (Tasks 2, 11), `tests/test_count_list.py` (Task 11), `tests/test_infra_alert_rules.py` (Task 12), `tests/test_infra_alloy_series.py` (Task 13).
- `infra/scripts/count-list.sh`: `hosts-off-the-fleets-alloy-version` (Task 11); `docs/reference/fleet-pins.md`'s non-image paragraph (Task 11).
- `infra/grafana/alerts.yaml`, `infra/grafana/fleet-health-dashboard.json`, `infra/runbooks/mon.md`'s new section (Task 12).
- `infra/ansible/roles/capture/templates/alloy-secrets.env.j2` and `files/config.alloy` (Task 13).
- The runbook pages and the two READMEs (Task 14); `docs/reference/fleet.md` (Task 15); `.claude/rules/fleet-deploys.md` (Task 16); `.claude/skills/zcrypto-bump-alloy/SKILL.md` (Task 17); `.claude/skills/zcrypto-rollout-image/SKILL.md` (Task 18); `docs/specs/00121-self-hosted-observability-design.md` and `docs/plans/00121-dual-shipping.md` (Task 19); `docs/open-topics/T0219-one-alloy-version-across-the-fleet.md` and the index (Task 21).
- `docs/reference/deploy-log.jsonl`, the `fleet-pins.md` rows, `drill-log.md`, T0217 and the measured-basis amendments: the records branch `docs/t0217-phase-2-records`, after the wave, not a task's.

## Review Focus

Five classes, each held by the tests of the tasks named beside it.

- An `alloy` run that reaches past Alloy — a capture daemon, the engine, the liquidations poller, Valkey or Sentinel, `archive-pull`, Caddy, WireGuard, the SSH relay, Grafana or its stores: each role's exclusion test, the family's six cases — capture (Task 4), ops (Task 5), cache (Task 6), the NAS (Task 7), access (Task 8) and mon (Task 9) — each carrying beside its named refusals one module allowlist of its own: the modules a tagged task may use with any arguments, those that change nothing on the host; a `file`, `copy` or `template` task only while its `path` or `dest`, as the task writes it, lies on the role's Alloy paths — capture's, ops' and the cache's Alloy directory, the NAS's config directory and its two Alloy files, the apt roles' `/etc/alloy` and the bridgehead's `/etc/default/alloy`; and the tasks admitted only verbatim, module and arguments, every tagged `user`, `deb822_repository`, `command`, `shell`, `systemd`, `systemd_service`, `service`, `apt`, `package`, `dpkg_selections`, `reboot` or `meta` task among them, the access and mon cases taking `alloy_apt`'s share from one pair of constants — and the fleet-wide play-selection test, `tests/test_alloy_tag.py::test_an_alloy_run_runs_each_plays_always_tasks_and_its_alloy_part_and_nothing_else` (Tasks 3 to 10).
- A run that claims a version it did not land: the container roles' image read (Tasks 4 to 7), the apt post-condition on the bridgehead's shape and the node's (Task 8), the fail-fast (Tasks 5 and 6), `converge.sh`'s reach refusal (Task 10), and the NAS row's contract during a wave (Task 2).
- The hold and the pin: `Pin-Priority: 1001` exactly, the hold after the install, the install at `alloy_deb_version` with both options, the access role's Alloy after the revocation path (Tasks 8 and 9); no role but `alloy_apt` installing or holding the package, and none bringing `alloy_apt` in by an include (Task 10).
- The fleet file as the one source: the NAS literal held to it and every operand refused off it without a reasoned override, a held host's hold file — the NAS's among them — standing in for it there; the gate's target present in both sources with its index digest and the index's own deb string (Tasks 2, 4 to 9, 11 and 20).
- A converge outside its bounds: the primary in any form but its one, a cache node outside the day's window, a venue-facing host inside a Kraken window, the NAS's puller touched (the Rollout).

---

### Before Task 1: the branch merges `develop`

Tasks 9 and 12 are written against `develop` at `414097c23`, whose mon role includes Caddy from a shared `edge` role and its secret refusal, reboot check and self-check from `node_common` task files, and whose alert-rule test holds the node-only rule groups in `NODE_ONLY_GROUPS`; the branch merged `develop` at `a12c85d1d`, which holds it, and Step 1 merges any later move of `develop`, so Task 1's probes and consumers run on the merged tree.

- [ ] **Step 1: Merge** — `git fetch origin`, then `git merge origin/develop`, its message `Merge origin/develop into feat/t0219-one-alloy-version` and the trailer; a merge and never a rebase, so the twelve commits Task 1 reads keep their hashes. Expected: no conflict, and `Already up to date`, with no commit, while `develop` has not moved since `a12c85d1d`.
- [ ] **Step 2: The consumers of both sides** — the test files the branch's last merge changed, read against that merge's first parent, the tip before it, beside Task 1's Step 3 list; the merge is named, `git log -1 --merges --first-parent`, never read as `HEAD`, so a re-run after a fix commit selects the same files; when Step 1 merged nothing, the last merge is `a12c85d1d` and the test files it changed run again, a selection wider than the step needs and never narrower:

```bash
m=$(git log -1 --merges --first-parent --format=%H)
uv run pytest $(git diff --name-only --diff-filter=d "$m^1" "$m" -- 'tests/test_*.py') tests/test_capture_alloy_tag.py tests/test_nas_alloy_tag.py tests/test_pins_converged.py tests/test_converge_sh.py tests/test_count_list.py tests/test_deploy_log_audit.py tests/test_infra_alloy_series.py tests/test_infra_converge_guards.py tests/test_ops_daily.py tests/test_internal_terms_not_operator_visible.py tests/test_runbook_internal_tokens.py tests/test_runbook_triggers.py tests/test_code_prose_citations.py -q -p no:cacheprovider
```

Expected: no failure. A failure is the two sides disagreeing in meaning, fixed in a commit of its own before Task 1, its guard's probe recorded as the Global Constraints say.

- [ ] **Step 3: The tree is clean** — `git status --porcelain`; Expected: empty.

---

### Task 1: The task-review debt — the twelve commits built outside a plan, read against what they were built for

The branch carries twelve commits that were built and probed but never task-reviewed. This task is their review; it changes no file unless a finding does, and a finding's fix is a commit of its own, never an amend, its guard proven by the probe.

**The commits and what a reviewer reads them against:**
- The capture role's share of the tag: `af6f5c131` (the tag, the fail-fast, `tests/test_capture_alloy_tag.py`), `013e345af` (`converge.sh`'s whitelist, the capture-pair count), `34746b383` (runbook pages), `4bb20b2cd` and `496493ed1` (`claude` commits on the bump and rollout skills), `b5f1a96d2` (the rename to the fleet-wide `alloy`). Against the spec's D5 *Guards* — selection (the tagged tasks by name and their notifies), closure (every name a tagged task or a notified handler reads produced by an earlier tagged task) and exclusion (nothing of the capture daemon: its compose render, its unit, `capture_image_digest`, `restart capture service`) — D7's fail-fast and play selection, D13's premise that `--tags alloy` reaches neither the engine nor the capture daemon on the primary, and the readers of a converge's tags (`infra/scripts/count-list.sh`'s capture-pair count, `infra/scripts/pins-converged.py`, `infra/scripts/deploy-log-audit.py`, `infra/scripts/ops_daily.py`) reading an `alloy` row as the rules need. The two `claude` commits are read under `.claude/skills/zcrypto-refine-rules/SKILL.md`'s *Before you write guidance*; their sentence that only the capture role carries the tag is Task 17's to re-true. The exclusion case's module allowlist, which D5's *Guards* ask of every role, is Task 4's to add, not a finding here.
- Plan 00121's Task 7, the NAS shipping to the node: `1408962dc` and `bac386834`. Against Task 7's text in `docs/plans/00121-dual-shipping.md` — its Files (the config's second endpoint, `loki.write "mon"`, the `forward_to`, the `netdev` exclusion; the template's six `MON_*` lines and its re-trued header; the role's comment; the README's names), its guards parametrised over the NAS file and template, its Step 4 dry-start against v1.19.2 and its Step 10's six mutations — and the class walk plan 00121's Review Focus names for a dual-shipping config. Task 7's "merges in a pull request of its own after the box" is superseded by the spec's D13 and D14 and is not a finding; Task 19 records the supersession.
- The NAS's Alloy-only form: `005ffa179` (the tag, the block, `tests/test_nas_alloy_tag.py`), `4d862a375` (`converge.sh`, `pins-converged.py`'s narrow-row evidence), `c7bd5e6e6` (the README and three runbook pages), and `c734bd635` (the capture carriers list widened to the nas role). Against D6's *The NAS* bullet as built (the config and secrets file landed, the `.env` read and refusal, `compose up -d --no-deps --force-recreate alloy`, never `archive-pull`, a whole converge unchanged), D17 (an applied `alloy` row evidences the committed `grafana/alloy@` pins and nothing else; a render-only row nothing) and the same tag readers. The narrow form's render-only `--tags nas` precondition is superseded by D6's decision and changed by Task 7, and the exclusion case's module allowlist of D5's *Guards* is Task 7's to add; neither is a finding here.

- [ ] **Step 1: The reviews** — three task reviewers, one per group above, each reading its commits whole (`git show <sha>` for each) against the text named, and returning findings as Critical, Important or Minor with the file and line.
- [ ] **Step 2: Re-run every probe the commit messages quote, at this branch's tip** — each command exactly as its message prints it, from the repository root, and `1408962dc`'s eight, which its message gives in prose, composed from that prose; Expected: each ends `mutate-probe: KILLED (control proven, tree restored byte-identically)`. A probe that no longer runs as printed — a later commit moved its control's or its mutation's text, renamed the test its `-k` selects (`b5f1a96d2`'s sixth, whose `test_no_other_role_and_no_play_carries_the_tag_yet` `c734bd635` renamed), or left its sed a no-op (`4d862a375`'s first, `alloy` now following `capture` in `TAGNAMES`) — or whose mutation writes the YAML boolean `true` (`b5f1a96d2`'s fourth and seventh, re-run with `"true"` as the Global Constraints say), is re-composed on the same guard and recorded as such in the review; the probes of `af6f5c131` and `013e345af`, whose `capture-alloy` text `b5f1a96d2` renamed, are run in `b5f1a96d2`'s form.
- [ ] **Step 3: The consumers at the tip**

```bash
uv run pytest tests/test_capture_alloy_tag.py tests/test_nas_alloy_tag.py tests/test_pins_converged.py tests/test_converge_sh.py tests/test_count_list.py tests/test_deploy_log_audit.py tests/test_infra_alloy_series.py tests/test_infra_converge_guards.py tests/test_ops_daily.py tests/test_internal_terms_not_operator_visible.py tests/test_runbook_internal_tokens.py tests/test_runbook_triggers.py tests/test_code_prose_citations.py -q -p no:cacheprovider
```

Expected: no failure; a skip only where its reason names a missing `develop` ref or an `alloy` binary off PATH.

- [ ] **Step 4: Fix each Critical and Important finding** in a commit of its own, `fix(infra): <what was wrong>`, its guard's probe recorded as the Global Constraints say; fold the Minors once in one commit or name each dropped one in the pull request body.
- [ ] **Step 5: The tree is clean** — `git status --porcelain`; Expected: empty.

---

### Task 2: The fleet file — one committed version, the NAS literal held to it, and the Alloy override

**Files:**
- Create: `infra/ansible/group_vars/observed/alloy.yml`
- Modify: `infra/ansible/scripts/converge.sh` (`OVERRIDES` gains `alloy_override`, the comment above it reading five, not four, as does the `PYCHK` heredoc's comment, "each of the four asserts"; `EVKEYS` gains `alloy_deb_version`, its comment naming spec 00123's rollback; a refusal of an `alloy_deb_version` operand that no `alloy_override` operand rides beside, before the preview)
- Test: `tests/test_fleet_contracts.py` (`test_the_fleet_file_carries_three_values_in_their_shapes`; `test_the_nas_alloy_literal_is_the_nas_committed_digest`; `test_the_nas_rows_agree_with_the_committed_pins` changed for the NAS Alloy row)
- Test: `tests/test_converge_sh.py` (`PUBLISHED` gains the two one-host rollback forms; `OUTSIDE` gains the deb version with no reason and the override as `k=v`; `test_the_json_override_operand_is_recorded_whole`'s docstring, "the four names travel as JSON", made count-free)

**Interfaces:**
- Consumes: `fleet-pins.md`'s full digest of v1.19.2, `b8ec653c44235fbe910879145dac3597d66b0aaecf60bcbbe82580767771a839`, and the apt index's `1.19.2-1` (the spec's measured basis); `converge.sh`'s `OVERRIDES` check, which already parses a braced operand and names the override.
- Produces, for every later task and the Rollout: `alloy_version`, `alloy_image_digest`, `alloy_deb_version` in the `observed` group; `-e '{"alloy_override": "<reason>"}'` and `-e alloy_deb_version=<previous>` beside it as `converge.sh` operands; the NAS row's contract during a wave.

**What this task decides, where the spec leaves it open:**
- The file starts at the version seven of the nine Alloys run, v1.19.2, its index digest and `1.19.2-1`: the three values are true of the container fleet today, and the move to the gate's target is Task 20's, a commit of its own from R0's reading, so this task writes no value read off the network.
- `tests/test_fleet_contracts.py::test_the_nas_rows_agree_with_the_committed_pins` holds the NAS's two committed pins equal to their `fleet-pins.md` rows, and `tests/test_pins_converged.py::test_the_real_pair_reads_zero` holds every row converged; with D2's equality the NAS literal moves with the fleet file, before the NAS's wave converge, while its row keeps what the NAS runs until that converge's records. The NAS Alloy row is therefore held equal to the committed literal, or, while a wave is open, to a converged digest while the literal is the fleet file's: the test admits a row behind the literal only when the literal is `grafana/alloy@<alloy_image_digest>` and another `alloy` row of the image table, of a host with no `infra/ansible/host_vars/<host>/alloy.yml`, is off `alloy_image_digest` too, the wave visibly open in the same file, so a NAS row the records leave behind fails once the other rows are re-trued; a held host's row is off by design, and counting it would keep the arm open while the hold stands. The NAS's own hold has its exit in the same arm: the row is admitted behind a literal equal to the fleet's also while its digest cell carries `held`, the word before the reason a held row keeps until the NAS's converge re-trues it (spec D16), so the change that ends the hold — the hold file deleted and the literal moved to the fleet's digest — merges before the NAS converges from it. The `archive-pull` row keeps the strict equality. The row stays the truth of what the NAS runs, the count of Task 11 reads the NAS off through the wave, and a literal moved anywhere but to the NAS's committed digest still fails.
- `alloy_deb_version` is admitted as an operand only beside an `alloy_override` operand: alone it would move an apt host off the fleet's version with no reason on the record.
- The literal test reads the NAS's committed digest as `alloy_apt` reads an apt host's version (Task 8): `alloy_image_digest` in `infra/ansible/host_vars/nas/alloy.yml` while the NAS is held (spec D16), else the fleet file's; a hold sets `nas_alloy_image` back in the same commit, so every NAS converge from it lands the previous pin.

The fleet file, determined by D2 and the measured basis:

```yaml
---
# The fleet's one Alloy version: every Alloy of the `observed` group runs it outside a wave. A bump writes the three
# together from one reading of the gate in .claude/skills/zcrypto-bump-alloy/SKILL.md's Step 0, and moves
# `nas_alloy_image` in host_vars/nas/vars.yml with them; no value is derived from another.
alloy_version: "1.19.2"
alloy_image_digest: sha256:b8ec653c44235fbe910879145dac3597d66b0aaecf60bcbbe82580767771a839
alloy_deb_version: "1.19.2-1"
```

The refusal, after the operand loop and before the preview:

```bash
# `alloy_deb_version` moves an apt host off the fleet file's version (spec 00123 D16), so it travels beside a reason.
has_deb=0; has_override=0
OLDIFS="$IFS"; IFS=$'\x1e'
for op in $EV; do
  case "$op" in
    alloy_deb_version=*) has_deb=1 ;;
    '{'*'"alloy_override"'*) has_override=1 ;;
  esac
done
IFS="$OLDIFS"
[ "$has_deb" -eq 0 ] || [ "$has_override" -eq 1 ] \
  || refuse "alloy_deb_version moves an apt host off the fleet's version: pass it beside -e '{\"alloy_override\": \"<why>\"}'"
```

The literal test's shape:

```python
ALLOY_FILE = REPO / "infra" / "ansible" / "group_vars" / "observed" / "alloy.yml"
NAS_HOLD = REPO / "infra" / "ansible" / "host_vars" / "nas" / "alloy.yml"


def _nas_literal_is_committed(nas_vars: Path, hold: Path, fleet: Path) -> bool:
    committed = yaml.safe_load((hold if hold.exists() else fleet).read_text())
    (literal,) = re.findall(r"^nas_alloy_image:\s*(\S+@sha256:[0-9a-f]{64})\s*$", nas_vars.read_text(), re.M)
    return literal == f"grafana/alloy@{committed['alloy_image_digest']}"


def test_the_nas_alloy_literal_is_the_nas_committed_digest():
    assert _nas_literal_is_committed(NAS_VARS, NAS_HOLD, ALLOY_FILE)
```

- [ ] **Step 1: Write the failing tests** — the shape test (keys exactly the three; `alloy_version` `^\d+\.\d+\.\d+$`; `alloy_image_digest` `^sha256:[0-9a-f]{64}$`; `alloy_deb_version` `^\d+\.\d+\.\d+-\d+$` and starting with `alloy_version` and `-`); the literal test, over the real files and over a constructed tree whose NAS hold file names another digest (a literal equal to it passes, one equal to the fleet's fails; with no hold file the fleet's passes); the NAS-row test's two arms, a fixture-free reading of the real files plus a case over a constructed table where the row is behind a literal equal to the fleet file while another `alloy` row is off it too (passes), behind such a literal with every other `alloy` row on the fleet's digest (fails), behind such a literal with one held host's row off and every other row on (fails), behind such a literal with every other row on and the NAS row's digest cell carrying `held` and a reason (passes), and behind a literal off it (fails); the strict case, the `archive-pull` row behind its literal `nas_capture_image`, the NAS's `alloy` row on its own literal and another `alloy` row off the fleet's digest, the wave open (fails); `PUBLISHED`'s `--limit zaccess --tags alloy -e alloy_deb_version=1.20.0-1 -e '{"alloy_override": "1.20.1 drops journal lines on the edge, back while the owner reads it"}'` and `--limit zcrypto-ops --tags alloy -e ops_alloy_digest=<DIGEST> -e '{"alloy_override": "<the same kind of reason>"}'`, each recorded with both operands; `OUTSIDE`'s `-e alloy_deb_version=1.20.0-1` refused with `beside`, and `-e alloy_override=a reason` refused with `an override is a reason`.
- [ ] **Step 2: Run them and read the failure**

```bash
uv run pytest tests/test_fleet_contracts.py tests/test_converge_sh.py -q -p no:cacheprovider
```

Expected: the shape and literal tests fail on the missing file; the two published rollbacks fail `assert rc == 0` on rc 2, the harness's stderr carrying the refusals `not in this script's key set` and `is not an override name`, which the case's assertion does not print; the deb-version refusal case fails for refusing on the key set rather than for the reason; the `-e alloy_override=a reason` case fails as `alloy_override is not in this script's key set`, the override not yet named.

- [ ] **Step 3: The file, the two `converge.sh` sets, the refusal and the test changes**
- [ ] **Step 4: Run the tests** — Step 2's command; Expected: no failure.
- [ ] **Step 5: The consumers** — every test file `grep -rl --include='test_*.py' 'converge.sh\|group_vars/observed\|fleet-pins\|host_vars/nas' tests/` names, `tests/test_pins_converged.py` and `tests/test_infra_converge_guards.py` among them, plus `tests/test_run_sh.py`, which it does not name; Expected: no failure.
- [ ] **Step 6: The commit gate**
- [ ] **Step 7: Commit** — `feat(infra): one file names the fleet's Alloy version, the NAS literal is held to it, and converge.sh takes an Alloy override`, with `PROBE_VERDICT` and the trailer.
- [ ] **Step 8: The tree is clean**
- [ ] **Step 9: Prove the guards with one probe per guard, then record their verdicts** — mutations: the literal's last hex changed (the literal test); the hold file dropped from the literal test's read (the constructed held case); `alloy_deb_version` deleted from the fleet file (the shape test); the NAS-row arm admitting any literal (the constructed off-file case); the arm's other-row-off conjunct dropped (the constructed every-other-row-on case); the held-host exclusion dropped from that conjunct (the constructed held-host case); the held-reason arm dropped (the constructed hold-ending case); the archive-pull arm relaxed the same way (the strict case); the refusal's `|| refuse` line deleted (the deb-version `OUTSIDE` case); `alloy_override` dropped from `OVERRIDES` (the published rollbacks).

---

### Task 3: One walk of `site.yml`, the inventory and the roles — `alloy-version.py reaches`, read by the two built tag tests

**Files:**
- Create: `infra/scripts/alloy-version.py` (the walk and its `reaches` subcommand; Task 11 adds `off-fleet` and `gate`)
- Create: `tests/test_alloy_version.py`
- Modify: `tests/test_capture_alloy_tag.py` and `tests/test_nas_alloy_tag.py` (each file's own `_walk` and `_tags` deleted and the script's imported; their assertions unchanged — the change to built guards this task makes)
- Modify: `infra/ansible/scripts/converge.sh` (the `TAGNAMES` comment's "which the capture role and the nas role carry so far" re-trued to name no role: the tag the roles share, which `infra/scripts/alloy-version.py reaches` reads)

**Interfaces:**
- Consumes: `pins-converged.py`'s `inventory_groups(root)`, loaded from the script's own directory by `importlib.util`, so one inventory reader serves both; it reads `<root>/infra/ansible/inventory/hosts.yml`, so the walk passes it `ansible_dir.resolve().parents[1]` — resolved, since `converge.sh`'s `ADIR` is `scripts/..` — as `tests/test_nas_alloy_tag.py` passes `ANSIBLE.parents[1]`, and every fixture tree is laid out under `<tmp>/infra/ansible/`; `site.yml`'s plays, their `pre_tasks` and role entries; each role's `tasks/main.yml`.
- Produces, for Tasks 4 to 10 and `converge.sh`: `walk(tasks, tags=frozenset(), gates=(), *, roles_dir=<infra/ansible/roles>, base=None)` returning `(task, tags, gates)` leaves; `role_leaves(role, inherited, *, ansible_dir=ANSIBLE_DIR)`; `plays_reaching(host, *, ansible_dir=ANSIBLE_DIR)`; `selection(host, run_tags, *, ansible_dir=ANSIBLE_DIR)` returning `(where, task name)` in run order; `reaches(host, *, ansible_dir=ANSIBLE_DIR)`, `ANSIBLE_DIR` the repository's `infra/ansible` beside the script; the CLI `uv run python infra/scripts/alloy-version.py reaches [--ansible-dir DIR] HOST`, exit 0 printing nothing when a play that reaches the host runs an `alloy`-tagged task, exit 1 printing `no play that reaches <host> runs an alloy-tagged task`, exit 2 printing `reaches: <what failed>`.

**What this task decides, where the spec leaves it open:**
- The walk lives in `alloy-version.py`, the script D8 and D9 already name, because `converge.sh` needs a command and the tests need functions, and the spec's "one shared walk" is the one the capture test does; moving the two built tests onto it means a walk that learns a new shape — Task 8's `import_role` — reaches every guard at once.
- The walk expands the static imports Ansible expands at parse time: `ansible.builtin.import_role` (the named role's `tasks/<tasks_from or main>.yml`) and `ansible.builtin.import_tasks` (relative to the importing file), each handing its own tags and `when` to every task inside, as a block does. A dynamic `include_role` or `include_tasks` stays a leaf carrying its own tags, which is what Ansible selects.
- A run selects a leaf when its tags hold `always` or meet the run's tags, or when the run asks for `all` and the leaf carries no `never`, or for `tagged` and the leaf carries a tag.

The walk's core:

```python
def walk(tasks, tags=frozenset(), gates=(), *, roles_dir: Path = ROLES_DIR, base: Path | None = None):
    out = []
    for task in tasks or []:
        own = frozenset(tags | tags_of(task))
        conds = gates + when_of(task)
        if "ansible.builtin.import_role" in task:
            args = task["ansible.builtin.import_role"]
            path = roles_dir / args["name"] / "tasks" / f"{args.get('tasks_from', 'main')}.yml"
            out += walk(load(path), own, conds, roles_dir=roles_dir, base=path.parent)
        elif "ansible.builtin.import_tasks" in task:
            if base is None:
                raise ValueError(f"{task.get('name')}: import_tasks with no importing file to resolve it against")
            path = base / task["ansible.builtin.import_tasks"]
            out += walk(load(path), own, conds, roles_dir=roles_dir, base=path.parent)
        elif any(k in task for k in ("block", "rescue", "always")):
            for key in ("block", "rescue", "always"):
                out += walk(task.get(key), own, conds, roles_dir=roles_dir, base=base)
        else:
            out.append((task, own, conds))
    return out
```

- [ ] **Step 1: Write the failing tests** in `tests/test_alloy_version.py`, over fixture trees built under `tmp_path / "infra" / "ansible"` (an `inventory/hosts.yml`, a `site.yml`, `roles/<r>/tasks/main.yml`), `--ansible-dir` and `ansible_dir` naming that directory: `test_a_block_tagged_alloy_hands_the_tag_to_its_children`; `test_an_import_role_under_the_tag_hands_it_to_every_imported_task` (with `tasks_from`); `test_an_include_role_under_the_tag_stays_one_leaf`; `test_a_host_in_a_child_group_is_reached_through_its_parent_play`; `test_a_host_whose_plays_carry_no_alloy_task_is_not_reached`; `test_a_host_in_no_play_is_not_reached`; `test_the_selection_runs_always_tasks_and_the_asked_tags_alone`; `test_the_cli_exits_0_1_and_2_with_its_lines` (a broken `site.yml` for 2). `tests/test_scripts_have_tests.py` reads the file's naming of `alloy-version.py`.
- [ ] **Step 2: Run them and read the failure** — `uv run pytest tests/test_alloy_version.py -q -p no:cacheprovider`; Expected: every case fails on the missing script.
- [ ] **Step 3: The script, the two tests re-pointed, the `TAGNAMES` comment**
- [ ] **Step 4: Run the tests**

```bash
uv run pytest tests/test_alloy_version.py tests/test_capture_alloy_tag.py tests/test_nas_alloy_tag.py tests/test_scripts_have_tests.py -q -p no:cacheprovider
```

Expected: no failure, the two tag tests with the same cases passing as before.

- [ ] **Step 5: The consumers** — every test file `grep -rl --exclude='*vault*' --exclude='*.sops.*' 'alloy-version\|pins-converged\|converge.sh' tests/ infra/ .claude/` names under `tests/`, `tests/test_pins_converged.py` and `tests/test_converge_sh.py` among them; Expected: no failure.
- [ ] **Step 6: The commit gate**
- [ ] **Step 7: Commit** — `feat(infra): one walk of site.yml, the inventory and the roles answers what an alloy run selects, and the two tag tests read it`, with `PROBE_VERDICT` and the trailer.
- [ ] **Step 8: The tree is clean**
- [ ] **Step 9: Prove the guards** — mutations in `alloy-version.py`: the `import_role` arm handing no tags inward; the `import_role` arm widened to `ansible.builtin.include_role`, its `args` read from whichever of the two keys the task carries (the include case); the `always` arm dropped from the selection; in `pins-converged.py`, which holds the inventory read, `inventory_groups`' `resolve` returning a group's own hosts alone (the child-group case); then, with the capture and NAS tag tests as the probe, the walk's block arm handing no tags to children (both tag tests' selection cases fail), recorded as the proof that the moved tests still bite.

---

### Task 4: The capture role brings Alloy to the fleet's digest — the operand refusal, the recreate and the image read

This task changes the capture role's built Alloy part: D6's decision lands on the role whose tag Task 1 reviewed.

**Files:**
- Modify: `infra/ansible/roles/capture/tasks/main.yml` (inside the Alloy block, first: `refuse an Alloy digest that is not the one committed for this host, unless an alloy_override gives the reason`, its `fail_msg` naming both places the committed digest comes from, `infra/ansible/host_vars/<host>/alloy.yml` on a held host and `infra/ansible/group_vars/observed/alloy.yml` otherwise, and its echo `the alloy_override's reason, on the record`; the secrets render registers `capture_alloy_secrets`; after `render the alloy compose file`: `bring the alloy container to the digest, recreated when its secrets file changed`, `read which image the running alloy container was created from`, `refuse a converge whose alloy container does not run the digest it converged`; the comment above the block, "This RENDERS the stack only and never starts Alloy … the first start is an attended step, not a converge side effect", re-trued — Alloy is brought to the digest by the role, the capture daemon's first start stays attended; the drift assert's message, "Re-run this converge with `-e capture_alloy_digest=<currently-running>` … no task here starts it", re-trued to `--tags alloy` with the fleet's digest, whose run copies the file and brings the container to the digest; the fail-fast's `fail_msg`, "pass the digest the host runs, or the new one on a bump", re-trued, since the refusal now admits the committed digest alone: it renders that digest, `-e capture_alloy_digest={{ alloy_image_digest }}`, which on a held host is its hold file's)
- Modify: `infra/ansible/roles/capture/templates/alloy-compose.yaml.j2` (its header's "Deliberately NOT started here -- the first Alloy start on a capture host is an attended step" re-trued: the role brings the container to the digest) and `roles/capture/handlers/main.yml` (`reload alloy`'s "this role never owned the stack's lifecycle" and "a rotated credential needs a recreate" re-trued: the handler stays a reload, and the role's recreate takes a changed digest or secrets file)
- Create: `tests/test_alloy_container_recreate.py` (parametrised over the container roles, `capture` alone here; Tasks 5 and 6 widen it)
- Modify: `tests/test_capture_alloy_tag.py` (`ALLOY_PART` gains the five tasks in their places; the exclusion case gains the module allowlist below)

**Interfaces:**
- Consumes: Task 2's `alloy_image_digest` and `alloy_override`; the block's `capture_alloy_dir`, `capture_alloy_image` and the compose file it renders, whose service is `alloy` and whose container is `grafana-alloy`.
- Produces, for Tasks 5, 6 and 17 and the Rollout: the three tasks' names and shapes, which ops and cache copy; on a capture host's `--tags alloy` run, a container at `grafana/alloy@<capture_alloy_digest>` or a failed run.

**What this task decides, where the spec leaves it open:**
- The refusal compares the operand with `alloy_image_digest`, the var, not the file read on the controller: `converge.sh` admits no `alloy_image_digest` operand, so the var is the fleet file's on every host but a held one, whose `host_vars/<host>/alloy.yml` outranks the group file (spec D16). The override is accepted as the other overrides are: a reason longer than 8 characters that is not a boolean word.
- The recreate is `docker compose -f compose.yaml up -d`, with `--force-recreate` appended when `capture_alloy_secrets is changed`, `chdir` the Alloy project directory, its `-f` naming that directory's own file so a missing one fails the run where a bare `up -d` would search the parent directories for another project's (ops's finds the liquidations project, the cache's Valkey and Sentinel's), skipped under check mode, and `changed_when` its stderr naming `Recreated`, `Created` or `Started`; the ops leg in the Rollout reads that report against the container's `.State.StartedAt`, since the report's words are Compose's.
- The image read is `docker inspect grafana-alloy --format '{{ "{{" }}.Config.Image{{ "}}" }}'`, `changed_when: false`, skipped under check mode, and the assert holds its stdout equal to `capture_alloy_image ~ '@' ~ capture_alloy_digest`, exactly.
- The exclusion case gains a module allowlist beside its four refusals, the form spec D5's *Guards* give every role's exclusion: a tagged task's module is one of `ansible.builtin.assert`, `debug`, `stat`, `getent` and `set_fact`, which change nothing on the host, with any arguments; or one of `file`, `copy` and `template` whose `path` or `dest` is `{{ capture_alloy_dir }}` or below it with no `..` component, the role's Alloy paths, since the four refusals read a `dest` only against the capture daemon's two files and never a `path`; or the task is one of the three matched on module and arguments verbatim — the `user` task as it stands, whose `state: absent` no refusal names, the recreate's `command` with its `cmd` template and `chdir: "{{ capture_alloy_dir }}"`, and the image read's `command` — each compared on the module key's whole value, a string as the string, never through a reader that maps it to `{}`. The four refusals alone admit a tagged `docker restart zcrypto-capture`, a `systemctl` call, a compose call that retargets its project, a `community.docker` module, a `reboot` or the stale-config removal's `path` pointed at `{{ capture_data_dir }}`; the list refuses each, and a module the Alloy part takes later joins it in that change.

The three tasks, at the block's end:

```yaml
    # The fleet's digest reaches the container only through a recreate, and a changed env file reaches it
    # only through a forced one: Compose's recreate on an env file alone is version-dependent. `-f` names
    # this directory's own file, so a missing one fails the run where a bare `up -d` would search the
    # parent directories for another project's.
    - name: bring the alloy container to the digest, recreated when its secrets file changed
      ansible.builtin.command:
        cmd: "docker compose -f compose.yaml up -d{{ ' --force-recreate' if capture_alloy_secrets is changed else '' }}"
        chdir: "{{ capture_alloy_dir }}"
      register: capture_alloy_up
      changed_when: capture_alloy_up.stderr is search('Recreated|Created|Started')
      when: not ansible_check_mode

    - name: read which image the running alloy container was created from
      ansible.builtin.command: docker inspect grafana-alloy --format '{{ "{{" }}.Config.Image{{ "}}" }}'
      register: capture_alloy_running_image
      changed_when: false
      when: not ansible_check_mode

    - name: refuse a converge whose alloy container does not run the digest it converged
      ansible.builtin.assert:
        that: capture_alloy_running_image.stdout == capture_alloy_image ~ '@' ~ capture_alloy_digest
        fail_msg: >-
          grafana-alloy runs {{ capture_alloy_running_image.stdout }}, not
          {{ capture_alloy_image }}@{{ capture_alloy_digest }}: the recreate did not take. Read the container's
          state and logs before anything else on this host.
      when: not ansible_check_mode
```

- [ ] **Step 1: Write the failing tests** — in `tests/test_alloy_container_recreate.py`, each parametrised by role: `test_an_operand_off_the_committed_digest_is_refused_unless_a_reasoned_override_rides_with_it` (the committed digest passes; another refused; another beside a 60-character reason passes; beside `true`, and beside `short`, refused); `test_the_override_echo_fires_only_on_an_accepted_override`; `test_the_recreate_forces_only_when_the_secrets_file_changed` (the `cmd` rendered with the register changed and unchanged; `chdir` the role's Alloy directory); `test_the_image_read_names_one_field`; `test_the_image_assert_admits_only_the_runs_digest` (equal passes; another digest, an empty stdout, and the same digest behind a tag, `grafana/alloy:v1.19.2@sha256:…`, each refused); `test_the_recreate_the_read_and_the_assert_end_the_block_and_skip_the_preview` (the block's last three tasks in order, each gated `not ansible_check_mode`, after the compose render and the secrets render). In `tests/test_capture_alloy_tag.py`, `ALLOY_PART` and the exclusion case as above.
- [ ] **Step 2: Run them and read the failure**

```bash
uv run pytest tests/test_alloy_container_recreate.py tests/test_capture_alloy_tag.py -q -p no:cacheprovider
```

Expected: every recreate case fails on the missing tasks; the selection case and the play-selection case, `test_an_alloy_run_on_the_capture_and_engine_plays_runs_the_alloy_part_beside_the_always_pre_tasks`, fail on `ALLOY_PART`'s five new names; the exclusion case passes, every tagged task already admitted by its list, the `user` task verbatim as it stands, and no tagged command task existing yet.

- [ ] **Step 3: The five tasks, the register, the two comments**
- [ ] **Step 4: Run the tests** — Step 2's command; Expected: no failure, the closure case among them with `capture_alloy_secrets` produced before the recreate reads it.
- [ ] **Step 5: The consumers** — every test file `grep -rl 'roles/capture\|CAPTURE\b' tests/` names, `tests/test_infra_converge_guards.py`, `tests/test_infra_alloy_series.py` and `tests/test_clock_offset.py` among them; Expected: no failure.
- [ ] **Step 6: The commit gate**
- [ ] **Step 7: Commit** — `feat(infra): the capture role refuses an Alloy digest that is not the fleet's, brings the container to it and reads the image it runs`, with `PROBE_VERDICT` and the trailer.
- [ ] **Step 8: The tree is clean**
- [ ] **Step 9: Prove the guards** — mutations: the refusal's `that:` made `"true"`; the refusal's `length > 8` lowered to `length > 0` on its `or ((alloy_override` line alone, the echo's line and the `canary_override` and `pins_override` asserts' and echoes' lines carrying the same text (the `short` case — the arm's boolean-word conjunct is redundant behind the length test, every word it names being shorter than 9 characters, so a mutation dropping it moves no case); the `--force-recreate` condition inverted; the recreate's `chdir` pointed at `/opt/zcrypto-capture` (the exclusion case); the recreate's `cmd` gaining ` -p zcrypto-capture` after `docker compose` (the exclusion case); the image read's command made `docker restart zcrypto-capture` (the exclusion case); the recreate's module made `ansible.builtin.reboot`, its name and arguments kept (the exclusion case's module list, which no other refusal of the case meets); the image assert made `"true"`; the image read's format, in the task registering `capture_alloy_running_image`, widened to `{{json .Config}}`, `.Config.Image` also sitting in three reads of the capture daemon's image; the recreate's `when: not ansible_check_mode`, in the task registering `capture_alloy_up`, dropped, the same line also gating the read, the assert and one task outside the Alloy part; the recreate moved above the compose render; the echo's `when` made `"true"` (the echo case); the stale-config removal's `path` made `{{ capture_data_dir }}` (the exclusion case's Alloy paths, which none of its four refusals reads); the `user` task's `state` made `absent` (the exclusion case's verbatim tasks).

---

### Task 5: ops joins the tag — its Alloy part alone, the fail-fast, and the same recreate

**Files:**
- Modify: `infra/ansible/roles/ops/tasks/main.yml` (`tags: [alloy]` on `remove the pre-conf layout's stale alloy config` (line 720), the drift check's two stats and its assert (730 to 770), and the Alloy block (772); a fail-fast `fail fast if an alloy run was not handed the ops host's Alloy digest` above them, its message Task 4's re-trued one in ops' names; inside the block, first `refuse an Alloy digest that is not the one committed for this host, unless an alloy_override gives the reason` and its echo `the alloy_override's reason, on the record`, the secrets render registering `ops_alloy_secrets`, and after `render the alloy compose file` `bring the alloy container to the digest, recreated when its secrets file changed`, `read which image the running alloy container was created from` and `refuse a converge whose alloy container does not run the digest it converged`, each the capture role's task of that name with the `ops_` names; the comments above the stale removal and the drift check, "Ungated for the same reason …" and "This check lives OUTSIDE that gate on purpose", kept true and given the tag's reason; the drift assert's message re-trued to `--tags alloy` with the fleet's digest, whose run copies the file and brings the container to the digest)
- Modify: `infra/ansible/roles/ops/templates/alloy-compose.yaml.j2` (its header's "Deliberately NOT started here -- first start is an attended step" re-trued: the role brings the container to the digest) and `roles/ops/handlers/main.yml` (`reload alloy`'s "this role never owned the stack's lifecycle" and "a rotated credential needs a recreate" re-trued: the handler stays a reload, and the role's recreate takes a changed digest or secrets file)
- Create: `tests/test_ops_alloy_tag.py` (the capture test's shape: selection, closure, exclusion, the fail-fast)
- Modify: `tests/test_alloy_container_recreate.py` (`ops` joins the parametrisation)
- Modify: `tests/test_capture_alloy_tag.py` (the carriers list gains `roles/ops/tasks/main.yml`)

**Interfaces:**
- Consumes: Task 3's walk; Task 4's task shapes; the ops play's `always` charter note; the role's `ops_alloy_dir`, `ops_alloy_image` and `reload alloy` handler.
- Produces, for Task 10 and the Rollout: `--limit zcrypto-ops --tags alloy -e ops_alloy_digest=<alloy_image_digest>` as the ops leg; the tagged task names.

**What this task decides, where the spec leaves it open:**
- The tagged set is D6's: the stale removal, the drift check and the Alloy block, and the fail-fast; the closure test reads every tagged task's gates, arguments and rendered templates against the leaves, so a name the Alloy part reads from an untagged task fails it, and that task is tagged in this commit or the read is moved inside the part.
- The exclusion test holds that no tagged task reads `ops_image_digest`, `liquidations_decision` or a name containing `liquidations`, `rrsync`, `watchdog`, `keepalive` or `automount` in its module arguments or gates — a template's text is not read, since the Alloy compose template's comments name the poller to say it is never restarted — writes a `path` or `dest` outside `{{ ops_alloy_dir }}` or through a `..` component, or notifies anything but `reload alloy`; that, under Task 4's module allowlist in ops' terms, a tagged task's module is one of the five modules Task 4 admits with any arguments, or one of Task 4's three writer modules on ops' Alloy paths, or the task is one of the three admitted verbatim, the `user` task as it stands, the recreate (`cmd` `docker compose -f compose.yaml up -d{{ ' --force-recreate' if ops_alloy_secrets is changed else '' }}`, `chdir: "{{ ops_alloy_dir }}"`) and the image read (`docker inspect grafana-alloy --format '{{ "{{" }}.Config.Image{{ "}}" }}'`), so a tagged restart of `docker` by a service module, which names no refused word, a `community.docker` module, a `systemctl` call and the `user` task's `state: absent` are each refused; and that `base`, `chrony`, `docker` and `access_ops` stay untagged (Task 10 holds the last fleet-wide).

- [ ] **Step 1: Write the failing tests** — `tests/test_ops_alloy_tag.py`: `test_the_ops_roles_tagged_tasks_are_exactly_its_alloy_part` (by name, in order, `reload alloy` the one notify); `test_every_name_a_tagged_task_reads_is_produced_by_an_earlier_tagged_task`; `test_no_tagged_task_reaches_the_poller_the_timers_or_the_nas_paths`; `test_an_alloy_run_refuses_without_the_ops_alloy_digest_and_no_other_run_meets_that_refusal` (the capture case's seven run-tag rows with `ops`); `test_an_alloy_run_on_the_ops_play_runs_the_alloy_part_beside_the_charter_note`. The recreate file's `ops` cases; the carriers list.
- [ ] **Step 2: Run them and read the failure**

```bash
uv run pytest tests/test_ops_alloy_tag.py tests/test_alloy_container_recreate.py tests/test_capture_alloy_tag.py -q -p no:cacheprovider
```

Expected: the selection, fail-fast, play and recreate cases fail; the carriers case fails on the list naming a role that carries no tag yet.

- [ ] **Step 3: The tags, the fail-fast, the five tasks and the register in the block, the comments**
- [ ] **Step 4: Run the tests** — Step 2's command; Expected: no failure.
- [ ] **Step 5: The consumers** — every test file `grep -rl 'roles/ops' tests/` names, `tests/test_infra_alloy_series.py`, `tests/test_infra_converge_guards.py` and `tests/test_ops_daily.py` among them; Expected: no failure.
- [ ] **Step 6: The commit gate**
- [ ] **Step 7: Commit** — `feat(infra): the ops role's Alloy part joins the alloy tag and brings its container to the fleet's digest`, with `PROBE_VERDICT` and the trailer.
- [ ] **Step 8: The tree is clean**
- [ ] **Step 9: Prove the guards** — mutations: the tag deleted from the block (selection); the tag deleted from the deployed-config stat (closure); the tag added to `render the ops compose file (liquidations poller)` (exclusion); the ops image read's command made `docker restart zcrypto-ops-liquidations` (exclusion); the ops image read made `ansible.builtin.systemd_service: {name: docker, state: restarted}`, its name kept (the exclusion's module list); the fail-fast's `that:` made `"true"`; the ops refusal's `that:` made `"true"`; the ops recreate's `--force-recreate` condition inverted; the tag added to the ops play's `access_ops` entry in `site.yml` (the play case); the ops echo's `when` made `"true"`; the ops `user` task's `state` made `absent` (the exclusion's verbatim tasks).

---

### Task 6: The cache nodes join the tag — the drift check and the Alloy block, the fail-fast, and the same recreate

**Files:**
- Modify: `infra/ansible/roles/cache/tasks/main.yml` (`tags: [alloy]` on the drift check (line 333 to the assert) and the Alloy block (368), the digest-shape refusal and the Alloy pins-recording tasks riding inside it; a fail-fast `fail fast if an alloy run was not handed the cache node's Alloy digest` above them, its message Task 4's re-trued one in the cache role's names; inside the block, after the shape refusal, `refuse an Alloy digest that is not the one committed for this host, unless an alloy_override gives the reason` and its echo `the alloy_override's reason, on the record`, then the secrets render registering `cache_alloy_secrets`, and at the block's end `bring the alloy container to the digest, recreated when its secrets file changed`, `read which image the running alloy container was created from` and `refuse a converge whose alloy container does not run the digest it converged`, each the capture role's task of that name with the `cache_` names; the drift assert's message re-trued to `--tags alloy` with the fleet's digest, whose run copies the file and brings the container to the digest)
- Modify: `infra/ansible/roles/cache/templates/alloy-compose.yaml.j2` (its header's "The role renders it and never starts it: `sudo docker compose up -d` in this directory is the operator's step" re-trued: the role brings the container to the digest) and `roles/cache/handlers/main.yml` (`reload alloy`'s "this role never owns the stack's lifecycle" re-trued: the handler stays a reload, and the role's recreate takes a changed digest or secrets file)
- Create: `tests/test_cache_alloy_tag.py`
- Modify: `tests/test_alloy_container_recreate.py` (`cache` joins); `tests/test_capture_alloy_tag.py` (the carriers list gains `roles/cache/tasks/main.yml`)

**Interfaces:**
- Consumes: Tasks 3 and 4; the role's `cache_alloy_dir`, `cache_alloy_image`, `reload alloy` and its pins-recording read of `fleet-pins.md`, which `pins_override` bypasses.
- Produces, for the Rollout: `--limit zcrypto-valkey<N> --tags alloy -e cache_alloy_digest=<alloy_image_digest>` as the cache leg.

**What this task decides, where the spec leaves it open:**
- The exclusion test holds that no tagged task names `zcrypto-valkey`, `zcrypto-sentinel`, `valkey`, `sentinel`, `sysctl`, `cache_image_digest` or `cache_config_reset` in its module arguments or gates — a template's text is not read: the Alloy secrets template renders `cache_sentinel_requirepass`, the credential the Sentinel scrape needs, and the compose template's comment names Valkey and Sentinel to say neither restarts — writes a `path` or `dest` outside `{{ cache_alloy_dir }}` or through a `..` component, or notifies anything but `reload alloy`; that, under Task 4's module allowlist in the cache role's terms, a tagged task's module is one of the five modules Task 4 admits with any arguments, or one of Task 4's three writer modules on the cache role's Alloy paths, or the task is one of the four admitted verbatim, the `user` task as it stands, the pins-recording probe (`docker inspect --format '{{ "{{" }}.Config.Image{{ "}}" }}' grafana-alloy`), the recreate (`cmd` `docker compose -f compose.yaml up -d{{ ' --force-recreate' if cache_alloy_secrets is changed else '' }}`, `chdir: "{{ cache_alloy_dir }}"`) and the image read (`docker inspect grafana-alloy --format '{{ "{{" }}.Config.Image{{ "}}" }}'`), so a tagged restart of `docker` by a service module, which names no refused word, a `community.docker` module, a `systemctl` call and the `user` task's `state: absent` are each refused; the `cache_link` role stays untagged.
- The pins-recording refusal stays where it is, inside the block, and its probe of the running digest runs before the recreate, so a node whose running Alloy digest is unrecorded is refused before its container moves.

- [ ] **Step 1: Write the failing tests** — `tests/test_cache_alloy_tag.py`, in `tests/test_ops_alloy_tag.py`'s shape: `test_the_cache_roles_tagged_tasks_are_exactly_its_alloy_part`; `test_every_name_a_tagged_task_reads_is_produced_by_an_earlier_tagged_task`; `test_no_tagged_task_reaches_valkey_sentinel_or_the_sysctl`; `test_an_alloy_run_refuses_without_the_cache_alloy_digest_and_no_other_run_meets_that_refusal`; `test_an_alloy_run_on_the_cache_play_runs_the_alloy_part_beside_the_charter_note`; the recreate file's `cache` cases; the carriers list.
- [ ] **Step 2: Run them and read the failure** — `uv run pytest tests/test_cache_alloy_tag.py tests/test_alloy_container_recreate.py tests/test_capture_alloy_tag.py -q -p no:cacheprovider`; Expected: the selection, fail-fast, play and recreate cases fail; the carriers case fails on the list naming a role that carries no tag yet.
- [ ] **Step 3: The tags, the fail-fast, the tasks, the message**
- [ ] **Step 4: Run the tests** — Step 2's command; Expected: no failure.
- [ ] **Step 5: The consumers** — every test file `grep -rl 'roles/cache' tests/` names, `tests/test_infra_cache_templates.py`, `tests/test_infra_cache_proxy.py`, `tests/test_infra_alloy_series.py` and `tests/test_clock_offset.py` among them; Expected: no failure.
- [ ] **Step 6: The commit gate**
- [ ] **Step 7: Commit** — `feat(infra): the cache role's Alloy part joins the alloy tag and brings its container to the fleet's digest`, with `PROBE_VERDICT` and the trailer.
- [ ] **Step 8: The tree is clean**
- [ ] **Step 9: Prove the guards** — mutations: the tag deleted from the block; the tag deleted from the repo-side checksum stat; the tag added to the Valkey compose render; the cache image read's command made `docker restart zcrypto-sentinel` (exclusion); the cache image read made `ansible.builtin.service: {name: docker, state: restarted}`, its name kept (the exclusion's module list); the fail-fast made `"true"`; the cache refusal made `"true"`; the pins-recording probe moved after the recreate; the cache echo's `when` made `"true"`; the cache `user` task's `state` made `absent` (the exclusion's verbatim tasks).

---

### Task 7: The NAS's Alloy-only run writes its own Alloy pin line and reads the image Alloy runs

This task changes the NAS's built Alloy-only form, as D6's decision and Open question 7's ruling say.

**Files:**
- Modify: `infra/ansible/roles/nas/tasks/main.yml` (inside `the Alloy-only form` block, first: `write the stack .env's Alloy pin line, the line templates/env.j2 renders`, a `lineinfile`, `no_log` and `diff: false`, registered `nas_env_alloy_line`; the report's changed list gains `'.env': nas_env_alloy_line`; after the recreate, `read which image the running alloy container was created from` and `refuse a converge whose alloy container does not run the committed Alloy pin`, both flag-gated and skipped under check mode; the `.env` read and its refusal gated also on `not (ansible_check_mode and nas_env_alloy_line is changed)`; the comment above the `.env` read, "The recreate reads ALLOY_IMAGE from the stack .env, which this form does not render …", and the refusal's message, "Land the pin with a render-only --tags nas converge (no apply flag), then re-run this one", re-trued: the run writes the line and the read proves the write; the block's header comment re-trued for the line)
- Modify: `tests/test_nas_alloy_tag.py` (`ALLOY_PART`, the narrow paths and the exclusion case re-read for the line edit and the read, the exclusion case given the module allowlist; a parity case for the line; a case holding both writers of the stack `.env` to `no_log` and `diff: false`)
- Modify: `infra/ansible/host_vars/nas/vars.yml` (lines 47 to 49, the `--slice` comment's "any nas-tagged converge (an Alloy bump included) pairs the tree's entrypoint with whatever image runs" re-trued: an Alloy bump is now the narrow `--tags alloy` run, which deploys no entrypoint)

**Interfaces:**
- Consumes: `templates/env.j2`'s line `ALLOY_IMAGE={{ nas_alloy_image }}`; `nas_docker`, `/usr/local/bin/docker`; the block's gate.
- Produces, for the Rollout and Task 17: one applied `--limit nas --tags alloy -e nas_apply_compose=true` run as the NAS's bump; the line edit's name and shape.

**What this task decides, where the spec leaves it open:**
- The line edit runs on every narrow run, render-only included, since a render-only run lands files and this is a file; it is never flag-gated, and it lives inside the narrow block, so a whole converge, which renders the `.env` from the template, runs exactly the tasks it ran before.
- The edit is `ansible.builtin.lineinfile` with `path: "{{ nas_stack_dir }}/.env"`, `regexp: '^ALLOY_IMAGE='`, `line: "ALLOY_IMAGE={{ nas_alloy_image }}"`, `create: false`, so a NAS whose `.env` was never rendered fails the task rather than gaining a one-line file.
- The exclusion case admits one tagged writer of a puller file, this `lineinfile` on `.env` with that `regexp` and that `line`, and refuses any other write, the `.env`'s mode or owner included; the parity case holds its `line` byte-identical to `templates/env.j2`'s `ALLOY_IMAGE=` line, so the template's render and the edit never disagree at one tree.
- The read is `{{ nas_docker }} inspect grafana-alloy --format '{{ "{{" }}.Config.Image{{ "}}" }}'`, and the assert holds its stdout equal to `nas_alloy_image`.
- The exclusion case gains the module allowlist spec D5's *Guards* give every role's exclusion, beside its puller refusals: a tagged task's module is `ansible.builtin.debug` or `assert`, with any arguments; or one of `file`, `copy` and `template` whose `path` or `dest` is one of the NAS's Alloy paths — `{{ nas_stack_dir }}/conf` or below it with no `..` component, `{{ nas_stack_dir }}/config.alloy` or `{{ nas_stack_dir }}/alloy-secrets.env` —, since the puller refusals read a writer's target by its last component alone; or the task is one of the four admitted verbatim, module and arguments — the `.env` read's `command` (`argv: [grep, -qxF, "ALLOY_IMAGE={{ nas_alloy_image }}", "{{ nas_stack_dir }}/.env"]`), the line edit's `lineinfile` and the image read's `command` above, and the recreate's `shell` (`cd {{ nas_stack_dir }} && {{ nas_docker }} compose up -d --no-deps --force-recreate alloy`). The puller refusals alone admit a tagged restart of the Docker daemon by a service module, a `systemctl` call, a `{{ nas_docker }} restart $({{ nas_docker }} ps -q)` and the stale-config removal's `path` pointed at the archive, `/volume1/ZhaoCrypto`, none of which names the puller or calls compose; the list refuses each.
- The preview `converge.sh` runs first, with the run's own operands, reaches these tasks under `--check`: the line edit reports its pending write and writes nothing, so the `.env` read, which keeps `check_mode: false`, would read the old line, and its refusal would fail every preview of a run that moves the pin. The read and its refusal therefore stand down while the edit is pending in a preview, and run in a preview with no edit pending and on every real pass, where the read proves the write. The image read is a `command`, which check mode skips, so it and its assert are gated `not ansible_check_mode`, as the other container roles' are.

- [ ] **Step 1: Write the failing tests** — `test_the_tag_selects_exactly_the_alloy_part` with the three new names; `test_an_alloy_run_renders_alloys_files_reports_and_recreates_alloy_alone_under_the_flag` with the line edit in both paths and the read and assert after the recreate under the flag, its facts gaining `ansible_check_mode: false` and `nas_env_alloy_line` changed; `test_no_tagged_task_reaches_the_puller` admitting the one line edit and carrying the module allowlist; `test_the_alloy_pin_line_is_the_templates_own_line`; `test_the_narrow_image_assert_admits_only_the_committed_pin`; `test_the_pin_read_and_its_refusal_stand_down_in_a_preview_while_the_line_edit_is_pending` (a preview with the edit changed skips both; a preview with it unchanged, and a real pass with it changed, run both); `test_the_narrow_image_read_and_assert_skip_the_preview`; `test_both_writers_of_the_stack_env_are_never_logged_or_diffed`, parametrised over the line edit and `render the stack .env (image pins, pull sources, the vaulted gate dead-man URL)`, each `no_log` true and `diff` false, in the shape of `tests/test_infra_converge_guards.py::test_every_cache_secret_render_is_never_logged_or_diffed`; the whole-converge parity case unchanged and passing.
- [ ] **Step 2: Run them and read the failure** — `uv run pytest tests/test_nas_alloy_tag.py -q -p no:cacheprovider`; Expected: the selection, path, line and assert cases, the two preview cases and the `.env` writers' case on the line edit fail.
- [ ] **Step 3: The three tasks, the report entry, the comments and the message**
- [ ] **Step 4: Run the tests** — Step 2's command; Expected: no failure, the parity case among them.
- [ ] **Step 5: The consumers** — every test file `grep -rl 'roles/nas\|host_vars/nas\|infra/nas' tests/` names, `tests/test_infra_alloy_series.py` among them, plus `tests/test_pins_converged.py`, `tests/test_fleet_contracts.py` and `tests/test_infra_converge_guards.py`, which it does not name; Expected: no failure.
- [ ] **Step 6: The commit gate**
- [ ] **Step 7: Commit** — `feat(infra): the NAS's Alloy-only run writes the stack .env's Alloy pin line itself and reads the image Alloy runs`, with `PROBE_VERDICT` and the trailer.
- [ ] **Step 8: The tree is clean**
- [ ] **Step 9: Prove the guards** — mutations: the line's `regexp` widened to `^` (the exclusion case); the `line` changed to `ALLOY_IMAGE="{{ nas_alloy_image }}"` (the parity case); `create: true` (the exclusion case); the line edit flag-gated (the render-only path); the image assert made `"true"`; the read pointed at `zcrypto-archive-pull`; the image read made `ansible.builtin.systemd: {name: pkg-ContainerManager-dockerd, state: restarted}`, its name kept (the exclusion case's module list); the image read's command made `{{ nas_docker }} restart $({{ nas_docker }} ps -q)` (the exclusion case's verbatim tasks); the preview conjunct dropped from the `.env` read and its refusal, one sed over both lines (the preview case); `not ansible_check_mode` dropped from the image read and its assert, one sed over both lines (the preview case); the stale-config removal's `path` made `/volume1/ZhaoCrypto` (the exclusion case's Alloy paths); `diff: false` deleted from the line edit (the `.env` writers' case).

---

### Task 8: The shared apt Alloy role and the bridgehead — held, pinned at 1001, installed at the fleet's version after the revocation path

**Files:**
- Create: `infra/ansible/roles/alloy_apt/tasks/main.yml` (the install, D5's steps 1 to 4, with the version refusal and its echo ahead of them and the preview fact between the install and the hold)
- Create: `infra/ansible/roles/alloy_apt/tasks/postcondition.yml` (D5's step 7: the flush, the read, the restart)
- Modify: `infra/ansible/roles/access/tasks/main.yml` (the Grafana repository task, the comment block "Alloy and Caddy are apt packages from THIRD-PARTY repos …", `alloy present — version FOLLOWED from apt, never forced` and `alloy is never held …` removed; the env, the config and `alloy enabled + started` moved after `apply pending handlers before the relay drift gate`, between `import_role: alloy_apt` and `import_role: alloy_apt, tasks_from: postcondition`, every one of them tagged `alloy`; the config copy gains `validate: alloy validate %s`; `alloy enabled + started` gated `not alloy_apt_previewed`; `caddy is never held — same reason as alloy above` renamed for its own reason, a hold makes `apt upgrade` skip it silently; the comment above the Caddy repository, "Caddy follows apt too", re-trued, Caddy alone following apt now; the flush's comment, which says it precedes the relay gate, re-trued to say it precedes the Alloy part too; a comment above the Alloy part stating the stance: held at the fleet's version, pinned, after the revocation path so no Alloy failure in the real pass takes it, while a preview that cannot fetch the repository's signing key refuses the whole converge as the Caddy repository's fetch already does)
- Modify: `.pre-commit-config.yaml` (the `ansible-lint` hook's `entry` made `env ANSIBLE_ROLES_PATH=infra/ansible/roles uv run ansible-lint`, its comment saying why: the hook runs from the repository root, where `infra/ansible/ansible.cfg`'s `roles_path = roles` is not read, and ansible-lint syntax-checks each role alone, so the access role's static `import_role` of `alloy_apt`, the tree's first static import of one role by another, fails as `The role 'alloy_apt' was not found` without it, as Task 9's mon import would; the relative path resolves against the root the hook runs from)
- Create: `tests/test_infra_alloy_apt.py` (the shared role's behaviour; `ALLOY_APT_FREE` and `ALLOY_APT_VERBATIM`, its share of each importer's exclusion allowlist)
- Create: `tests/test_access_alloy_tag.py` (selection, closure, exclusion, the order)
- Modify: `tests/test_capture_alloy_tag.py` (the carriers list gains `roles/access/tasks/main.yml`)

**Interfaces:**
- Consumes: Task 2's `alloy_deb_version` and `alloy_override`; Task 3's walk, whose `import_role` arm this task is the first to use; the access role's `restart alloy` handler and `alloy-env.j2`.
- Produces, for Task 9 and the Rollout: `alloy_apt`'s two entry points and their task names; `alloy_apt_grafana_repo`, `alloy_apt_pin`, `alloy_apt_install`, `alloy_apt_previewed`, `alloy_apt_running_exe`; `ALLOY_APT_FREE` and `ALLOY_APT_VERBATIM`; `--limit zaccess --tags alloy` as the bridgehead's leg.
- Produces, for plan 00122's Task 9, as a requirement and not an edit (spec D14, "What this asks of plan 00122"): the `hc` role imports `alloy_apt` before its env file and config and `alloy_apt` with `tasks_from: postcondition` after its `alloy enabled + started`, each import and each Alloy task of its own tagged `alloy`; its config copy validated by `alloy validate %s`; its dry-start against the release binary of the version the fleet file names; `test_access_alloy_tag.py`'s three guards in its terms, its exclusion's allowlist built on `ALLOY_APT_FREE` and `ALLOY_APT_VERBATIM`; the carriers list and Task 10's static test widened to it; an `alloy` row in `fleet-pins.md` at its build; its place in the wave after `zaccess`. If its pull request merges before this package's, this package's pull request carries the join (the Rollout's R0 and R2 stop for it). Task 10's `test_the_alloy_package_is_installed_and_held_by_alloy_apt_alone_and_each_importer_takes_its_postcondition` holds the install and the hold on that role and refuses `alloy_apt` brought in there by an include, and Task 10's observed-host case holds its tag, the carriers case then holding the list at seven, so plan 00122's Task 9 meets those halves of the requirement as failing tests whatever its own text says.

**What this task decides, where the spec leaves it open:**
- The shared role is `alloy_apt`, under `infra/ansible/roles/`, whichever of this package and spec 00122's `node_common` merges first (spec D5): the access role imports it too, and `node_common` is task files that spec 00122 has the mon and `hc` roles include with variables; its registers and facts take the `alloy_apt_` prefix `ansible-lint`'s `var-naming[no-role-prefix]` asks of a role.
- The pin file is written by `copy` with `content`, so its text is in the task the test reads; the install's preview gate reads the repository's and the pin file's registers, and the preview fact set after it reads those and the install's, D5's "a preview fact of its own".
- A preview read of host state stands down while a write before it in the same run is pending, since `converge.sh` previews first and a failed preview refuses the whole converge, the access role's revocation path with it: the install while the repository or the pin file would change — the apt module refuses a version below the pin file on disk and one the host's unrefreshed lists lack, so a rollback's preview, the fleet's or one host's, and a move to a version those lists do not yet carry fail there otherwise, and every version move changes the pin file; the hold, `alloy enabled + started` and the node's `restart alloy` while the preview fact holds; the post-condition in every preview. A config copy's `validate` runs on a real pass alone and needs no gate. Tasks 4 to 7 stand the containers' image read and the NAS's `.env` read down on the same ground.
- The post-condition reads the process's executable link as the access role's relay gate reads its relay: `/proc/<MainPID>/exe` ending ` (deleted)` is a process older than the installed binary, `__not_running__` is no process, and an empty read restarts too; each case is a test, the bridgehead's shape — a version moved and the package left the old process running — and the node's — the package restarted it — among them.
- The access exclusion carries the module allowlist spec D5's *Guards* give every role's exclusion, and `alloy_apt`'s share of it is one pair of constants in `tests/test_infra_alloy_apt.py`, written out and never read from the role, so a change to the shared role fails each importer's case until the constants move with it: `ALLOY_APT_FREE`, the modules `ansible.builtin.assert`, `debug` and `set_fact`, which change nothing on the host, with any arguments; `ALLOY_APT_VERBATIM`, the seven tasks admitted only verbatim, module and arguments — the repository's `deb822_repository`, the pin file's `copy`, the install's `apt`, the hold's `dpkg_selections`, the flush's `meta`, the post-condition read's `shell` and its restart's `systemd_service`. The access case admits those; its own `ansible.builtin.copy` and `ansible.builtin.template` whose `dest` is `/etc/default/alloy` or lies under `/etc/alloy/` with no `..` component, its env file and its config; and its `alloy enabled + started`, `ansible.builtin.systemd: {name: alloy, enabled: true, state: started}`, verbatim. A tagged `apt` task with `upgrade: dist` or `name: "*"`, a `package` task, a `reboot`, a repository pointed elsewhere or a config copy whose `dest` is `/etc/wireguard/zaccess0.conf`, in `alloy_apt` or in the importer, names nothing the refusals name; the list refuses it.
- `alloy validate` on the access config needs none of its six `sys.env` names set (the spec's "Not confirmed here"): Step 4 reads it before the validate is committed, and a refusal there holds the task for the orchestrator.

`alloy_apt/tasks/main.yml`, determined by D3 and D5:

```yaml
---
# The apt hosts' Alloy at the fleet's version (spec 00123 D3, D5): imported statically by each apt role under the
# `alloy` tag, so the tag reaches every task here. A hold and an exact-version pin, because each covers what the
# other leaves: the hold is the floor dpkg enforces, the pin makes the held version the candidate.
# The committed version, read on the controller: a held host's hold file's (spec 00123 D16), else the fleet
# file's. The var differs from it only under an extra-var.
- name: refuse an alloy_deb_version that is not the one committed for this host, unless an alloy_override gives the reason
  ansible.builtin.assert:
    that: >-
      alloy_deb_version == alloy_apt_committed.alloy_deb_version
      or ((alloy_override | default('') | string | length > 8)
          and (alloy_override | default('') | string | lower not in ['true', 'false', '1', 'yes']))
    fail_msg: >-
      alloy_deb_version is {{ alloy_deb_version }}, the version committed for this host is
      {{ alloy_apt_committed.alloy_deb_version }}: a version off it moves this host alone, so it takes
      -e '{"alloy_override": "<why>"}' beside it.
  vars: &alloy_apt_committed_vars
    alloy_apt_committed: "{{ lookup('ansible.builtin.file', lookup('ansible.builtin.first_found', [playbook_dir ~ '/host_vars/' ~ inventory_hostname ~ '/alloy.yml', playbook_dir ~ '/group_vars/observed/alloy.yml'])) | from_yaml }}"

- name: the alloy_override's reason, on the record
  ansible.builtin.debug:
    msg: "alloy_override accepted: {{ alloy_override }}"
  vars: *alloy_apt_committed_vars
  when: >-
    alloy_deb_version != alloy_apt_committed.alloy_deb_version
    and (alloy_override | default('') | string | length > 8)
    and (alloy_override | default('') | string | lower not in ['true', 'false', '1', 'yes'])

- name: add the Grafana apt repository (deb822; the module fetches and stores the signing key)
  ansible.builtin.deb822_repository:
    name: grafana
    types: [deb]
    uris: https://apt.grafana.com
    suites: [stable]
    components: [main]
    signed_by: https://apt.grafana.com/gpg.key
    install_python_debian: true
  register: alloy_apt_grafana_repo

- name: pin alloy at the version committed for this host, above every other candidate
  ansible.builtin.copy:
    content: |
      Package: alloy
      Pin: version {{ alloy_deb_version }}
      Pin-Priority: 1001
    dest: /etc/apt/preferences.d/alloy
    owner: root
    group: root
    mode: "0644"
  register: alloy_apt_pin

# allow_downgrade, or a host ahead of the fleet's version is a refused downgrade that drops it from the play;
# allow_change_held_packages, or the hold below refuses every later move. Skipped in a preview whose repository
# or pin file would change: the module refuses a version below the pin file on disk and one the unrefreshed
# package lists lack, so a rollback's preview, or a move to a version those lists do not yet carry, would fail
# here and refuse the whole converge; every version move changes the pin file.
- name: install alloy at the version committed for this host, moving a newer or held one
  ansible.builtin.apt:
    name: "alloy={{ alloy_deb_version }}"
    state: present
    update_cache: true
    allow_downgrade: true
    allow_change_held_packages: true
  register: alloy_apt_install
  when: not (ansible_check_mode and (alloy_apt_grafana_repo is changed or alloy_apt_pin is changed))

- name: note a preview that runs before alloy is installed and pinned at the version committed for this host
  ansible.builtin.set_fact:
    alloy_apt_previewed: "{{ ansible_check_mode and (alloy_apt_grafana_repo is changed or alloy_apt_pin is changed or alloy_apt_install is changed) }}"

# After the install: dpkg_selections hard-fails on a package dpkg has never seen.
- name: hold alloy, so no apt upgrade moves it
  ansible.builtin.dpkg_selections:
    name: alloy
    selection: hold
  when: not alloy_apt_previewed
```

`alloy_apt/tasks/postcondition.yml`, determined by D5 as amended:

```yaml
---
# A state read, not a notify: a `restart alloy` stranded by a later failure is never sent again, and on a host whose
# package does not restart Alloy on an upgrade the old binary keeps running behind a green converge.
- name: apply the pending alloy restart before reading what the process runs
  ansible.builtin.meta: flush_handlers

- name: read whether the running alloy process runs the installed binary
  ansible.builtin.shell:
    cmd: |
      set -o pipefail
      pid=$(systemctl show -p MainPID --value alloy)
      if [ -z "$pid" ] || [ "$pid" = "0" ]; then echo __not_running__; else readlink "/proc/$pid/exe"; fi
    executable: /bin/bash
  register: alloy_apt_running_exe
  changed_when: false
  when: not ansible_check_mode

- name: restart alloy when its process predates the installed binary or none runs
  ansible.builtin.systemd_service:
    name: alloy
    state: restarted
  when: >-
    not ansible_check_mode
    and (alloy_apt_running_exe.stdout | default('') in ['', '__not_running__']
         or alloy_apt_running_exe.stdout is search(' \(deleted\)$'))
```

- [ ] **Step 1: Write the failing tests** — `tests/test_infra_alloy_apt.py`: `test_the_install_runs_the_refusal_its_echo_the_repository_the_pin_the_install_the_fact_and_the_hold_in_order`; `test_the_echo_fires_only_on_an_accepted_override`; `test_the_install_takes_exactly_the_fleets_deb_version_with_both_options`; `test_the_pin_file_reads_the_fleets_version_at_1001`; `test_the_version_refusal_admits_the_committed_version_or_a_reasoned_override` (with the fleet file's value committed: the fleet's passes; another refused; another beside a long reason passes; beside `yes` refused; with a hold file's value committed: the held version passes and the fleet's is refused without an override; the `first_found` list naming the host's hold file before the fleet file); `test_the_install_stands_down_in_a_preview_whose_repository_or_pin_file_would_change` (check with either changed skips it; check with neither runs it; a real run with both changed runs it); `test_the_preview_fact_is_true_only_in_a_preview_whose_repository_pin_or_install_would_change` (check with the repository changed; check with the pin file changed and the install skipped, a first install or a version move alike; check with the install changed under a pin that stands, a host moved by hand; an established host's check; a real run); `test_the_postcondition_flushes_before_it_reads`; `test_the_postcondition_restarts_on_the_bridgeheads_shape_and_not_on_the_nodes` (stdout `/usr/bin/alloy (deleted)` restarts; `/usr/bin/alloy` does not; `__not_running__` and `''` restart; a preview reads and restarts nothing). `tests/test_access_alloy_tag.py`: `test_the_access_roles_tagged_tasks_are_exactly_its_alloy_part` (through the walk's `import_role` expansion, by name, `restart alloy` the one notify); `test_every_name_a_tagged_task_reads_is_produced_by_an_earlier_tagged_task` (`alloy_apt_previewed` before `alloy enabled + started`); `test_no_tagged_task_reaches_caddy_wireguard_the_relay_or_the_probe` (no tagged task names `caddy`, `wg-quick`, `zaccess-ssh-proxy`, `zaccess-probe` or `pinned-leaves`, nor notifies `reload caddy`, `restart wg-quick@zaccess0` or `reload systemd`; every tagged task admitted by the access allowlist, by its free modules, its writers on its Alloy paths or its verbatim tasks, as decided above); `test_the_alloy_part_runs_after_the_revocation_path_and_before_the_relay_gate` (the first import after `pinned mTLS client leaves …`, the Caddyfile task and `apply pending handlers before the relay drift gate`, the postcondition import before `read the ssh relay's running target`); `test_the_access_config_is_validated_and_restarts_alloy_on_a_change`; the carriers list.
- [ ] **Step 2: Run them and read the failure**

```bash
uv run pytest tests/test_infra_alloy_apt.py tests/test_access_alloy_tag.py tests/test_capture_alloy_tag.py -q -p no:cacheprovider
```

Expected: every shared-role case fails on the missing role; the access cases fail on the untagged, unordered role, but for the exclusion and closure cases, which pass while no task is tagged; the carriers case fails on the list naming a role that carries no tag yet.

- [ ] **Step 3: The two task files, the access role's edits and comments**
- [ ] **Step 4: Read `alloy validate` on the access config** — the release binary of v1.20.1, the target the spec's measured basis reads, unzipped from `https://github.com/grafana/alloy/releases/download/v1.20.1/alloy-linux-amd64.zip` into the scratch directory `.tmp/alloy-validate/` and made executable, `chmod +x .tmp/alloy-validate/alloy-linux-amd64`; then, from the repository root, `env -i PATH=/usr/bin:/bin .tmp/alloy-validate/alloy-linux-amd64 validate infra/ansible/roles/access/files/config.alloy; echo rc=$?` and the same over `infra/ansible/roles/mon/files/config.alloy`; Expected: `rc=0` on both, the environment empty of every `sys.env` name. A non-zero `rc` on the access config holds the task for the orchestrator with the printed error. The scratch directory is removed after.
- [ ] **Step 5: Run the tests** — Step 2's command; Expected: no failure.
- [ ] **Step 6: The consumers** — every test file `grep -rl --exclude='*vault*' --exclude='*.sops.*' 'roles/access\|roles/alloy_apt\|alloy-env.j2\|pre-commit-config' tests/ infra/ .claude/` names under `tests/`, `tests/test_infra_alloy_series.py`, `tests/test_infra_converge_guards.py`, `tests/test_pre_push_stage.py` and `tests/test_message_citations.py` among them; Expected: no failure.
- [ ] **Step 7: The commit gate** — Expected: every hook Passed, `ansible-lint` among them over the new role and the access role's static import of it, which the hook's roles path resolves.
- [ ] **Step 8: Commit** — `feat(infra): the bridgehead holds Alloy at the fleet's version, pinned at 1001, installed under the alloy tag after the revocation path`, with `PROBE_VERDICT` and the trailer.
- [ ] **Step 9: The tree is clean**
- [ ] **Step 10: Prove the guards** — mutations: `Pin-Priority: 1001` to `990`; `alloy_apt_pin is changed` dropped from the install's `when` (the install's preview case); `alloy_apt_pin is changed` dropped from the preview fact (the fact's pin case); `allow_downgrade: true` deleted; `selection: hold` to `install`; the hold moved above the install; the refusal's `that:` made `"true"`; the restart's ` \(deleted\)` arm deleted (the bridgehead's shape); the restart's `__not_running__` arm deleted; the flush deleted; the tag deleted from the first import (selection); the first import moved above the Caddyfile task (order); `notify: reload caddy` added to the access config copy (exclusion); `alloy enabled + started`'s unit made `caddy` (exclusion); the install's `name: "alloy={{ alloy_deb_version }}"` line made `upgrade: dist`, the task's name kept (the access exclusion's verbatim tasks); `alloy enabled + started`'s `ansible.builtin.systemd: {name: alloy, enabled: true, state: started}` made `ansible.builtin.package: {name: "*", state: latest}` (the access exclusion's module list); the access copy's `validate` deleted; the hold file dropped from the refusal's `first_found` list (the held-host case); the echo's `when` made `"true"` (the echo case); the repository task gaining `state: absent` (the access exclusion's verbatim tasks, the repository among them); the access config copy's `dest` made `/etc/wireguard/zaccess0.conf` (the access exclusion's Alloy paths); and, with `uv run pre-commit run ansible-lint --all-files` as the probe, the access role's first `import_role`'s `name: alloy_apt` made `name: alloy_apt_absent`, a role that does not exist (the hook's roles path resolves the shared role and still fails a missing one).

---

### Task 9: The observability node holds Alloy at the fleet's version under the tag, its other packages still followed

**Files:**
- Modify: `infra/ansible/roles/mon/tasks/main.yml` (`add the Grafana apt repository (grafana, loki, alloy)` replaced by `import_role: alloy_apt` tagged `alloy`; `note a preview that runs before the repositories exist` reading `alloy_apt_grafana_repo` alone, Grafana's being the role's one repository; `alloy` out of `[grafana, loki, alloy]`, the task renamed `grafana and loki present — versions FOLLOWED from apt, never forced or held`; `alloy config — …` and `alloy enabled + started` tagged `alloy`, the second gated `not alloy_apt_previewed`; `import_role: alloy_apt, tasks_from: postcondition` tagged `alloy` after it; the header's "Packages followed from apt, never forced or held" re-trued: but Alloy, held and pinned at the fleet's version)
- Modify: `infra/ansible/roles/mon/handlers/main.yml` (`restart alloy` gated `not alloy_apt_previewed`)
- Modify: `tests/test_infra_converge_guards.py` (`test_every_register_a_preview_guard_reads_is_set_in_its_own_role` reads each role file's leaves through Task 3's `walk`, which expands `import_role`, so a register the imported `alloy_apt` sets counts for the mon role, whose `mon_repos_previewed` reads `alloy_apt_grafana_repo`; `iter_tasks` stays for its other callers)
- Modify: `tests/test_infra_mon_role.py` (`test_no_package_is_forced_held_or_pinned_to_a_version` re-trued as `test_alloy_alone_is_held_and_pinned_and_the_other_packages_followed`: Grafana, Loki and Prometheus, `curl` beside them, `state: present` with no version, no `allow_downgrade` and no hold, read through the walk; Alloy installed by the shared role alone; Caddy is the `edge` role's, which the node includes, and no case here reads it; `test_the_two_preview_facts_are_true_only_where_a_preview_has_no_package_to_find` reading `alloy_apt_grafana_repo`; `test_what_needs_a_repository_or_a_unit_skips_the_preview_that_has_neither` admitting `not alloy_apt_previewed` on `alloy enabled + started` and on `restart alloy`, and reading one third-party install, `[grafana, loki]`)
- Create: `tests/test_mon_alloy_tag.py`
- Modify: `tests/test_capture_alloy_tag.py` (the carriers list gains `roles/mon/tasks/main.yml`)

**Interfaces:**
- Consumes: Task 8's role and facts, and `ALLOY_APT_FREE` and `ALLOY_APT_VERBATIM`; Task 8's `ansible-lint` roles path, which resolves this task's import at the commit gate; Task 3's `walk`, which the register case reads through; the node's `restart alloy`; `mon_repos_previewed` and `mon_units_previewed`, which keep gating everything but Alloy.
- Produces, for the Rollout: `--limit zcrypto-mon --tags alloy` as the node's leg; the node's un-tagged converge of `mon-patch-pass` step 4 installing the fleet's version, D4's design.

**What this task decides, where the spec leaves it open:**
- The shared install takes the Grafana repository task's place, after the secret refusal, so the repository it registers is the one `mon_repos_previewed` reads, and the node's other installs still find Grafana's packages behind it.
- The exclusion test holds that no tagged task names `grafana`, `loki`, `prometheus` or `caddy` in a package, a path or a unit, the shared role's repository task admitted — its `name: grafana` and `https://apt.grafana.com` are the apt source Alloy installs from, which the other packages share — nor the token include, the edge include, the self-check or the reboot check, nor notifies anything but `restart alloy`; and it carries the module allowlist in the node's terms: a tagged task's module is in `ALLOY_APT_FREE`, with any arguments, or is the node's own `ansible.builtin.copy` whose `dest` lies under `/etc/alloy/` with no `..` component, its config, or the task is one of `ALLOY_APT_VERBATIM` or the node's `alloy enabled + started`, `ansible.builtin.systemd_service` with `name: alloy`, `enabled: true` and `state: started`, verbatim — so a tagged `apt` task with `upgrade: dist` or `name: "*"`, which names no refused word and would move the node's other packages, a `package` task and a `reboot` are each refused.

- [ ] **Step 1: Write the failing tests** — `tests/test_mon_alloy_tag.py`: selection (through the import, by name), closure (`restart alloy`'s gate produced by a tagged task), `test_no_tagged_task_reaches_grafana_its_stores_or_caddy`, and the play case (the charter note beside the Alloy part); the three re-trued cases of `tests/test_infra_mon_role.py`; the register case of `tests/test_infra_converge_guards.py` re-trued; the carriers list.
- [ ] **Step 2: Run them and read the failure**

```bash
uv run pytest tests/test_mon_alloy_tag.py tests/test_infra_mon_role.py tests/test_capture_alloy_tag.py tests/test_infra_converge_guards.py -q -p no:cacheprovider
```

Expected: the tag cases fail, but for the exclusion and closure cases, which pass while no task is tagged; the carriers case fails on the list naming a role that carries no tag yet; the package case fails on `alloy` still in the Grafana install, and the skip case on the same install, which it reads as `[grafana, loki]`; the re-trued preview-facts case fails, the `alloy_apt_grafana_repo` it passes read by no task while the fact still reads `mon_grafana_repo`; the re-trued register case passes, before Step 3 as after it — without its re-true, Step 3's preview fact fails it `[mon]` on `alloy_apt_grafana_repo`, the state Step 9's `iter_tasks` mutation restores.

- [ ] **Step 3: The role's and the handler's edits, the header**
- [ ] **Step 4: Run the tests** — Step 2's command; Expected: no failure, `test_the_alloy_config_is_validated_and_alloy_restarted_on_a_change` among them.
- [ ] **Step 5: The consumers** — every test file `grep -rl 'roles/mon' tests/` names, `tests/test_mon_selfcheck.py` and `tests/test_infra_alloy_series.py` among them, plus `tests/test_infra_unattended_upgrades.py`, which it does not name; Expected: no failure.
- [ ] **Step 6: The commit gate**
- [ ] **Step 7: Commit** — `feat(infra): the observability node holds Alloy at the fleet's version under the alloy tag, its other packages still followed`, with `PROBE_VERDICT` and the trailer.
- [ ] **Step 8: The tree is clean**
- [ ] **Step 9: Prove the guards** — mutations: `alloy` back in `[grafana, loki]`; the import's tag deleted; `restart alloy`'s gate back to `mon_units_previewed` (closure); `notify: restart grafana` added to the Alloy config copy (exclusion); `mon_repos_previewed` reading `mon_grafana_repo` (the preview case, and the register case `[mon]`, a probe each); the register case's `walk` replaced by `iter_tasks` (its `[mon]` case fails on `alloy_apt_grafana_repo`); `alloy enabled + started`'s module made `ansible.builtin.package`, its name and arguments kept (the exclusion's module list); a task `ansible.builtin.apt: {upgrade: dist}` tagged `alloy` added after `alloy enabled + started` (the exclusion's verbatim tasks); the Alloy config copy's `dest` made `/etc/default/alloy` (the exclusion's Alloy paths).

---

### Task 10: `converge.sh` refuses an `alloy` run that would land nothing, and every observed play reaches the tag

**Files:**
- Modify: `infra/ansible/scripts/converge.sh` (`REPO="${ZCRYPTO_REPO:-$SD/../../..}"` and the existing `ADIR` assignment moved above the operand checks; the reach refusal after the operand checks and before the preview)
- Create: `tests/test_alloy_tag.py` (the fleet-wide guards: every observed host reached; the play selection generalised; the carriers, moved here from `tests/test_capture_alloy_tag.py`, exactly six; the `alloy` package installed and held by `alloy_apt` alone, and `alloy_apt` imported, never included)
- Modify: `tests/test_capture_alloy_tag.py` (`test_only_the_roles_that_joined_the_tag_carry_it_and_no_play_does` deleted, moved to `tests/test_alloy_tag.py` under its name)
- Modify: `tests/test_converge_sh.py` (the refusal's cases; `test_every_invocation_this_fleet_publishes_records_its_operands` and every other case passing `--tags alloy` run with `ZCRYPTO_REPO` at the repository and `ZCRYPTO_ANSIBLE_DIR` at `infra/ansible`)

**Interfaces:**
- Consumes: Task 3's `reaches` CLI; Tasks 4 to 9's joins.
- Produces: no `alloy` row for a host none of whose plays runs an `alloy` task; the static guards that keep the refusal from meeting a fleet host.

**What this task decides, where the spec leaves it open:**
- `converge.sh` runs the walk through `uv run`, since the system `python3` it uses for its other checks has no `yaml`: `uv run --project "$REPO" python "$REPO/infra/scripts/alloy-version.py" reaches --ansible-dir "$ADIR" "$LIMIT"`, a non-zero exit refusing with the walk's own line, and a walk that cannot run refusing too, never passing.
- D7's static test is read per host: every host of the `observed` group has a play that reaches it and runs an `alloy`-tagged task. Read per play it would fail the engine play by design, which reaches `zcrypto` and carries no Alloy task while the capture play reaching the same host carries the capture role's; the refusal in `converge.sh` asks the same per-host question.
- The carriers list is the six role task files in path order, `access`, `cache`, `capture`, `mon`, `nas`, `ops`; `alloy_apt`'s files carry no tag of their own, the imports hand it in, so the dead-man node's role widens the list to seven and the shared role never does.
- The play-selection case runs `selection(host, ["alloy"])` for one host of each play and holds that every selected role leaf belongs to that play's Alloy role, and that `base`, `hardening`, `firewall`, `fail2ban`, `chrony`, `docker`, `cache_link`, `access_ops` and `engine` yield no selected leaf; a selected `pre_task` carries `always`.
- The apt install is held to the shared role statically: no task of any role but `alloy_apt` names the `alloy` package — `alloy` or `alloy=<version>`, alone or in a list — in an `ansible.builtin.apt` or `ansible.builtin.package` task, or in an `ansible.builtin.dpkg_selections` task; no task of `site.yml`'s plays or of any task file under `roles/*/tasks/` is an `include_role` whose `name` is `alloy_apt` or an `include_tasks` whose file, free-form or `file:`, has `alloy_apt` as a path component, the module read by its last dotted name, so `ansible.builtin.`, `ansible.legacy.` and the bare name are one; and every role whose tasks import `alloy_apt` imports it with `tasks_from: postcondition` too. An include is a leaf to the walk, so no guard here reads the tasks it brings in, and without `apply` it carries the tag on its own statement alone and selects nothing inside (spec D5): an importer that included the shared role would pass the case's other two checks while its install, pin and hold went unselected under `--tags alloy`. This is what holds plan 00122's Task 9 to Task 8's requirement, its message naming `import_role: alloy_apt`.

```bash
case ",$TAGS," in
  *,alloy,*)
    why="$(uv run --project "$REPO" python "$REPO/infra/scripts/alloy-version.py" reaches --ansible-dir "$ADIR" "$LIMIT" 2>&1)" \
      || refuse "--tags alloy on $LIMIT: ${why:-the tag walk did not run}"
    ;;
esac
```

- [ ] **Step 1: Write the failing tests** — `tests/test_alloy_tag.py`: `test_every_observed_host_has_a_play_that_runs_an_alloy_task`; `test_an_alloy_run_runs_each_plays_always_tasks_and_its_alloy_part_and_nothing_else`; `test_only_the_roles_that_joined_the_tag_carry_it_and_no_play_does`, moved under its name, its list the six; `test_the_alloy_package_is_installed_and_held_by_alloy_apt_alone_and_each_importer_takes_its_postcondition`, its include refusal among its checks. `tests/test_converge_sh.py`: `test_an_alloy_run_on_a_host_no_play_reaches_with_an_alloy_task_is_refused_before_the_preview` (a fixture ansible directory, `<tmp>/infra/ansible`, whose one play for the limit carries no tag: rc 2, the refusal naming the host, no invocation); `test_an_alloy_run_whose_walk_cannot_run_is_refused` (`ZCRYPTO_ANSIBLE_DIR` at an empty directory: rc 2); `test_a_run_without_the_tag_never_runs_the_walk` (a `--tags capture` run with `ZCRYPTO_REPO` at an empty directory still previews).
- [ ] **Step 2: Run them and read the failure**

```bash
uv run pytest tests/test_alloy_tag.py tests/test_converge_sh.py tests/test_capture_alloy_tag.py -q -p no:cacheprovider
```

Expected: the two refusal cases fail, the script previewing; the four static cases pass, since Tasks 4 to 9 landed the joins and the shared install — their failing state is the mutations of Step 9.

- [ ] **Step 3: The refusal, the moved assignments, the tests**
- [ ] **Step 4: Run the tests** — Step 2's command; Expected: no failure.
- [ ] **Step 5: The consumers** — every test file `grep -rl --exclude='*vault*' --exclude='*.sops.*' 'converge.sh' tests/ infra/ .claude/` names under `tests/`, plus `tests/test_run_sh.py`, which it does not name; Expected: no failure.
- [ ] **Step 6: The commit gate**
- [ ] **Step 7: Commit** — `feat(infra): converge.sh refuses an alloy run on a host no play reaches with an alloy task, and every observed play reaches one`, with `PROBE_VERDICT` and the trailer.
- [ ] **Step 8: The tree is clean**
- [ ] **Step 9: Prove the guards** — mutations: the refusal's `|| refuse` deleted; the walk's exit read as success (`|| true`); every `tags: [alloy]` line of `roles/cache/tasks/main.yml` deleted, the fail-fast's and the drift check's with the block's (the observed-host case, `zcrypto-valkey1` unreached); the tag added to the `docker` role entry of the capture play (the play case); the tag added to a task of `base` (the carriers case); `alloy` added back to the mon role's `[grafana, loki]` install, the access role's postcondition import deleted, and the access role's install import, `ansible.builtin.import_role` with `name: alloy_apt` and no `tasks_from`, made `ansible.builtin.include_role` (the shared-install case, a probe each); the reach refusal's `case` arm widened to `*)` (the untagged run's case).

---

### Task 11: The bump gate, the hosts off the fleet's version, and the count

**Operator step P1 (Rollout) runs before Step 1: the gate's fixtures recorded.**

**Files:**
- Modify: `infra/scripts/alloy-version.py` (`gate` and `off-fleet`)
- Create: `tests/fixtures/alloy_version/hub-tags.json`, `Packages`, `index-v1.20.1.json`, `index-v1.20.1.digest` (P1's recordings, committed here)
- Modify: `tests/test_alloy_version.py` (the gate's and `off-fleet`'s cases)
- Modify: `infra/scripts/count-list.sh` (`c_hosts_off_the_fleets_alloy_version` and its `emit` line)
- Modify: `tests/test_count_list.py` (`test_the_alloy_version_count_runs_the_scripts_off_fleet`)
- Modify: `docs/reference/fleet-pins.md` (the **Non-image pins** paragraph: Caddy keeps no row; Alloy on each apt host takes an `alloy` row in the table below, written from the host's `dpkg-query -W alloy` after its first `--tags alloy` converge, with its universal, its set and its count)
- Modify: `tests/test_fleet_contracts.py` (`test_the_alloy_package_rows_name_apt_hosts_at_a_deb_version`)
- Modify: `infra/ansible/group_vars/observed/alloy.yml` (the comment's gate named as `uv run python infra/scripts/alloy-version.py gate`)

**Interfaces:**
- Consumes: Task 2's fleet file; Task 3's script and inventory reader; `fleet-pins.md`'s two tables; P1's fixtures.
- Produces, for R0, Task 17 and `mon-patch-pass`: `uv run python infra/scripts/alloy-version.py gate`, whose lines are `fleet: <version> <digest> <deb>`, then `target: <version> <digest> <deb>` or `target: none — the fleet runs the newest version present in both`, then one `image only: v<version>` or `apt only: <deb>` per newer version in one source, exit 0; or `gate: failed: <source>: <what>`, exit 2. For the count: `uv run python infra/scripts/alloy-version.py off-fleet`, one integer on stdout, each off host on stderr as `  <host>: <why>`; `infra/scripts/count-list.sh hosts-off-the-fleets-alloy-version`.

**What this task decides, where the spec leaves it open:**
- The gate reads Docker Hub's listing (`https://hub.docker.com/v2/repositories/grafana/alloy/tags?page_size=100&ordering=last_updated`) for `v<x.y.z>` names; for each version above the fleet's, an anonymous pull token from `https://auth.docker.io/token?service=registry.docker.io&scope=repository:grafana/alloy:pull`, then `GET https://registry-1.docker.io/v2/grafana/alloy/manifests/v<x.y.z>` with `Accept: application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.list.v2+json`, the digest from `Docker-Content-Digest` and a `linux/amd64` entry required in the body's `manifests`; and `https://apt.grafana.com/dists/stable/main/binary-amd64/Packages`, the `Version:` of each stanza whose `Package:` is exactly `alloy`, the highest revision of an upstream version its deb string. Every request carries a 30 s timeout and goes through one injectable `fetch(url, headers)`, the seam the tests stub.
- `off-fleet` counts each `observed` host whose `alloy` row is off the fleet file — a row of the image table whose leading 12 hex are not `alloy_image_digest`'s, a row of the package table whose backticked version is not `alloy_deb_version` — and each `observed` host with no `alloy` row; a file with neither table exits 2.
- The apt hosts' `alloy` rows are not written here: their producer under D8 is each host's read after its first `--tags alloy` converge, which the records branch writes (R4, R5, R-records). Until then the count reads both apt hosts as hosts with no row, which is the truth of an unheld package.
- The count names its set in `fleet-pins.md`'s paragraph, a corpus file `tests/test_count_list.py` reads, so the entry is named the commit it lands and the rule's line in Task 16 names it again.

The count-list entry:

```bash
c_hosts_off_the_fleets_alloy_version() { uv run python infra/scripts/alloy-version.py off-fleet; }
```

- [ ] **Step 1: P1's fixtures read present** — `ls tests/fixtures/alloy_version/`; Expected: the four files. A missing file holds the task for P1.
- [ ] **Step 2: Write the failing tests** — the gate, its cases over a fixture fleet file at v1.20.0 under the case's `ansible_dir`, as Task 3's functions take their tree, so the one version above it is v1.20.1, whose index P1 recorded (`test_no_newer_version_in_both_prints_none`'s at v1.20.1; a case that needs another index has the stubbed `fetch` answer it): `test_the_newest_version_in_both_is_the_target_with_its_index_digest_and_deb_version`; `test_a_version_in_one_source_alone_is_named_and_never_the_target`; `test_an_index_without_linux_amd64_is_never_the_target`; `test_the_deb_version_is_the_indexs_own_string` (a fixture variant carrying `1.20.1-2` alone yields `1.20.1-2`); `test_no_newer_version_in_both_prints_none`; `test_a_source_that_fails_ends_gate_failed_naming_it` (each of the three, exit 2); `test_every_request_carries_its_timeout`; `test_the_digest_is_the_registrys_answer_and_not_the_listings` (a listing digest that differs from the header loses); `test_a_package_named_like_alloy_is_not_alloy` (a fixture variant appending a stanza whose `Package:` begins `alloy` and is not `alloy`, at a version above every `alloy` stanza, since the index carries no such package). `off-fleet`: `test_an_image_row_off_the_fleets_digest_is_off`; `test_an_apt_row_at_the_fleets_deb_version_is_on_and_another_is_off`; `test_an_observed_host_with_no_alloy_row_is_off`; `test_a_host_outside_observed_is_not_read`; `test_a_pins_file_without_its_tables_exits_2`; `test_the_real_tree_prints_one_count`. The count case; the contract case over a constructed package table — a row on `zaccess` at `` `1.20.1-1` `` passes, a row on `zcrypto-ops`, a container host, fails, and a row at `1.20.1-1` without backticks and one at `` `1.20.1` ``, without its revision, each fail.
- [ ] **Step 3: Run them and read the failure**

```bash
uv run pytest tests/test_alloy_version.py tests/test_count_list.py tests/test_fleet_contracts.py -q -p no:cacheprovider
```

Expected: the gate and `off-fleet` cases fail on the missing subcommands, and `test_the_alloy_version_count_runs_the_scripts_off_fleet` on the missing entry; `test_the_corpus_names_every_entry_but_the_four_the_script_carries_on_its_own` passes, no entry existing yet, and holds the entry named once Step 4 lands it with the paragraph. The contract case passes, its constructed rows read by the case alone.

- [ ] **Step 4: The two subcommands, the entry, the paragraph, the comment**
- [ ] **Step 5: Run the tests** — Step 3's command; Expected: no failure.
- [ ] **Step 6: The consumers** — every test file `grep -rl 'alloy-version\|count-list\|fleet-pins' tests/` names, `tests/test_pins_converged.py`, `tests/test_scripts_have_tests.py` and `tests/test_guidance_guard.py` among them; Expected: no failure.
- [ ] **Step 7: The commit gate**
- [ ] **Step 8: Commit** — `feat(infra): alloy-version.py reads the bump gate from both sources and the hosts off the fleet's version, and the count names them`, with `PROBE_VERDICT` and the trailer.
- [ ] **Step 9: The tree is clean**
- [ ] **Step 10: Prove the guards** — mutations: the target taken from the registry alone, its deb string read with a fallback (the one-source case); the target taken from the apt index alone; the `linux/amd64` check dropped; the deb string derived as `<version>-1`; the digest taken from the listing; a failed apt index read as an empty one (the failing-source case; an empty Hub listing or token answer raises in its JSON parse before the case reads it); the missing-row arm dropped from `off-fleet`; the apt-row comparison against `alloy_version` rather than `alloy_deb_version`; the package match by prefix (the decoy variant); the contract's host check dropped (the container-host row); its backtick check dropped (the bare row); its revision check dropped (the `1.20.1` row); the count entry's `off-fleet` made `reaches zcrypto` (the count case), a subcommand that reads the tree alone: the case runs the entry, and `gate` would read the registry and the apt index.

---

### Task 12: The observability node pages a fleet split across Alloy versions

**Files:**
- Modify: `infra/grafana/alerts.yaml` (`zcrypto-mon-alloy-versions-split` in the `zcrypto-mon` group, after `zcrypto-mon-shipper-loss`)
- Modify: `infra/grafana/fleet-health-dashboard.json` (panel 910, `Monitor — Alloy versions across the fleet`, timeseries, `count by (version) (alloy_build_info{job="integrations/self"})`, `gridPos` `{"h": 8, "w": 12, "x": 12, "y": 128}`, panel 909's datasource and shape)
- Modify: `infra/runbooks/mon.md` (a section `zcrypto-mon-alloy-versions-split` in the shape of `zcrypto-mon-shipper-loss`'s: what you are seeing, what it means — a wave longer than a day or a host the wave did not reach — what to do — read `count by (host, version) (alloy_build_info{job="integrations/self"})` with `--stack mon`, then the host's `alloy` row and `infra/scripts/count-list.sh hosts-off-the-fleets-alloy-version`, then the bump skill's held-host step — and its *Retire when*)
- Modify: `tests/test_infra_alert_rules.py` (`_MON_RULES` gains `"zcrypto-mon-alloy-versions-split": ("warning", "910")`; `test_a_rule_reads_the_node_exactly_when_it_is_in_the_nodes_group` admits it with no `host` matcher in the arm that names `zcrypto-mon-shipper-loss`'s uid, ahead of the arm that holds every other rule of a `NODE_ONLY_GROUPS` group to its host; `test_the_split_rule_counts_versions_across_every_host_for_a_day`)

**Interfaces:**
- Consumes: the measured series, `alloy_build_info` with `version` under `job="integrations/self"` on the node (the spec's measured basis); the group's receiver `metrics`, the shadow channel until spec 00121's cutover.
- Produces, for R10: the rule's uid and expression, read by the push skill's preflight before the node's push.

**What this task decides, where the spec leaves it open:**
- The expression counts the versions, `count(count by (version) (alloy_build_info{job="integrations/self"}))`, the threshold `gt 1`, `for: 24h`, `noDataState: OK` (no series, no split), `execErrState: Alerting`; the summary names no internal token and ends `Runbook: infra/runbooks/mon.md#zcrypto-mon-alloy-versions-split`.
- The rule is pushed to the node only at the wave's close (R10): pushed before, it pages the shadow channel a day after the push while three versions run.

- [ ] **Step 1: Load `zcrypto-refine-rules`** and read *Before you write guidance*, for the runbook section.
- [ ] **Step 2: Write the failing tests** — the `_MON_RULES` entry and the node-group arm; `test_the_split_rule_counts_versions_across_every_host_for_a_day` (the expression exactly, `gt 1`, `24h`, `noDataState` `OK`, the panel 910).
- [ ] **Step 3: Run them and read the failure** — `uv run pytest tests/test_infra_alert_rules.py tests/test_dashboards_cover_metrics.py -q -p no:cacheprovider`; Expected: the group and split cases fail on the missing rule.
- [ ] **Step 4: The rule, the panel, the section**
- [ ] **Step 5: Run the tests** — `uv run pytest tests/test_infra_alert_rules.py tests/test_dashboards_cover_metrics.py tests/test_grafana_push_sh.py tests/test_grafana_compare.py -q -p no:cacheprovider` and the runbook walkers; Expected: no failure.
- [ ] **Step 6: The commit gate**
- [ ] **Step 7: Commit** — `feat(grafana): the observability node pages a fleet whose Alloys run more than one version for a day`, with `PROBE_VERDICT` and the trailer.
- [ ] **Step 8: The tree is clean**
- [ ] **Step 9: Prove the guards** — mutations: `gt 1` to `gt 2`; `for: 24h` to `1h`; the expression counting hosts, `count(alloy_build_info{job="integrations/self"})`; a `host!="zcrypto-mon"` matcher added; the panel id changed to 911.

---

### Task 13: The capture pair ships to both — plan 00121's Task 8, in the tag form

Carried from Task 8 of plan 00121, `docs/plans/00121-dual-shipping.md`, its text the reference for the reviewer; what changes is the converge that lands it and the absence of a hand recreate.

**Files:**
- Modify: `infra/ansible/roles/capture/templates/alloy-secrets.env.j2` (plan 00121's Task 5 six `MON_*` lines appended; its header's "Grafana Cloud credentials", its one source `group_vars/observed/vault.yml`, "The SAME six names" and "does not check this file" re-trued)
- Modify: `infra/ansible/roles/capture/files/config.alloy` (the second `endpoint`; `loki.write "mon"`; the parse stage's `forward_to`; `netdev { device_exclude = "^(veth|br-)" }`; the header's "the same six names the ops and nas Alloy copies read" re-trued; the self-scrape comment's "are unwanted here" and "This target's surviving contribution is therefore its own `up` plus those six process_* names, nothing more" (117 to 120), which the unfiltered node leg falsifies, scoped to the Cloud leg as the NAS copy's are; the Cloud endpoint's "does not merely go undashboarded -- it does not exist", which the node leg falsifies too, scoped to Grafana Cloud as the cache copy's is)
- Modify: `infra/ansible/roles/capture/templates/alloy-compose.yaml.j2` (the `env_file` comment, which named the six `GRAFANA_*` names and `group_vars/observed/vault.yml` alone, re-trued to name both credential sets and `alloy-secrets.env.j2`; nothing else in the file)
- Modify: `infra/ansible/roles/capture/tasks/main.yml` (the comment above `render the alloy secrets env file`, "Renders straight from the vault", re-trued with `group_vars/observed/vars.yml`; no task changes)
- Test: `tests/test_infra_alloy_series.py` (the endpoint guard, the literal case, the template-config case at `read == rendered`, the `loki.write` guard parametrised over the capture file and template; the capture config moved from `test_the_unix_exporter_has_no_netdev_block_where_none_is_prescribed` to `test_the_unix_exporter_excludes_the_container_and_bridge_devices`)

**Interfaces:**
- Consumes: plan 00121's Task 1 group vars and six names, Task 5's template lines and block texts; Task 4's recreate, which forces the recreate on the secrets file's change.
- Produces, for R8, R9 and plan 00121's phase 3: on the node, every capture-host family unfiltered under both hosts, `engine_app` and `cache_proxy` at `up` 0 on `zcrypto-red`; the journal streams of both.

**What this task decides, where the spec leaves it open:**
- Plan 00121 Task 8's decisions stand: the capture pair joins the template-config case at `read == rendered`; the second endpoint's queue is its own; nothing touches `logship-secrets.env.j2` or the capture compose template.
- The converge that lands it is each capture host's wave converge, `--tags alloy` with the fleet's digest, whose recreate is forced by the changed secrets file, so plan 00121's R6 hand `up -d` and its whole-role form are gone (spec D6, D12).

- [ ] **Step 1: Write the failing tests**
- [ ] **Step 2: Run the tests and read the failure** — `uv run pytest tests/test_infra_alloy_series.py -q -p no:cacheprovider`; Expected: the capture cases of the endpoint, literal, `loki.write` and `netdev` guards fail; the template-config case passes before and after the commit, failing on either half alone.
- [ ] **Step 3: The template, the config and the comments**
- [ ] **Step 4: Dry-start the edited config in the dry-start form, against v1.19.2's binary** — Expected: the form's; Task 20 re-runs it at the target.
- [ ] **Step 5: Run the tests** — Step 2's command; Expected: no failure.
- [ ] **Step 6: The consumers** — every test file `grep -rl --exclude='*vault*' --exclude='*.sops.*' 'alloy-secrets.env\|alloy-env.j2\|group_vars/observed\|config.alloy' tests/ infra/ .claude/` names under `tests/`, `tests/test_clock_offset.py` among them; Expected: no failure.
- [ ] **Step 7: The commit gate**
- [ ] **Step 8: Commit** — `feat(infra): a capture host's Alloy ships unfiltered to the node beside Grafana Cloud`, with `PROBE_VERDICT` and the trailer.
- [ ] **Step 9: The tree is clean**
- [ ] **Step 10: Prove the guards** — plan 00121 Task 8's six mutations: a `MON_` line dropped from the template; a `GRAFANA_` line edited; a `MON_PROM_*` credential substituted into the Cloud endpoint; a `MON_LOKI_*` read substituted into `loki.write "grafana"`; the second receiver dropped from the `forward_to`; the `netdev` exclusion removed.

---

### Task 14: The runbook pages and the two READMEs — every Alloy converge is the host's `--tags alloy`, and the patch pass leaves Alloy to the gate

**Files** — each line re-trued to `--tags alloy` with the fleet's digest where the role takes one (on a host held under `infra/ansible/host_vars/<host>/alloy.yml`, the digest that file names, the role refusing the fleet's there), the role's recreate in place of a hand `docker compose up -d`, and the apt hosts held and pinned; a line a sweep finds beyond these is re-trued the same way:
- `infra/runbooks/zaccess.md`: `zaccess-alloy-converge` rewritten, its own *Retire when* having fired — a config change ships by `--limit zaccess --tags alloy`, which installs the fleet's version, held and pinned, with no digest operand and no bake; the version moves only by a bump; its *Retire when* the access role no longer importing the shared Alloy install; and `zaccess-cut-ssh-relay` step 3's "the two procedures above too", false for an Alloy converge that no longer runs the relay's tasks, re-trued; and `zaccess-revoke-client-cert`'s *What it means* gains that the converge's preview fetches the Grafana and Caddy repositories' signing keys, so a source that does not answer refuses the converge and the revocation waits on it.
- `infra/runbooks/mon.md`: `mon-patch-pass` — *What it means*'s four vendor packages become three, Alloy held at the fleet's version and moved by a bump alone; a step of its own appended as step 7, after the reboot flag, `uv run python infra/scripts/alloy-version.py gate`, whose `target:` line newer than the fleet's is carried into `.claude/skills/zcrypto-bump-alloy/SKILL.md` and never installed here — appended, so steps 1 to 6 keep the numbers the pages cite: in `mon.md`, `mon-dark`'s step 6 (step 5), the patch pass's own *What it means* (steps 2 to 5) and `zcrypto-mon-reboot-pending` (step 6); in `drills-telemetry.md`, the rule-cadence bullet and the two `mon_get` lines (step 5); step 1's read compares the node's `alloy` with `alloy_deb_version` in `infra/ansible/group_vars/observed/alloy.yml`; `alloy` out of both lines of step 3; step 3's closing `alloy validate` sentence, "an upgraded Alloy was restarted by its package", re-trued; step 4's un-tagged converge installing the fleet's version; `mon-secrets` step 4's container-host form, a converge with the running digest then a hand `up -d`, becoming `--tags alloy` with the fleet's digest, the role's recreate proven by `.State.StartedAt`; and the same step's NAS sentence (148), the whole apply dropped as a path for a changed password, since its `compose restart alloy` keeps the environment the container was created with and its `compose up -d` can recreate `archive-pull`: the NAS takes the narrow form alone.
- `infra/runbooks/cache.md`: step 4 of the reset (line 86) and step 5 (114) passing the fleet's Alloy digest, the node's recreate the converge's own; the Alloy recreate step (145); the config-fault step (146) as `--limit zcrypto-valkey<N> --tags alloy -e cache_alloy_digest=<the fleet's>`.
- `infra/runbooks/hosts.md`: the keep-regex step (163), the fleet's digest in the narrow form.
- `infra/runbooks/observability.md`: step 6 (56), the capture and ops recreate by the host's `--tags alloy` converge; step 7 (57), "pass the currently running Alloy digest" to the fleet's; *Restarting Alloy* (293), a recreate being the converge's.
- `infra/runbooks/fleet.md`: the preamble's sentence on the bridgehead's Alloy (5) and the memory-headroom step 3 (54) where they name an Alloy converge.
- `infra/runbooks/ops-node.md`, `infra/runbooks/nas.md`, `infra/runbooks/gate.md`: swept for an Alloy converge or recreate; a restart by hand (`docker restart`, `compose restart alloy`) stays.
- `infra/runbooks/drills-telemetry.md`: W4's preconditions, "after the box", to after the wave, on a later day, inside the box, outside the day's window; its restore unchanged, a `docker restart` of the same image, with one sentence that a recreate is the host's `--tags alloy` converge.
- `infra/nas/README.md`: the Deploy block's narrow form and its paragraph (16 to 22), its render-only `--tags nas` precondition gone, the narrow run writing its own Alloy pin line; line 190; line 9's "renders the two env files next to them", `config.alloy` landing in the stack directory's `conf/`; line 180's "to the already-provisioned Grafana Cloud instance" and line 184's "Host metrics + the gate metrics + the container logs are what flow off this NAS", the node's leg shipping beside Cloud's and carrying Alloy's whole self-scrape.
- `infra/ops/README.md`: the Alloy section's deploy steps (196 to 204), `--tags alloy -e ops_alloy_digest=<the fleet's>` with the role's recreate.

- [ ] **Step 1: Load `zcrypto-refine-rules`** and read *Before you write guidance*.
- [ ] **Step 2: The sweep** — `grep -rn -i 'compose up -d\|alloy_digest\|apt-followed\|followed from apt\|only-upgrade\|nas_apply_compose' infra/runbooks/ infra/nas/README.md infra/ops/README.md`, each hit read against the line list.
- [ ] **Step 3: The edits**
- [ ] **Step 4: The consumers**

```bash
uv run pytest tests/test_internal_terms_not_operator_visible.py tests/test_runbook_internal_tokens.py tests/test_runbook_triggers.py tests/test_guidance_guard.py tests/test_guidance_refs_resolve.py tests/test_count_list.py tests/test_code_prose_citations.py tests/test_ops_daily.py tests/test_drill_log.py -q -p no:cacheprovider
```

Expected: no failure.

- [ ] **Step 5: The commit gate** — mdformat reformats the runbook pages; re-run until clean.
- [ ] **Step 6: Commit** — `docs(runbooks): every Alloy converge on the pages is the host's --tags alloy, and the patch pass leaves Alloy to the gate`, with the trailer; no guard changes, so no probe.
- [ ] **Step 7: The tree is clean**

---

### Task 15: `docs/reference/fleet.md` names the fleet file and the held apt Alloys

**Files:**
- Modify: `docs/reference/fleet.md` (the bridgehead bullet's "Its Alloy is a native deb followed from apt — no digest, no pins row, no bake" re-trued: held at the fleet's version, pinned at 1001, installed by `--tags alloy`, its `alloy` row in `fleet-pins.md`'s package table; the Services table's `grafana-alloy` row brought to the fleet's digest by each role's `--tags alloy` converge; the native `alloy` row naming `zaccess` beside `zcrypto-mon`, held at the fleet's version; a Hosts bullet naming `infra/ansible/group_vars/observed/alloy.yml` as the version every `observed` host's Alloy runs outside a wave, with its set and count)

- [ ] **Step 1: The edits**, each cell under 200 characters and each bullet under 700, no date.
- [ ] **Step 2: The consumers** — `uv run pytest tests/test_fleet_contracts.py tests/test_count_list.py tests/test_guidance_guard.py tests/test_code_prose_citations.py -q -p no:cacheprovider`; Expected: no failure.
- [ ] **Step 3: The commit gate**
- [ ] **Step 4: Commit** — `docs(reference): fleet.md names the fleet's Alloy version file and the apt Alloys held at it`, with the trailer.
- [ ] **Step 5: The tree is clean**

---

### Task 16: The rule — every host's Alloy runs the fleet's version outside a wave

**Files:**
- Modify: `.claude/rules/fleet-deploys.md` (its opening line naming `.claude/skills/zcrypto-bump-alloy/SKILL.md` for every Alloy, the apt ones included; a bullet: every host's Alloy runs the version `infra/ansible/group_vars/observed/alloy.yml` names outside a wave (set: the hosts of the inventory's `observed` group, each by its `alloy` row in `docs/reference/fleet-pins.md`; count: `infra/scripts/count-list.sh hosts-off-the-fleets-alloy-version`), the one claim its count reads — one wave at a time and the primary last and attended stay with the wave's order in the bump skill (Task 17); the pin-row rule's evidence clause gaining the NAS's Alloy pin on an applied `--tags alloy` run, as `infra/scripts/pins-converged.py` reads it)

**What this task decides, where the spec leaves it open:**
- The always-loaded set grows by the new bullet and the clause: the commit carries `Ambient grows by N bytes: <reason>`, N the guard's own measure of the staged file, the reason the owner's rulings of 2026-10-05, which name the rules among what the package updates; if the orchestrator reads those rulings as no grant of growth, the commit waits for the owner's word or an equal deletion.

- [ ] **Step 1: Load `zcrypto-refine-rules`** and read *Before you write guidance*; each line on ground 1, the check named in it.
- [ ] **Step 2: The edits**
- [ ] **Step 3: The consumers** — `uv run pytest tests/test_guidance_guard.py tests/test_guidance_refs_resolve.py tests/test_count_list.py tests/test_internal_terms_not_operator_visible.py -q -p no:cacheprovider`, and `infra/scripts/count-list.sh ambient-bytes` before and after; Expected: no failure, and the growth the line states.
- [ ] **Step 4: The commit gate** — the `staged-kind` hook Passed.
- [ ] **Step 5: Commit** — `claude(rules): every host's Alloy runs the fleet's version outside a wave, and an applied NAS alloy run evidences its Alloy pin`, with the growth line and the trailer; a `claude` commit carrying no other file; the commit's `guidance-guard` hook Passed, its growth line accepted.
- [ ] **Step 6: The tree is clean**

---

### Task 17: The bump skill — one wave of every Alloy under `--tags alloy`, gated on a version in both sources

**Files:**
- Modify: `.claude/skills/zcrypto-bump-alloy/SKILL.md` (the description, a trigger alone, naming every Alloy and the gate; *What this is*: nine Alloys, ten with the dead-man node's, seven containers and the apt ones held at the fleet's version, and its "on the NAS the apply also bounces `archive-pull`" (line 11) re-trued — the narrow run recreates Alloy alone and leaves `archive-pull` running — as are the order paragraph's "its apply bundles an archive-pull bounce" (51), the NAS leg's "the apply also restarts `archive-pull`" (72), Step 3's (141) and Closeout's (157) below, the five sentences of the skill that have a NAS Alloy bump restart `archive-pull`; the hosts table gaining `zaccess` and `zcrypto-mon`; the paragraph that puts the apt Alloys outside the canary order removed; the standing caution's "the render-only Alloy compose" re-trued to the role's recreate; Step 0: `uv run python infra/scripts/alloy-version.py gate` in place of `gh api …/releases/latest` and `docker buildx imagetools inspect`, the release notes still read for config-language changes, a fix the fleet needs that ships in one channel alone put to the owner, every config dry-started at the target in plan 00121's dry-start form as this plan's Global Constraints change it, every loopback address the copy dials pointed at `127.0.0.1:9` — six configs, seven with the dead-man node's once it exists — and the baseline's "6 of 7 (per-converge extra-vars, no repo default)" re-trued: `docker inspect grafana-alloy --format '{{.Config.Image}}'` on the seven container hosts, the NAS's through `sudo /usr/local/bin/docker`, and `dpkg-query -W alloy` on `zaccess`, `zcrypto-mon` and the dead-man node once it exists, each against its `fleet-pins.md` row; Step 1: the fleet file's three values and the NAS literal in one commit, the rows re-trued per host after its converge; Step 2: the order and the forms below, one wave at a time (a change that moves the fleet file again does not merge while a wave is open), no host-side `up -d`, the box's cache-node and primary bounds, ops the stop point, and the held-host paragraph re-trued — a host the wave cannot reach held with its row, its reason after the word `held`, and its hold file, the NAS's hold setting `nas_alloy_image` back beside its hold file, and a hold ended by a change that deletes the hold file, the NAS's moving `nas_alloy_image` to the fleet's digest, the row keeping `held` until the host's converge re-trues it; Step 3: the role's image read or post-condition inside the run, on an apt host `dpkg-query -W alloy`, `apt-mark showhold`, `apt-cache policy alloy` and `sudo readlink "/proc/$(systemctl show -p MainPID --value alloy)/exe"`, and the NAS's addition "(the apply bounced it)" re-trued, the narrow run leaving `archive-pull` alone; Rollback: the forms below; Closeout's re-true of `archive-pull | nas`'s `since` dropped, the narrow run never restarting it; the sentence that only the capture role carries the tag removed; and the same paragraph's list of what the narrow run touches, "the stale-config removal, the config drift check, and the Alloy block's user, directories, config, secrets file and compose file", which Task 4's refusal, recreate and image read outgrow, dropped, the paragraph keeping "nothing of the capture daemon" and the test that holds what the tag selects)

**The order and the forms the skill takes** (spec D12 and D16):

- The order: `zcrypto-ops`, the stop point; `zcrypto-mon`, then `zaccess`, then the dead-man node once it exists; `nas`; `zcrypto-valkey1`, `zcrypto-valkey2`, `zcrypto-valkey3`, one per run, each outside the day's window and away from an engine restart; `zcrypto-red`; `zcrypto`, attended and last, away from a 4-hourly boundary and any engine restart, outside the day's window.
- The converges, each previewed by `converge.sh` and never under `timeout`:

```
infra/ansible/scripts/converge.sh site.yml --limit zcrypto-ops --tags alloy -e ops_alloy_digest=<alloy_image_digest>
infra/ansible/scripts/converge.sh site.yml --limit zcrypto-mon --tags alloy
infra/ansible/scripts/converge.sh site.yml --limit zaccess --tags alloy
infra/ansible/scripts/converge.sh site.yml --limit nas --tags alloy -e nas_apply_compose=true
infra/ansible/scripts/converge.sh site.yml --limit zcrypto-valkey<N> --tags alloy -e cache_alloy_digest=<alloy_image_digest>
infra/ansible/scripts/converge.sh site.yml --limit zcrypto-red --tags alloy -e capture_alloy_digest=<alloy_image_digest>
infra/ansible/scripts/converge.sh site.yml --limit zcrypto --tags alloy -e converge_primary=true -e capture_alloy_digest=<alloy_image_digest>
```

- One host's rollback, then its hold — the previous value committed in `infra/ansible/host_vars/<host>/alloy.yml`, `alloy_image_digest` on a container host and `alloy_deb_version` on an apt host, its reason in a comment above it; a cache node adds `pins_override` while `fleet-pins.md` does not yet record the digest it runs, and the primary `-e converge_primary=true`, as its wave form does:

```
infra/ansible/scripts/converge.sh site.yml --limit <host> --tags alloy -e <role>_alloy_digest=<previous digest> -e '{"alloy_override": "<reason>"}'
infra/ansible/scripts/converge.sh site.yml --limit zcrypto --tags alloy -e converge_primary=true -e capture_alloy_digest=<previous digest> -e '{"alloy_override": "<reason>"}'
infra/ansible/scripts/converge.sh site.yml --limit zcrypto-valkey<N> --tags alloy -e cache_alloy_digest=<previous digest> -e '{"alloy_override": "<reason>"}' -e '{"pins_override": "<reason>"}'
infra/ansible/scripts/converge.sh site.yml --limit <apt host> --tags alloy -e alloy_deb_version=<previous> -e '{"alloy_override": "<reason>"}'
```

- The NAS, which takes no operand: a hand recreate from the previous pin on the host, the previous image still there, `cd /volume1/docker/zcrypto-archive && sudo sed -i 's|^ALLOY_IMAGE=.*|ALLOY_IMAGE=grafana/alloy@<previous index digest>|' .env && sudo /usr/local/bin/docker compose up -d --no-deps --force-recreate alloy`; then its hold, the previous digest as `alloy_image_digest` in `infra/ansible/host_vars/nas/alloy.yml` with its reason and `nas_alloy_image` set back to it in the same commit, no NAS converge running before that commit merges.
- The fleet's rollback: revert the change that moved the fleet file, merge, and run the wave again in the same order.

- [ ] **Step 1: Load `zcrypto-refine-rules`** and read *Before you write guidance*; the description is ambient, so a commit that grows it carries its `Ambient grows by N bytes: <reason>` line, under the reason Task 16's growth line gives, the owner's rulings of 2026-10-05; if the orchestrator reads those as no grant of growth, the commit waits for the owner's word or an equal deletion.
- [ ] **Step 2: The edits**
- [ ] **Step 3: The consumers** — `uv run pytest tests/test_guidance_guard.py tests/test_guidance_refs_resolve.py tests/test_internal_terms_not_operator_visible.py tests/test_infra_alloy_series.py -q -p no:cacheprovider` and every test file `grep -rl 'zcrypto-bump-alloy' tests/` names; Expected: no failure.
- [ ] **Step 4: The commit gate**
- [ ] **Step 5: Commit** — `claude(skills): the Alloy bump moves every Alloy to one version present in both sources, host by host under --tags alloy`, with the trailer and, where the description grew, its growth line.
- [ ] **Step 6: The tree is clean**

---

### Task 18: The rollout skill's Alloy bullets — the role's recreate and the fleet's digest

**Files:**
- Modify: `.claude/skills/zcrypto-rollout-image/SKILL.md` (the bullet on a `config.alloy` edit, "pass the currently-running Alloy digest", to the fleet's; the bullet that the ops and capture roles render the Alloy compose and never restart it, re-trued to the role's recreate under the tag on a digest or secrets change, a `memory:` change reaching the container through the compose file's hash; the engine re-pin's `--tags alloy,engine -e capture_alloy_digest=<currently-running>` to the fleet's; the NAS bullet's apply-only restart, beside the narrow form; the cache re-pin's `cache_alloy_digest=sha256:<running>` to the fleet's, which the node runs outside a wave; each of these "the fleet's" naming a host held under `infra/ansible/host_vars/<host>/alloy.yml` as the one exception, its digest that file's)

- [ ] **Step 1: Load `zcrypto-refine-rules`**
- [ ] **Step 2: The edits**
- [ ] **Step 3: The consumers** — `uv run pytest tests/test_guidance_guard.py tests/test_guidance_refs_resolve.py tests/test_internal_terms_not_operator_visible.py -q -p no:cacheprovider` and every test file `grep -rl 'zcrypto-rollout-image' tests/` names; Expected: no failure.
- [ ] **Step 4: The commit gate**
- [ ] **Step 5: Commit** — `claude(skills): the rollout skill's Alloy bullets name the role's recreate and the fleet's digest`, with the trailer.
- [ ] **Step 6: The tree is clean**

---

### Task 19: What spec 00121 and plan 00121 owe — the ordering this package supersedes

**Files:**
- Modify: `docs/specs/00121-self-hosted-observability-design.md` — at D2, D14, D15 and D21 and at the first invariant, one line each in the form `**AMENDED by spec 00123 D<n> (2026-10-06).** <what now holds>`: D2, Alloy on the node held and pinned at the fleet's version, installed under `--tags alloy`, with an `alloy` row in `fleet-pins.md`, the other packages still followed (spec 00123 D3); D14 and D15, the NAS and capture changes riding spec 00123's pull request and reaching their hosts in its wave, inside the box, by the applied `--tags alloy` on the NAS and `--tags alloy` with the fleet's digest on the capture pair, the primary's `--skip-tags engine` form retired (D13, D14); D21, W4 after spec 00123's wave, on a later day, inside the box (D18); the first invariant, the primary's one converge of this work being spec 00123's `--tags alloy -e converge_primary=true` in its wave (D13).
- Modify: `docs/plans/00121-dual-shipping.md` — the same form, `**AMENDED by plan 00123 (2026-10-06).**`, at: the Global Constraints' bullets on the merge order, the inside-box set and the primary's form, the shipper-stop drill's timing, and the dry-start form, as this plan's Global Constraints change it; Task 7's heading and its "merges in a pull request of its own after the box", it being built on spec 00123's branch at `1408962dc` and `bac386834`; the Global Constraints' bullet on a name reaching an Alloy process, at the NAS's "their converge restarting Alloy after both files land", and Task 7's *Interfaces*, at "restarts Alloy after them", a restart keeping the environment the container was created with, so the NAS's `MON_*` names load by the narrow form's `--force-recreate` (spec 00123 D6); Task 8, carried as plan 00123's Task 13; R5 and R6, replaced by plan 00123's R6, R8 and R9; R7, after plan 00123's wave; R9, counted from the primary's recreate in plan 00123's R9; R-records-2, the records branch after plan 00123's wave.

**What this task decides, where the spec leaves it open:**
- Each amendment adds a line beside the text it supersedes and deletes nothing, so the record of what was planned stays readable; neither file is pinned by a registry record (`grep -c '00121' docs/reference/trial-registry.jsonl` prints 0).
- The records branch `docs/t0217-phase-2-records` edits plan 00121's slots too: it rebases onto `develop` after this package merges, and the slot lines and these amendment lines sit apart.

- [ ] **Step 1: The amendment lines**
- [ ] **Step 2: The consumers** — `uv run pytest tests/test_code_prose_citations.py tests/test_change_index.py -q -p no:cacheprovider`; Expected: no failure.
- [ ] **Step 3: The commit gate**
- [ ] **Step 4: Commit** — `docs(specs): spec 00121 and plan 00121 carry the ordering spec 00123 supersedes`, with the trailer.
- [ ] **Step 5: The tree is clean**

---

### Task 20: The fleet file at the gate's reading, every config dry-started at it

**Runs after R0.**

**Files:**
- Modify: `infra/ansible/group_vars/observed/alloy.yml` (the three values: [[ROLLOUT: R0's gate reading — the target version, its full index digest and its deb version string, and each newer version in one source alone]])
- Modify: `infra/ansible/host_vars/nas/vars.yml` (`nas_alloy_image: grafana/alloy@<the target's index digest>`, bare)

**Interfaces:**
- Consumes: R0's reading; Task 2's NAS-row contract, under which the NAS's row keeps what the NAS runs until its wave converge.
- Produces, for the pull request and the wave: the fleet file at the target; the change that, merged, opens the wave (spec D1).

**What this task decides, where the spec leaves it open:**
- `fleet-pins.md` is not edited here: every row records what its host runs, and each is re-trued from that host's wave converge in the records branch.
- When R0's target is not 1.20.1, the apt hosts' moves follow from it: a target below `1.20.1-1` moves the node down under `allow_downgrade` (spec D11), named in the commit message and in R4.

- [ ] **Step 1: The two edits** from the slot's three values.
- [ ] **Step 2: Dry-start every config at the target** — the dry-start form against the target's release binary for `infra/nas/config.alloy`, `roles/ops/files/config.alloy`, `roles/capture/files/config.alloy`, `roles/cache/files/config.alloy`, `roles/access/files/config.alloy`, and `roles/mon/files/config.alloy`, and the dead-man node's config if the `hc` role is on this branch; Expected: each the form's; then the target's release binary unzipped from `https://github.com/grafana/alloy/releases/download/v<target>/alloy-linux-amd64.zip` into the scratch directory `.tmp/alloy-validate/` and made executable, `chmod +x .tmp/alloy-validate/alloy-linux-amd64`, and from the repository root `env -i PATH=/usr/bin:/bin .tmp/alloy-validate/alloy-linux-amd64 validate infra/ansible/roles/access/files/config.alloy; echo rc=$?` and the same over `infra/ansible/roles/mon/files/config.alloy`, Expected `rc=0` on both; then the access and mon configs dry-started and validated the same way against v1.19.2's release binary, the version a revert of this task's commit installs on `zaccess` and `zcrypto-mon` under `allow_downgrade` — the first wave's fleet rollback (spec D16) — Expected the same; the scratch directory removed after.
- [ ] **Step 3: The consumers** — `uv run pytest tests/test_fleet_contracts.py tests/test_pins_converged.py tests/test_alloy_version.py tests/test_infra_alloy_series.py tests/test_converge_sh.py -q -p no:cacheprovider`; Expected: no failure, `test_the_nas_alloy_literal_is_the_nas_committed_digest` and `test_the_real_pair_reads_zero` among them.
- [ ] **Step 4: The commit gate**
- [ ] **Step 5: Commit** — `chore(fleet): the fleet's Alloy version is <the target>, present in the image registry and the apt index`, its message carrying R0's three lines and each dry-start's reading, with the trailer.
- [ ] **Step 6: The tree is clean**

---

### Task 21: T0219 resolved

**Files:**
- Modify: `docs/open-topics/T0219-one-alloy-version-across-the-fleet.md` and `docs/open-topics/README.md`, by the `topic-ops` skill: `status: resolved`, the findings carrying the package's delivery, the wave left to the fleet as `CLAUDE.md` places a converge a solution still needs.

- [ ] **Step 1: Load `topic-ops`** and follow its resolve mechanics, the index re-rendered by `uv run python infra/scripts/topics-index.py`.
- [ ] **Step 2: The consumers** — `uv run pytest tests/test_open_topics_frontmatter.py tests/test_internal_terms_not_operator_visible.py -q -p no:cacheprovider`; Expected: no failure.
- [ ] **Step 3: The commit gate**
- [ ] **Step 4: Commit** — `docs(topics): T0219 resolved — one Alloy version across the fleet`, with the trailer.
- [ ] **Step 5: The tree is clean**

---

## Rollout (attended)

**Operator steps.** Nothing below is an executor step: each reaches a host, a registry, the apt index, the node, Grafana Cloud or Slack. Every converge goes through `infra/ansible/scripts/converge.sh` from merged `develop`, which previews, asks for the typed `--limit` and appends its row to `docs/reference/deploy-log.jsonl`; it is never wrapped in `timeout`, and each host's real pass follows its own `--check` preview. `W$` is the workstation at the repository root, `H$` a shell on the named host (`ssh hp`, `ssh mon`, `ssh access`, `ssh nas`, `ssh db1` to `db3`, `ssh red`, `ssh zcrypto`). `DIGEST` below is `alloy_image_digest` and `DEB` is `alloy_deb_version` in `infra/ansible/group_vars/observed/alloy.yml` at merged `develop`. `KRAKEN` is the whole-feed read, `curl -fsS https://status.kraken.com/api/v2/scheduled-maintenances.json | jq .`, read entire and judged by `.claude/rules/fleet-deploys.md`'s test, at planning and again immediately before each converge of `zcrypto-ops`, `zcrypto-red` and `zcrypto`. `STEP3` is `.claude/skills/zcrypto-bump-alloy/SKILL.md`'s Step 3 for the host: the container or unit read (on the NAS through `sudo /usr/local/bin/docker`, which sudo's PATH omits), the shipping counters on `127.0.0.1:12345` read twice more than 60 s apart, `failed_total` 0 on every destination, the host's alloy-dark rule Normal and a fresh Loki line for it. `PROOF` is plan 00121's per-host proof for the node's leg, its shipper-loss row read an hour after the recreate. `AUDIT` is `uv run python infra/scripts/deploy-log-audit.py maintenance --venue-facing --since <R2's instant>`.

**Stop conditions, for every host.** A preview that names a file or a task outside the host's Alloy part holds the host, and nothing converges there until the owner has read it. A refusal by the role — an operand off the host's committed digest, the fail-fast, the deb-version refusal, the NAS pin read — means the operand was wrong: the host's committed value is re-read — `infra/ansible/host_vars/<host>/alloy.yml`'s where the host is held, else the fleet file's — and the converge re-typed with it, and no `alloy_override` is passed to get past it in this wave. An image read or post-condition that fails, or an Alloy that is not running after the run, darkens the host: its restore is spec D16's one-host rollback, attended — the previous version under `-e '{"alloy_override": "<reason>"}'`, on a cache node with R7's `pins_override` beside it, on the primary with `-e converge_primary=true` — and the host is then held: its `fleet-pins.md` row carries what it runs and, after the word `held`, the reason, and a commit puts the previous value in `infra/ansible/host_vars/<host>/alloy.yml` (`alloy_image_digest` on a container host, `alloy_deb_version` on an apt host, the reason in a comment above it), which every later converge of the host reads before the fleet file's, so none moves it back unasked; the wave stops for the owner. The NAS takes no operand: its restore is the attended hand recreate from the previous pin, the image still on the NAS, `H$ cd /volume1/docker/zcrypto-archive && sudo sed -i 's|^ALLOY_IMAGE=.*|ALLOY_IMAGE=grafana/alloy@<the previous index digest>|' .env && sudo /usr/local/bin/docker compose up -d --no-deps --force-recreate alloy`, and its hold is the other hosts': a commit puts the previous digest as `alloy_image_digest` in `infra/ansible/host_vars/nas/alloy.yml`, the reason in a comment above it, and sets `nas_alloy_image` back to `grafana/alloy@<that digest>`, which Task 2's literal test then holds equal to the hold file, so every NAS converge from that commit on lands the previous pin; no NAS converge runs before it merges. A hold ends by a change that deletes the hold file — the NAS's also setting `nas_alloy_image` to the fleet's digest — and leaves the row's `held` reason until the host's converge from merged `develop` re-trues it, which Task 2's NAS-row test admits. In this first wave the fleet's rollback, a revert of Task 20's commit, takes `zaccess` and `zcrypto-mon` down to `1.19.2-1`, below the version each runs now, on configs Task 20's Step 2 dry-started at v1.19.2. STEP3 not green within fifteen minutes of the recreate stops the wave. A Kraken window over a venue-facing converge waits it out. Any touch of a capture daemon, the engine, the liquidations poller, Valkey or Sentinel, `archive-pull`, Caddy, WireGuard, the SSH relay, Grafana or its stores stops the wave for the owner.

**P1. The gate's fixtures** (before Task 11). From the branch's worktree, written into `tests/fixtures/alloy_version/` for Task 11 to commit:

```
W$ mkdir -p tests/fixtures/alloy_version && cd tests/fixtures/alloy_version
W$ curl -fsS 'https://hub.docker.com/v2/repositories/grafana/alloy/tags?page_size=100&ordering=last_updated' | jq '{results: [.results[] | {name, digest, last_updated}]}' > hub-tags.json
W$ curl -fsS https://apt.grafana.com/dists/stable/main/binary-amd64/Packages | awk 'BEGIN{RS=""; ORS="\n\n"} {match($0, /^Package: [^\n]+/); p = substr($0, 10, RLENGTH - 9)} (p == "alloy" && $0 ~ /\nVersion: 1\.(19|2[0-9])\./) || (p != "alloy" && p ~ /^(alloy|loki)/ && !(p in seen)) {if (p != "alloy") seen[p] = 1; print}' > Packages
W$ tok="$(curl -fsS 'https://auth.docker.io/token?service=registry.docker.io&scope=repository:grafana/alloy:pull' | jq -r .token)"
W$ curl -fsS -D headers.tmp -H "Authorization: Bearer $tok" -H 'Accept: application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.list.v2+json' https://registry-1.docker.io/v2/grafana/alloy/manifests/v1.20.1 -o index-v1.20.1.json && grep -i '^docker-content-digest:' headers.tmp | awk '{print $2}' | tr -d '\r' > index-v1.20.1.digest && rm headers.tmp && unset tok
```

Expected: four files; `hub-tags.json` naming no `v<x.y.z>` tag above `v1.20.1` — one there holds Task 11, whose gate cases stand on v1.20.1 being the newest version, for a re-plan of its fixtures; `Packages` holding the five `alloy` stanzas `1.19.0-1` to `1.20.1-1` and the first stanza of `loki` and of `loki-canary`, the index carrying no other `alloy*` package, so Task 11's decoy is a fixture variant; `index-v1.20.1.digest` one `sha256:` line beginning `2aa2099af76c`.

**R0. The gate's reading** (after Task 19, before Task 20). `W$ uv run python infra/scripts/alloy-version.py gate` from the branch's tip. Expected: `fleet: 1.19.2 sha256:b8ec653c4423… 1.19.2-1`, a `target:` line and any one-source lines; the reading fills [[ROLLOUT: R0's gate reading — the target version, its full index digest and its deb version string, and each newer version in one source alone]]. A `gate: failed:` line is read again after the source answers; a target other than 1.20.1 is checked against the apt hosts' installed versions, spec D11's downgrade case named for R4 or R5. The same sitting reads `git ls-tree origin/develop infra/ansible/roles/hc` and the state of plan 00122's second pull request, its Tasks 8 to 10 on `feat/t0218-dead-man-tasks-8-10`: an `hc` role on `develop` before this package merges is spec D14's case, its join carried by this pull request: the plan stops for a re-plan that adds that join as a task — the `hc` role's imports of `alloy_apt`, its tag test with the three guards and its exclusions, the carriers and Task 10's static cases at seven, its config's dry-start — and the node's wave step after R5, before R6.

**R1. The pull request** (after Task 21). Through the `open-pr` skill over the branch; the `pre-review` workflow over the range's prose and messages, then `review` once the branch is complete, `re-review` over a fix range at most twice, every reviewer on Opus; the body names the read, the tip and the probes. It is not merged before R2: the merge arms the capture hosts' drift asserts, the NAS's new config and the apt hosts' pin (spec D14), so it lands on the wave's day and that state lasts the wave alone. Before it opens, `git fetch origin`; when `origin/develop` has moved since the merge before Task 1, the branch merges it again as that merge's Step 1 does, and its Step 2 runs on the new merge with `tests/test_infra_mon_role.py`, `tests/test_infra_alert_rules.py`, `tests/test_mon_alloy_tag.py` and `tests/test_alloy_tag.py` beside it.

**R2. The wave's day, and the merge.** The first attended window after R1's review that lies outside the box's day's window (`infra/runbooks/engine-procedures.md#rung-2-the-day-s-window`) and outside plan 00122's sitting, which runs after this wave (spec D14). At planning: `KRAKEN`; `date -u +%Y-%m-%dT%H:%M:%SZ`, the instant `AUDIT` counts from; the fleet's running Alloys read off the hosts against `fleet-pins.md` (`sudo docker inspect grafana-alloy --format '{{.Config.Image}}'` on the six other container hosts and `sudo /usr/local/bin/docker inspect grafana-alloy --format '{{.Config.Image}}'` on the NAS, `dpkg-query -W alloy` on the two apt hosts); `git fetch origin` and R0's `git ls-tree origin/develop infra/ansible/roles/hc` read again, an `hc` role there stopping the plan as R0 says; when `origin/develop` has moved since R1's read, R1's merge and test runs are repeated and the moved range takes its reads before the merge, the body naming the new tip. Then `merge-pr` merges the pull request, and `git switch develop && git pull --ff-only && git status --porcelain` reads empty. The wave runs to its end with no other converge of a capture host, the NAS, the edge or the node between its hosts, nor of a cache node before its own R7 (spec D14).

**R3. ops — the wave's stop point.** `KRAKEN` immediately before. `H$ sudo docker inspect zcrypto-ops-liquidations --format '{{.RestartCount}} {{.State.StartedAt}}'` before. `W$ infra/ansible/scripts/converge.sh site.yml --limit zcrypto-ops --tags alloy -e ops_alloy_digest=DIGEST --check` — the preview names `/etc/zcrypto-ops/alloy/compose.yaml` changed and nothing outside `/etc/zcrypto-ops/alloy`, the recreate, read and assert skipped. Then the same without `--check`: the recreate reports `changed`, the image assert passes. After: the liquidations read unchanged; `H$ sudo docker inspect grafana-alloy --format '{{.Config.Image}}'` reads `grafana/alloy@DIGEST` and `--format '{{.RestartCount}} {{.State.StartedAt}}'` reads 0 and a start after the converge, the recreate's report read against it; STEP3 with ops' additions, `zcrypto-hcio-watchdog` back to Normal and `up{job="liquidations_app"} == 1`; `Ops · ERROR logs` once on the outgoing container's `remotecfg` lines and `zcrypto-fleet-daemon-restarted` once, each the skill's known shape. Every later host waits on this one: any stop condition here holds the wave until its fix has merged.

**R4. The observability node.** `W$ infra/ansible/scripts/converge.sh site.yml --limit zcrypto-mon --tags alloy --check` — the preview names `/etc/apt/preferences.d/alloy` created, and the install, the hold and `alloy enabled + started` skipped, the preview fact true while the pin file would change, and nothing of Grafana, Loki, Prometheus or Caddy. Then the real pass: the pin file created, the install unchanged where the node already runs DEB, the hold changed. After, on the node as the deploy user: `dpkg-query -W alloy` reads DEB; `apt-mark showhold` lists `alloy`; `apt-cache policy alloy` shows DEB as installed and candidate, its line at priority 1001; `apt-get -s upgrade`, `apt-get -s full-upgrade` and `apt-get -s install --only-upgrade alloy` each with `grep -c '^Inst alloy '` reading 0; `sudo readlink "/proc/$(systemctl show -p MainPID --value alloy)/exe"; echo rc=$?` reading `/usr/bin/alloy`, no ` (deleted)`, and `rc=0` — under sudo, since the deb's unit runs Alloy as the `alloy` user and an unprivileged read of another user's `/proc/<pid>/exe` prints nothing. Where no version moved, the post-condition's restart is skipped, the node's shape with no upgrade at all; where the target moved the node, its package's restart already ran and the post-condition restarts nothing. Then STEP3 on the node, its own `zcrypto-alloy-dark-mon` read on the node's rules endpoint. The readings fill [[ROLLOUT: each apt host's reads after its converge — the installed version, the hold, the pinned candidate at 1001, the three simulations and the post-condition's restart or none]].

**R5. The bridgehead.** `H$ systemctl show -p ActiveEnterTimestamp --value caddy wg-quick@zaccess0 zaccess-ssh-proxy.socket` before. `W$ infra/ansible/scripts/converge.sh site.yml --limit zaccess --tags alloy --check` — the preview names the pin file created, and the install, the hold and `alloy enabled + started` skipped — the preview fact is true while the pin file would change — and nothing of Caddy, WireGuard, the relay or the probe. Then the real pass: the install moving `alloy` from `1.20.0-1` to DEB, the hold changed, the post-condition's restart reporting `changed`, the bridgehead's shape, whose package does not restart Alloy on an upgrade. After: the Caddy, WireGuard and relay reads unchanged; `grep ' upgrade alloy:' /var/log/dpkg.log | tail -1` against `systemctl show -p ExecMainStartTimestamp --value alloy`, the start after the upgrade; R4's exe read under sudo, `/usr/bin/alloy` with no ` (deleted)` and `rc=0`; R4's package reads and simulations; STEP3, `count(up{host="zaccess"})` on Cloud and on the node. Its readings join R4's slot.

**R6. The NAS.** `H$ sudo /usr/local/bin/docker inspect zcrypto-archive-pull --format '{{.State.StartedAt}} {{.RestartCount}}'` and `sudo /usr/local/bin/docker inspect grafana-alloy --format '{{.Created}} {{.RestartCount}}'` before. `W$ infra/ansible/scripts/converge.sh site.yml --limit nas --tags alloy --check` — the report names `config.alloy`, `alloy-secrets.env` and `.env`, render-only. Then `… --tags alloy -e nas_apply_compose=true`: its preview names the `.env` line edit changed and skips the pin read, its refusal, the recreate, the image read and its assert; the real pass: the pin read passes, the recreate runs, the image assert passes. After: `archive-pull`'s read unchanged; Alloy's `.Created` moved; `.Config.Image` reads `grafana/alloy@DIGEST`; STEP3 with the NAS's addition, `zcrypto_gate_*` series still arriving; `PROOF` for the NAS, its reading into [[ROLLOUT: the NAS's and each capture host's count by (job) on the node after its converge, against Cloud's count for it]].

**R7. The cache nodes, one node per run.** After R6's `PROOF` (spec D1); each outside the day's window and away from an engine restart (`infra/runbooks/engine-procedures.md#rung-2-what-not-to-do`), `zcrypto-valkey1`, then `2`, then `3`: `H$ sudo docker inspect --format '{{.Name}} {{.RestartCount}} {{.State.StartedAt}}' zcrypto-valkey zcrypto-sentinel` before and after, the same two lines; `W$ infra/ansible/scripts/converge.sh site.yml --limit zcrypto-valkey<N> --tags alloy -e cache_alloy_digest=DIGEST --check`, the preview naming `/opt/zcrypto-cache/alloy/compose.yaml` alone, then the real pass, the recreate and the assert; STEP3 with the cache nodes' addition, `redis_up` 1 under `valkey` and `sentinel`. From a node's converge until the records branch merges, the node runs the target, which `fleet-pins.md` does not yet record, so its Alloy pins-recording refusal meets every later converge of that node carrying `cache_alloy_digest` — a re-run of this step, the one-host restore, a `cache.md` procedure — whose form then carries `-e '{"pins_override": "<reason>"}'` beside it.

**R8. The capture secondary.** `KRAKEN` immediately before. `H$ sudo docker inspect zcrypto-capture --format '{{.RestartCount}} {{.State.StartedAt}}'` before. `W$ infra/ansible/scripts/converge.sh site.yml --limit zcrypto-red --tags alloy -e capture_alloy_digest=DIGEST --check` — the preview names `alloy-secrets.env` (Task 13's names), `conf/config.alloy` and `compose.yaml` under `/etc/zcrypto-capture/alloy`, and nothing under `/opt/zcrypto-capture`. Then the real pass: the recreate forced by the secrets file, the assert passing. After: `zcrypto-capture`'s read unchanged, its newest parquet still advancing; STEP3 with the capture hosts' additions; `PROOF` for `zcrypto-red`, its shipper-loss row read an hour after the recreate, its reading into R6's slot.

**R9. The capture primary, attended.** After R8's shipper-loss read, so at least an hour after R8's recreate (spec D1); `KRAKEN` immediately before; away from a 4-hourly boundary and any engine restart, outside the day's window. `H$ sudo docker inspect zcrypto-capture --format '{{.RestartCount}} {{.State.StartedAt}}'` and the same for `zcrypto-engine` before. `W$ infra/ansible/scripts/converge.sh site.yml --limit zcrypto --tags alloy -e converge_primary=true -e capture_alloy_digest=DIGEST --check`, the preview as R8's, then the real pass. After: both containers' reads unchanged; STEP3 with `up{job="capture_app"}` and `up{job="engine_app"}` 1; `PROOF` for `zcrypto`, its recreate time the one plan 00121's R9 counts from, its count by (job) into R6's slot, its head reading into [[ROLLOUT: R9's head-series reading with every host shipping, against plan 00121's R0 node-alone reading, 10222 head series in T0217's findings on branch docs/t0217-phase-2-records, plus the fleet's figure, and the bar of 40,000]].

**R10. The wave's close.** Every `observed` host's Alloy runs DIGEST or DEB, by the reads above. `AUDIT`, its count over the wave's rows 0. The node's rule: the push skill's Step 1 preflight, `W$ uv run python infra/scripts/grafana-query.py --stack mon 'count by (host, version) (alloy_build_info{job="integrations/self"})'`, every host of the fleet on one version, into [[ROLLOUT: R10's preflight — alloy_build_info on the node, one version across the fleet's hosts]]; then the node's push, `infra/runbooks/mon.md#mon-push` step 1, and Grafana Cloud's push of the dashboard, the push skill's Step 0 in the dual period, from merged `develop`; the rule's first sample read by value, `count(count by (version) (alloy_build_info{job="integrations/self"}))` reading 1, and its health `ok` on the node's rules endpoint.

**R11. The shipper-stop drill on the secondary** (plan 00121's R7, `infra/runbooks/drills-telemetry.md#drill-w4`; spec D18). On a later day than the wave, in its own attended window, inside the box and outside the day's window, on `zcrypto-red` alone, never in a sitting with a capture converge; `KRAKEN` at planning and immediately before the stop; its section's seven parts; its reading into [[ROLLOUT: R11's W4 reading — both copies' activeAt against about 16 minutes, and the absent-not-0 read on the node]].

**R12. Plan 00121's R8 and R9.** The boundary reading as plan 00121's R8 writes it, into [[ROLLOUT: R12's two boundary readings — equal, or off by the boundary sample]], written into spec 00121's measured basis by amendment in the records; and the comparison's earliest day, [[ROLLOUT: the first day whose 00:00 UTC is at least R9's primary recreate time plus 50 h — the comparison's earliest day]], into `COMPARISON_FROM` in `infra/scripts/ops_daily.py` and T0217's `ripe_when` by a pull request of its own, as plan 00121's R9 says.

**R-records. What the records branch `docs/t0217-phase-2-records` receives**, rebased onto `develop` after the merge: the wave's deploy-log rows; `fleet-pins.md`'s seven container `alloy` rows at the target's 12 hex and version, each `since` from its container's `.State.StartedAt` (the NAS's from `.Created`), each operand `b8ec653c4423 — v1.19.2`, the NAS's version cell keeping "upstream `grafana/alloy`, no `-compat` variant"; the glossary gaining the target's full digest, `b8ec653c4423`'s line naming it every container row's operand, and `491b0578c049`'s line dropped, no table cell carrying it after the rewrite; the two apt rows of the package table, `alloy` on `zaccess` and on `zcrypto-mon`, each version cell DEB in backticks, each `since` from its converge and each note `dpkg hold; pinned at 1001`, never the word `held`, which marks a host the wave left behind (spec D16); `infra/scripts/count-list.sh hosts-off-the-fleets-alloy-version` reading 0 on the branch; the measured-basis amendment to spec 00123 with R4's and R5's readings, the D4 simulations and both post-condition shapes; W4's `docs/reference/drill-log.md` entry and its findings in its section; R12's boundary reading into spec 00121; plan 00121's slots and T0217's findings and done list; `AUDIT`'s line. Its message carries every slot's reading.

## Resolution

This plan delivers T0219: one version in one file, every role's Alloy under one tag, the apt Alloys held, the gate, the record, the count, the node's rule and the first wave. It does not build the dead-man node, whose role joins by plan 00122's Task 9 under Task 8's requirement, nor deliver plan 00121's phases 3 and 4; it hands plan 00121 the capture pair's dual shipping, the shipper-stop drill's timing and the comparison's earliest day.

## Slots the rollout fills

- `[[ROLLOUT: R0's gate reading — the target version, its full index digest and its deb version string, and each newer version in one source alone]]` (R0; Task 20) — the gate's live run from the branch.
- `[[ROLLOUT: each apt host's reads after its converge — the installed version, the hold, the pinned candidate at 1001, the three simulations and the post-condition's restart or none]]` (R4, R5) — into spec 00123's measured basis in the records.
- `[[ROLLOUT: the NAS's and each capture host's count by (job) on the node after its converge, against Cloud's count for it]]` (R6, R8, R9) — plan 00121's per-host proof.
- `[[ROLLOUT: R9's head-series reading with every host shipping, against plan 00121's R0 node-alone reading, 10222 head series in T0217's findings on branch docs/t0217-phase-2-records, plus the fleet's figure, and the bar of 40,000]]` (R9) — plan 00121's R6 slot, read here.
- `[[ROLLOUT: R10's preflight — alloy_build_info on the node, one version across the fleet's hosts]]` (R10) — the node's push waits on it.
- `[[ROLLOUT: R11's W4 reading — both copies' activeAt against about 16 minutes, and the absent-not-0 read on the node]]` (R11) — the drill-log entry.
- `[[ROLLOUT: R12's two boundary readings — equal, or off by the boundary sample]]` (R12) — spec 00121's amendment.
- `[[ROLLOUT: the first day whose 00:00 UTC is at least R9's primary recreate time plus 50 h — the comparison's earliest day]]` (R12) — `COMPARISON_FROM` and `ripe_when`, in their own pull request.
