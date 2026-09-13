---
status: resolved
---

# The capture hosts' Alloy drift refusal prescribes a recreate the converge does not need

## Context — what

`infra/ansible/roles/capture/tasks/main.yml:431` is the `fail_msg` of the assert that catches a `config.alloy` on a capture host not matching the repo. It tells the operator to re-run the converge with `-e capture_alloy_digest=<currently-running>`, "then recreate the container so the new file is read". That re-run does not need a recreate: the config copy at `:528` carries `notify: reload alloy`, and that handler POSTs `/-/reload`. The recreate is the remedy for a ROTATED CREDENTIAL — the reload does not re-read `alloy-secrets.env`, which is process-level — and it has been imported into the refusal for a config-drift case that a reload resolves.

The identical defect on the ops host was fixed on `feat/grafana-keepalive`; this is its untouched twin on the capture pair.

## Why this matters

A `fail_msg` is the text a tripped guard shows an operator on a converge path, and this one is on the unbackfillable capture path. An operator following it recreates the Alloy container on `zcrypto` or `zcrypto-red` for no reason, which fires the daemon-restarted and ERROR-logs rules and puts a needless container lifecycle event on the host that must never lose L2 capture. The cost is noise and an unnecessary production action, not data loss — the recreate is safe, merely unwarranted — but it is an instruction the repo gives and does not mean.

## Findings so far

Checked rather than inferred from the ops twin, because a shared phrase is not a shared mechanism:

- `infra/ansible/roles/capture/handlers/main.yml:8-16` — the handler is semantically identical to the ops role's: `uri` POST to `http://127.0.0.1:12345/-/reload`, `status_code: [200, -1]`, and the same comment, "A reload, never `--force-recreate`: … It does not re-read alloy-secrets.env (process-level), so a rotated credential needs a recreate."
- `infra/ansible/roles/capture/tasks/main.yml:528` — the config copy notifies it, so the re-run reloads without further action.
- `infra/ansible/roles/capture/tasks/main.yml:431` — the clause, split across lines 431-432 ("…so the new file is / read."), which is why a single-line grep for the whole phrase misses it.

The ops-side fix and its reasoning are on `feat/grafana-keepalive` — the same correction applies here, with `capture_alloy_digest` for `ops_alloy_digest`. Its second half is worth carrying too: "nothing further is needed" is false when the container is DOWN, because `status_code: [200, -1]` treats a connection failure as success and no task in that play starts Alloy.

## Resolution

The `fail_msg` now says what the re-run does. Its remedy clause reads: that run copies the file and its handler
reloads a RUNNING Alloy, which is all this refusal needs, and if the container is down its next start reads the
new file because no task here starts it. The wording is the ops twin's, already on develop, with
`capture_alloy_digest` for `ops_alloy_digest`.

Each link `## Findings so far` asserts was re-checked on the capture role at this tip rather than carried over
from the ops side, since a shared phrase is not a shared mechanism. The recreate knowledge stays in the handler
comment, where someone rotating a credential meets it.

**One premise the topic did not name, and the whole correction rests on it:** a reload only reaches the process
because `alloy-compose.yaml.j2` mounts `./conf:/etc/alloy:ro`, a DIRECTORY. Under a single-file bind the reload
re-reads a pinned stale inode and still returns 200, which would make this `fail_msg` false while looking right.
That mount is the structural fix [[T0109]] landed, and `tests/test_infra_compose_templates.py` holds it:
`test_the_alloy_config_is_never_bind_mounted_as_a_single_file`.

The sentence before the refusal is untouched: the `when:` guard exists so a run carrying the
digest is never asserted against before its copy runs, and that re-run IS the remedy the guard keeps open.

**The unblocking, recorded because the trigger named it:** this topic's `ripe_when` first arm was "a session
holding the Fable review floor picks this up". The account's Fable quota is exhausted, and the gate now accepts
an Opus read on a guarded path when the PR body carries `Fable floor substituted by Opus: <reason>` — so the arm
is satisfied by substitution rather than by Fable becoming available.

No converge is owed by this topic: the text surfaces only when the assert trips, and a converge a solution still
needs is the fleet's concern (`.claude/rules/fleet-deploys.md`), not the topic's.
