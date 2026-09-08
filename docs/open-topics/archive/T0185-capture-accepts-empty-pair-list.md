---
status: resolved
---

# The capture daemon accepts an empty pair list and keeps the dead-man switch green

## Context — what

`cli/capture/command.py` resolves the pairs to capture as `pairs or _default_pairs(...)`, and nothing between that expression and the `_run` call it feeds refuses an empty result. `_default_pairs` refuses a missing universe file and an unparseable one, filters `selected` to `/EUR` symbols, logs an ERROR for what it dropped, and returns whatever is left — including nothing. A daemon started with no pairs connects to the venue, subscribes to nothing, and runs.

`GapMonitor.is_healthy` (`cli/capture/gap_monitor.py`) is `not any(self.is_open(pair) for pair in pairs)`, `True` over an empty list, and it gates the healthchecks.io ping — `client.connected and monitor.is_healthy(pairs) and not watermark.breached and watermark.measurable` — where `client.connected` is independent of `pairs`. So with no pairs the daemon captures nothing and keeps the dead-man switch green: a false all-clear on the unbackfillable capture path, the one failure the switch exists to expose.

`is_healthy([])` is a member of `T0183`'s family — a summary over an empty set returning the value that also means success, the same shape as `all_match` — and this topic exists because its correct fix is not at that site. Spec `00073` D3 makes `is_healthy` deliberately conservative about what darkens the dead-man for every pair at once; adding a condition there is what D3 refused. The defect is upstream: the daemon accepts an input it should refuse.

## Why this matters

The reachable radius, from the tree rather than the headline. `infra/docker/Dockerfile`'s entrypoint adds `--pairs` only when `CAPTURE_PAIRS` is non-empty — its own comment says an unset variable omits `--pairs` — and `capture_pairs` is a twelve-item literal in `infra/ansible/group_vars/capture_host/vars.yml` that **nothing asserted was non-empty**: the role's pair-add asserts in `infra/ansible/roles/capture/tasks/main.yml` compare it against the deployed and primary sets, never its length. So an empty `capture_pairs` converged cleanly, the container started without `--pairs`, and production was on the `_default_pairs` path — one variable edit away, not hand-start only. **What that edit produces in production is not the silent case.** The universe file yields the `/EUR` majors, so the daemon starts on that reduced set, drops the BTC-quoted legs `_default_pairs` filters out by construction, and the deploy path exists to pass them explicitly — its own comment says so, logs an ERROR naming them, and the dead-man stays legitimately green because it really is capturing. That is a paging gap, not a silent one. The silent case — nothing captured, switch green — needs the universe file to yield no `/EUR` symbol as well.

On that path, a non-empty `selected` naming no `/EUR` symbol logs an ERROR that `alerts.yaml`'s `Capture · daemon ERROR logs` rule selects (`configure()` runs in the Typer callback before `_default_pairs`, so the line is shipped rather than lost). Only a fully empty `selected` reached an empty `pairs` silently. Two misconfigurations had to coincide on the deploy path; one sufficed by hand.

## Findings so far

- `_default_pairs`'s own comment said the deploy path always passes `--pairs`. It did, because `capture_pairs` was populated — but the entrypoint's `if [ -n "${CAPTURE_PAIRS:-}" ]` is what decides it, and the comment described the variable's value, not the mechanism.
- A `CaptureError` raised at startup is logged with a level before the process dies: `cli/__main__.py`'s `main()` wraps `app()` and logs an unhandled fault, so a refusal pages through the ERROR rule and, since nothing pings, through the dead-man — two channels, both truthful, immediately.
- The alternative — `is_healthy` returning `False` on empty `pairs` — pages once, after the healthchecks.io grace, with a daemon that is running and reads as alive in `docker ps` and its own `starting capture pairs=[]` line. Rejected: a daemon running while capturing nothing is the state the switch exists to expose, not one to keep alive, and it adds to `is_healthy` the kind of condition D3 exists to keep out.

## Resolution

Two guards, because the two failures are not the same one: an empty `capture_pairs` produces the reduced-set capture, which only the converge-time assert prevents; the `_default_pairs` refusal fires only when the universe yields no `/EUR` symbol. Both landed in the PR that carries this file into `archive/`, reviewed at the Fable floor on the owner's word.

- **`_default_pairs` refuses an empty result** as its third refusal, after the `dropped` ERROR so the diagnostic that says *why* the list is empty still logs first — the commit `fix(capture): _default_pairs refuses an empty pair list instead of returning it`. Every route funnels through `pairs or _default_pairs(...)`, so the one refusal covers an explicit empty list, an empty env var and a bare hand-start. `tests/test_capture_command.py` holds the four cases: `selected: []` raises; all non-`/EUR` logs the dropped ERROR and raises; mixed returns the `/EUR` subset; all-`/EUR` returns everything with no record at ERROR or above. Both reds were proved by restoring the bare `return pairs`.
- **The capture role asserts `capture_pairs | length > 0`** before its first read of the variable, on every capture host, primary included — `compose.yaml.j2` renders `CAPTURE_PAIRS` unconditionally — the commit `fix(ansible): the capture role refuses an empty capture_pairs at the converge`, pinned by `test_capture_pairs_must_be_non_empty` in `tests/test_infra_converge_guards.py`. The misconfiguration now fails the converge that would have deployed it, which is the first moment it could reach a host; the daemon's own refusal reaches the hosts with the next capture-image rollout.
- `is_healthy` is untouched, per spec `00073` D3, and with both refusals in place an empty pair list no longer reaches it through the daemon.
