---
status: open
ripe_when: a session holding the Fable review floor picks this up, OR a change to `infra/ansible/roles/capture/` opens — `git log --oneline develop..HEAD -- infra/ansible/roles/capture/` non-empty on the branch doing that work
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

The ops-side fix and its reasoning are on `feat/grafana-keepalive` — the same correction applies here, with `capture_alloy_digest` for `ops_alloy_digest`. Its second half is worth carrying too: "nothing further is needed" is false when the container is DOWN, because `status_code: [200, -1]` treats a connection failure as success and no role in that play runs `compose up`.

## Suggested next steps

- Replace the recreate clause with what the re-run actually does: the handler reloads a RUNNING Alloy, and starting a stopped one reads the new file. Scope the promise to clearing the refusal, not to finishing a rollout — a new metric family still owes the by-value first scrape `zcrypto-bump-alloy` requires.
- Leave the recreate knowledge in the handler comment, where someone rotating a credential meets it; it is correct there and only misplaced in the refusal.
- Do not rewrite the sentence before it: the comment under that task explains that the `when:` guard exists so a run carrying the digest is never asserted against before its copy runs, and the re-run IS the remedy that guard keeps open.
- The change touches the capture path, so `commit-messages.md` puts its review floor at Fable and `fleet-deploys.md` governs any converge that deploys it.
