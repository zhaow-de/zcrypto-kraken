---
status: resolved
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

## Resolution

The owner pruned the tail on 2026-09-06, agreeing in full to the coordinator's recommendations. All of it landed on branch `fix/t0174-tests-remainder-tail`.

### The keeps

Each a guard with a constructed defect that trips it and a production-shaped true positive beside it.

- `_fires_on_absence` takes the direction from a math node as well as a threshold, and refuses every shape it cannot read — `test(obs): the dead-man shape the classifier read as a burst rule`, widened by `test(obs): the pass-over arm that re-opened the silent answer the refusal exists to close` after a review showed arithmetic under a threshold was where the silent wrong answer lived.
- `OPS_CONTEXT` reads `ops_liquidations_container` from the role defaults instead of hand-typing it — `test(infra): the ops container name read from the role default, never re-typed`. Deleting the key from the defaults file previously left the render tests green.
- The rc-9 cleanup test carries a `skipif` for the non-root run its docstring only assumed — `test(infra): the rc-9 test's non-root assumption, which only the docstring was holding`. Under a mapped-root euid that test is a false red, not a pass.
- The rc-8 refusal's sandbox dir is asserted gone, through a TMPDIR scoped to the subprocess — `test(infra): the rc-8 refusal's temp dir, claimed clean by a test that read no TMPDIR`.
- The future-dated final's "loudly" is a level assertion separating silence from a downgrade — `test(capture): the word "loudly" over a log line nothing read`.
- The alloy token sweep reads a capitalised name and keys on `.lower()` — `test(obs): the metric sweep reads a name spelled with a capital` — and rather than leave the canonicalisation's blind spot enumerated in prose, refuses any capitalised `zcrypto_` name outright, in `test(obs): a capitalised metric name refused, so the case the sweep canonicalises cannot arise`.

### The drops

With the reasons the owner agreed to.

- `_HEADROOM_DELIBERATELY_ABSENT` being empty, so its arm iterates nothing: an empty exemption list is the invariant, a future entry is a reviewed diff, and a test asserting a constant is empty is prose in disguise.
- "mirrors Ansible's own template defaults" being unasserted: asserting it means depending on another project's internals for a drift that has never happened. The sentence was cut, and cut family-wide — it stood in three siblings besides the file the drop named.
- The derived guard's `zcrypto_*`-only scope: the `ops_*`, `node_*` and `hc_*` families are third-party exporters whose series are allowlisted by hand, so a new family is a reviewed diff. It was the one item that is real work rather than a line.
