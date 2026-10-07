# The engine's own re-pin gate: the candidate image's offline preflight on the engine host — implementation plan

> Every value a rollout reading decides is a marked slot, `ROLLOUT:` inside double square brackets, listed at the end.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An engine re-pin is refused unless the candidate image's own `zcrypto engine preflight` passed on the engine host against a candidate render of its configuration and the image's revision is on `develop`, or a reason-bearing `engine_preflight_override` is on the record; the capture bake no longer gates the engine (spec 00124).

**Architecture:** Six tasks on `feat/00124-engine-repin-gate`, one pull request. The subcommand first, because the role's tests describe the command the role runs and the rule names the subcommand; then the role, the wrapper, the counts, the prose, and the final sweep. The first image to carry the preflight is the one built from the merged tree; the rollout slots are read at that rollout.

**Tech Stack:** Typer (`cli/engine/command.py`), the exec gate's readers (`cli/engine/execgate.py`), Ansible 2.x with the Templar test substrate (`tests/test_infra_converge_guards.py`), bash (`infra/ansible/scripts/converge.sh`, `infra/scripts/count-list.sh`), jq, `infra/scripts/mutate-probe.sh`.

## Global Constraints

- Every commit is green over the changed files' consumers (`grep -rl <script-or-module> tests/ infra/ .claude/` names them); the full suite runs in CI alone.
- One file kind per commit (`.cz.toml`; the `staged-kind` hook); never an amend after a review has read a commit; the `claude(rules)` and `claude(skills)` commits carry their `Ambient grows by N bytes: <reason>` line where they grow the set.
- A guard change is proven with `infra/scripts/mutate-probe.sh`, each verdict quoted verbatim in the commit message; never a hand-rolled mutate-and-restore.
- Nothing reaches a host, a venue, Grafana, GitHub or a registry; no `ansible-playbook` runs — the workstation is a fleet host; role behaviour is proven on the Templar substrate the existing guard tests use.
- Never print a container's environment; a `docker inspect` names one field. Never read, print, grep or diff a file whose path contains `vault`.
- A comment or docstring stays only if a reader would act differently without it; help text and runbook text carry no internal term (`tests/test_internal_terms_not_operator_visible.py`, whose allowlist is never widened).
- Spec 00083 is not edited (spec 00124 D1).
- The runbook-read floor `tests/test_ops_daily.py` holds is measured before and after any runbook edit; a page is never reshaped to fit it.

## File structure

- `cli/engine/preflight.py` (new): `run_preflight(state_dir: Path) -> PreflightResult` and the JSON line; `cli/engine/command.py`: the `preflight` subcommand.
- `infra/ansible/roles/engine/tasks/main.yml`: the D5 tasks removed; the candidate render, the preflight run, the provenance read, the two asserts, the echo, the cleanup, the record append.
- `infra/ansible/scripts/converge.sh`: `engine_preflight_override` in `OVERRIDES`; the row's `preflight` key.
- `infra/scripts/count-list.sh`: `c_engine_repins_without_a_preflight`, `c_engine_preflight_overrides`, their `emit` lines.
- `.claude/rules/fleet-deploys.md`, `.claude/skills/zcrypto-rollout-image/SKILL.md`, `docs/reference/fleet-pins.md`, `infra/runbooks/engine-procedures.md`.
- `tests/test_engine_preflight.py` (new); `tests/test_infra_converge_guards.py`; `tests/test_converge_sh.py`; `tests/test_count_list.py`.

## Review Focus

- The preflight container's isolation: `--network none`, both mounts `:ro`, no `--env-file`, no `-p`, `--entrypoint zcrypto` — in the task's text and in a test on that text.
- The preflight writes nothing: a test over the state dir's listing and mtimes.
- The asserts fail closed: an unreadable probe or an empty label refuses; only the reason-bearing override admits.
- The candidate render is removed on every path.
- The ten D5 tests are gone and nothing else references the removed registers.

### Before Task 1: the branch is at develop's tip and the plan's premises hold

- [ ] `git -C /home/zhaow/Projects/zcrypto-kraken/.claude/worktrees/repin-gate merge-base --is-ancestor origin/develop HEAD` exits 0 after `git fetch origin develop`.
- [ ] `grep -n 'engine canary parity' infra/ansible/roles/engine/tasks/main.yml` prints the assert's name once; `grep -c 'engine canary parity' tests/test_infra_converge_guards.py` prints at least 1.
- [ ] `grep -n '_verified_nautilus_versions\|_installed_nautilus_version' cli/engine/execgate.py` prints both definitions.

### Task 1: `zcrypto engine preflight` — the image's offline self-test

**Files:** `cli/engine/preflight.py` (new), `cli/engine/command.py`, `tests/test_engine_preflight.py` (new).

**Steps:**

- [ ] Write the tests first, red: `test_preflight_happy_path_exits_0_with_the_json_shape` (a tmp state dir holding every BASKET×GRID store file as `_store_path` names them, a journal day with one `cycle-HH.json` the replay reader loads, a configuration the loader accepts — the loader's fixed location is monkeypatched to a tmp file the way `tests/test_engine_command.py` does for `engine run`); `test_preflight_refuses_a_config_the_loader_rejects` (exit 1, `config` carries the error text); `test_preflight_refuses_an_unverified_library_version` (`_verified_nautilus_versions` monkeypatched to a set lacking the installed version; exit 1, `verified` false); `test_preflight_lists_every_missing_store` (two store files removed; exit 1, `stores_missing` names exactly those two); `test_preflight_refuses_an_unloadable_newest_cycle_record` (the newest `cycle-HH.json` truncated; exit 1, `journal` carries the error); `test_preflight_reports_journal_none_without_a_record` (no journal day; `journal` is `none`, exit 0); `test_preflight_writes_nothing` (the state dir's recursive listing and every mtime equal before and after a run); `test_preflight_imports_no_venue_or_cache_client` (`python -I -c "import sys, cli.engine.preflight; print(sorted(m for m in sys.modules if m.startswith('cli.engine')))"` prints no `venue`, `execclient` or `cache` module).
- [ ] Implement `cli/engine/preflight.py`: `run_preflight(state_dir)` returns a dataclass with the fields spec 00124 D2 names, each check in its own function; `to_json_line()`; the config check calls `_load_engine_config()` through `cli.engine.command`'s loader by late import (so the command module's Typer app is not re-built); the verified check calls the two `execgate` readers; the store check reuses `BASKET`, `GRID_INTERVALS` and `_store_path`; the journal check finds the newest `<YYYY-MM-DD>/cycle-<HH>.json` by name order and loads it with the replay reader.
- [ ] Wire `engine preflight` in `cli/engine/command.py` beside `probe-plan`: `--state-dir` required; prints the JSON line; `raise typer.Exit(0 if result.ok else 1)`; the help text one sentence, operator-readable.
- [ ] Run: `uv run pytest tests/test_engine_preflight.py tests/test_engine_command.py tests/test_cli_help_hygiene.py tests/test_internal_terms_not_operator_visible.py -q -p no:cacheprovider` → `Expected: all passed`.
- [ ] Probes (`infra/scripts/mutate-probe.sh`, each verdict into the message): the verified check inverted (`s/version in verified/version not in verified/` or the equivalent on the written line) against `-k unverified`; the store walk's `exists()` negated against `-k missing_store`; the journal loader call removed against `-k unloadable`; a `Path.write_text` planted into `run_preflight` against `-k writes_nothing` — `Expected: mutate-probe: KILLED (control proven, tree restored byte-identically)` for each.
- [ ] `uv run pre-commit run -a` clean.
- [ ] Commit `feat(engine): zcrypto engine preflight — the image's offline self-test for the re-pin gate` with the probe verdicts.

### Task 2: The engine role — the preflight, the provenance read, the asserts; the capture bake goes

**Files:** `infra/ansible/roles/engine/tasks/main.yml`, `tests/test_infra_converge_guards.py`.

**Steps:**

- [ ] Read `tests/test_infra_converge_guards.py:1-120` and `:784-897` for the Templar substrate and the ten tests this task replaces; read `roles/engine/tasks/main.yml:120-210` and `:600-616` (the live render and its handler).
- [ ] Replace the ten tests with, under a heading "engine preflight (spec 00124)": `test_engine_preflight_runs_the_candidate_image_isolated` (the `docker run` task's command carries `--network none`, `{{ engine_state_dir }}:{{ engine_state_dir }}:ro`, `/opt/zcrypto-engine/zcrypto.toml.candidate:/app/zcrypto.toml:ro`, `--entrypoint zcrypto`, `engine preflight --state-dir`, and carries neither `--env-file` nor ` -p ` nor `--network host`); `test_engine_preflight_engages_only_on_a_re_pin` (the `when` reads the running-digest probe exactly as the parity probe did); `test_engine_preflight_renders_the_candidate_without_a_handler` (the candidate template task has no `notify` and `check_mode: false`); `test_engine_preflight_candidate_is_removed_on_every_path` (the removal sits in the block's `always`); `test_engine_preflight_refuses_rc_1_and_rc_2_and_admits_a_reason` (the assert's two arms under Templar: rc 0 passes; rc 1 and rc 2 fail with the `fail_msg` naming the JSON line and "carries no preflight" respectively; a 9-character reason passes, `true` does not); `test_engine_preflight_fails_closed_when_the_probe_is_skipped_or_unreadable`; `test_engine_provenance_reads_one_label_field_and_checks_develop` (the inspect format is `{{index .Config.Labels "org.opencontainers.image.revision"}}` and nothing wider; the check task is `git merge-base --is-ancestor`, `delegate_to: localhost`, `run_once: true`, no `fetch`); `test_engine_provenance_refuses_an_empty_label`; `test_engine_preflight_record_carries_the_five_keys` (the append writes `digest`, `rc`, `revision`, `on_develop`, `line`); `test_engine_canary_parity_is_gone` (`engine_secondary_digest_probe` and `engine canary parity` appear nowhere under `infra/ansible/`).
- [ ] Edit the role: remove :150-202's four tasks and the comment; keep the running-digest probe under its name; add, in order, the candidate render, the `docker run` (registered, `failed_when: false`, `check_mode: false`), the label read (same flags), the controller check (`command: git merge-base --is-ancestor {{ label }} origin/develop`, `delegate_to: localhost`, `run_once: true`, `failed_when: false`, `changed_when: false`), the preflight assert, the provenance assert (both with the shared override arm), the echo, the record append (a `copy` of the merged dict into `zcrypto_window_record` when that var is defined, mirroring `site.yml:165-190`), all inside a `block` whose `always` removes the candidate file.
- [ ] Run: `uv run pytest tests/test_infra_converge_guards.py tests/test_infra_cache_proxy.py -q -p no:cacheprovider` → `Expected: all passed`; `grep -rn 'engine_secondary_digest_probe\|engine canary parity' infra/ tests/ .claude/ docs/reference/` → `Expected: no line under infra/ or tests/`.
- [ ] Probes: `:ro` dropped from the state mount against `-k isolated`; `--network none` dropped against `-k isolated`; the `always` turned into a plain task after the assert against `-k removed_on_every_path`; the inspect format widened to `{{json .Config.Labels}}` against `-k one_label_field`; the assert's rc arm loosened to `rc != 2` against `-k refuses_rc_1` — `Expected: KILLED (control proven …)` for each.
- [ ] Commit `feat(config): the engine's re-pin gate is the candidate image's preflight on the engine host; the capture bake gates capture alone` with the verdicts.

### Task 3: The wrapper admits the override and records the preflight

**Files:** `infra/ansible/scripts/converge.sh`, `tests/test_converge_sh.py`.

**Steps:**

- [ ] Read `converge.sh:40-60` (OVERRIDES), `:140-165` (the braced-JSON refusal), `:224-310` (the row); read `tests/test_converge_sh.py:245-277` and `:835-844` (the override grammar tests) and `:699-709` (the window key).
- [ ] Tests first: `test_engine_preflight_override_is_admitted_only_as_braced_json` (the `k=v` form is refused with the existing message; the JSON form passes); `test_row_carries_preflight_when_the_record_has_it` (a record file holding both `window` and `preflight` yields a row with both, each key intact); `test_row_omits_preflight_when_the_record_lacks_it`.
- [ ] Add `engine_preflight_override` to `OVERRIDES`; copy a `preflight` key from the record file into the row beside `window` with the same jq shape.
- [ ] Run: `uv run pytest tests/test_converge_sh.py -q -p no:cacheprovider` → `Expected: all passed`; `bash -n infra/ansible/scripts/converge.sh` → rc 0.
- [ ] Probe: the `preflight` copy removed against `-k carries_preflight` → `Expected: KILLED (control proven …)`.
- [ ] Commit `feat(config): converge.sh admits engine_preflight_override and records the preflight beside the window`.

### Task 4: Two counts over the engine's preflight rows

**Files:** `infra/scripts/count-list.sh`, `tests/test_count_list.py`.

**Steps:**

- [ ] Read `count-list.sh:320-340` (`round_closed_at`, `c_canary_bypasses`) and `:560-572` (the `emit` lines); read `tests/test_count_list.py:764-771` (the canary fixture).
- [ ] Tests first, on a fixture log under `COUNT_LIST_DEPLOY_LOG`: `test_engine_repins_without_a_preflight_counts_the_row_the_gate_did_not_pass` (a row tagged engine with `engine_image_digest`, `preflight.rc` 1 and no override counts 1; the same row with `preflight.rc` 0 counts 0; the same row with the override and no `preflight` counts 0); `test_engine_preflight_overrides_counts_the_bypass` (a row carrying `engine_preflight_override` counts 1); both entries appear in the `emit` list, so `infra/scripts/count-list.sh` prints each name.
- [ ] Add `c_engine_repins_without_a_preflight` and `c_engine_preflight_overrides` in `c_canary_bypasses`'s shape with the selectors spec 00124 D5 names; add the two `emit` lines.
- [ ] Run: `uv run pytest tests/test_count_list.py -q -p no:cacheprovider` → `Expected: all passed`; `infra/scripts/count-list.sh engine-repins-without-a-preflight engine-preflight-overrides` → `Expected: engine-repins-without-a-preflight	0` and `engine-preflight-overrides	0` (no row carries a preflight yet).
- [ ] Probe: the `.preflight.rc != 0` selector dropped against `-k did_not_pass` → `Expected: KILLED (control proven …)`.
- [ ] Commit `feat(infra): two counts over the engine's preflight rows`.

### Task 5: The rule, the skill, the pins reference and the runbook follow the mechanism

**Files:** `.claude/rules/fleet-deploys.md`, `.claude/skills/zcrypto-rollout-image/SKILL.md`, `docs/reference/fleet-pins.md`, `infra/runbooks/engine-procedures.md`.

**Steps:**

- [ ] Measure before: `infra/scripts/count-list.sh ambient-bytes`; `uv run pytest tests/test_ops_daily.py -k 'read_only_diagnostics' -q -p no:cacheprovider` and note the ratio its assertion message prints when run with `-rA` (or read the floor function's value the way the test does).
- [ ] `fleet-deploys.md`: edit :5 to the capture-only text spec 00124 D6 gives; insert the engine bullet after it verbatim from D6. Commit alone as `claude(rules): the engine's re-pin gate is its preflight; the capture bake gates capture alone` with `Ambient grows by N bytes: the engine gate's bullet names the new mechanism and its two counts — the owner's ruling of 2026-10-05` where N is what `infra/scripts/guidance-guard.py` measures from the staged file.
- [ ] `SKILL.md`: Phase 3's checklist gains the preflight line; Phase 4's rollback paragraph replaces the parity-assert sentence with D7's text; "## Engine converges" :113 replaces the mechanical-bake clause. Commit alone as `claude(skills): the rollout skill reads the engine preflight where it read the bake` with its `Ambient grows by` line only if the description line changed (the body is not ambient).
- [ ] `fleet-pins.md:44`: name the engine bullet beside the capture one. `engine-procedures.md:768-790`: one sentence that the converge runs the image's preflight itself. Commit `docs(reference): fleet-pins names the engine's preflight gate` and `docs(runbooks): the dry run owes only the account read now that the converge runs the preflight`.
- [ ] Run: `uv run pytest tests/test_internal_terms_not_operator_visible.py tests/test_guidance_refs_resolve.py tests/test_count_list.py tests/test_ops_daily.py -q -p no:cacheprovider` → `Expected: all passed`; `uv run python infra/scripts/guidance-guard.py --range develop..HEAD` → `Expected: every commit states its ambient growth`; `infra/scripts/count-list.sh ambient-bytes` after, the delta recorded in the PR body.

### Task 6: The sweep and the body

**Files:** none new.

**Steps:**

- [ ] `uv run pre-commit run -a` clean; `infra/scripts/count-list.sh probe-verdicts-without-the-script prose-only-commits-without-the-prover` → `Expected: 0 and 0`.
- [ ] `uv run pytest tests/test_engine_preflight.py tests/test_infra_converge_guards.py tests/test_converge_sh.py tests/test_count_list.py tests/test_engine_command.py tests/test_cli_help_hygiene.py tests/test_internal_terms_not_operator_visible.py -q -p no:cacheprovider` → `Expected: all passed`.
- [ ] The PR body (through `open-pr`): `## Spec / Plan` names 00124; the read line; the `Fable floor substituted by Opus: <reason>` line if the read ran on Opus (`cli/engine/` is on the floor's path list — `uv run python infra/scripts/merge-gate.py --fable-paths`); `## Changes` from the diff; `## Rollout` carries the slots below as the November bump's reading.

## Rollout slots (read at the first engine converge under the gate — the November bump)

- [[ROLLOUT: the preflight's JSON line on the primary, quoted from the play output]]
- [[ROLLOUT: the deploy-log row's `preflight` object]]
- [[ROLLOUT: `infra/scripts/count-list.sh engine-repins-without-a-preflight engine-preflight-overrides` after the row]]
- [[ROLLOUT: whether `--memory 512m` was admitted on the engine host (the run's stderr)]]
