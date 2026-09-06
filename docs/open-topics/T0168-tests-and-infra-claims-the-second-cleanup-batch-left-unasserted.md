---
status: open
---

# Tests and infra claims the second cleanup batch left unasserted

## Context — what

The `tests/` + `infra/` prose-cleanup batches (T0164) condensed comments across both trees. Some sentences describe a blind spot nothing else carries and stay in their files on `prose.md`'s clause that a blind spot that matters gets a test or a topic; other claims the comments made about the tree, which no test asserts, left the prose. Each item below is a test to write, or a recorded drop.

## Why this matters

The claims sit on the ops role, the daily pass, the engine node wrapper and the capture writer. A sentence that says what a guard covers, with nothing asserting it, is the class that produced most of the review findings of 2026-09-04.

## Findings so far

Kept in the files until this topic closes them:

- `infra/ansible/roles/ops/tasks/main.yml`: `ops_unit_install`'s loop aggregates eight items, so under `--check` any changed unit template suppresses the timer preview for all four timers.
- `tests/test_engine_node.py`: the venue-sourced join (an external order reaching the observer through live reconciliation) is beyond the suite, proven by hand in archived T0152; an opt-in live test would need the IP-bound engine-host key. Same file: the stub-cache tests never run reconciliation, so the `filter_unclaimed_external_orders is False` pin is the only guard against an upstream default flip.
- `infra/scripts/ops_daily.py`: no fixture exercises the read side of `_UNREACHABLE` (a 200 whose body read raises).
- `tests/test_ops_daily.py`: `Report.reminders` gaining a default is watched by nothing; a reader added to `ops_daily.py` without an endpoint pin is caught by nothing; the grep operand-0 skip is sound only while no flag consumes the pattern.

Dropped from the prose, unasserted:

- Every probe in the ops role carries `failed_when: false`; the `daemon.json` task notifies `restart docker` (the docker-role ordering test stays green if the notify is dropped); every image-consuming ops guard carries `when: ops_image_digest is defined`; `env.j2` renders the empty hash scope as an empty assignment that compose and the entrypoint substitute `full` for; the echo's negated clause equals the assert's first disjunct verbatim.
- `zcrypto-capture.service` has `Restart=always` and no `After=time-sync.target`, the premise of the leading-clock scenario; `_recover`'s `.tmp` unlink is `__init__`'s one unguarded operation.
- Each `VERDICT_CHECKS` bound equals its owning rule's evaluator; the healthchecks fixture's keys are a subset of `{name, tags, desc}`; `test_legitimate_heavy_tails_stay_measured` claimed a 200-seed sweep over a loop of ten.
- `infra/ansible/roles/base/defaults/main.yml`: a FAILED unattended upgrade pages nobody. `node_reboot_required` (spec 00071) covers only the opposite case, a SUCCESSFUL upgrade awaiting reboot, so the gap is patches that never install. T0027 and T0100 cover the reboot side alone, and no rule in `infra/grafana/alerts.yaml` reads an upgrade failure.
- `infra/ansible/roles/access/tasks/main.yml`: the bridgehead relay's socket half is applied by neither its restart handler nor its end-of-role drift assert, so a changed `ListenStream` is written and never applied. The fact itself is stated in archived T0156; what had no live home is its TRIGGER — widen the gate if that value ever changes — and an archived topic is never re-read. `git grep -n ListenStream -- tests/` is empty.
- `infra/ansible/roles/access/tasks/main.yml`: no alert fires on a caddy-only outage. The cert-expiry rule that probes the edge carries `noDataState: OK` because it treats `zcrypto-alloy-dark-zaccess` as owning "the host is dark", and that rule stays green while Alloy is healthy; spec 00075 D11's rule list — bridgehead dark, WG stale, cert expiry, disk — has no member covering it.

## Suggested next steps

- Ops role, in `tests/test_infra_converge_guards.py`: a case on a changed-but-not-new unit template under check mode against the existing `ops_unit_install` fixture; a walk over the role's probes asserting `failed_when: false`; a read of `docker/tasks/main.yml` asserting the `daemon.json` task's notify; the `ops_image_digest is defined` gate asserted over every image-consuming ops task; a render of `env.j2` with the empty scope asserting the empty assignment and the `full` substitution; the echo/assert text equality.
- Engine node, in `tests/test_engine_node.py`: decide the venue-sourced join (an opt-in live test gated on `ZCRYPTO_LIVE_VENUE_TESTS`, or a recorded drop naming T0152 as the proof); a reconciliation-level case that flips the upstream default and asserts the adopted order enters the cache.
- Daily pass, in `tests/test_ops_daily.py`: a fake opener whose `read` raises `IncompleteRead`, asserting `.unreadable` on each of the four reads; `Report.reminders` has no default; the endpoint-building call-site count equals the pinned count; `'-e' not in shape.flags` for both grep shapes; `VERDICT_CHECKS` bounds parsed from `alerts.yaml`'s three rules; the healthchecks fixture's key set.
- Capture writer, in `tests/test_capture_segment_writer.py`: a read of `zcrypto-capture.service` beside the other unit-file guards; the `.tmp` unlink as the one unguarded operation.
- Continuity: run `test_legitimate_heavy_tails_stay_measured` over the range its old docstring named, or leave the loop at ten and record that seed-independence is not asserted.
- Unattended upgrades: decide whether a failed security patch on the host holding the live trade key should page. If it should, the signal does not exist and the work is a metric plus a rule in `alerts.yaml`; if it should not, this line is the record of that decision.
- zaccess relay: the trigger is `ListenStream` in `infra/ansible/roles/access/templates/zaccess-ssh-proxy.socket.j2` no longer reading `0.0.0.0:20022` and `[::]:20022`. False today; when it fires, widen the end-of-role drift assert to the socket half, or add the per-half restart handler pair `roles/access_ops` already carries.
- Caddy edge: page on a caddy-only outage, or record the acceptance and its reason — this tier carries interactive access only, no trading and no data path.
