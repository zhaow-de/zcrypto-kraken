# 00105 — the go-live drill program: implementation plan

Spec: `docs/specs/00105-go-live-drill-program-design.md`. Branch `feat/t0049-drill-program`, cut from `develop` after PR #352 ([[T0157]] / spec `00104`) merged — `infra/runbooks/observability.md`, `engine.md` and the PROCEDURE kind all exist there now, so no task here creates them.

## Goal

Every go-live drill scenario has an induction instrument, a derived bound and a recording shape before anyone needs one at 03:00; the telemetry tier is **executed**, not just written; and the two gaps no rehearsal can close — the dark-with-exposure alert and the Grafana-dark procedure — are built.

## Global constraints

- **A drill that induces a fault runs in the main loop, never in a subagent or workflow** — the permission gate blocks ssh/sudo there and the step dies where nobody sees the prompt (`agent-ops.md`).
- **Never induce a fault on live capture outside an attended window, and never inside a published Kraken maintenance window** — read `https://status.kraken.com/api/v2/scheduled-maintenances.json` at planning time and again immediately before each induction (`fleet-deploys.md`). The **primary's capture daemon and its Alloy are not touched by any task here.**
- **Every induction is reverted and verified BY VALUE before the next one starts.** A drill that leaves the fleet degraded is a incident, not a drill.
- **Bounds are derived, never guessed**: a Grafana rule's `for` plus its group's evaluation interval; a healthchecks check's timeout plus grace, quoted from the check itself.
- **A drill result lives in `docs/reference/drill-log.md` and in its runbook section.** A result that lives only in a report or a PR body is not recorded (`open-topics.md`).
- Every commit reviewed by a subagent other than its author; **Fable floor for anything touching the capture path or the live trade path** (`spec-plan-locations.md`).

## Tasks

### Task 1 — the drill log and its guard, red first

Write `tests/test_drill_log.py` asserting only what D2 specifies: every `##` heading matches `<YYYY-MM-DD> — <scenario id> — <pass | fail | partial>`, and dates within the file do not decrease. Create `docs/reference/drill-log.md` with its header and no entries.

**Verify**: the test is seen RED against a deliberately malformed heading before the file is made valid — a guard is unproven until the defect it names trips it. Then green on the empty log.

### Task 2 — `infra/runbooks/drills-telemetry.md`

Sections C, C′, I, J′, K, O, P+R, Q in the seven-part PROCEDURE shape (D1), plus one section stating when the **proven** tier (F, H, J, L, M, N, T) is re-verified — only when the code path it proved changes, citing the incident or drill that proved it — and recording that **N is due now** ([[T0048]] changed the Alloy path after the 2026-07-15/16 incident that proved it). That section also carries the two dropped items with their reasons: the reboot-window overlap check (both capture hosts are attended-reboot since [[T0027]]) and drills for [[T0039]]'s phantom-splice guard and [[T0043]]'s lost-trades detector (code guards with tests, not fleet failure scenarios).

**Verify**: every bound in the file is derived from a quoted `for` + interval or timeout + grace, with the source named; no section exceeds the README's shape; `uv run pytest tests/test_infra_alert_rules.py`.

### Task 3 — `infra/runbooks/drills-order-path.md`

Sections A1, A2, B, D, E (with E′), F2, G, in the same seven parts, fitted around `engine-procedures.md#engine-probe-window`. Each names the four enhancements it waits on where relevant, and G carries the [[T0018]] by-value reading (`zcrypto_exec_external_events_total{disposition="matched"}` expected 1, 2 under a fill race, 0 meaning no `cl_ord_id` echo) with A2's `matched`-reads-0 caveat stated where it belongs.

**Verify**: a cold reviewer dry-reads every command against the probe procedure — every command resolves, every expected ledger value names its field (spec Verification).

### Task 4 — index both files

Add both to `infra/runbooks/README.md` under their own headings.

**Verify**: `uv run pytest tests/test_infra_alert_rules.py` (index routing is asserted there).

### Task 5 — `zcrypto-engine-dark-with-exposure`

Add the critical rule to `infra/grafana/alerts.yaml`: `zcrypto_exec_position` non-zero at last sight AND the engine's scrape absent, pinned against `up{job="engine_app",host="zcrypto"}` — the job is scraped on both capture hosts and reads 0 on `zcrypto-red` by design, so the host label is load-bearing. Runbook section in `engine.md`, response is B.

**Verify**: `uv run pytest tests/test_infra_alert_rules.py tests/test_internal_terms_not_operator_visible.py` — the rule must carry a resolving runbook link and its summary must hold no internal token. The push and the first-sample-by-value read are Task 11.

### Task 6 — `observability.md#grafana-cloud-dark`

The PROCEDURE section: for the duration, the dead-man domain plus the daily pass's direct healthchecks read, `docker logs` on hosts, `exec-status` on the engine host. On return: the rules blind to a condition already present at first sample, re-verified by value. Its permanent-loss-per-plane statement and page bound are filled from drills C and C′ (Task 10), so this task lands the section with those two values explicitly marked as pending that run — and Task 10 fills them.

**Verify**: `uv run pytest tests/test_infra_alert_rules.py`.

### Task 7 — README rows and the master-plan artifact line

Add the two runbooks and the drill log to `README.md` where the runbook tree is described; add `docs/reference/drill-log.md` to the master plan's Stage-6b artifact list.

**Verify**: `uv run pytest tests/test_internal_terms_not_operator_visible.py` (README is operator-visible).

### Task 8 — mutation probe on the drill-log guard

`infra/scripts/mutate-probe.sh`, `--collect-only` first to prove the `-k` filter reaches the test under proof.

**Verify**: KILLED with the control proven and the tree restored byte-identically.

### Task 9 — execute J′ (workstation-only, no host access)

Read `engine_healthcheck_url` through `grafana_auth.vault_var` from `group_vars/engine_host/vault.yml`; `curl <url>/fail` **from the workstation** — never from the engine host, whose only copies sit beside the trade key; engine disarmed. Read the native page and `zcrypto-hcio-watchdog` by value; write the drill-log entry; then a success ping to clear it.

**Verify**: the entry records the three timestamps; the check is green again, read by value.

### Task 10 — execute the ops-node telemetry drills

In the main loop, one at a time, each reverted and verified by value before the next: **K** (`docker stop grafana-alloy` on ops) → **O** (one ops timer past its check's timeout + grace) → **I** (throwaway container + throwaway check, the check created with `channels` naming the Slack integration explicitly — an API-created check inherits NO integrations, the [[T0085]] finding, and an unchannelled one breaches in silence) → **C-ops** and **C-secondary** (2 h each) → **C′-staleness** → **N** → **R** (secondary only, primary read by value first, hard cap = `capture-redundant`'s timeout + grace + one evaluation) → **Q-machine** (per path: rule `activeAt`, Slack message timestamp).

**Verify**: each drill gets its `drill-log.md` entry and its section amendment **before the next starts**; the Kraken maintenance feed is read immediately before each induction; every revert verified by value.

### Task 11 — Grafana push, from MERGED `develop` only

After the PR merges: push `zcrypto-engine-dark-with-exposure`, orphan report clean, first sample read **by value** before anything is pruned (`fleet-deploys.md`).

### Task 12 — closeout

Append the `iter-<N>` entry to `docs/iterations-history-phase6.md`; run `infra/scripts/review-trailer-audit.sh develop` and resolve what it reports; **bring [[T0158]] current in this same PR** — `ripe_when` re-cut to the order-path tier at rung 1, the executed drills' results in `## Done so far`, `## Suggested next steps` trimmed to P, C′'s `/fail` route and Q's phone reading with their `(autonomous)`/`(human)` tags; open the PR into `develop` and merge on CI green.

## What this plan does not do

The order-path tier is written and parked, never run — rung 1 has not opened and the engine has never been armed. The four enhancements it needs (`00106` flatten, `rest-hold`, cancel-on-stop, re-cancel-on-reconnect) are each their own spec and PR at the Fable floor, and none is built here. **P** (its restore is a secondary converge) and **C′'s `/fail` route** (a converge) stay attended and are not in Task 10.
