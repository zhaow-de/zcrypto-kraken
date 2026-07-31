# 00077 — `verify-replay` alerts on NEW breakage, not on exit code

**Goal:** a known bad hour pages once and goes quiet; a *new* one pages; a broken *run* pages separately — replacing the single exit-code rule that conflates all three and would otherwise page forever.

## Why now

Spec `00076` D7 tried to solve "one historical bad hour exits 1 every day forever behind the CRITICAL alert" by windowing the sweep. That shipped 2026-07-30 and was reverted the same evening: `--since` cuts the chain-anchoring predecessor set, so 1,870 of 2,218 hours reported `anchored=False` on real data. Anchor-aware windowing was measured and rejected too — anchors are 17 days stale and the required lookback grows the healthier capture stays ([[T0114]]).

The original complaint was never about the sweep's *scope*. It was about what the alert *means*. This fixes that directly, and needs no CLI change and no image rebuild.

## Current state, measured

- One rule exists: **`Ops · verify-replay non-zero exit`**, `ops_verify_replay_exit_code > 0`, `for: 5m`, CRITICAL. There is no staleness rule; "did it run at all" is covered only by the healthchecks.io dead-man.
- The runner publishes `exit_code`, `last_run_timestamp`, `last_success_timestamp`, and **pings the dead-man only when `rc == 0`**.
- The CLI already emits the counts twice per run — `replayed N hour(s): X ok, Y failed` and, in logfmt, `verify-replay complete hours=N ok=X failed=Y`. Nothing consumes either.
- The archive is currently clean (a full unwindowed run passed 2026-07-30), so this change is **pre-emptive**: it fixes what happens the day a bad hour appears.

## Decisions

**D1 — Three failure modes, separated.** (i) *new bad hours* → page; (ii) *known bad hours persisting* → do not re-page; (iii) *the run itself broke* (crash, NAS `EIO`, no parseable output) → page. Today all three collapse into `exit_code > 0`, which is why (ii) pages forever.

**D2 — Publish three new series**, every run, unconditionally: `ops_verify_replay_failed_hours`, `ops_verify_replay_hours_total`, `ops_verify_replay_run_ok` (1 iff the summary parsed, i.e. the sweep completed). `exit_code`, `last_run_timestamp` and `last_success_timestamp` are unchanged. **Omitting a line deletes the series** — the shape that already paged this fleet once when `trade-backfill`'s `last_success` was dropped on failed runs against a `noDataState: Alerting` rule.

**D3 — `failed_hours` is CARRIED FORWARD on a broken run, never written as a sentinel.** A `-1` (or an omission) makes the next good run look like a jump from `-1` to `N` and fires the new-breakage rule falsely. Carrying the previous value forward is also the established local pattern — `last_success_timestamp` already does exactly this in both ops runners.

**D4 — The paging rules.** Retire `Ops · verify-replay non-zero exit`. Replace with:
- **`Ops · verify-replay NEW hours stopped replaying`** — `delta(ops_verify_replay_failed_hours[25h]) > 0`, CRITICAL. A known bad hour is a constant, so it contributes zero; a second one pages.
- **`Ops · verify-replay run broken`** — `ops_verify_replay_run_ok == 0`, `for: 15m`, CRITICAL. This is mode (iii), and it is the rule that keeps a crashed or `EIO`-ing sweep loud now that exit code alone no longer pages.

**D5 — The dead-man ping gates on `run_ok`, not on `rc`. This is the load-bearing fix.** Today the ping fires only when `rc == 0`. The moment any bad hour exists `rc` is 1 forever, the ping is withheld forever, and healthchecks.io pages forever — **the identical defect in a second channel, which windowing never addressed and which would have survived D7 even if D7 had worked.** Findings are a data fact; liveness is a run fact. A sweep that completed and reported bad hours *ran*, and must ping.

**D6 — No CLI change, no image rebuild.** The runner parses the logfmt line the CLI already emits (`hours=`, `failed=`), following `archive-pull.sh.j2`'s precedent verbatim, including its four hard-won rules:
- **Capture to a temp file and `cat` it back to the journal — never a pipe.** This script sets `set -u` but not `pipefail`, so `docker run | tee` would report tee's status and every failure would read as success.
- **`sed -n 's/.*failed=\([0-9][0-9]*\).*/\1/p' | tail -1`** — explicit digit class, last match (the CLI prints the summary twice).
- **`10#` on BOTH operands of any arithmetic.** A bare `$(( ))` reads `08` as octal; the expansion error leaves the variable UNSET and `set -u` then aborts the shell at the next `printf`, so the `mv` never runs, the `.prom` keeps stale content with `exit_code` still 0, and the ping is skipped. A wrong number would be better than that.
- Write every series on every path.

**D7 — The 25 h window is accepted with its delay named.** A run that over-runs and skips a tick leaves the series un-updated, so `delta` reads 0 — no false page, but a new bad hour waits a day. Accepted: detection is delayed, never lost, and the dead-man independently covers "not running at all". Not widened, because a wider window would also widen the period over which a *triaged* hour keeps re-paging.

**D8 — No standing low-severity "known bad hours exist" alert.** `failed_hours` is a dashboard quantity. Adding a second rule for it would grow the alert surface for a fact no one must act on within minutes.

## Non-goals

- Windowing or scoping the sweep in any form — refuted, and its runtime motive is [[T0114]].
- Any change to `cli/archive/replay.py` or the replay semantics.
- A staleness rule for `last_run_timestamp` — the dead-man already owns "did it run", and D5 is what repairs that channel.

## Verification

- **Render-harness test** (`tests/test_infra_verify_replay_template.py`, recreated with new content): the rendered script is `bash -n` valid; every series is emitted on **both** the success and the failure path; `failed_hours` carries forward when the run breaks; `run_ok` is 0 exactly when the summary does not parse; and the ping condition references `run_ok`, not `rc`. Crucially, the parse assertion runs **the template's real `sed` over a line in the CLI's actual `logger.info` format**, so wording drift on either side fails the test — the same construction that pins `archive-pull`'s repair count.
- **Constructed-defect proof**, per `.claude/rules/agent-ops.md`: feed the parser a truncated/absent summary and confirm `run_ok=0` with `failed_hours` unchanged; feed it a summary with a larger count and confirm the delta rule's operand moves. Reading the assertions is not verification.
- **Deploy verification by outcome**: after the ops converge, the next daily tick publishes all three new series with `run_ok=1`; after the attended `grafana-push.sh`, both rules read back from the API.

## Risks

- **The alert surface changes on a live fleet.** Between the converge and the rules push, `exit_code` is still the only rule — so the sequence matters: converge first (new series start flowing, nothing breaks), push rules second.
- **`delta()` on a gauge that resets.** If the archive is ever rebuilt and `failed_hours` drops, `delta` goes negative and does not fire — correct, and the same `resets()`-class reasoning the reconciler rules already carry.
- The parse depends on a log line's wording; the render harness is what makes that a test failure rather than a silent zero.
