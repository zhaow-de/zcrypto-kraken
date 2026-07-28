---
status: open
ripe_when: NOW for the repo-side half (the guard test and the rule line); the converge that actually delivers the four series is ATTENDED and rides the next capture-host converge for any reason
---

# Every `config.alloy` change is silently skipped by ordinary capture converges

## Context — what

Found 2026-07-28 while checking whether [[T0105]]'s `ripe_when:` trigger was satisfiable. It is not, and the reason is a deploy gate, not a missing metric.

`infra/ansible/roles/capture/tasks/main.yml` wraps the whole Alloy block — **including `install the alloy pipeline config`, a plain `copy:` of the static `config.alloy`** — in:

```yaml
when: capture_alloy_digest is defined
```

Ordinary converges omit that variable by design; `capture-deploys.md` states the same discipline for the ops tier ("Omit `ops_alloy_digest` unless Alloy is the subject"). So every capture converge that is not *about* Alloy skips the config install, and a repo edit to `config.alloy` reaches neither host.

Measured on `zcrypto-red`, deployed keep-regex vs the repo's — **46 terms deployed, 50 in repo, 4 admitted by the repo and dropped in production**:

| series | emitted by the running image? | consequence |
| --- | --- | --- |
| `zcrypto_capture_seconds_since_last_book_message` | **yes — 12 series** | dropped at remote-write; absent from Cloud |
| `zcrypto_capture_venue_status_total` | **yes — 1 series** | dropped at remote-write; absent from Cloud |
| `zcrypto_capture_resubscribe_errors_total` | no (image not rolled) | doubly blocked — needs [[T0107]]'s roll **and** this converge |
| `zcrypto_capture_resubscribe_ack_timeouts_total` | no (image not rolled) | same |

Both hosts are identical: `sudo grep -c` on the deployed config returns **0** for the first two names on `zcrypto` and `zcrypto-red` alike, while each host's `127.0.0.1:9101/metrics` returns **13** matching lines. Cloud returns `(no series)` for both, against 24 series for the sibling `zcrypto_capture_book_desynced` that *is* in the deployed keep-list.

## Why this matters

**The measurement half of the 2026-07-27 blackout response is invisible in production.** Spec `00073` built `seconds_since_last_book_message` and `venue_status_total` precisely because every existing liveness signal read healthy through a 12-pair blackout. That code now runs on both hosts and emits correctly — and no alert can be written against it, no dashboard can show it, because the series never leaves the host.

It is the [[T0051]] trap in its most expensive form: an allow-list silently discarding a published series, with the twist that the repo is **correct** and the host is stale, so every review that reads the repo concludes the series is admitted.

Two compounding failures, and the second is the durable one:

- The variable is named `capture_alloy_digest`. Nothing in that name says it also gates a static config file, so omitting it — which the deploy discipline actively instructs — reads as "don't change the Alloy image", not "don't ship the config".
- **Nothing detects the drift.** No test compares repo `config.alloy` to what a host runs; the converge exits 0 having skipped the task; `--check --diff` reports `skipping` in a wall of other skips.

## Findings so far

- The gate is on the block, not the task: the digest render, the secrets env, the compose file, and the config copy are all inside it.
- The deployed file is a genuinely older revision — its line 91 carries a comment about two series having been removed from the keep-regex, text the current repo file no longer has.
- Both capture hosts are equally stale; this is not a one-host miss.
- `zcrypto_capture_book_desynced` arriving with 24 series proves the pipeline itself is healthy — this is exclusively an allow-list-contents problem.
- The two undeployed T0102 counters mean [[T0107]]'s payload list is **incomplete**: it names the image roll but not the Alloy converge, so following it exactly would roll the image and still leave the new alert rule reading no data.

## Suggested next steps

- *(autonomous, ripe NOW)* **Add the drift guard.** A test that fails when the repo's keep-regex does not contain every `zcrypto_*` metric name the codebase registers — the reverse direction of the [[T0051]] trap, catchable without a host. It cannot see host staleness, but it is the half that runs in CI.
- *(autonomous, ripe NOW)* **Record the gate in `capture-deploys.md`** — one line naming the safe alternative, per `agent-ops.md`'s footgun rule: a `config.alloy` change requires passing `capture_alloy_digest` (the currently-running one) or it does not ship.
- *(autonomous, ripe NOW)* **Amend [[T0107]]** so its payload names this converge alongside the image roll, and its post-roll verification covers all four series rather than the two resubscribe counters.
- *(ATTENDED, at the next capture converge)* Pass `capture_alloy_digest=<currently-running>` so the config installs; then confirm all four series arrive in Cloud. This is a config change, not a digest re-pin — no bake owed, per `capture-deploys.md`'s pair-list precedent.
- *(autonomous, after that converge)* Re-evaluate [[T0105]]'s trigger, which is unsatisfiable until then.
