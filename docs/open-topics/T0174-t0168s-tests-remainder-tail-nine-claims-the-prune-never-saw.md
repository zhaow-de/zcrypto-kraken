---
status: open
---

# T0168's tests-remainder tail: nine claims the prune never saw

## Context — what

The `tests/` prose-remainder batch (T0164, `cleanup/prose-tests-remainder`) appended eleven bullets to T0168's `## Suggested next steps` after the owner's prune list for that topic had already been built. The prune enumerated 52 of the file's 63 bullets, so these eleven were in neither the keeps nor the drops — never in front of the owner. Two of them were asserted on `feat/t0168-wave2-remaining-claims`; the nine below are split out here so T0168 could close truthfully rather than by emptying a section that still held live claims.

## Why this matters

Each names a guard that is degenerate or blind today: an evaluator shape a matcher cannot see, an exclusion list that is empty so its arm never runs, a hand-typed context that drifts from what the deploy renders, a claimed lock-step nothing checks, two probe exit paths whose declared assumptions are unasserted, a future-dated final whose promise is untested, and two token patterns that cannot see the metric names they exist to police. None is a coverage claim about the suite; each is one file's own sentence with no assertion under it.

## Findings so far

Verbatim from T0168's `### From the tests/ remainder` section at `7be03116`, each keeping the reading it was registered with.

### The four alert-rule and compose-template claims

- `tests/test_infra_alert_rules.py` — `_fires_on_absence` is blind to an `lt` evaluator folded into a `math` node; the file says so in prose and asserts nothing. Wanted: a rule fixture whose absence-firing shape is expressed that way, asserted to be classified.
- `tests/test_infra_alert_rules.py` — `_HEADROOM_DELIBERATELY_ABSENT` is empty, so the stale-excuse arm of its test iterates nothing and is degenerate today. Wanted: either an entry, or the arm asserted to be empty on purpose so a future entry is a decision rather than drift.
- `tests/test_infra_compose_templates.py` — `OPS_CONTEXT` hand-types `"zcrypto-ops-liquidations"` under a comment claiming it IS the role default, with nothing tying it to `roles/ops/defaults/main.yml`. Wanted: the context read from the role default, so a changed default cannot leave every render test green against a `container_name` production never renders.
- `tests/test_infra_compose_templates.py` — "mirrors Ansible's own template defaults" is unasserted, so an ansible-core default change diverges from a real converge silently. Wanted: the rendering Environment's `trim_blocks`/`lstrip_blocks` compared against `ansible.plugins.action.template`'s own defaults.
### The probe, writer and series claims

- `tests/test_mutate_probe.py` — `test_cleanup_cp_failure_is_rc9_and_keeps_pristine` declares "Assumes a non-root test run" with no guard: under root `chmod 0444` is a no-op and rc is never 9. Wanted: the `os.geteuid() == 0` skipif its sibling at `tests/test_capture_segment_writer.py:962` was given today.
- `tests/test_mutate_probe.py` — `test_seeding_failure_is_rc8_not_usage` claimed the rc-8 path leaves no temp dir while reading no TMPDIR. Wanted: the temp dir asserted absent.
- `tests/test_capture_segment_writer.py` — `test_a_future_dated_final_can_never_brick_the_stream` says the nonsense final is ignored "loudly" with no caplog assertion. Wanted: the log line asserted.
- `tests/test_infra_alloy_series.py` — the token pattern `zcrypto_[a-z0-9_]{4,}` cannot see an uppercase metric name. Wanted: a case-insensitive sweep asserting every hit is already classified.
- `tests/test_infra_alloy_series.py` — the derived guard's scope is `zcrypto_*` only, so an `ops_*`, `node_*` or `hc_*` family added to code and to no list is dropped at remote_write with the suite green. Wanted: the same derivation over those prefixes.

## Suggested next steps

- The owner prunes the nine as T0168's 52 were pruned: each keep becomes a guard with a constructed defect that trips it and a production-shaped true positive beside it, each drop a reason recorded in this file.
