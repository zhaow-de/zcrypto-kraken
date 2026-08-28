---
status: resolved
---

# Every `config.alloy` change is silently skipped by ordinary capture converges

## Context — what

Found 2026-07-28 while checking whether [[T0105]]'s `ripe_when:` trigger was satisfiable. It is not, and the reason is a deploy gate, not a missing metric.

`infra/ansible/roles/capture/tasks/main.yml` wraps the whole Alloy block — **including `install the alloy pipeline config`, a plain `copy:` of the static `config.alloy`** — in:

```yaml
when: capture_alloy_digest is defined
```

Ordinary converges omit that variable by design; `fleet-deploys.md` states the same discipline for the ops tier ("Omit `ops_alloy_digest` unless Alloy is the subject"). So every capture converge that is not *about* Alloy skips the config install, and a repo edit to `config.alloy` reaches neither host.

Measured on `zcrypto-red`, deployed keep-regex vs the repo's — **46 terms deployed against the repo's 50 when this was measured on 2026-07-28; 4 admitted by the repo and dropped in production** (the 46-term revision is `e82d8f05`, which differs from its successor by exactly the keep-regex line; the repo side is 51 today — a later commit on this branch added the logship liveness gauge, so re-count rather than trusting the 50):

| series | emitted by the running image? | consequence |
| --- | --- | --- |
| `zcrypto_capture_seconds_since_last_book_message` | **yes — 12 series** | dropped at remote-write; absent from Cloud |
| `zcrypto_capture_venue_status_total` | **yes — 1 series** | dropped at remote-write; absent from Cloud |
| `zcrypto_capture_resubscribe_errors_total` | no (image not rolled) | doubly blocked — needs [[T0107]]'s roll **and** this converge |
| `zcrypto_capture_resubscribe_ack_timeouts_total` | no (image not rolled) | same |

Both hosts are identical: `sudo grep -c` on the deployed config returns **0** for the first two names on `zcrypto` and `zcrypto-red` alike, while each host's `127.0.0.1:9101/metrics` returns **13** matching lines. Cloud returns `(no series)` for both, against 24 series for the sibling `zcrypto_capture_book_desynced` that *is* in the deployed keep-list.

**The ops tier has the identical gate, and it has already cost a series.** `infra/ansible/roles/ops/tasks/main.yml` wraps its Alloy block in the same `when: ops_alloy_digest is defined`, with its config install inside — and `fleet-deploys.md` instructs omitting that variable unless Alloy is the subject. Found 2026-07-28 by a reviewer checking a coverage claim: **`node_textfile_mtime_seconds` is admitted on capture but not on ops**, while `zcrypto-ops` runs the textfile collector (`node_scrape_collector_success{collector="textfile"}` = 1) over six `.prom` files. Cloud carries it for `zcrypto` and `zcrypto-red` and **not for `zcrypto-ops`** — so on the host running four timers, the signal that distinguishes *"the timer stopped"* from *"the timer ran and had nothing to report"* is invisible. The sibling `node_textfile_scrape_error` **is** admitted there, which is why nothing looked wrong.

**SECOND LAYER — and it was already known.** `docs/specs/00071` records the same mechanism (*"bind-mounted as a *single file*, which pins the inode; `copy:` writes a new inode, so the running container keeps serving the old config"*) and chose attended-recreate as the answer, explicitly warning against a handler. **The defect is not that nobody found it — it is that the remedy never reached the operator-facing rules**, so a converge run from `fleet-deploys.md` alone lands the config and stops. Re-derived the hard way on 2026-07-28, during the very converge that fixed the first layer, which it defeats. Passing the digest makes the config reach the *host*. It does not make it reach the *process*. All three tiers bind-mount a **single file**:

```yaml
- ./config.alloy:/etc/alloy/config.alloy:ro
```

A single-file bind mount binds the **inode**, not the path, and Ansible's `copy` writes atomically — temp file, then rename over the destination — which **replaces** the inode. The container keeps a handle on the old one and never sees another edit for its whole lifetime.

Measured on `zcrypto-ops` immediately after a clean converge: host sha256 `4dc9663f…` against container sha256 `afccfc96…`, host inode `143271091` against container inode `143143831`, `grep -c` for the new term **1 on the host and 0 inside**. Alloy had reloaded successfully in between (`alloy_config_last_load_successful 1`) — re-reading the stale inode.

**Every check said it worked.** Ansible reported `changed` (it did change the host file); `grep` on the host found the new term (it is there); the reload succeeded (it did); the exporter emitted all six `node_textfile_mtime_seconds` series (it always had). Each verification was correct and each measured the wrong side of the mount. Only comparing the host and container hashes exposed it.

**Neither role has an ALLOY handler** — capture has two `notify: restart capture service` for the daemon, so the absence is Alloy-specific, not total — and a `restart` is not enough — the mount must re-resolve, which needs `docker compose up -d --force-recreate`.

**Status by tier**: ops was *actively* stale and is fixed (container recreated 23:43:12Z; `node_textfile_mtime_seconds{instance=zcrypto-ops}` now reports 6, one per `.prom` file). Capture is *latent* — its containers happen to postdate their last config write, so they are correct today and will go stale the moment a config change ships. The NAS uses the same pattern.

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

The repo-side sub-items all landed 2026-07-28 on `docs/ops-converge-0728-record`:

- **`fleet-deploys.md` records the gate** — one line naming the safe alternative in the same sentence, per `agent-ops.md`'s footgun rule, since "omit the digest" is the surrounding discipline and reads as correct.
- **[[T0107]] amended** — the Alloy converge is now listed as *required, not optional*, and its post-roll verification covers five undelivered series. **Those five are T0107's bar, not this converge's**: an Alloy-config-only converge can deliver at most the two the running image already emits.
- **The CI drift guard landed** in `tests/test_infra_alloy_series.py`: a source-derived check that fails when a published `zcrypto_*` name matches no host's keep-regex. The pre-existing guards used hand-maintained lists, so a metric nobody listed was invisible to them.
- **The real lesson is narrower than first recorded, and the first version was wrong.** A first pass reported 18 unadmitted names and blamed an admission surface "split across `config.alloy` files and Ansible host_vars". **There is no such split** — `host_vars/nas/vars.yml` carries no keep-list at all, and its only `zcrypto_gate` mention is a comment. **15 of the 18** came from comparing keep-list entries as *literals* when they are *regexes*: `infra/nas/config.alloy` admits the whole gate family as `zcrypto_gate_.*`. The other 3 — `zcrypto_ed25519`, `zcrypto_owned`, `zcrypto_engine_orders_created` — are admitted by no keep-regex at all and needed the exclusion list, not regex semantics. Of the 18, **14 are live series** and 4 are not — the bare `zcrypto_reconcile_` stem IS admitted, by the `zcrypto_reconcile_.*` wildcard, so regex semantics does explain that one. Consulting host_vars would have changed nothing.


- **BOTH Ansible tiers are converged and recreated, 2026-07-29.** Ops 01:18:59Z (`node_textfile_mtime_seconds{instance=zcrypto-ops}` now reporting 6); capture with the [[T0107]] roll — secondary 00:54:10Z, primary 07:36:45Z. Every mount now reads `…/alloy/conf`.
- **The `docker compose up -d` was load-bearing on every tier, and the drift was visible each time.** On the capture primary, right after a clean converge with the digest correctly passed: host `fda087ea…` against container `e89f00d1…`. The handler had POSTed a reload that re-read the stale inode and returned 200. Without the recreate, that converge would have reported green and delivered two of five series.
- **The mount is fixed structurally (2026-07-28).** Both roles, and the NAS compose, now bind-mount the config **directory** (`./conf:/etc/alloy:ro`) instead of the file, so a later edit is visible through the path; a `reload alloy` handler POSTs `/-/reload` so Alloy parses it. `tests/test_infra_compose_templates.py` fails if any of the three regresses to a single-file mount.
- **This reverses `00071`'s "do not fix this with a handler" deliberately.** That ruling rejected *an automatic restart of Alloy on every converge*. What landed is a **reload**, fired **only when the config changed** — materially lighter, and it leaves the fleet's "roles render Alloy, humans start it" decision intact. The handler fails the converge on a 4xx/5xx (a config that does not parse) and tolerates only Alloy being down.
- **The delete of the old top-level `config.alloy` was deliberately NOT included.** A missing bind source is recreated as an empty *directory* on the next container start, which crash-loops Alloy — and the ops node auto-reboots at 02:25, so the window is real. It is a follow-up once all three tiers are transitioned.

## Resolution

**All three tiers are on the directory mount as of 2026-07-29**, and every series the gate was dropping now reaches Cloud.

| tier | converged | Alloy recreated | evidence |
| --- | --- | --- | --- |
| ops | 01:18 | 01:18:59Z | `node_textfile_mtime_seconds{zcrypto-ops}` = 6 |
| capture secondary | 00:52 | 00:54:10Z | with [[T0107]]'s roll |
| capture primary | 07:36 | 07:36:45Z | all five undelivered series arriving |
| NAS | 08:30 | 08:30 (`nas_apply_compose=true`) | `zcrypto_gate_status{host=nas}` = 1 after the recreate |

**A claim in this topic was wrong, and it hid a second defect.** This file asserted the NAS was "Container-Manager-managed rather than Ansible-converged", so its transition was manual. It is not: `roles/nas/tasks/main.yml` deploys **both** `compose.yaml` and `config.alloy`. Because that was believed, PR #226 changed the NAS compose to mount `./conf` while leaving the role writing the config to the stack dir's top level — so the next NAS converge-and-apply would have mounted a directory Docker creates empty and Alloy would have failed to start. The cold review accepted the framing and never checked the role. Fixed by making the role write into `conf/` before converging.

**The `docker compose up -d` proved load-bearing on every tier, and the drift was visible each time.** On the capture primary, immediately after a clean converge with the digest correctly passed: host `fda087ea…` against container `e89f00d1…`. The handler had POSTed a reload that re-read the stale inode and returned 200. Without the recreate that converge would have reported green and delivered two of five series.

**One remainder was split out, not dropped**: nothing compares a host's running `config.alloy` to the repo's — every automated check here is repo↔repo, and the digest gate that skips the copy is still in both roles. That is [[T0110]] — registered rather than left in an untracked file, and closed in the same branch: a converge-time assert now compares the deployed config's sha256 against the repo's, outside the digest gate.

**What the whole topic amounts to**: the trap was already documented in spec `00071`, which chose attended-recreate and warned against a handler. That ruling never reached the operator-facing rules, so it was re-derived the hard way, in production, during the converge that was fixing the layer above it. The fix is structural rather than procedural — mount the directory, reload on change, and a CI guard (`tests/test_infra_compose_templates.py`) that fails if any of the three compose files regresses to a single-file mount.

## Suggested next steps

*(All discharged — see `## Resolution`. These are the four items this section actually held when the topic was archived; an earlier rewrite substituted a different list under a claim of being verbatim, which is corrected here. The detection gap is [[T0110]], closed in the same branch.)*

- ~~*(ATTENDED, manual — the NAS)* move `config.alloy` into `conf/` and recreate the container by hand~~ — **superseded**: the NAS is Ansible-converged after all (`roles/nas/tasks/main.yml` deploys both compose and config), so it converged like the other tiers on 2026-07-29 with `nas_apply_compose=true`. The "Container-Manager-managed" premise was wrong and had hidden a role/compose mismatch.
- ~~*(ATTENDED, one more OPS converge — for the STRUCTURAL fix)*~~ — done 2026-07-29, followed by `docker compose up -d`; mount is now `/etc/zcrypto-ops/alloy/conf`.
- ~~*(ATTENDED, at the next capture converge)* pass `capture_alloy_digest`, recreate Alloy, confirm the series~~ — done with [[T0107]]'s roll on both hosts; the recreate was load-bearing on each, host `fda087ea…` against container `e89f00d1…` on the primary.
- ~~*(autonomous, after that converge)* re-evaluate [[T0105]]'s trigger~~ — done: its venue half is armed as an alert, its paging half is dated.
