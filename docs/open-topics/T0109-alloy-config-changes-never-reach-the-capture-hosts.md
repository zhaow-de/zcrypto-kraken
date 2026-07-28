---
status: partial
ripe_when: the repo-side half is DONE (rule line, T0107 amendment, CI drift guard). What remains is ATTENDED: pass `capture_alloy_digest` at the next capture converge so the config installs. **That alone delivers only the TWO series the running image already emits** — `seconds_since_last_book_message` and `venue_status_total`. The other three admitted-but-undelivered series need [[T0107]]'s image roll as well, since the running image does not publish them; do not treat this converge as satisfying them
---

# Every `config.alloy` change is silently skipped by ordinary capture converges

## Context — what

Found 2026-07-28 while checking whether [[T0105]]'s `ripe_when:` trigger was satisfiable. It is not, and the reason is a deploy gate, not a missing metric.

`infra/ansible/roles/capture/tasks/main.yml` wraps the whole Alloy block — **including `install the alloy pipeline config`, a plain `copy:` of the static `config.alloy`** — in:

```yaml
when: capture_alloy_digest is defined
```

Ordinary converges omit that variable by design; `capture-deploys.md` states the same discipline for the ops tier ("Omit `ops_alloy_digest` unless Alloy is the subject"). So every capture converge that is not *about* Alloy skips the config install, and a repo edit to `config.alloy` reaches neither host.

Measured on `zcrypto-red`, deployed keep-regex vs the repo's — **46 terms deployed against the repo's 50 when this was measured on 2026-07-28; 4 admitted by the repo and dropped in production** (the 46-term revision is `e82d8f05`, which differs from its successor by exactly the keep-regex line; the repo side is 51 today — a later commit on this branch added the logship liveness gauge, so re-count rather than trusting the 50):

| series | emitted by the running image? | consequence |
| --- | --- | --- |
| `zcrypto_capture_seconds_since_last_book_message` | **yes — 12 series** | dropped at remote-write; absent from Cloud |
| `zcrypto_capture_venue_status_total` | **yes — 1 series** | dropped at remote-write; absent from Cloud |
| `zcrypto_capture_resubscribe_errors_total` | no (image not rolled) | doubly blocked — needs [[T0107]]'s roll **and** this converge |
| `zcrypto_capture_resubscribe_ack_timeouts_total` | no (image not rolled) | same |

Both hosts are identical: `sudo grep -c` on the deployed config returns **0** for the first two names on `zcrypto` and `zcrypto-red` alike, while each host's `127.0.0.1:9101/metrics` returns **13** matching lines. Cloud returns `(no series)` for both, against 24 series for the sibling `zcrypto_capture_book_desynced` that *is* in the deployed keep-list.

**The ops tier has the identical gate, and it has already cost a series.** `infra/ansible/roles/ops/tasks/main.yml` wraps its Alloy block in the same `when: ops_alloy_digest is defined`, with its config install inside — and `capture-deploys.md` instructs omitting that variable unless Alloy is the subject. Found 2026-07-28 by a reviewer checking a coverage claim: **`node_textfile_mtime_seconds` is admitted on capture but not on ops**, while `zcrypto-ops` runs the textfile collector (`node_scrape_collector_success{collector="textfile"}` = 1) over six `.prom` files. Cloud carries it for `zcrypto` and `zcrypto-red` and **not for `zcrypto-ops`** — so on the host running four timers, the signal that distinguishes *"the timer stopped"* from *"the timer ran and had nothing to report"* is invisible. The sibling `node_textfile_scrape_error` **is** admitted there, which is why nothing looked wrong.

## Why this matters

**The measurement half of the 2026-07-27 blackout response is invisible in production.** Spec `00073` built `seconds_since_last_book_message` and `venue_status_total` precisely because every existing liveness signal read healthy through a 12-pair blackout. That code now runs on both hosts and emits correctly — and no alert can be written against it, no dashboard can show it, because the series never leaves the host.

It is the [[T0051]] trap in its most expensive form: an allow-list silently discarding a published series, with the twist that the repo is **correct** and the host is stale, so every review that reads the repo concludes the series is admitted.

Two compounding failures, and the second is the durable one:

- The variable is named `capture_alloy_digest`. Nothing in that name says it also gates a static config file, so omitting it — which the deploy discipline actively instructs — reads as "don't change the Alloy image", not "don't ship the config".
- **Nothing detects the drift.** No test compares repo `config.alloy` to what a host runs; the converge exits 0 having skipped the task; `--check --diff` reports `skipping` in a wall of other skips.

## Findings so far

- The gate is on the block, not the task: the digest render, the secrets env, the compose file, and the config copy are all inside it.
- The deployed file is a genuinely older revision, and the **term count is the proof**: 46 against the repo's 50, differing by exactly the four names above. (An earlier version of this bullet cited a line-91 comment as absent from the repo; it is present there verbatim, and that evidence line was simply wrong — the count is what establishes the claim.)
- Both capture hosts are equally stale; this is not a one-host miss.
- `zcrypto_capture_book_desynced` arriving with 24 series proves the pipeline itself is healthy — this is exclusively an allow-list-contents problem.
- The keep-regex fix for `node_textfile_mtime_seconds` is committed here, but like every other `config.alloy` change it **only ships if the converge passes `ops_alloy_digest`** — the same gate that hid it.
- The two undeployed T0102 counters mean [[T0107]]'s payload list is **incomplete**: it names the image roll but not the Alloy converge, so following it exactly would roll the image and still leave the new alert rule reading no data.

## Done so far

Both repo-side sub-items landed 2026-07-28 on `docs/ops-converge-0728-record`:

- **`capture-deploys.md` records the gate** — one line naming the safe alternative in the same sentence, per `agent-ops.md`'s footgun rule, since "omit the digest" is the surrounding discipline and reads as correct.
- **[[T0107]] amended** — the Alloy converge is now listed as *required, not optional*, and its post-roll verification covers five undelivered series. **Those five are T0107's bar, not this converge's**: an Alloy-config-only converge can deliver at most the two the running image already emits.
- **The CI drift guard landed** in `tests/test_infra_alloy_series.py`: a source-derived check that fails when a published `zcrypto_*` name matches no host's keep-regex. The pre-existing guards used hand-maintained lists, so a metric nobody listed was invisible to them.
- **The real lesson is narrower than first recorded, and the first version was wrong.** A first pass reported 18 unadmitted names and blamed an admission surface "split across `config.alloy` files and Ansible host_vars". **There is no such split** — `host_vars/nas/vars.yml` carries no keep-list at all, and its only `zcrypto_gate` mention is a comment. All 18 came from comparing keep-list entries as *literals* when they are *regexes*: `infra/nas/config.alloy` admits the whole gate family as `zcrypto_gate_.*`. Of the 18, **14 are live series** and 3 are non-metrics (`zcrypto_ed25519`, `zcrypto_owned`, a bare `zcrypto_reconcile_` stem); the 4th non-live is `zcrypto_engine_orders_created`, a `_created` series suppressed process-wide. Consulting host_vars would have changed nothing.


## Suggested next steps

- *(ATTENDED, at the next capture converge)* Pass `capture_alloy_digest=<currently-running>` so the config installs, then confirm **the two series the running image emits** — `zcrypto_capture_seconds_since_last_book_message` and `zcrypto_capture_venue_status_total` — arrive in Cloud. The two resubscribe counters and the logship liveness gauge are **not** expected to appear: none is in the running image (verified — their commits are not ancestors of the converged revision), so they wait on [[T0107]]'s roll. Config change, not a re-pin: no bake owed.
- *(ATTENDED, at the next OPS converge)* Pass `ops_alloy_digest=<currently-running>` so the ops config installs, then confirm `node_textfile_mtime_seconds` appears for `zcrypto-ops` in Cloud. Config change, not a re-pin; no bake owed on the ops tier.
- *(autonomous, after that converge)* Re-evaluate [[T0105]]'s trigger, which is unsatisfiable until then.
