---
status: resolved
---

# Nothing compares a host's running Alloy config to the repo's

## Context — what

Split out of [[T0109]] on 2026-07-29, which fixed two layers of this and left this one named but unregistered — it lived only in `docs/memo.local.md`, which is gitignored, and that is exactly the failure [[T0107]] was opened to prevent.

[[T0109]] closed the two mechanisms that let a `config.alloy` edit fail to take effect: the digest gate now has a rule line, and the single-file bind mount became a directory mount with a change-triggered reload. **Neither closes the detection gap.** The Alloy block on both Ansible tiers is still wrapped in:

```yaml
when: <tier>_alloy_digest is defined
```

An ordinary converge still omits that variable by design, still skips the config copy, and still exits 0. The only thing standing between that and a silently stale keep-regex is prose in `.claude/rules/capture-deploys.md`.

## Why this matters

**Every automated check in the repo compares the repo to itself.** `tests/test_infra_alloy_series.py` verifies that the keep-regexes in `infra/**/config.alloy` admit the metrics the code publishes — repo↔repo. It cannot see a host running last month's file, which is the direction that actually caused the incident: on 2026-07-28 both capture hosts had been dropping spec `00073`'s blackout measurement for a day, with the repo entirely correct throughout.

The 2026-07-29 rollout showed the drift is still reachable by an ordinary mistake: on the capture primary, immediately after a converge that passed the digest correctly, host `fda087ea…` against container `e89f00d1…`. That one was caught because the runbook said to compare hashes. Nothing enforces that it is compared.

**It is the reassuring direction again**: the converge reports `changed`, the host file is right, the metric endpoint looks right, and the series never arrives.

## Findings so far

- The check cannot live in CI: GitHub Actions has no route to the fleet, and giving it one is a larger decision than this topic.
- Three candidate homes, none obviously right:
  - **The converge itself** — an Ansible task that reads the deployed file's hash and asserts it matches the repo's. Runs only when someone converges, which is exactly when it is least needed and most likely to be skipped.
  - **A periodic ops timer** — a small unit on `zcrypto-ops` that `ssh`es each host, hashes `conf/config.alloy`, compares against a hash the ops image carries, and writes a `.prom`. Detects drift without a converge, and turns it into an alertable series. Costs an ops-node SSH channel to the capture hosts, which does not exist today.
  - **A `--check --diff` habit** — no code, purely procedural. Cheapest, and the weakest: it is the class of remedy that produced this topic, since [[T0109]] showed a documented ruling that never reached the operator's rules.
- The directory mount changed the shape of the failure but not its existence: a stale *file* now propagates to the process on reload, so drift is strictly between host and repo rather than between host, file and process.

## Resolution

**Decided and implemented 2026-07-29, in the same branch that split it out.** The check lives in the **converge**, not an ops timer and not a procedure.

The reasoning that settled it: the failure this guards against is *a converge that silently skipped the config copy*. The converge is therefore the moment the drift is created, and a check there catches it with no new access between hosts — the ops-timer option's only advantage is detecting drift nobody went looking for, and it needs an ops→capture SSH channel that does not exist. The procedural option is what produced [[T0109]] in the first place.

Two tasks in the `capture` and `ops` roles, **deliberately outside** `when: <tier>_alloy_digest is defined` — inside the gate they would be skipped by exactly the converge that causes the drift:

- `stat` the deployed `conf/config.alloy` with `checksum_algorithm: sha256`
- compare it against the repo file's checksum, read by `stat` **on the controller** (`delegate_to: localhost`)

The assert runs only when a config is already deployed, so a host that has never had Alloy passes and its first real deploy creates one. Its `fail_msg` names the remedy — re-run passing the digest, then recreate the container.

**Proven in both directions against the live ops host**, because a check that only ever passes is the defect it exists to catch:

| probe | result |
| --- | --- |
| host matches repo | `ok=57 changed=0 failed=0` |
| one line appended to the repo file | `failed=1`, with the remediation message |

**The first implementation was broken and the verification is what caught it.** It compared the remote checksum against `lookup('ansible.builtin.file', …) | hash('sha256')` — and the file lookup **strips the trailing newline**, so the hash never equals the file's real sha256. That version failed on a host whose config was byte-identical to the repo, and would have failed on every converge forever. A permanently-red assert does not get investigated; it gets deleted. Controller-side `stat` hashes the same bytes as the remote one.

**What it still does not cover**: drift that appears without a converge, and the NAS, whose role writes the config from `{{ playbook_dir }}/../nas/config.alloy` rather than a role `files/` dir. Both are accepted — the converge is the only mechanism that creates this drift, and the NAS's apply step already recreates its container.

## Suggested next steps

*(All discharged — see `## Resolution`.)*

- ~~Decide where the check lives~~ — the converge, for the reason recorded above.
- ~~Implement it, and give it an alert rule if it produces a series~~ — implemented as a converge-time assert; it produces no series, so no rule is owed.
- ~~Record it in `capture-deploys.md`~~ — the digest-gate line there already states the requirement; the assert now enforces it rather than relying on the reader.
