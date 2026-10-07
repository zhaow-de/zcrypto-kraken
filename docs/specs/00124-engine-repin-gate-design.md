# The engine's own re-pin gate: the candidate image's offline preflight on the engine host replaces the capture bake as the engine converge's gate

## Problem

The engine role refuses a re-pin until the secondary runs the candidate digest as capture (spec 00083 D5, `infra/ansible/roles/engine/tasks/main.yml:150-202`): there is no engine secondary, so the capture bake was made the engine's gate.
The bake proves what the two images share — the base layers, the dependencies, the entrypoint, the memory envelope, the log shipping — and nothing of the engine's own payload: the rollout skill already says so (`.claude/skills/zcrypto-rollout-image/SKILL.md:38`, "an engine payload's own proof is its next disarmed boundary cycles, never the bake").
It also couples every engine change to a capture re-pin of the secondary, inside rung 2's box where no capture converge is wanted, and it reads a live host that may be unreachable for a reason unrelated to the engine.
The owner's ruling of 2026-10-05 (`.local/deadman/spec-decisions.md`, carried in the memo): the engine role's canary parity is replaced by an engine preflight on the candidate digest, run on the engine host before the re-pin — an offline self-test from that image — with CI green on the revision the image was built from, the converge inside the inter-cycle gap, and the disarmed proving cycle after; the capture bake stays the capture role's alone.

## Decisions

### D1 — The engine role reads no capture bake

The four tasks at `roles/engine/tasks/main.yml:150-202` go: the secondary's capture-digest probe, the parity assert, its override echo, and the comment that cites 00083 D5; the running-engine digest probe at :155-161 stays as the preflight's engagement condition (D3).
`canary_override` becomes the capture role's alone, with its grammar, its echo and its count entry `canary-bypasses-on-the-primary` unchanged — the capture re-pin on the primary is still the set that count reads.
The ten tests under "engine canary parity (spec 00083 D5)" in `tests/test_infra_converge_guards.py:784-897` go with the tasks; D10 names what replaces them.
Spec 00083 is not edited: D5 stays as the record of what was built, and this spec is the record of its replacement.

### D2 — The image carries its own preflight: `zcrypto engine preflight`

A new subcommand, `zcrypto engine preflight --state-dir <dir>`, offline and read-only: it opens no socket, imports no venue client, and writes nothing under the state dir or anywhere else.
Its checks, each a field of one JSON line on stdout:
- `config`: the engine configuration loads through the same loader `engine run` uses, `_load_engine_config()` (`cli/engine/command.py:102`, which takes no path and reads the application configuration from its fixed location, the `/app/zcrypto.toml` the compose file mounts); the value is `ok` or the loader's error text.
- `verified`: the library version the image runs is a member of the image's own `cli/engine/order-semantics-verified.json` — read through the exec gate's own readers, `_verified_nautilus_versions()` and `_installed_nautilus_version()` in `cli/engine/execgate.py`, so the preflight and the gate can never disagree — and an image whose order semantics were never verified is refused before it ever runs.
- `stores_missing`: the store files `engine run` requires before it connects (`cli/engine/command.py:822-834`, the BASKET×GRID walk), listed when absent under `--state-dir`; the preflight reads the directory listing and nothing else.
- `journal`: the newest `cycle-<HH>.json` under the state dir's journal, if any, loads through the reader `engine replay` uses (`cli/engine/command.py:974-1000`) — `ok`, `none` when no record exists, or the reader's error text; it is a load, never a replay, so a candidate whose decisions legitimately differ from the recorded ones still passes.
- `version` and `nautilus`: the image's own `zcrypto` version string and the library version, for the record.
- `ok`: true when `config` is `ok`, `verified` is true, `stores_missing` is empty and `journal` is not an error.
Exit 0 when `ok` is true, 1 when any check failed; an image built before this spec has no such command, and Typer's exit 2 on an unknown command is the preflight's third verdict — "this image carries no preflight" — which D3's assert names.
The subcommand lives in `cli/engine/preflight.py`, wired in `cli/engine/command.py`; its help text carries no internal term.

### D3 — The role runs the preflight on the engine host, against a candidate render, before anything else renders

Engagement: `engine_image_digest` is defined and absent from the running engine container's `{{.Config.Image}}` (the probe at :155-161, which stays) — the same condition the parity probe had, so an unchanged digest takes no preflight.
The role first renders the engine configuration template to a candidate path beside the live one, `/opt/zcrypto-engine/zcrypto.toml.candidate`, with `check_mode: false` and no handler: the candidate is tested against the configuration it will run with, not the previous converge's render, so a template error is refused here and not at the restart.
The run, on the engine host: `docker run --rm --network none --user {{ engine_uid }}:{{ engine_gid }} --memory 512m -v {{ engine_state_dir }}:{{ engine_state_dir }}:ro -v /opt/zcrypto-engine/zcrypto.toml.candidate:/app/zcrypto.toml:ro --entrypoint zcrypto {{ engine_image }}@{{ engine_image_digest }} engine preflight --state-dir {{ engine_state_dir }}` — no `--env-file`, no published port, the state dir read-only, the network none: nothing of the live engine (its arm file, its restart hold, its journal, its key, its cache session, its metrics port) is reachable from the preflight container.
The task is `check_mode: false`, `failed_when: false`, registered; the candidate render is removed after the assert whether it passed or failed (a `block`/`always`).
The assert, "engine preflight — refuse an engine re-pin the candidate image has not passed on this host": `rc == 0`, or `engine_preflight_override` under spec 00082 D1's grammar (longer than 8 characters, not `true`/`false`/`1`/`yes`); its `fail_msg` quotes the JSON line on rc 1, names "the image carries no preflight (built before spec 00124)" on rc 2, and gives the bypass as JSON — `-e '{"engine_preflight_override": "<why this cannot wait>"}'`.
The echo task, "engine preflight override accepted — the reason, on the record", mirrors the capture echo's shape.
`engine_preflight_override` joins `converge.sh`'s `OVERRIDES` list (:50), so the braced-JSON form is the only one the wrapper admits.

### D4 — The image's revision is on `develop`

The pulled image's `org.opencontainers.image.revision` label (`docker inspect --format '{{index .Config.Labels "org.opencontainers.image.revision"}}' {{ engine_image }}@{{ engine_image_digest }}` — one field, never `.Config`) is read on the engine host, and the controller checks it against its own checkout: `git merge-base --is-ancestor <revision> origin/develop`, `delegate_to: localhost`, `run_once`, no fetch — a stale `origin/develop` refuses a fresh image until the operator pulls, which `merge-pr` has them do at every merge.
This is what "CI green on the tag" means mechanically: `test-suite.yml` runs on pull requests alone and the image workflow runs no tests, but branch protection admits a commit to `develop` only through a green `Full test suite`, so a revision on `develop`'s history passed the suite as the PR that merged it.
The assert shares D3's override: a hotfix image built off a branch is a bypass with its reason on the record, never a silent pass.
An empty label (an image built outside the workflow) is refused the same way.

### D5 — The row records the preflight, and two counts read it

The engine role appends a `preflight` object to the record file `site.yml` already writes for the window (`zcrypto_window_record`, :165-190): `{"digest": "<sha256:…>", "rc": <int>, "revision": "<label>", "on_develop": <bool>, "line": <the JSON line or null>}`; `converge.sh` copies it into the deploy-log row beside `window` (:280-302).
`infra/scripts/count-list.sh` gains two entries, both over rows since the last refine round closed whose `tags` reach `engine` and whose `extra_vars` carry `engine_image_digest`:
- `engine-repins-without-a-preflight`: rows whose `preflight.rc` is absent or not 0 and whose `extra_vars.engine_preflight_override` is null — a re-pin the gate did not pass and nothing bypassed, which can only be a row written outside the role's path.
- `engine-preflight-overrides`: rows whose `extra_vars.engine_preflight_override` is non-null.
Both are `jq` over the log in the shape of `c_canary_bypasses` (:334-338); `tests/test_count_list.py` pins each against a fixture row.

### D6 — The rule follows the mechanism

`.claude/rules/fleet-deploys.md:5` loses the engine: "Never re-pin the primary to a capture-image digest whose secondary bake gate has not passed — the capture role refuses it …", its set and count unchanged.
A new bullet follows it: "Never converge the engine onto a digest whose preflight has not passed on the engine host — the role runs the candidate image's own `zcrypto engine preflight` against a candidate render, read-only and offline, and refuses rc ≠ 0 and a revision label off `develop`; `-e '{"engine_preflight_override": "<reason>"}'` is the bypass — JSON, as every override — and takes the user's explicit approval, never silently (set: deploy-log rows tagged `engine` carrying `engine_image_digest` since the last refine round closed; count: `infra/scripts/count-list.sh engine-repins-without-a-preflight`; count: `infra/scripts/count-list.sh engine-preflight-overrides`)."
The ambient set grows by the new bullet's bytes less the deletion; the owner's ruling of 2026-10-05 and their word of 2026-10-07 ("handle the engine's own re-pin gate") are the word the refine-rules contract requires, and the commit carries its `Ambient grows by` line.

### D7 — The skill and the runbooks name the preflight where they named the bake

`.claude/skills/zcrypto-rollout-image/SKILL.md`: the description (:3) and Phase 3 (:57-71) keep the capture half as it is — the one-shot converge re-pins capture and engine together, and the capture digest still owes the secondary's bake; the engine half gains one checklist line, "the engine preflight's JSON line in the play output, `ok: true`"; Phase 4 (:75) says the engine's way back is a converge the preflight admits, and an image built before spec 00124 answers rc 2, so a rollback to one is the bypass with its reason; "## Engine converges" (:113) replaces "the engine role enforces that gate mechanically" with the preflight.
`docs/reference/fleet-pins.md:44` points at the new rule bullet beside the old.
`infra/runbooks/engine-procedures.md`'s "A dry run of an image before its converge" (:768-790) keeps the account read, which needs the key, and gains one sentence: the converge itself runs the image's preflight, so the dry run is owed only for the account read; the runbook-read floor `tests/test_ops_daily.py` holds is measured before and after.
`.claude/skills/zcrypto-bump-nautilus/SKILL.md:57` is not touched here: its Step 6 item 2 names the rollout skill, which carries the change.

### D8 — The gap and the proving cycle are the gate's other two legs, unchanged

The converge runs inside the inter-cycle gap `site.yml:77-190` asserts, and a converge that restarted the engine owes the next disarmed boundary cycle (`infra/runbooks/engine-procedures.md:28`, `:349`); neither is changed by this spec, and the rule's engine-gap bullet (`fleet-deploys.md:9`) stands.
The gate is therefore: the preflight passes on the engine host → the converge inside the gap → the proving cycle lands — the three legs the ruling names.

### D9 — The first image under the gate is the November bump's

The subcommand exists in an image only once this spec's merge is in the image's revision; the bump image is built from the merged tree, so it carries the preflight, and the rung-3 pair's rollout step reads the rule then in force (plan 00092 R2, on its own branch) — which is D6 once merged.
An engine rollback to any image built before this merge answers rc 2 and takes the bypass with its reason, until the fleet's history holds only preflight-capable images.

### D10 — Every guard is proven, and the tests replace the ten

`tests/test_engine_preflight.py`: each check's failure drives exit 1 and its field (a config file the loader refuses; a verified list lacking the running version, through a monkeypatched list path; a missing store file; an unparsable newest cycle record); the happy path exits 0 with the JSON shape; the state dir's listing and mtimes are unchanged after a run; the module imports no venue or cache client; each proven with `infra/scripts/mutate-probe.sh`.
`tests/test_infra_converge_guards.py`: on the Templar substrate, the preflight task's command carries `--network none`, both `:ro` mounts, `--entrypoint zcrypto`, no `--env-file` and no `-p`; the assert's two arms and its `when`; the candidate render's removal sits in an `always`; the provenance check's command and its `delegate_to: localhost`; the record append's keys; the four D5 tasks are gone by name and `engine_secondary_digest_probe` appears nowhere.
`tests/test_converge_sh.py`: a row carries `preflight` when the record file has it, and `engine_preflight_override` is admitted only in braced JSON.
`tests/test_count_list.py`: the two entries exist and read a fixture row each; `tests/test_guidance_refs_resolve.py` and the universal guard read the new rule bullet.

## What changes in the repo

- `cli/engine/preflight.py` (new), `cli/engine/command.py` (the subcommand).
- `infra/ansible/roles/engine/tasks/main.yml` (D1, D3, D4, D5), `infra/ansible/scripts/converge.sh` (the override in `OVERRIDES`, the `preflight` key), `infra/scripts/count-list.sh` (two entries).
- `.claude/rules/fleet-deploys.md`, `.claude/skills/zcrypto-rollout-image/SKILL.md`, `docs/reference/fleet-pins.md`, `infra/runbooks/engine-procedures.md`.
- `tests/test_engine_preflight.py` (new), `tests/test_infra_converge_guards.py`, `tests/test_converge_sh.py`, `tests/test_count_list.py`.

## Invariants

- The preflight container reaches nothing live: `--network none`, the state dir mounted read-only, no env file, no published port — held by the role test on the command's text.
- The preflight writes nothing — held by the listing-and-mtime test.
- An engine re-pin is refused unless the candidate image's own preflight passed on the engine host or a reason-bearing override is on the record — held by the assert's test and the count.
- The capture role's gate is unchanged in text and test.

## What stays manual

- The operator reads the preflight's JSON line in the play output and the row's `preflight` field after the converge; the rollout skill's checklist names both.
- The event-coverage read of the capture bake stays the capture rollout's human read (spec 00082 :63).
- The disarmed proving cycle's read (engine-procedures :28) is an operator act nothing in the tree records.

## The measured basis

Read 2026-10-07 at develop `8a4945a17`; the read-only pass's detail is the branch author's record, the facts below are the ones the decisions rest on.
- The engine gate is four tasks at `infra/ansible/roles/engine/tasks/main.yml:150-202`; nothing else in `site.yml` or a shared role compares the engine digest to the bake (`grep -rn canary infra/ansible/site.yml` prints nothing).
- `canary_override` is read at engine tasks :180-181, :196, :201-202 and capture tasks :129-130, :145, :150-151; `converge.sh:50` lists it in `OVERRIDES`; `count-list.sh:334-338` counts it; the only row ever carrying it is the engine rollback of 2026-09-16T13:39:05Z.
- `infra/scripts/count-list.sh canary-bypasses-on-the-primary` → `0`; `engine-rows-outside-the-gap` → `0`; `engine-window-overrides` → `0` (since round 17 closed 2026-09-28T11:54:00Z; `COUNT_LIST_ALL=1` reads 1, 1, 0).
- No file or field records a capture bake as passed: the mechanized gate reads the secondary's running `.Config.Image` live (capture tasks :112-138); the evidence of event coverage lives in the rollout PR's commit message (SKILL.md:81) and `fleet-pins.md:18`.
- `uv run zcrypto engine --help` lists 14 subcommands — seed, run, cycle, replay, report, soak-check, gate-export, decompose, accum-replay, tracking-report, exec-status, flatten, probe-plan, draft-plan — and none is a self-test: `run` writes `exec/restart-hold` unconditionally (`cli/engine/command.py:817-819`) and walks the store files (:822-834) before connecting; `cycle` writes the journal; `exec-status` reads Kraken's public status over the network (`cli/engine/venue.py:26-36`); `flatten` needs the trade key; `replay` and `report` read the journal and call `_load_engine_config()` (:1018).
- The exec gate's verified-version list is `cli/engine/order-semantics-verified.json`, read by `cli/engine/execgate.py:21-36`.
- The compose template `roles/engine/templates/compose.yaml.j2` mounts `{{ engine_state_dir }}` read-write and `/opt/zcrypto-engine/zcrypto.toml:/app/zcrypto.toml:ro` (:87-91), publishes `127.0.0.1:9102:9102` (:66-67), sets `ZCRYPTO_METRICS_PORT` in `environment` (the exporter starts only when it is set, `cli/obs/metrics.py:41-46`), reads `/opt/zcrypto-engine/engine.env` (names only: `KRAKEN_SPOT_API_KEY`, `KRAKEN_SPOT_API_SECRET`, `ZCRYPTO_CACHE_PASSWORD`, `HEALTHCHECK_URL`, `ZCRYPTO_REQUIRE_CONFIG`), and names no `networks:` key; the image's own ENTRYPOINT is the capture launcher (`infra/docker/Dockerfile:66`), so `--entrypoint zcrypto` is load-bearing (`engine-procedures.md:810`).
- A second container from the candidate on the engine host touches nothing live unless it runs `engine run` or `engine cycle` or mounts the state dir read-write; there is no instance lock in `cli/engine` (no `fcntl`/`flock`).
- `.github/workflows/test-suite.yml:3-8` runs on `pull_request` into `develop`/`main` only; `capture-image.yml:3-13` builds on push to `develop`/`main` and `v*` tags and labels the image `org.opencontainers.image.revision` (:78-80); it runs no tests.
- The window record is written by `site.yml:165-190` into `zcrypto_window_record`, a `mktemp` path `converge.sh` passes as its own extra var (:151, :160) and copies into the row (:280-302).
- The tests pinning the engine parity: `tests/test_infra_converge_guards.py:784-897`, ten functions; no other test names `engine_secondary_digest_probe` or `engine_running_parity_probe`.
- `docs/reference/change-index.md`'s highest iteration is `iter-173` (#648); the highest spec serial is 00123 on every branch; this branch is `feat/00124-engine-repin-gate` from `8a4945a17`.

## Not confirmed here, and the read that settles each

- That the replay reader's module imports pull in no venue or cache client when the preflight imports them: the pin imports `cli.engine.preflight` under `python -I -c` with no network and lists what it loaded; a venue import there moves the loader into the preflight module.
- That `docker run --memory 512m` is admitted on the engine host's cgroup v2 setup: settled at the first rollout's preflight, and the role's command drops the flag if the pin's `docker info` read on a workstation container shows the limit unsupported.
- Settled at authoring: the live render is the template task at `roles/engine/tasks/main.yml:608-614` with `notify: restart engine service`; a second template task to the candidate path carries no `notify`, so the handler never sees it.

## Out of scope

- The capture role's bake gate and its count.
- The inter-cycle gap's computation and the audit's 600-vs-900 discrepancy (`site.yml:114-135` against 00083 D6), a separate finding.
- The rung-2 entry record's item-5 amendment and the bump skill's Step 6 item 2, which are 00092's.
- A replay-based behavioural check of the candidate against the recorded journal (a mismatch is expected on a behaviour change; the disarmed proving cycle is that proof).

## Rulings on the open questions

The three questions put to the owner with the spec's recommendations were ruled on 2026-10-07 ("agree to all the three recommendations"):
1. The override is `engine_preflight_override`, with its own count set — not a reuse of `canary_override`, whose count reads the capture re-pin on the primary.
2. D4's provenance arm is in: the role refuses an image whose revision label is not an ancestor of the controller's `origin/develop`, the override covering a hotfix image built off a branch.
3. The preflight container keeps `--memory 512m`.
