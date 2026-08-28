# Spec 00083 — T0111 wave 2: converge scripts, the engine parity mirror, and the wave-1 gap closures

**Goal:** finish mechanizing `fleet-deploys.md`'s converge discipline — the five wave-2 scripts, the three guard gaps wave 1 left registered (the engine parity mirror, from its final whole-branch review; the window-floor journal probe and the skip-tags tightening, from its execution), and the three tooling-polish items that same review raised — so the remaining rule prose shrinks to pointers and T0111's only open remainder is the attended ops-host drills.

Owner rulings (2026-08-03, attended): scope = all eleven registered items; `converge.sh` uses an interactive type-the-limit-back confirm; `converge.sh` becomes the documented converge path with the rule shrink at closeout (per-edit sign-offs, protected set). Override convention throughout: wave 1's D1 — `-e <name>_override="<reason>"`, refused when empty/boolean-like/<9 chars, accepted reason echoed.

**Scope correction, measured before design:** the registered item "`continuity.py` genesis annotation" is **already implemented and shipped** — `stream_timeline()` takes `genesis_hour` and skips the genesis head measurement (its D5 comments), rows print a ` genesis` mark via `genesis_skipped`, `tests/test_continuity_overlay.py` exercises the `genesis=` parameter, and `fleet-deploys.md` already states "a new stream's genesis hour is annotated and not booked". Wave 2 does **not** re-implement it; closeout records it in T0111 as landed via the spec-00079-era continuity work. Ten items build; one books.

## D1 — `infra/ansible/scripts/converge.sh`: the documented converge path

A wrapper over `run.sh` (which loads the vaulted deploy keys and execs `ansible-playbook`). Contract:

- Invocation: `converge.sh <playbook.yml> --limit <target> [more ansible args…]`. Both `--limit X` and `--limit=X` forms are parsed; the extracted value is the confirm token.
- **rc 2 (usage)**: no playbook argument, or no `--limit` anywhere in the args. The refusal names the fix: "converge.sh requires --limit — a bare site.yml still runs every play; use --limit <host>".
- **Preview first, always**: runs `run.sh <playbook> --check --diff <args…>` with output to the terminal. Preview exit ≠ 0 → **rc 4**, "preview failed — fix the check pass before converging". If the caller's own args already contain `--check`, the script stops after the preview with rc 0 — a preview-only invocation has nothing to gate.
- **Interactive confirm**: prints `Type the --limit value (<target>) to converge, anything else aborts:` and reads one line from `/dev/tty` — never stdin, so `yes |` and heredocs cannot drive it. No `/dev/tty` (non-interactive) → **rc 3**: unattended contexts do not converge through this path (the auto-exec boundary parks converges anyway). Input must equal the limit value byte-exactly; anything else → **rc 3**, nothing executed.
- On confirm: `exec run.sh <playbook> <args…>` (the real pass; exec so the exit code is ansible's own).
- The script never parses or handles vault material; it composes `run.sh` only.

## D2 — `zcrypto-panel-regenerate` (ops role installs to `/usr/local/sbin`, template `panel-regenerate.sh.j2`)

The delete-and-rebuild flow as one refusing script, replacing the panel-generation checklist prose. Steps, in order, each refusing forward on failure:

1. **Stop the timer** (`systemctl stop zcrypto-panel-materialize.timer`) and say so — plus the reminder that a converge re-arms it unless `-e ops_panel_timer_hold=true` is passed.
2. **Size the window**: `du -sm` over the canonical input (`{{ ops_nas_mount }}/{{ ops_capture_subdir }}`) plus the local overlay (`{{ ops_data_dir }}/{{ ops_reconciled_subdir }}`); ETA = MB × 2.1 s × 1.2 margin. If now+ETA crosses the next 02:25 UTC auto-reboot → refuse, naming the ETA, the deadline, and the override (`--override "<reason>"`, wave-1 D1 semantics validated in-script: ≥9 chars, not boolean-like).
3. **hc.io gate**: print the pause checklist (the panel check pings only on rc 0 and is the timer's only liveness signal; pause it time-boxed) and require the operator to type `paused` on `/dev/tty`. Anything else aborts with nothing deleted.
4. **Delete the ops copy**: `rm -rf` of `{{ ops_data_dir }}/{{ ops_panel_subdir }}` — the whole panel root, so out-of-scope subtrees die with it (the `_check_generation` tree-scan refusal otherwise blocks the next materialize).
5. **Rebuild inside the unit**: `systemctl start --wait zcrypto-panel-materialize.service`. Running AS the unit means a stray timer tick collides with an active unit (no-op) instead of double-writing; the deleted tree took the per-pair watermarks with it, so the run rebuilds everything. `Type=oneshot` has no start timeout — only the (refused-against) reboot kills it. Non-zero unit result → the script reports it and does NOT proceed to step 6's resume line (the tree is now the anomaly to investigate).
6. **Print the closing checklist**: the NAS-side deletion (ops cannot reach the NAS shell; the `rsync -a` pull has no `--delete`, so the old NAS copy survives until deleted there — name the panel subdir on the share), the hc.io un-pause, and `systemctl start zcrypto-panel-materialize.timer` to resume the hourly cadence (the script restarts the timer itself only after a clean step 5; on failure the timer stays stopped and the checklist says so).

**The point of no return stays human**: the script's step-3/4 boundary is where the owner's word is taken (typed `paused` after reading the checklist that names the irreversibility) — the not-mechanizable consent from T0111's classification is the typed gate, not removed by it.

## D3 — `infra/scripts/ops-postverify.sh`: verify-by-outcome as one command

Wraps `uv run python infra/scripts/grafana-query.py` (workstation-side, vault handled there). Six checks (the counter pair split, one per series), each printed `PASS`/`FAIL <detail>`; any FAIL → exit 1; `(no series)` is a FAIL for that check, never a zero (agent-ops' empty-query rule, mechanized):

1. `ops_archive_pull_exit_code == 0`
2. `ops_panel_exit_code == 0`
3. reconcile freshness: `time() - node_textfile_mtime_seconds{file=~".*reconcile.prom"}` under 4200 s (one cycle + margin)
4. reconcile counters unbumped: `increase()` over 2 h of `zcrypto_reconcile_residual_gap_seconds_total` and `zcrypto_reconcile_healable_gap_seconds_total` both 0 (the exporter's real names, verified: `residual_gap`/`healable_gap`/`spliced_hours`/`union_hours` — there is no `permanent_loss` series; the test pins the two names against the exporter template)
5. `hc_checks_down_total == 0`

Timeout-guarded per query; a query error is FAIL, not skip. The rule's verify-by-outcome bullet shrinks to a pointer at this script (+ the next-tick timing sentence, which stays — timing is judgment).

## D4 — `vault-pass.sh` ancestor check

Before `exec`ing sops, walk `/proc` ancestry (PPID chain from `$$` to 1, reading each `/proc/<pid>/cmdline`): if any ancestor's cmdline contains `ansible-inventory` together with `--host` or `--list`, refuse rc 1 with one stderr line naming the safe alternatives (`--graph`, `--list-tags`, or a key-names-only filter). Everything else is unchanged — the two-line script keeps its exec shape on the allow path. The CLAUDE.md/rules "never run ansible-inventory --host/--list" line keeps its imperative but gains the pointer that the vault password script itself now refuses.

## D5 — Engine canary-parity mirror (engine role)

Wave 1's capture-role parity assert, mirrored: engages when `engine_image_digest` is defined AND differs from the running engine container's `{{.Config.Image}}` digest; delegates to the secondary (`groups['capture_host'] | difference(groups['engine_host'])`) a probe of its running **capture** digest (`ignore_unreachable: true`); asserts the new engine digest is what the secondary runs as capture — there is no engine secondary, the red capture bake IS the engine's gate (`fleet-pins.md`'s own words). Same `canary_override` variable and D1 semantics; same fail-closed shape as the capture pair (probe `is not skipped` gate + `stdout | default('')`); override echo task mirrors byte-for-byte modulo prefix. Placement: beside the engine role's digest preflight, before anything renders. The wave-1 qualifiers ("no assert enforces engine parity yet") come OUT of `fleet-deploys.md` at closeout — sign-off edits.

## D6 — Window-floor journal probe (site.yml engine pre_tasks)

The fixed B+30 floor is conservative when the boundary's cycle already finished. Extension, same task block as guard 5: slurp the engine journal's current boundary artifact (`{{ engine_state_dir }}/journal/<UTC day>/cycle-<HH>.json` for the boundary hour — `engine_state_dir` is the role's existing `/var/lib/zcrypto-engine` default; `failed_when: false`), and when it exists with a parseable `completed_at`, the floor becomes `completed_at + 300 s` instead of B+1800; absent, unparseable, or in-check-mode keeps B+1800. The ceiling (next−600) and override are unchanged. The guard's `that:` keeps a single expression evaluating both branches (Templar-testable like wave 1); parse failures must land on the CONSERVATIVE branch, constructed in tests.

## D7 — Guard-4 skip-tags tightening (site.yml)

Current pass condition `ansible_run_tags != ['all'] or ansible_skip_tags | length > 0` accepts any non-empty `--skip-tags`. Tightened: a run on the primary passes iff `ansible_run_tags != ['all']` (explicit `--tags`) **or** `'engine' in ansible_skip_tags` — the only skip-tags form the rule ever licensed. `--skip-tags something-else` on a bare run now refuses. fail_msg names the three accepted forms.

## D8 — `mutate-probe.sh` exit-code hermeticity

Three defects, one change-set: (a) sandbox seeding (`git archive | tar`) failure gets its own **rc 8** (checked explicitly, no longer surfacing the pipeline's own status colliding with usage rc 2); (b) a failing `cp` inside `restore`/`cleanup` reports **rc 9** after still attempting the remaining cleanup, and the trap path preserves the restore-before-clean order (wave-1's signal guarantee untouched — its tests re-run and must stay green); (c) the no-op-abort message names which sed failed to match: `control sed` vs `mutation sed`. Header contract updated (2/3/4/5/6/7/8/9); every new code constructed in tests.

## D9 — Liquidations pin-probe rc split (ops role)

`grep` rc 2 currently lumps "file absent" (legitimate first-provision stand-down) with "file present but unreadable" (a permission fault that must fail closed). A `stat`-based probe (`test -e` / `test -r`, `failed_when: false`) runs before the grep; the decision guard's `when:` becomes: skip only when the file **does not exist**; existing-but-unreadable refuses with its own fail_msg naming the permission fault. Both states constructed in the Templar tests.

## D10 — `git-mv-guard.sh` coverage

The hook currently judges the porcelain of its own process cwd and matches only literal `git mv`. Extended: (a) also match `git -C <dir> mv`, resolving the porcelain read against `<dir>`; (b) a leading `cd <dir> &&` prefix resolves against `<dir>`; (c) when the command matches a mv-ish git form but the repo cannot be resolved (quoting, variables), emit a one-line **note** (not the full warning) saying the guard could not check — visible, never wrong-repo. Plain `mv` + `git add` stays out of scope (registered residual in T0111 — matching bare `mv` would fire on every shell move). Warn channel unchanged (stderr + exit 2).

## D11 — Test substrate

- **Bash scripts** (D1, D2, D3, D4, D8): pytest subprocess tests with stubbed externals prepended on `PATH` — a fake `run.sh`/`ansible-playbook` recording argv, fake `systemctl`, fake `du`/tree fixtures, fake `grafana-query.py` emitting canned/`(no series)` outputs, a crafted parent-process chain for D4 (the test launches `vault-pass.sh` under an intermediate `bash -c` wrapper exec'd with argv0/args mimicking `ansible-inventory --list`, proving the ancestry walk sees it; sops itself is stubbed). `/dev/tty` interactions run under a pty (`pty` module) for the confirm paths; the no-tty refusal is tested by closing the controlling terminal. Every refusal rc constructed and read; every happy path proves the wrapped command actually ran (argv recorded), not just rc 0.
- **Guards** (D5, D6, D7, D9): wave 1's Templar substrate in `tests/test_infra_converge_guards.py` — real `that:`/`when:` from committed YAML, `trust_as_template`, violation + pass fixtures per branch, including D6's parse-failure→conservative-floor construction and D9's unreadable-file construction.
- **New files**: `tests/test_converge_sh.py`, `tests/test_panel_regenerate.py`, `tests/test_ops_postverify.py`, `tests/test_vault_pass_guard.py`; extensions to `tests/test_infra_converge_guards.py`, `tests/test_mutate_probe.py`, `tests/test_git_mv_guard.py`. Scratch repos set their own git identity (the wave-1 CI lesson).
- `panel-regenerate.sh.j2` is a template — tests render it with representative vars (Jinja via ansible's Templar or plain substitution fixtures) and run the rendered script against stubs.
- Operator-facing surfaces (all five scripts' output, fail_msgs) carry no internal serials — `test_internal_terms_not_operator_visible.py` extends to the new scripts.

## D12 — Rule shrink & closeout protocol

Same as wave 1's D7: each landed mechanism's `fleet-deploys.md` line becomes a pointer, presented as per-edit owner sign-offs at closeout — the `--limit`/preview lines (D1), the panel-generation section's mechanized steps (D2 — the judgment sentences stay), the verify-by-outcome bullet (D3), the ansible-inventory line gains its pointer (D4), the engine-parity "prose is the gate" qualifiers come out (D5), plus `agent-ops.md`'s grafana-query bullet gaining the ops-postverify pointer if the owner agrees. T0111 flips its wave-2 items to Done-so-far (genesis item recorded as already-landed); status stays `partial` with the attended drills as the sole remainder, `ripe_when` a maintenance window. Iterations-history entry (phase 6), decisions-log entries for the three rulings above. **Drills are out of scope for this branch** — registered, attended.

## Out of scope

- The ops-host drills for D1/D2 (attended, maintenance window — T0111's remainder).
- Bare `mv`+`git add` detection (D10's registered residual).
- Any capture-role or alert-rule change; no host converges ride this branch.
