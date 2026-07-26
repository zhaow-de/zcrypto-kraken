# Attended reboots on the capture VPSes, and a transport for one-off timer metrics (spec 00071, T0027 + T0100)

**Goal.** Flip `unattended-upgrades` to `Automatic-Reboot "false"` on the two capture VPSes, and give the fleet's **one-off timers** a working metrics path — without which attended mode silently stretches the security-patch window.

**Scope.** `roles/base` (the flip), `roles/capture`'s Alloy config + a detector timer, `roles/engine`'s prune unit (a retro-fix), two alert rules, and the durable docs each of these makes stale. The ops node and the NAS keep auto-reboot and are untouched.

## The defect this spec exists to close

Spec `00069` moved **long-lived** services from node-exporter textfiles to `/metrics` endpoints Alloy scrapes. That was right, and the capture-host Alloy dropped its textfile collector accordingly — for a **contingent** reason, stated in `roles/capture/files/config.alloy:27-30`: *"there is no gate/replay/archive timer on them"*.

That premise has since expired, and the cost was paid before it was noticed:

- **A one-off has no process to scrape.** A daily timer runs for a second; `/metrics` cannot express it. Textfile is the correct transport for that class, which is exactly why the ops node still runs the collector for its four ephemeral timers.
- **T0021's journal prune (spec `00070`) shipped observable through nothing.** It was built to write a `.prom`, then deliberately made not to — on the reasoning that nobody would read it. The reasoning was sound and the conclusion was backwards: the fix is to add the reader. Worse, the fallback claimed in its place is also false — `config.alloy:161`'s journal keep-regex admits only `zcrypto-capture-prune.service` and Alloy's own stream, so the prune's log line reaches host journald and **is never shipped to Loki**.
- **T0027's recorded guideline assumed the transport already existed** ("No regex, no new plumbing"), naming a component (`integrations/unix`) from static-mode Grafana Agent that this flow-mode fleet does not use.

So this is one defect with three victims. It is registered as [[T0100]].

## D1 — Transport: the textfile collector, via the mount that already exists

**One-off timers publish a `.prom`; long-lived services publish `/metrics`.** That rule is now stated in the config itself so the next reader does not re-derive it from an expired premise.

The material simplification: Alloy already bind-mounts the host root read-only (`alloy-compose.yaml.j2:62`, `- /:/host/root:ro`). The textfile collector's `directory` is just a path it globs `*.prom` in — it has no relationship to `rootfs_path`. Pointing it at `/host/root/var/lib/zcrypto-node-textfile` therefore needs **no compose edit and no Alloy container recreate**: `config.alloy` is `copy:`'d and reloaded.

Rejected alternatives, with the reason each fails rather than a preference:

- **Publish from the capture daemon's `/metrics`.** The capture container mounts only `capture_data_dir`; it cannot see `/run/reboot-required`. Adding a mount means recreating the container carrying the unbackfillable L2 stream, for a housekeeping boolean — the exact hazard `capture-deploys.md` exists to prevent. It also cannot cover `zcrypto-red` via the engine, which is primary-only.
- **A Loki log-line alert.** Viable, and genuinely cheaper. Rejected because the level signal (a gauge you can look at, and alert on staleness) is worth the difference, and because the same converge has to touch the journal keep-regex anyway.
- **Probe from `zcrypto-ops`, which already has the transport.** There is no ops→capture path by construction: ops reads the NAS over `ro,soft` NFS, and the only capture-outbound channel is the NAS's `rrsync -ro` forced command. Building one means new credentials into the trade-adjacent host.

## D2 — The keep-list is an allow-list: publishing a metric does not make it visible

`config.alloy:132`'s `write_relabel_config` is an explicit `__name__` allow-list with **no `node_.*` wildcard**. A new series that is published but not admitted is dropped silently at the remote-write boundary — indistinguishable, from the dashboard, from a producer that never ran.

Every metric this spec introduces is therefore added to the allow-list **and** to `tests/test_infra_alloy_series.py`'s `CAPTURE_REQUIRED`, which fails until the regex is edited. Also admitted: `node_textfile_scrape_error`, which ops and nas already carry and the capture hosts omit — without it a malformed `.prom` is invisible.

## D3 — A stale `.prom` is not a scrape error, so freshness is its own gauge

`node_textfile_scrape_error` fires on a *malformed* file, never on a *stale* one: a timer that stops running leaves its last `.prom` in place, and the collector keeps serving those values forever. A metric that cannot go stale-detectably is worse than no metric — it reads as healthy.

Every `.prom` this spec produces therefore carries `_last_run_timestamp_seconds`, and every alert on it is written against that freshness, not only against the value. (T0021's prune script already emits this gauge; it was simply never wired to a reader.)

## D4 — The flip: a variable with a safe default, quoted

Three edits, one line changed and two added:

1. `roles/base/templates/50unattended-upgrades.j2` — the hardcoded `"true"` becomes `"{{ base_unattended_upgrades_automatic_reboot }}"`.
2. `roles/base/defaults/main.yml` — `base_unattended_upgrades_automatic_reboot: "true"`. Defaulting to the **current** behaviour is what leaves `zcrypto-ops` on auto-reboot with no host_vars edit anywhere.
3. `group_vars/capture_host/vars.yml` — `"false"`. That group is exactly `{zcrypto, zcrypto-red}`; the NAS never runs the base role at all.

**Both values are quoted YAML strings.** A bare `false` renders through Jinja as Python's `False`, emitting `Automatic-Reboot "False";` — accepted by apt as not-true by accident, and no test in the repo would catch it.

Deliberately **not** touched: `Automatic-Reboot-WithUsers` (inert on capture, live on ops) and `Automatic-Reboot-Time` (inert once the flip lands, but it keeps the on-host file readable as human scheduling guidance, and the fleet-collision assert at `roles/base/tasks/main.yml:11-28` reads `base_unattended_upgrades_reboot_time` out of `hostvars` and fails the whole fleet closed if it is `UNDECLARED`).

The base role has **no `handlers/` directory and zero `notify:` in any task** — verified by grep, not assumed — so the flip restarts nothing. Its one service task is `state: started`, not `restarted`.

## D5 — Ordering: the flip lands before the detector is ever tested

T0027's recorded verification is "touching and removing the flag file on one host". While `Automatic-Reboot "true"` is still in effect, a touched `/run/reboot-required` is **precisely the condition unattended-upgrades acts on** — the next daily run would reboot the live capture + engine primary at 21:25.

So: converge `--tags base`, verify on-host that the rendered file reads `"false"` on both capture hosts, and only then deploy and exercise the detector. This ordering is not a preference; the reverse order can reboot production.

Two further converge hazards, both silent-on-failure:

- `--tags capture` **must** carry `-e capture_alloy_digest=<currently running>`. The Alloy block is gated on that variable; without it the whole block skips and `config.alloy` never lands — a converge that reports success and changes nothing.
- `-e converge_primary=true` is still required on the primary even for `--tags base`, because `site.yml:41`'s refusal assert carries `tags: [always]`.

## D6 — Alert shape

Two rules, both `receiver: metrics` → Slack, `severity: warning`, `execErrState: Alerting`, and **`noDataState: OK`**. `OK` because the existing `zcrypto-alloy-dark-capture-*` canaries already own "this host went silent"; alerting on no-data here would double-page one fault (the precedent is stated verbatim at `alerts.yaml:78-80`).

1. **Reboot pending** — `node_reboot_required == 1`, per host. Fires until the human reboots; that persistence is the point of attended mode.
2. **Prune liveness** — the journal prune's `_last_run_timestamp_seconds` older than ~26 h, i.e. D3's staleness made actionable. This is the alert whose absence made T0021's gap invisible.

## D7 — Scheduling and ordering stay human guidance

Unchanged from T0027's 2026-07-23 ruling and restated here because the flip makes the reboot-time values inert: traffic trough, ≥1 h off any 4 h bar boundary, ≥1 h host separation, engine host right after a completed cycle. **Attended mode inverts spec `00050`'s primary-first order** — that ordering was unattended paging logic; attended, with both hosts taking the same kernel, canary logic wins: **secondary first, verify it boots and captures, then primary.**

## Out of scope

- The mid-order-submission reboot reconciliation test ([[T0018]]) — a 6b requirement, still open, unaffected by this.
- The attended-reboot **skill** as a sibling of [[T0081]]/[[T0084]] — deferred to when the skill family is built; T0027 keeps that next-step.
- Retro-fitting `/metrics` to anything currently on textfile: the ops node's four timers are one-offs and stay on textfile by D1's rule.
