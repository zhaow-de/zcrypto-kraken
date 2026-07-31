# 00077 — `verify-replay` alerts on NEW breakage, not on exit code

**Goal:** a known bad hour pages once and goes quiet; a *new* one pages; a broken *run* pages separately — across **all three** channels that can page on it (the metric rule, the healthchecks.io dead-man, and the ops ERROR-logs rule), not just the one that is obvious.

## Why now

Spec `00076` D7 tried to solve "one historical bad hour exits 1 every day forever behind the CRITICAL alert" by windowing the sweep. That shipped 2026-07-30 and was reverted the same evening: `--since` cuts the chain-anchoring predecessor set, so 1,870 of 2,218 hours reported `anchored=False` on real data. Anchor-aware windowing was measured and rejected too — anchors are 17 days stale and the required lookback grows the healthier capture stays ([[T0114]]).

The original complaint was never about the sweep's *scope*. It was about what the alert *means*. This fixes that directly.

**And it fixes it in all three channels.** A cold review of this spec's first draft found a third one the draft had not audited: the CLI logs every failed hour at ERROR, those lines reach Loki, and `Ops · ERROR logs` fires on them nightly, forever. That is the same failure shape as the 00076 revert — an adjacent, already-shipping fact the design did not read — caught this time before shipping rather than after.

## Current state, measured

- One rule exists: **`Ops · verify-replay non-zero exit`**, `ops_verify_replay_exit_code > 0`, `for: 5m`, CRITICAL. There is no staleness rule; "did it run at all" is covered only by the healthchecks.io dead-man.
- The runner publishes `exit_code`, `last_run_timestamp`, `last_success_timestamp`, and **pings the dead-man only when `rc == 0`**.
- The CLI already emits the counts twice per run — `replayed N hour(s): X ok, Y failed` and, in logfmt, `verify-replay complete hours=N ok=X failed=Y`. Nothing consumes either.
- **A third channel exists and was missed by the first draft**: `cli/archive/command.py` logs each failed hour at ERROR (`archive verify-replay: hour failed pair=…`); the runner's output reaches Loki through the unit journal, and `Ops · ERROR logs` (`level=~"ERROR|CRITICAL"`, `for: 0s`, warning) fires on it. So retiring the exit-code rule alone would leave a known bad hour paging nightly through the catch-all.
- The archive is currently clean (a full unwindowed run passed 2026-07-30), so this change is **pre-emptive**: it fixes what happens the day a bad hour appears.

## Decisions

**D1 — Three failure modes, separated.** (i) *new bad hours* → page; (ii) *known bad hours persisting* → do not re-page; (iii) *the run itself broke* (crash, NAS `EIO`, no parseable output) → page. Today all three collapse into `exit_code > 0`, which is why (ii) pages forever.

**D2 — Publish three new series**, every run, unconditionally: `ops_verify_replay_failed_hours`, `ops_verify_replay_hours_total`, `ops_verify_replay_run_ok` (1 iff the summary parsed). **Note the deliberate edge**: the CLI returns rc 0 with *no* summary when it finds no canonical hours at all — an unmounted NAS bind reads as *healthy* today. Under this design that path yields `run_ok=0` and pages, which closes a real blind spot. Nobody should later "fix" `run_ok=1` for it. `exit_code`, `last_run_timestamp` and `last_success_timestamp` are unchanged. **Omitting a line deletes the series** — the shape that already paged this fleet once when `trade-backfill`'s `last_success` was dropped on failed runs against a `noDataState: Alerting` rule.

**D3 — `failed_hours` is CARRIED FORWARD on a broken run, never written as a sentinel.** A `-1` (or an omission) makes the next good run look like a jump from `-1` to `N` and fires the new-breakage rule falsely. Carrying the previous value forward is also the established local pattern — `last_success_timestamp` already does exactly this in both ops runners.

**D4 — The paging rules.** Retire `Ops · verify-replay non-zero exit` (uid `zcrypto-ops-verify-replay-exit-nonzero`) — **and note that deleting it from `alerts.yaml` does NOT retire it.** `infra/scripts/grafana-push.sh` upserts and never deletes; its own comment states the consequence: *"a rule removed from alerts.yaml keeps evaluating and emailing forever."* Pruning is dry-run by default and needs `GRAFANA_PRUNE=1`. Without that step this iteration ships with the very rule it exists to retire still paging on an `exit_code` D2 keeps publishing — **the third instance in this thread of an adjacent, already-shipping fact defeating the design**, after the `--since` docstring and the ERROR-logs channel. Replace with:
- **`Ops · verify-replay NEW hours stopped replaying`** — `delta(ops_verify_replay_failed_hours[25h]) > 0`, CRITICAL. A known bad hour is a constant, so it contributes zero; a second one pages. **Named limitation**: a repair and a new breakage inside the same window net to zero and stay silent — inherent to a count signal, so triage guidance is that the day after healing hours, silence is not evidence.
- **`Ops · verify-replay run broken`** — `ops_verify_replay_run_ok == 0`, `for: 15m`, CRITICAL. This is mode (iii), and it is the rule that keeps a crashed or `EIO`-ing sweep loud now that exit code alone no longer pages.

**D5 — The dead-man ping gates on `run_ok`, not on `rc`. This is the load-bearing fix.** Today the ping fires only when `rc == 0`. The moment any bad hour exists `rc` is 1 forever, the ping is withheld forever, and healthchecks.io pages forever — **the identical defect in a second channel, which windowing never addressed and which would have survived D7 even if D7 had worked.** Findings are a data fact; liveness is a run fact. A sweep that completed and reported bad hours *ran*, and must ping.

**D6 — The parse needs no CLI change; the runner reads the logfmt line the CLI already emits** (`hours=`, `failed=`), following `archive-pull.sh.j2`'s precedent verbatim, including its four hard-won rules (D9 does require a CLI change, for a different reason):
- **Capture to a temp file and `cat` it back to the journal — never a pipe.** This script sets `set -u` but not `pipefail`, so `docker run | tee` would report tee's status and every failure would read as success.
- **`sed -n 's/.*failed=\([0-9][0-9]*\).*/\1/p' | tail -1`** — explicit digit class, last match (the CLI prints the summary twice).
- **`10#` on BOTH operands of any arithmetic.** A bare `$(( ))` reads `08` as octal; the expansion error leaves the variable UNSET and `set -u` then aborts the shell at the next `printf`, so the `mv` never runs, the `.prom` keeps stale content with `exit_code` still 0, and the ping is skipped. A wrong number would be better than that.
- Write every series on every path.
- **The carry-forward is an assignment, never arithmetic** — deliberately, so the octal trap above cannot arise here at all. No `$(( ))` is introduced by this change.

**D7 — The 25 h window is accepted with its delay named.** A run that over-runs and skips a tick leaves the series un-updated, so `delta` reads 0 — no false page, but a new bad hour waits a day. Accepted: detection is delayed rather than lost for a skipped *run* (the textfile persists the previous value, so both sides of the change stay in a later window). The one case where it IS lost is the ops series going dark for >25 h across the change — an Alloy or host outage, which the Alloy-dark rules and the dead-man own. Not widened, because a wider window would also widen the period over which a *triaged* hour keeps re-paging.

**D8 — No standing low-severity "known bad hours exist" alert.** `failed_hours` is a dashboard quantity. Adding a second rule for it would grow the alert surface for a fact no one must act on within minutes.

**D9 — A failed hour logs at WARNING, not ERROR; ERROR is reserved for the sweep itself failing.** This is the third channel's fix, made at the source rather than by filtering the alert. The reasoning is semantic, not expedient: a failed hour is a **finding about data**, and the sweep reporting it is the program working correctly. `Ops · ERROR logs` means "something on this host errored", and a data finding is not that. The alternatives were both worse — filtering this specific message out of the catch-all adds an exception list to the one rule whose value is catching what nobody predicted, and accepting the nightly warning trains an operator to ignore an alert that covers everything else on the node.

The cost is real and is accepted: this makes the change an **image rebuild plus an ops re-pin** rather than a template-only edit. No canary bake is owed (ops is the compute tier), but the deploy tail grows and the sequence in D10 becomes load-bearing.

**D10 — Deploy order, and the liquidations decision the digest change forces.** Converge before pushing rules (the new series must be flowing before a rule reads them; until then `exit_code` is still the only rule and nothing is worse than today). And because this converge **moves `ops_image_digest`** — unlike the previous one, where the digest was unchanged and the question was moot — `capture-deploys.md`'s standing hazard is live: the same variable re-pins the liquidations compose, which the role never restarts, so the file moves while the container does not. The converge must end with an explicit decision to roll the liquidations container or to leave it deliberately pinned-but-not-rolled, recorded either way.

## Non-goals

- Windowing or scoping the sweep in any form — refuted, and its runtime motive is [[T0114]].
- Any change to `cli/archive/replay.py` or the replay **semantics** — D9 changes one log level in `cli/archive/command.py` and nothing else; what counts as a failed hour is untouched.
- A staleness rule for `last_run_timestamp` — the dead-man already owns "did it run", and D5 is what repairs that channel.

## Verification

- **Render-harness test** (`tests/test_infra_verify_replay_template.py`, recreated with new content): the rendered script is `bash -n` valid; every series is emitted on **both** the success and the failure path; `failed_hours` carries forward when the run breaks; `run_ok` is 0 exactly when the summary does not parse; and the ping condition references `run_ok`, not `rc`. Crucially, the parse assertion runs **the template's real `sed` over a line in the CLI's actual `logger.info` format**, so wording drift on either side fails the test — the same construction that pins `archive-pull`'s repair count.
- **A test pinning the per-hour log level to WARNING** (D9), with a comment naming the ERROR-logs channel it protects — so a later "tidy-up" that restores `logger.error` fails rather than silently re-arming a nightly page.
- **Constructed-defect proof**, per `.claude/rules/agent-ops.md`: feed the parser a truncated/absent summary and confirm `run_ok=0` with `failed_hours` unchanged; feed it a summary with a larger count and confirm the delta rule's operand moves. Reading the assertions is not verification.
- **Deploy verification by outcome**: after the ops converge, the next daily tick publishes all three new series with `run_ok=1`; after the attended `grafana-push.sh`, both new rules read back from the API. The prune that retires the old uid runs **only after that first tick is verified** — including reading `failed_hours`'s *value*, not merely its presence — and then `zcrypto-ops-verify-replay-exit-nonzero` must return 404: a push alone leaves it live, so "the new rules exist" is not evidence the old one is gone.
- **Because `ops_image_digest` moves, the converge re-runs every ops runner on a new image**, so `capture-deploys.md`'s standard ops outcome checks are load-bearing here rather than routine: `ops_archive_pull_exit_code` / `ops_panel_exit_code` 0, `reconcile.prom` mtime advanced, reconcile counters unchanged, `hc_checks_down_total` 0.

## Risks

- **This is now an image change**, so the deploy tail is build → pull the digest on the host → record it in `fleet-pins.md` (the only rollback operand; `ops_image_digest` has no repo default) → converge → push rules. Longer, and each step is attended.
- **The alert surface changes on a live fleet.** Between the converge and the rules push, `exit_code` is still the only rule — so the sequence matters: converge first (new series start flowing, nothing breaks), push rules second.
- **`delta()` on a gauge that resets.** If the archive is ever rebuilt and `failed_hours` drops, `delta` goes negative and does not fire — correct, and the same `resets()`-class reasoning the reconciler rules already carry.
- The parse depends on a log line's wording; the render harness is what makes that a test failure rather than a silent zero.
