# Spec 00084 — the fleet's presentation layer: dashboards, notification templates, and the two alerting holes (T0020)

Resolves [[T0020]] in full. The telemetry layer is complete — spec `00043` built the transport, spec `00069` shipped the app-level `/metrics` families fleet-wide — and this iteration builds the layer that makes it *readable*: what an operator sees on a dashboard, and what a firing alert says on a phone.

## Goal

Every metric family that can page you is visible on a dashboard, every alert points at the panel that shows it, and the Slack message is legible without opening Grafana.

## The gap this closes, measured

The committed dashboards chart **18** metric families. The alert rules fire on **40**. Roughly **32 families page an alert with no graph anywhere** — including the entire continuity verify-replay sweep (11 families, four of them paging critical), all 13 capture families, and all 8 engine families. An operator paged at 03:00 currently has nowhere to look.

Two defects and one blind spot were found while scoping, all confirmed against the tree:

- **Three of the four `NAS ·` panels are not NAS panels.** `NAS · Load (1m)` selects bare `node_load1`, `NAS · Memory Available %` selects bare `node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes`, and `NAS · Network IO` selects bare `rate(node_network_*_bytes_total[5m])` — none carries a `host` matcher, so each silently became a five-host panel under a one-host title when the rest of the fleet started publishing the same families. Only `/volume1 Free %` is accidentally correct, because the mountpoint name is Synology-specific.
- **The `zaccess` bridgehead is structurally invisible to its own collector-failure alert** (D10).
- **`zcrypto_capture_seconds_since_last_book_message` is watched by nothing** (D10), despite its own docstring naming it the staleness watchdog's proof-of-life signal.

## D1 — Four dashboards, split by who is asking; no product prefix in titles

| uid | title | question it answers |
| --- | --- | --- |
| `zcrypto-fleet` *(new)* | `Fleet health` | is any machine in the fleet unwell? |
| `zcrypto-integrity` *(new)* | `Data integrity` | is the data we are betting on sound? |
| `zcrypto-engine` *(new)* | `Engine` | what is the trading engine doing? |
| `zcrypto-logs` *(existing, reworked)* | `Logs` | what did it say? |

**All four boards carry `tags: []`** (owner's call, my judgement on the form): tags exist to filter a long board list, and four purpose-named boards in one folder are already the filter. The current values are actively wrong — `["zcrypto","gate","nas"]` on a board about to cover the whole fleet — and a corrected set would be maintenance surface with no reader. Purged rather than rewritten.

**Titles carry no `zcrypto` prefix** (owner's call): the Grafana instance and the `zcrypto` folder already establish it, so the prefix is noise repeated on every board. **Titles are sentence case** — first word capitalised, the rest lower unless a proper noun.

**All three metric boards mint NEW uids; `zcrypto-main` is not reused** (owner's call). Reuse would have replaced the old board in place, but it also welds the new design to the old board's identity — every link, bookmark and future prune decision inherits a uid whose name (`main`) no longer describes anything. Three purpose-named uids are worth one cleanup step.

**That cleanup step is the owner's, because the tooling cannot do it.** `grafana-push.sh`'s prune path (`GRAFANA_PRUNE=1`) is scoped to `/api/v1/provisioning/alert-rules` in the alert folder — there is **no dashboard delete path in the script at all**, and the push upserts only. So `zcrypto-main` ("zcrypto — Data Pipeline Health") stays live beside the new three until deleted by hand in the Grafana UI. **Closeout carries an explicit owner step to delete it**, and the closeout is the right moment: the new boards are verified live first, so the deletion is never the thing that leaves a gap. Adding a dashboard-prune path to the script is deliberately **out of scope** — dashboard deletion is irreversible from the repo, and the rules-prune precedent took a dry-run-by-default design and a named-uid confirmation that a one-off cleanup does not warrant.

**The engine board is named `Engine`, not "Engine — intent".** The intent-versus-execution distinction is a property of the *metric*, and belongs at panel and `/metrics` level, where it already lives: `zcrypto_engine_orders_total` is documented "Intended orders emitted", `zcrypto_engine_order_notional_eur` "Intended order notional". Naming the board for intent would be wrong the moment [[T0018]]'s executor emits execution families — which then join **this same board** as new panels — recorded in the cross-topic section below and in T0018 itself, so the handoff lives on the topic that owns making those families exist.

**All three metric boards enable Shared Crosshair** (`graphTooltip: 1` at dashboard level) — hovering one timeseries draws the cursor on every other panel at the same instant. Correlating a load spike against a scrape failure, or a desync against a gap, is the routine act on all three boards, and doing it by reading timestamps across panels is exactly the friction this iteration exists to remove. Not Shared Tooltip (`2`), which stacks every panel's values into one hover card and becomes unreadable at these panel counts.

## D2 — `Fleet health`

`uid zcrypto-fleet` (new), title `Fleet health`. Answers *is any machine in the fleet unwell?* — the node/process/scrape layer, the healthchecks.io aggregate, and the access tier. It owns 28 families and 20 of the 52 metric-backed rules — the denominator re-derived against the shipped `alerts.yaml`; the earlier 48 predated D11's new rules.

### Panel rules P1–P6 — binding on all three boards

These are the difference between a board that looks complete and one that works. Each was found by an adversarial review or by a paged-at-3am walkthrough of a rule that already exists.

**P1 — a panel serving a rule plots the RULE'S EXPRESSION, not the rule's family, divisor included.** `Reconciler · primary gap rate high` evaluates `increase(healable[24h])` *divided by the live *pair* count*; a panel plotting raw healable seconds reports 3.6 while the page says 0.9, and at 03:00 a panel that disagrees with the page costs more time than no panel. This is the governing principle behind most of the corrections below: where a rule aggregates (`min_over_time`, `sum`, `max by`, `changes`, `delta`), the panel carries that exact series, and any additional context series sits beside it clearly marked as context.

**P2 — a panel serving a rule encodes that rule's threshold as a marked `fieldConfig.thresholds.steps` value.** A timeseries reading 0.061 answers nothing without the page line drawn on it. Where two rules watch one family (the owner's low/high-watermark example), **both steps go on the one panel** — that is what family-level coverage means. Where one family's rules carry **different bars per host**, the steps are **per-host field overrides, never one shared ladder**: `node_load1` has three rules with three genuinely different true bars, and one ladder for all three is the review's critical fleet finding.

**P3 — a panel's description carries the rule's `for:` duration.** `Gate · cache re-verification stalled` is `for: 15m`, its siblings `for: 5m`, `Ops · verify-replay backlog stuck` is `for: 27h`. A value above the line right now does not mean a page is coming, and a page can arrive while the value has already fallen back. Cheap to write, and it prevents the "the dashboard is red but I got no page" confusion in both directions.

**P4 — every monotone counter gets its recent-delta companion, alerted or not — and the delta form must match the counter's actual semantics.** D7 already requires this for the alerted damage counters; these five are the ones easy to miss because no rule forces the delta into existence:

| Family | Companion | Why this form |
| --- | --- | --- |
| `zcrypto_capture_gap_seconds_total{pair}` | `increase(…[24h])` | true monotone counter |
| `zcrypto_reconcile_trade_deficit_rows_total` | `increase(…[24h])` | true monotone counter |
| `zcrypto_trade_backfill_hours_repaired_after_loss_total` | `increase(…[24h])` | true monotone counter — the emitter reads its own previous value and adds |
| `ops_verify_replay_audit_mismatches` | `delta(…[25h])` | **not a counter**: a gauge carried forward from the last sweep that reported one, so `increase()` reads it as flat forever. 25h and `delta` are the idiom the sibling `failed_hours` rule already uses |
| `zcrypto_gate_cache_invalidated` | `max_over_time(…[24h])` | **not a counter**: a per-run 0/1 flag, so "did it happen at all in the last day" is the only meaningful window read |

**P5 — legends disambiguate the publisher, not just the host.** `zcrypto_logship_*` is published by four daemons across three hosts, and on `zcrypto` **both** capture and the engine publish it — `{{host}}` alone is ambiguous on the one host that matters most, and `{{instance}}` is useless fleet-wide (every Alloy binds `127.0.0.1:12345`). Every logship and every `process_*` legend is `{{host}}/{{job}}`.

**P6 — every board carries a restart annotation.** A Grafana annotation query over `changes(process_start_time_seconds[5m]) > 0`, titled by `{{host}}/{{job}}`, puts a marker on every timeseries at the moment anything restarted. Several rules fire benignly during a converge (`dropping late event` after a capture restart is documented-healthy; `Fleet · Alloy dark` during an Alloy bounce; the log-dead canaries inside a restart window), and this turns *"real fault or did we just deploy?"* from an investigation into a glance. **Unavailable on `zaccess`** — its Alloy is a native deb with no self-scrape, so no `process_*` family is published or admitted there; the annotation is silent for that host by construction and the board says so.

### Template variables

| Variable | Query | Notes |
| --- | --- | --- |
| `$host` | **custom** variable, `Capture primary : zcrypto, Capture secondary : zcrypto-red, Ops : ops, NAS : nas, Edge : zaccess`, multi, includeAll (supersedes the query form — see D6's naming section; a query variable cannot carry display labels) | Two stray `host` label values exist on the fleet — `primary` and `secondary`, root-caused below — and a bare `label_values(host)` (the natural thing to write) offers both in the dropdown. Metric-scoping to `up` excludes them today; the regex is belt-and-braces against the next family that carries its own `host` label. **`allValue` must be left EMPTY** so `All` interpolates to the pinned option list joined by `\|` — setting it to `.*` re-admits exactly the two values the regex just removed. The regex is anchored: Grafana applies it unanchored, so `zcrypto` alone would also match `zcrypto-red`. This variable is a second place that must be edited when a host joins the fleet. |
| `$daemon_host` | `label_values(process_resident_memory_bytes, host)`, same regex | Drives the repeat of the per-host RSS panel. Derived from the family itself, not from `$host`: `zaccess` publishes no `process_*` at all, so a `$host`-driven repeat renders an empty tile indistinguishable from a quiet daemon. Resolves to **four** hosts — `nas`, `ops`, `zcrypto`, `zcrypto-red` — and the NAS tile shows **Alloy's own** process, not an app daemon. |

The `primary` / `secondary` strays are root-caused (high confidence, one emitter, exactly two series): `cli/archive/command.py` emits `zcrypto_reconcile_trade_deficit_rows_total` with its **own** `host` label carrying a mirror *side*, and `external_labels` only stamps a label that is absent — so `host="ops"` is never applied to that family. Spec-level consequence is D3's selector, below; the mislabelling itself stays out of scope (renaming it changes series identity under an `increase()`).

### Rows and panels

| Row | Panel | What it answers | Rules it serves |
| --- | --- | --- | --- |
| Fleet at a glance | Alloy up — per host | Is each host's Alloy shipping anything at all? Five literal `count(up{host="…"}) or on() vector(0)` targets, one per host — **not** `$host`, because a regex selector cannot render a host whose series have vanished entirely | the five `Fleet · Alloy dark — …` rules |
| | Host vitals (now) | Which of the five machines is unwell right now — one row per host, instant queries joined on `host` | — (context; the load and disk page lines live on their own panels, per P2) |
| | healthchecks.io — checks down | Are any dead-man checks down, and is the hc.io scrape itself alive? Carries the rule's own `or on() vector(999)` so an unreachable endpoint shows 999 rather than going blank | `Fleet · healthchecks.io watchdog (check down, or hc.io dark)` |
| | healthchecks.io — per check | **WHICH** check is down — `hc_check_up{host="ops"}` as an instant table so every label column renders without guessing hc.io's label names | — (sits beside the aggregate above; closes the "log into healthchecks.io to find out which" gap) |
| Load, CPU & memory | Node load — each host against its own bar | Is a host saturated *by the standard its own rule uses* | `NAS · load high`, `Ops · node load high`, `Capture · node load high` |
| | Load per core (context) | Cross-host comparison on one normalised axis | — (**no page line**; see the correction below) |
| | CPU busy / iowait / steal | Is high load real CPU work, blocked IO, or hypervisor steal — three different fixes | — |
| | Memory available / free % | Is any host approaching OOM before it takes a capture daemon down | — (no rule watches any `node_memory_*` family fleet-wide; this panel is the only coverage) |
| Storage & network | Filesystem free % by mountpoint | Which mountpoint on which host is filling, and how fast | `Capture · spool disk low`, `NAS · /volume1 free space low`, `Access · bridgehead disk high` |
| | Filesystem headroom (bytes) | How many GiB before the capture daemon's own 1 GiB watermark starts discarding unbackfillable L2 | — (the 1 GiB step is the **daemon's** watermark, not an `alerts.yaml` bar) |
| | NAS inode headroom | Millions of small parquet segments exhaust inodes long before bytes; NAS-only families | — |
| | Network IO (excl. lo) | Is a link saturated or has it gone silent, and on which NIC | — |
| Scrape & collector health | Scrape targets up | Which individual scrape target stopped answering before the whole host goes dark; `unless up{job="engine_app", host="zcrypto-red"}` removes the permanently-0 series that is 0 by design | — (context; the Alloy-dark pointers live on the glance stat) |
| | node-exporter collector success | Is a collector failing, so its whole family is absent and every rule keyed on it evaluates NoData → OK, i.e. silently disarmed | `Node · a node-exporter collector is failing` |
| | Collector scrape duration | Is the exporter itself becoming the problem as a filesystem walk creeps toward the 60 s scrape interval | — |
| One-off timers & textfile freshness | Textfile age — did the timer run (capture) | Has a one-off timer stopped writing its `.prom`, freezing every gauge it publishes at a healthy-looking last value | `Capture · reboot probe is stale`, `Capture · daily one-off timer stopped publishing` |
| | Textfile collector parse errors | Is a `.prom` unreadable or malformed — the mode-0600-from-mktemp mistake makes a whole metric set vanish while everything else stays green | `Capture · node-exporter textfile unreadable or malformed` |
| | Reboot pending & probe presence | Does either capture host need its attended reboot — **and** is the probe that answers that still publishing on BOTH hosts | `Capture · reboot pending (attended)`, `Capture · a one-off timer stopped publishing entirely` |
| Daemon processes | Daemon memory — `$daemon_host` (RSS & VSZ) | Is a daemon's memory climbing against **that host's own** history — `repeat: daemon_host`, so the forbidden cross-host comparison has no shared axis to happen on | — |
| | Capture RSS growth per day | Is capture RSS actually trending up — a growth *rate* is the one leak form legitimately comparable across two hosts with different ceilings | — |
| | Open file descriptors (% of limit) | Is a daemon leaking sockets toward its own limit after a reconnect storm | — |
| | Daemon CPU (cores) | Is one daemon spinning — a wedged retry loop pins one core and is invisible in a 24-thread box's load average | — |
| | Daemon uptime (since last restart) | Did a daemon restart — the single fact that explains a counter that reset to zero | — |
| Access tier | WireGuard handshake age (both ends) | Is the ops↔zaccess tunnel alive, and **which end** lost it | `Access · WireGuard tunnel stale` (as corrected in D11) |
| | Edge TLS — time to expiry | How long until **each** tracked certificate expires, per vhost | `Access · edge cert expiring` (as corrected in D11) |

Every expression carries either a literal `host=` matcher or `$host` (D6). Where a family is **not admitted** on a host, the panel carries an explicit exclusion matcher rather than relying on the series simply being absent — `host!="zaccess"` on `node_memory_MemFree_bytes`, `node_filesystem_free_bytes`, both collector families and all `process_*` panels; literal `host="nas"` on the inode panel; literal `host=~"zcrypto|zcrypto-red"` on `node_reboot_required` and the textfile-age panel. **An exclusion written into the expression is auditable; an empty series is not.**

Two expressions are quoted because the expression itself is the decision.

**The load panel — three series, three per-host threshold overrides, one panel:**

```promql
node_load1{host=~"zcrypto|zcrypto-red"} / on(host) group_left() count by (host) (node_cpu_seconds_total{host=~"zcrypto|zcrypto-red", mode="idle"})   # step 1.5
node_load1{host="nas"}                                                                                                                             # step 4
node_load1{host="ops"}                                                                                                                             # step 20
```

**The collector panel — the second series is what makes a missing host visible:**

```promql
min by (host) (node_scrape_collector_success{host=~"$host", host!="zaccess"})
node_scrape_collector_success{host=~"$host", host!="zaccess"} == 0                      # names the failing collector
count by (host) (node_scrape_collector_success{host=~"$host", host!="zaccess"})         # a host that DISAPPEARS is visible
```

`node_scrape_collector_success` is absent from the access keep-regex, so `min by (host)(…)` returns four hosts and never five: a panel showing four green hosts reads as a healthy fleet. Until D10(a)'s converge lands, the `count by (host)` companion series and a description naming `zaccess` as **structurally excluded** are mandatory — *a blind spot rendered as green is the failure class this spec exists to close.* When the converge lands, drop `host!="zaccess"` from the **success** panel only. The **duration** panel keeps its exclusion permanently: D10(a) admits `node_scrape_collector_success` and nothing else, so `node_scrape_collector_duration_seconds` stays unadmitted on that host forever, and dropping its matcher would recreate the unmarked-empty-series class this very rule exists to prevent.

**Corrections applied from review:**

- **(critical) One load ladder cannot serve three hosts.** The proposed shared per-core ladder (green <1.0) reads GREEN across the whole band where `Ops · node load high` has already fired — `node_load1{host="ops"} > 20` on a 24-thread box is 0.833/core, *below* the ladder's first step. Fixed by P2: the panel plots each rule's own expression as its own series with its own marked step, and the normalised per-core view survives as a separate, explicitly page-line-free context panel.
- **(important) The textfile-age panel applied capture-only thresholds to ops and access.** `node_textfile_mtime_seconds` is referenced in `alerts.yaml` only under `host=~"zcrypto|zcrypto-red"`; the ops timers are governed by entirely different families with different bars (3 h dead-man, 48 h), and access has no governing rule at all. Panel is now scoped `host=~"zcrypto|zcrypto-red"`, matching what it claims to serve; ops timer freshness lives on `Data integrity` under its own families.
- **(important) `topk(5, …)` without a grouping clause** reduces over the entire matched vector, so at `$host = All` it returns the five globally-largest series — possibly all from one host — and silently hides every other host's collectors. Corrected to `topk by (host) (5, …)`.
- **(minor) `Capture · spool disk low` dropped** from the byte-headroom panel's rule list: that rule's bar is a percentage and is already correctly served by the free-% panel; the byte panel's 1 GiB step is the capture daemon's own watermark, which appears nowhere in `alerts.yaml`.
- **(minor) `zaccess` gets its own 0.15 red step** on the free-% panel via a field override — the same single-ladder-for-multiple-bars class as the load finding, milder only because orange still reads as attention.
- **(minor) `$daemon_host` resolves to four hosts, not three**, and the NAS tile renders Alloy's own process; both stated in the panel description and the layout note.
- **Two panels moved off this board.** The proposed "NAS timer substitute — gate export age" belongs to `Data integrity`'s gate row (it is a gate family and `Gate · exporter stale` points there); the two log-shipping panels move to `Data integrity`'s telemetry-integrity row. Rationale for the split is in D3.
- **Pointer ownership de-duplicated.** Where two panels could serve one rule, the `__panelId__` goes to the panel plotting the rule's expression (P1) and the other is marked context — Alloy-dark to the glance stat, not to "Scrape targets up"; the spool-disk pointer to `Fleet health`, not to `Data integrity`'s spool tile.

**Superseded panels.** `zcrypto-main`'s `NAS · Load (1m)`, `NAS · Memory Available %` and `NAS · Network IO` are host-unfiltered and plot five hosts under a one-host title; their scoped equivalents are this board's load, memory and network panels. `NAS · /volume1 Free %` is accidentally correct (Synology-specific mountpoint) and is likewise superseded by "Filesystem free % by mountpoint". None of the four *disappears* on push: `zcrypto-main` keeps its own uid and stays live until the owner deletes it at closeout (D1). That is the safer order — the broken-but-familiar board remains readable while the new three are verified — but it means the fleet briefly carries **two** answers to the same question, so the three new boards must land in the **same push** and the closeout deletion must not be skipped.

## D3 — `Data integrity`

`uid zcrypto-integrity` (new — D1), title `Data integrity`. Answers *is the data we are betting on sound?* — the unbackfillable capture edge, the reconciler, the continuity sweep, the canonical writers, the admission gate, and the telemetry path that carries all of it. It owns 68 families and 29 of the 52 metric-backed rules — both counts re-derived against the shipped board; the earlier 66/27 predated the two capture staleness rules D11 adds. P1–P6 bind here.

### Template variables

| Variable | Query | Notes |
| --- | --- | --- |
| `$capture_host` | **custom** variable, `Capture primary : zcrypto, Capture secondary : zcrypto-red`, multi, includeAll, default All (supersedes the `label_values(zcrypto_capture_book_desynced, host)` query form — see D6's naming section; a query variable cannot carry display labels) | Resolves to exactly the two capture hosts because they are the family's only publishers. Default All is deliberate: a fault on one host and not the other **is** the diagnosis. D6's goal (1) — a Linux hostname is never visible on an operator surface — bites on exactly `zcrypto` and `zcrypto-red`, and those are precisely this dropdown's two values, so the query form and that goal are mutually exclusive; the option list is also a *stronger* pin than the regex it replaces, since it cannot admit a stray value at all. Cost, same as D2's: a second place to edit if a third capture host ever joins. |
| `$pair` | `label_values(zcrypto_capture_book_desynced{host=~"$capture_host"}, pair)`, multi, includeAll, default All | Chained, so deselecting a host drops its pairs. At 12 pairs × 2 hosts the All view is legible; narrowing is for chasing one stuck stream. |
| `$logship_host` | `label_values(zcrypto_logship_last_cycle_timestamp_seconds, host)`, multi, includeAll | Scopes the three telemetry-integrity panels only. Named for its scope rather than `host`: a variable called `host` that governs three of thirty panels is a trap. Derived from a logship family so its domain is exactly the hosts that run a shipping worker. |

`allValue` is empty on all three (the D2 reasoning applies unchanged).

### Rows and panels

| Row | Panel | What it answers | Rules it serves |
| --- | --- | --- | --- |
| capture — live ingest | Book desync — live and stuck (15m) | Which pair's book is checksum-desynced now, and whether the daemon's single fire-and-forget resubscribe took or the pair is in the shape that pages | `Capture · book desync stuck on a pair` |
| | Seconds since last book message (per pair) | Per-pair proof of life: which stream has gone quiet and for how long, while it is still a live condition rather than a ledger entry booked hours later | the two new capture staleness rules (D11) |
| | Recovery ladder — 24h increase | Is the desync recovery path being exercised more than it should be, and are its attempts succeeding | `Capture · book resubscribe rate re-elevating`, `Capture · book resubscribe is failing (recovery degraded)` |
| | Book silence — gap seconds per pair (24h increase) | Which pair contributed how much book silence in the last day — the capture-side origin of every healable and residual second booked downstream | — |
| | Rows held vs quarantined (6h increase) | Did rows arrive after their hour was finalized and get spilled out of the canonical tree | `Capture · rows quarantined to .held` |
| | Capture counters — cumulative since process start | How much damage each host has taken over its whole life — **all-green, every step removed**, so scale reads here and recency reads in the delta panels beside it | — |
| | Spool free % (root filesystem) | How much runway the unbackfillable spool has before the prune ring must be fixed | — (context; the rule pointer is on `Fleet health`) |
| | Hard stops — disk watermark & venue status | The two conditions under which capture is no longer trustworthy at the source | `Capture · disk watermark breached -- DISCARDING data`, `Capture · Kraken reports the venue is not online` |
| | Segments written & bytes (1h increase) | Is the writer still committing hourly segments at normal size while the process stays up and keeps pinging | — |
| reconcile | Mirror lag by source & reconciler liveness | Are both mirrors still producing, and is the reconciler that compares them still running | `Reconciler · capture mirror lagging`, `Reconciler · exporter stale` |
| | Gap outcome — last 24h | Did loss and healing pressure happen **in the last day** — the panel that answers "is the red number new?" without leaving the board | `Reconciler · residual gap increased (permanent loss)`, `Reconciler · primary gap rate high (degrading host)` |
| | Gap totals — cumulative since ledger genesis | Lifetime scale in each of the three outcomes — **all-green, no steps**, description leading with "a number here is history, not an incident" | — |
| | Reconcile output — hours minted (24h) | Is the healer actually writing hours into the overlay, which separates "nothing was broken" from "the healing step is not running" | — |
| | Trade reconciliation — deficit & dedup rows (24h) | How many trade rows each mirror was missing that the other had — the only measure of whether the two trade streams are genuinely redundant | — |
| continuity | Verify-replay — run verdict | Did the sweep complete at all — a crash, an EIO, or a NAS mount that silently resolved empty all present as `run_ok 0` while every count below stays frozen | `Ops · verify-replay run broken` |
| | Verify-replay — freshness (last run vs last clean run) | Is the daily sweep still firing at all, separately from whether its runs come back clean | — (no rule watches verify-replay staleness; dashboard-only coverage, and the description says so) |
| | Verify-replay — hour ledger | Where every canonical hour sits, and whether total still balances against replayed + reused + pending | — (context for the panel below) |
| | Verify-replay — new breakage & backlog drift | Did a NEW hour break, or has the backlog stopped draining — as opposed to a failed count carried forward unchanged for weeks | `Ops · verify-replay NEW hours stopped replaying`, `Ops · verify-replay backlog stuck` |
| | Verify-replay — audit mismatches & sweep duration | Does the checkpoint the sweep reuses hours from still agree with a fresh replay — the only signal that a "reused" hour is verified rather than skipped | — |
| canonical writers | Job exit codes | Did each of the four canonical-tree writers come back clean on its last pass | `Ops · archive-pull non-zero exit`, `Ops · verified-replay non-zero exit`, `Ops · panel non-zero exit`, `Trade backfill · non-zero exit code` |
| | Job last-success age | How long since each writer last completed cleanly, against the exact budget its own rule uses | `Ops · archive-pull stalled (dead-man)`, `Ops · verified-replay stale`, `Trade backfill · last success stale` |
| | Did it run at all? — last-run age | Separates a timer that stopped firing from a job that fires and fails — the sawtooth is the signal, a rising ramp is the fault | — |
| | Verified-path lag & trade repairs | How far the verified path has fallen behind, and whether trade hours are being repaired **now** or merely were at some point | — |
| gate | Gate verdict | Does the fleet currently satisfy its own admission gate, and how long has it held | — (headline; the mismatch pointer is on the trend panel, per P1) |
| | Streak & mismatch trend | Is the streak climbing or was it reset, and is the mismatch behind it recent or ancient | `Gate · streak reset`, `Gate · mismatch in the last day` |
| | Exporter freshness, duration & journal pull lag | Is the verdict on screen fresh, is the journal it was computed from current, and **is a slow export still running or did it die** | `Gate · exporter stale`, `Gate · journal pull lag high` |
| | Scoring cache — is the journal still being re-hashed? | Is the rotating re-verification still hashing parquet bytes — a stalled cache is indistinguishable from a healthy one everywhere except these four numbers | `Gate · cache re-verification stalled` |
| telemetry integrity | Log shipping — dropped vs shipped (6h) | Was any log line discarded before Loki — the one fault that makes every Loki-based alert's silence meaningless | `Logs · lines dropped before reaching Loki` |
| | Log shipping — worker liveness | Is the shipper alive — read cycle age for that, and read a stale last-ship age only together with the shipped-lines count beside it | `Logs · the shipping worker has stopped cycling` |
| | Liquidations poller | Is the Coinalyze poller still landing cycles, and has any outage exceeded the 30 h window the next cycle would re-fetch for free | — (no rule watches any liquidations family) |

**Log shipping is owned here, not by `Fleet health`.** A dropped log line is data loss in the telemetry domain — the one fault that makes every Loki-based alert's *silence* meaningless — and that is a data-integrity question, not a host-health one.

**The liveness panel follows [[T0106]]'s resolution rather than re-litigating it.** That topic is **resolved and archived**: it did not document the false red as a caveat, it *replaced the signal*. `zcrypto_logship_last_cycle_timestamp_seconds` became the liveness gauge (0 s on a healthy host), and `_last_success_timestamp_seconds` was demoted to corroboration and explicitly marked **not** a fault signal — because the worker skips the post on an empty buffer, so on a healthy quiet host the two read 0 s and 39 min at the same instant, as the closing bake measured. The panel therefore **leads with cycle age**, carries the page line only there (matching `Logs · the shipping worker has stopped cycling`, which reads that gauge), and renders last-ship age as an unthresholded context series beside `shipped_lines_total`. Reintroducing a threshold on last-ship age would rebuild the exact false red a shipped fix already removed.

Both panels' legends are `{{host}}/{{job}}` (P5) — on `zcrypto` capture and the engine both publish this family, and the rules themselves need no change: neither aggregates, so Grafana already produces one alert instance per `(host, job)` with the labels intact.

Four expressions are quoted because the expression itself is the decision.

**The residual-gap series reproduces the rule's FULL expression, `resets()` guard included:**

```promql
(increase(zcrypto_reconcile_residual_gap_seconds_total{host="ops"}[24h]) > 0
   and resets(zcrypto_reconcile_residual_gap_seconds_total{host="ops"}[24h]) == 0)
 or on() vector(0)
```

**The per-desynced-pair rate reproduces the divisor, and the divisor stays UNSCOPED exactly as the rule has it:**

```promql
((increase(zcrypto_reconcile_healable_gap_seconds_total{host="ops"}[24h]) > 0
    and resets(zcrypto_reconcile_healable_gap_seconds_total{host="ops"}[24h]) == 0)
  or on() vector(0))
/ scalar(count(count by (pair) (zcrypto_capture_book_desynced)) or vector(1))
```

Adding `{host="ops"}` to the healable references does not change the computed value — that family is published only by ops — and D6 requires the explicit scope. The **divisor is deliberately left as the rule writes it**: scoping it would silently make the panel disagree with the page whenever the two capture hosts' pair sets differ, which is exactly the state a pair-add creates for one converge window. A second series plots the divisor itself. **Label it the live pair count, not the desynced-pair count**: `zcrypto_capture_book_desynced` is emitted for every pair on every scrape (0 or 1), so `count(count by (pair)(…))` is the *full* pair count — 12 today, constant except across a pair-add. That is exactly what makes the unscoped divisor safe, and a description calling a flat 12 "desynced pairs" would alarm a reader for no reason.

**The resubscribe-failure series is the alert's SUM, not the two counters separately:**

```promql
sum(increase(zcrypto_capture_resubscribe_errors_total{host=~"$capture_host"}[1d])
  + increase(zcrypto_capture_resubscribe_ack_timeouts_total{host=~"$capture_host"}[1d]))   # step 1.5
increase(zcrypto_capture_resubscribes_total{host=~"$capture_host"}[1d])                    # step 1.5
increase(zcrypto_capture_reconnects_total{host=~"$capture_host"}[1d])                      # NO step — nothing pages on it
```

**The trade-deficit selector is a mirror SIDE, not a fleet host:**

```promql
increase(zcrypto_reconcile_trade_deficit_rows_total{host=~"primary|secondary"}[24h])
```

`{host="ops"}` renders this panel empty — the emitter writes its own `host` label and `external_labels` never overwrites it. The panel description must say so, or the next reader "fixes" it to `host="ops"` and silently blanks it.

### The carried rider — [[T0044]]'s `zcrypto_reconcile_ledger_records` gauge

**This iteration carries T0044, and the memo is the authority that says so** (owner's ruling, 2026-07-27): the dependency had lived only inside T0044's own prose, which meant this item could be scoped and executed without anyone noticing it owed a rider. It is pulled in here because **it has no other carrier** — ship without it and T0044 returns to waiting on a human ledger correction that may never come.

**The shape is a gauge, not the counter the topic file proposes.** `zcrypto_reconcile_ledger_records` — the number of records `_totals()` summed on this cycle. The `corrections_total` counter T0044's own text suggests is the weaker design: it explains a reset only when someone remembers to bump it, whereas the record count explains **every** reset, including the silent empty-ledger path where the file is truncated or unreadable and every derived counter drops to zero with nothing marking why. The counters it explains sit behind the system's highest-severity alert.

- **Emit:** one more `_emit(...)` call in `cli/archive/command.py`'s `_write_textfile`, valued from the ledger scan `_totals()` already performs — no second read.
- **Keep-list:** nothing to change; the ops regex admits `zcrypto_reconcile_.*` as a wildcard.
- **Panel:** a second series on the reconcile row's "Gap totals — cumulative since ledger genesis", which is the panel whose discontinuities it exists to explain. **This is why it belongs on this board rather than anywhere else**: D7 gives the residual and healable panels the alert rule's own `resets(...[24h]) == 0` guard, so after a correction those panels correctly read zero — correct, and it also makes the correction *invisible*. The record count is the line that makes it legible again.
- **No rule.** A record count crossing a threshold means nothing on its own; it is an explanatory series read beside a discontinuity, not a page.

**Per-pair write counts do not exist, and the board says so.** `zcrypto_capture_segments_written_total`, `_segment_bytes_total`, `_rows_held_total` and `_rows_quarantined_total` are **unlabeled scalars**, summed across every pair and kind at the producer. So "the primary wrote 12 segments and the secondary 9" is visible and "which three pairs" is not. The only per-pair discriminators that exist are `zcrypto_capture_gap_seconds_total{pair}`, `zcrypto_capture_seconds_since_last_book_message{pair}` and `zcrypto_capture_book_desynced{pair}`. Consequence for layout: **"Mirror lag by source" is the first panel of the reconcile row, immediately after the capture row's per-pair staleness panel**, so the responder to `Reconciler · capture mirror lagging` lands next to the only per-pair evidence there is — and both panel descriptions state plainly that a per-pair write count cannot be built, so nobody hunts for a panel that does not exist.

**Corrections applied from review:**

- **(critical) The residual-gap panel used a bare `increase(…[24h])`.** The real rule carries `and resets(…[24h]) == 0` precisely so a deliberate ledger correction — the documented 2026-07-14 `6261.8 → 2661.8 s` purge — is not read as fresh permanent loss: Prometheus reads that decrease as a counter reset and a bare `increase()` reports the whole post-reset value as new loss. A panel without the guard reintroduces that exact false-alarm class **in the opposite direction**: it paints "PERMANENT LOSS" bright red at the very moment the rule, hardened against this, stays silent. The panel now reproduces the rule's full expression, matching what the healable-rate series in the same panel already did correctly.
- **(important) Resubscribe thresholds were per-series where the rule sums.** `Capture · book resubscribe is failing` evaluates `sum(increase(errors[1d]) + increase(ack_timeouts[1d])) > 1.5`; at errors=1 and ack_timeouts=1 the proposed panel read all-green while the rule fired. The summed series is now a first-class target carrying the 1.5 step (P1).
- **(important) `zcrypto_capture_reconnects_total` carried a "page line" it does not have** — no rule in `alerts.yaml` watches it. Step removed; the panel description names it as context.
- **(important) The per-pair gap panel claimed the reconciler's 600 s bar.** That number is computed on a different metric entirely — an ops-side aggregate divided by the live pair count — and applying it to one pair's raw counter is not "the same evaluator at the source". The 600 s red step is dropped. The 30 s step stays and is now sourced correctly: it is `BOOK_STALENESS_SECONDS`, the daemon's own derived silence bar (~2.4× the thinnest leg's worst natural spacing of 12.3 s), which deliberately equals the reconciler's `--min-gap-seconds`.
- **(important) `ops_verify_replay_exit_code` was coloured red.** `alerts.yaml` records that exit-code alerting was **retired** because that gauge stays 1 forever once any hour has ever failed, so it paged nightly for an already-triaged finding — superseded by the delta-based rule. Colouring it recreates the red-forever defect on a panel sitting beside the correct delta panel. Step removed; `run_ok` keeps the only red/green mapping in that panel.
- **(important) `zcrypto_gate_status` was coloured red for "NOT MET".** No rule reads that family — the rule that did was retired with an explicit note that `status == 0` is the **correct, expected** state for the whole ~14-day accumulation window. A red tile for twelve healthy days is the visual form of the same alarm fatigue. It is now informational: neutral background, text mapping only.
- **(important) `zcrypto_logship_dropped_lines_total` had a delta panel and no cumulative partner**, breaking D7 for the one counter whose delta panel was already correct. The raw cumulative value joins the telemetry-integrity row, all-green, as context.
- **(minor) The alert-expression series was the one unscoped expression** in an otherwise fully host-scoped board; `{host="ops"}` added to the healable references, and the divisor deliberately left as the rule writes it (above).
- **Ownership moved in:** log shipping and the gate export-age view arrive from the `Fleet health` draft; the spool-free tile stays but surrenders its rule pointer to `Fleet health` (P1 — that rule's expression is a percentage over `mountpoint="/"`, which the fleet panel plots for all hosts).
- **Empty-by-design series are documented, not left ambiguous:** `zcrypto_gate_cache_oldest_verification_age_seconds` is emitted only when the scoring cache is active and non-empty (its rule sets `noDataState: OK` for exactly this), and `zcrypto_logship_last_success_timestamp_seconds` is absent until the worker has completed one successful ship. Both panels carry a description saying an empty series is expected — otherwise the board reintroduces the ambiguity the whole exercise is about.

## D4 — `Engine`

`uid zcrypto-engine` (new), title **`Engine`** — not "Engine — intent" (D1). The intent-versus-execution distinction is a property of the metric and lives at panel and `/metrics` level, so [[T0018]]'s executed families join this same board without a rename. It owns 12 engine families plus two scoped second views (`up`, `node_textfile_mtime_seconds`), and serves one existing rule and two new ones. P1–P6 bind here.

**Panel titles must make intent unmistakable** — conflating an intended order with a fill on a trading dashboard is dangerous, so every intent panel carries "intended" in its title and the two counter panels say "decisions, not fills" outright.

### Template variables

| Variable | Query | Notes |
| --- | --- | --- |
| `$host` | **custom** variable, literal option list `zcrypto`, multi | Deliberately not `label_values(…)`: any query over an engine family empties out in exactly the incident where the engine is dark, blanking the whole board at once. A custom variable cannot fail, and its option list **is** the regex pin P1–P6 ask for elsewhere. Prometheus anchors regex matchers, so `host=~"zcrypto"` matches `zcrypto` and never `zcrypto-red`. `multi: true` so a second engine host is an options edit — but see the legend correction below: the presentation layer needs one edit too. |

The engine host is `zcrypto` alone by design: membership of that group grants the live Kraken trade key, so it is a security boundary, not a convenience. The capture role ships one `config.alloy` to both hosts and it scrapes `:9102` on both, so `up{job="engine_app", host="zcrypto-red"}` reads 0 permanently — pinning `$host` is what keeps that known-benign zero off every panel.

### Rows and panels

| Row | Panel | What it answers | Rules it serves |
| --- | --- | --- | --- |
| *(board head)* | **Intent only — realized state lives in the engine journal** (text) | What this board is **not**: there is no position family, no fill counter, no reject counter and no realized-PnL family anywhere in the codebase. States that `data/engine-journal` on the engine host is the **sole source of truth for realized state** | — |
| Cycle health | Last cycle age | How long since the engine last completed a cycle — the single glance that says whether the 4-hourly loop is still turning | `Engine · cycles have stopped` (D11) |
| | Last cycle outcome — absent is NOT failure | Did the most recent cycle succeed, fail, or has the engine not determined an outcome yet — **three distinct states rendered as three** | `Engine · the last cycle failed` (D11) |
| | Engine exporter scrape (`:9102`) | The absent-versus-dark discriminator that makes the two panels beside it readable: 1 = Alloy is scraping and a missing engine series is honest absence; 0 = Alloy is alive and the engine is not listening; blank = this host's Alloy stopped shipping and every panel here is blind | — (context) |
| | Cycle cadence — age sawtooth | Six teeth a day, each rising to at most 4 h 30 m then dropping — a missing tooth is a skipped boundary, an overtopping tooth is a late one, neither of which a point-in-time stat can show | — (context; the pointer is on the stat) |
| | Cycle duration — wall time per cycle | Is a cycle creeping toward the 25-minute refresh reserve and the 30-minute completion window — the leading indicator of the deadline failures that otherwise appear first as an unexplained failed cycle | — |
| Intent | Intended trade activity — last 24h (decisions, not fills) | Did we intend to trade today — the headline number for a shadow book | — |
| | Intended orders — cumulative & rolling 24h | Has the engine ever intended to trade, and is it intending to trade **now** | — |
| | Intended order notional — cumulative & rolling 24h | The euro weight of those intentions, so a day of many small rebalances is distinguishable from one large one | — |
| | Target weights by asset — INTENDED allocation (not held) | How the intended book is allocated and how that has moved — a stacked area makes an asset entering or leaving the target set legible as a band appearing or collapsing | — |
| | Target weights — latest cycle (intent snapshot) | Exactly which assets the last cycle targeted and at what weight — the view you read before touching anything | — |
| Composition | Active sleeves & composition changes (26h) | The alerted family, plotted **with the rule's own `changes(…[26h])` value** so the page and the panel show the same number | `Engine · sleeve composition changed` |
| | Sleeve gross — per sleeve (intended exposure) | **Which** sleeve moved — literally where that alert's summary sends the reader | — (the follow-up view; pointer is on the panel above, per P1) |
| | Book-level intent — net vs gross target weight | The quantitative consequence the alert warns about: a dormant sleeve re-arming roughly triples gross and invalidates the drift band, and this is the line on which that is measurable | — |
| Journal retention | Journal prune freshness — script clock vs textfile mtime | Is the daily prune still running, and do the script and the collector agree — the two normally track within seconds, and a gap between them means the script ran but its `.prom` was not written or not readable | — (context; `Fleet health`'s textfile panel owns the alert pointer) |
| | Journal retention — day-dirs kept vs deleted per run | Is the 60-day tail intact — a collapsing kept-count is the one housekeeping failure that changes what the engine **trades**, by turning the next cycle's deltas into a full-book rebuild | — |
| | Oldest retained journal day | Is the prune actually deleting, or only running — the age of the oldest surviving day-dir is the outcome measure where kept-days and last-run are process measures | — |

Every threshold **drawn** on this board is a repo constant, not a judgement: **16500 s** from the 4-hourly cadence (boundaries 00/04/08/12/16/20 UTC, completion inside `[B, B+30 min]`, so the worst healthy age is 16200 s), **1500 s** from the engine's 25-minute refresh reserve, **93600 s** copied verbatim from the daily-timer rule's own evaluator, and the **2-day-dir floor** from the point below which the cycle's delta derivation degenerates into a full-book rebuild.

**Three constants are named in panel descriptions but deliberately drawn as no line**, because a green/red palette has no honest colour for "normal". 16200 s and 1800 s are real repo constants describing the *healthy* worst case, not bars. And the journal-retention figures earlier given here as "60 and 63 days" were **drift**: the prune compares a strict cutoff against each day-dir's own ISO name, so the dir named exactly `today − retention` survives — steady state is **61** kept dirs, and the oldest day's age is 60 days *plus the hours since midnight*. Verified by running the prune against 200 fabricated day-dirs: `kept=61`, oldest survivor `today − 60`. A line at 60 days would paint a correct prune red, so the retention panels draw no upper bar and say why.

**Absence is never rendered as a value.** `zcrypto_engine_cycle_success`, `zcrypto_engine_active_sleeves` and — **as of this iteration's own engine fix** — `zcrypto_engine_cycle_duration_seconds` are *lazily* registered — deliberately left unpublished rather than shipped as a false `0` — so both panels take all their colour from **value mappings** with a neutral base step and an explicit `noValue` text. A thresholds-driven stat would paint that absence red, i.e. would invent exactly the claim the code refuses to publish. **The duration panel is included by this rule**: before the fix it published a false `0`, and after it publishes nothing until the first cycle completes — so a thresholds-driven "0 s" tile would re-invent, in the presentation layer, precisely the defect the code change just removed.

### Two source-level defects this board surfaced — fixed here, not deferred

Reading `_CycleGauges` closely enough to design these panels turned up two gauge-lifecycle defects. **Both are fixed in this iteration** (owner's ruling): a code-side defect gets fixed in the iteration that finds it, and the engine converge it costs is a bounded, known price — where a deferred fix hangs on a trigger nobody is driving toward and quietly becomes permanent. A panel description is a workaround, and shipping one *instead of* the fix would leave the board honest about a defect it had the means to remove.

- **A target weight persists at its last value until the engine process restarts.** The cycle gauges call `.labels(asset=…).set(…)` and never `.clear()` or `.remove()`, so an asset dropping out of the target set keeps publishing its last weight — the series neither zeroes nor goes absent, and both weight panels plus the book-level gross line over-report for the life of the process. **Fix:** track the label set written last cycle and `.remove()` the difference. *Remove*, not zero: a zero weight and a not-in-the-book asset are genuinely different states, and the executor will have to tell them apart.
- **`zcrypto_engine_cycle_duration_seconds` reads a false 0 after every restart.** Unlike its two siblings it is registered eagerly and never seeded, so it sits at the `prometheus_client` gauge default — a literal false value, not an absence — until the first cycle completes, rendering as a healthy green "the last cycle took 0 seconds" for up to a full 4-hourly gap. **Fix:** make it lazily registered, exactly as `cycle_success` already is. Seeding from the journal is the alternative and is rejected unless the artifact is confirmed to persist a duration — and lazy registration is the better answer regardless, because it is the pattern the same class already uses two lines away: the code refuses to publish a `cycle_success` it cannot justify, and should refuse a duration it cannot justify for the same reason.

Both are TDD-able against a fake registry with no live engine: assert a dropped asset's series is **gone** after the next cycle, and assert `cycle_duration` is **absent** rather than 0 before the first cycle of a fresh process. Neither can false-fire an existing rule — nothing reads either family today — so the change is safe to land ahead of the rules push.

**Operational cost, named:** this makes the iteration touch the **live trade host**. The engine converge follows `fleet-deploys.md` in full — inside a 4-hourly inter-cycle gap, digest recorded in `fleet-pins.md` first, the secondary's capture bake standing as the canary gate — and the panel descriptions ship **without** the two caveat sentences, because the defects will be gone.

**Corrections applied from review:**

- **(important) `zcrypto_engine_cycle_duration_seconds`' false zero was uncaught** by a design otherwise meticulous about this exact trap class. Rather than adding a caveat to the panel description, the defect itself is fixed in this iteration (above).
- **(important, ×2) Internal review vocabulary had leaked into panel description text** — "the constraint-4 pairing for order count…", "Family-level coverage for the one alerted engine family (constraint 3)…". `tests/test_internal_terms_not_operator_visible.py` walks dashboard JSON and these descriptions ship verbatim, so every such reference is rewritten in plain language: *"the recent-delta pairing for order count: the cumulative line answers 'has the engine ever intended to trade', the 24 h bars answer 'is it intending to trade now'"*. The rationale for a panel belongs in this spec; the panel says what it shows. Same scrub applies to the "gotcha (a)/(b)" phrasing in the two cycle-health stats.
- **(minor) `multi: true` overstated readiness.** The `{{asset}}`, `{{sleeve}}` and static journal legends carry no `{{host}}` component, so adding a second host would overlay two hosts' series under identical labels — two indistinguishable "BTC" lines. `{{host}}` is added to every legend now, while `$host` has one option and the change is free.
- **Title corrected to `Engine`** (D1), and the two overclaimed rule pointers dropped: the cycle panels claimed `Fleet · healthchecks.io watchdog` (a fleet-wide aggregate that cannot name which check is down) and the exporter tile claimed `Fleet · Alloy dark — capture primary` (which fires on series *presence*, not on this value). Both now point at the new engine rules in D11, which are the honest owners.
- **Journal-prune ownership settled here, not on `Fleet health`.** The families are the engine's own state and the panel's meaning — a collapsing kept-count changes what the engine trades — is an engine question. `node_textfile_mtime_seconds` remains owned by `Fleet health`, which carries both file slices with their own steps and therefore both textfile rule pointers; this board re-plots the prune file's slice beside the script's own clock as a deliberate second view.

**Gaps this board makes visible and cannot close.** There is no position, fill, reject, open-order, cash or realized-PnL family anywhere in `cli/` — the operator can see that the engine *wanted* to move and cannot see whether anything moved. That is a producer gap — distinct from the two lifecycle defects above, which this iteration fixes — and the board's head text panel is what stops a board titled `Engine` from implying a completeness it does not have. Those families arrive with [[T0018]]'s executor and join this board then. Separately, nothing alerts on the journal `kept_days` floor even though it is the one housekeeping metric that changes what the engine trades; visible here now, which is the precondition for a rule rather than a substitute for one.

## D5 — `Logs`: a rate lane at the top, and parsing at query time

The capture daemon's structured lines render as raw JSON. The cause recorded in the 2026-08-02 grooming — [[T0109]]'s single-file bind mount starving Alloy of its config — **is wrong**, and re-verified wrong on 2026-08-04:

- The capture daemon **does not ship through Alloy at all**. Spec `00068` D3/D6 gave it `--ship-logs`, pushing straight to Loki. The capture host's `loki.process "parse"` carries exactly one stage, a `stage.logfmt` for *Alloy's own* output, and its in-file comment says the docker log path that once carried the daemon's lines "is gone (D6)".
- What the daemon pushes is a JSON body by construction — `JsonLineFormatter` emits one object per record (`ts`, `level`, `logger`, `file`, `line`, `message`) — with labels `{host, container, level}` only.

So the lines bypass the only component that could parse them, and **no Alloy config change can reach them**. The fix is query-time in the panel's LogQL: `| json` plus a `line_format` promoting `message`. `level` is already a stream label, so filtering and colouring work today and are unaffected.

Rejected: reversing D3/D6 to route the daemon back through Alloy — heavier, and it re-opens a decision taken deliberately one spec ago.

### The rate lane — a short row above the viewer

**Eleven of the 63 rules point at this board, and today it cannot serve a single one of them.** Its only panel is a raw log *viewer*, so when the page is "no lines in 6 h", opening it shows an empty stream — which is precisely what the page already said. The board answers neither *when did it stop* nor *did it stop everywhere or on one container*.

A rate lane goes at the **top**, above the viewer, at **`h: 6`** (roughly a fifth of a 1080p viewport) — deliberately short, because the viewer stays the reason to open this board and the lane is orientation, not the destination:

| Panel | Query | What it answers |
| --- | --- | --- |
| Total lines/min | `sum(rate({host=~"$host", container=~"$container"}[5m])) * 60` | The single "is anything arriving at all" line — the transport canary, and the panel a `no lines in 6h` page lands on |
| Lines/min by level | `sum by (level) (rate({host=~"$host", container=~"$container", level=~".+"}[5m])) * 60` | Whether the mix shifted — an ERROR band appearing under a flat total is the signal a total-only view hides |
| Lines/min by host & container | `sum by (host, container) (rate({host=~"$host", container=~"$container"}[5m])) * 60` | **Which** stream went quiet — the question the split primary/secondary log-dead rules are asking |

Three properties the lane must have, each earned from a rule that already exists:

- **`level=~".+"` is the parse canary, and it is not the same series as the total.** Rules `Ops · unit log parse dead` and both `Capture · log pipeline dead` variants fire on the *parsed* count, while `Ops · journal transport dead` fires on the *raw* count. Plotting only one of them sends the responder to the wrong layer — a healthy transport with a broken parser looks identical to a dead transport on a total-only panel. Both series are therefore first-class, side by side.
- **Container names are asymmetric across hosts** — `archive-pull` on the NAS versus `zcrypto-archive-pull` on ops. A single `container=` selector is silently blank on one host. `$container` is a multi-select with `includeAll`, and the mismatch is stated in the panel description rather than hidden behind an `All` that appears to work.
- **A `rate()` of zero and an absent stream render identically.** So the by-host-and-container panel pairs with a small **"last line seen"** table (`max by (host, container) (max_over_time(…))` over a long window), which distinguishes a stream that has gone quiet from one that never existed. That distinction is the whole diagnostic value when a log-dead canary fires.

`Logs` keeps its existing uid and takes **no** Shared Crosshair setting: crosshair sync is a timeseries affordance, and this board is one lane of timeseries above a log viewer that does not participate.

## D6 — Every panel scopes its hosts explicitly

Every panel expression carries either a literal `host=` matcher or the board's `$host` template variable. **`instance` is not a discriminator** — every fleet Alloy binds `127.0.0.1:12345`, so `instance` collides across all five hosts; `host` (set via `external_labels`, uniform fleet-wide since spec `00069` D7) is the only one.

This is the direct fix for the three mis-scoped panels above, and the reason it is stated as a rule rather than three edits: the defect was not that someone wrote three bad panels, it is that an unscoped expression is *correct* on a single-host fleet and silently rots as hosts are added.

**The rule is about being unambiguous, not about a matcher being literally present — and that distinction is load-bearing, because 27 of the 52 metric rules are themselves host-unscoped.** P1 requires a panel to plot its rule's expression verbatim; read literally against a bare "every expression carries a matcher", the two would contradict each other on more than half the panels. They do not, because most of those 27 select a family with exactly **one publisher**, where the scope is implicit and a matcher adds noise rather than safety.

A panel satisfies this rule by any of three routes, and its description says which:

1. **An explicit `host=` / `$host` matcher** — required for every multi-publisher family: all `node_*`, all `process_*`, `zcrypto_capture_*` (two hosts), `zaccess_*` (two ends), `up`.
2. **A single-publisher family** — `zcrypto_gate_*` (NAS only), `zcrypto_reconcile_*`, `zcrypto_trade_backfill_*`, `ops_*` and `hc_*` (ops only), `zcrypto_engine_*` (the primary only). Adding a matcher here is inert; copying the rule verbatim per P1 wins. **State the publisher in the panel description** — that is what makes the omission auditable rather than accidental, and it is the fact an implementer otherwise has to dig out of a keep-regex.
3. **A per-host legend that names the host** — for a family deliberately plotted across hosts, `zcrypto_logship_*` above all, whose whole value is the cross-host comparison. P5's `{{host}}/{{job}}` legend is what discharges the ambiguity there.

Route 2 is exactly why the structural lint is a lint and not a pin: it can only see route 1.

### Host naming — one vocabulary at the operator surface, zero label rewrites

Two goals, the owner's: **(1)** a Linux hostname is never visible on an operator surface; **(2)** *fewer* names for one thing — "less, not none", so this must not become a renaming project.

**What is actually a hostname.** Only two label values are: `zcrypto` and `zcrypto-red` (the journal shows `zcrypto-ops systemd[1]`, so even the ops box's *label* `ops` is already an abstraction over its hostname). `nas` and `ops` are role words that happen to be short. `zaccess` is a project-coined role name that doubles as a hostname. **So goal (1) bites on exactly two values**, and a fleet-wide renaming would be solving four-fifths of a problem that does not exist.

**The vocabulary is adopted, not invented.** `fleet-deploys.md` already says primary/secondary throughout, and four alert titles already read *"— primary (zcrypto)"* / *"— secondary (zcrypto-red)"* (six carry a host token in total) — the parenthetical is redundant decoration next to a name that is already the operational one. Dropping it loses no information and closes goal (1) for both values.

| `host` label (**unchanged**) | display name | why |
| --- | --- | --- |
| `zcrypto` | **Capture primary** | hostname; the pair is already called this everywhere in operational prose |
| `zcrypto-red` | **Capture secondary** | hostname; `-red` is *redundancy*, which no reader outside the repo would infer |
| `ops` | `Ops` | already a role word — and the two *other* names for it, `zcrypto-ops` and the ssh alias `hp`, simply never appear on an operator surface |
| `nas` | `NAS` | already a role word |
| `zaccess` | `Edge` | coined, not distro-assigned; renamed only because "Edge" is what every prose description calls it |

**Applied at four surfaces, all of them presentation:**

1. **Alert rule titles** — drop the six hostname parentheticals; `Fleet · Alloy dark — ops` / `— zaccess` become `— Ops` / `— Edge`. Rule **uids are unchanged**, so this is a display-only edit and no alert loses its identity. One consequence to state: `alertname` changes, so any saved Grafana silence keyed on the old title stops matching — there are none today, and the push is the moment to confirm that.
2. **Slack templates (D12)** — the phone never shows a hostname. This is the highest-value surface: it is the only one read with nothing else open, and it is the one a test **cannot** protect, because the hostname arrives as runtime label data rather than as literal text the vocabulary check can walk.

   Concretely, D12's template gains a mapping define, and **every `host` render goes through it** — the title, the where-line, and the per-instance lines. D12's template text and its worked example are amended by this; where the two disagree, this rule wins:

   ```gotemplate
   {{ define "zcrypto.host" -}}
     {{ if eq . "zcrypto" }}Capture primary
     {{- else if eq . "zcrypto-red" }}Capture secondary
     {{- else if eq . "ops" }}Ops
     {{- else if eq . "nas" }}NAS
     {{- else if eq . "zaccess" }}Edge
     {{- else }}{{ . }}{{ end }}
   {{- end }}
   ```

   The fall-through is deliberate: a host the map does not know renders its raw label rather than vanishing. A new fleet member then shows up as an unmapped name — visible, correctable, and never silently unlabelled.

   **The mapping cannot reach a summary, and that constrains how summaries are written.** Grafana interpolates `{{ $labels.host }}` into the `summary` annotation **at rule-evaluation time**, long before any notification template runs — so a summary that names the host bakes in the raw label and no define can touch it. The rule is therefore: **a summary never interpolates `$labels.host`.** It does not need to: the template renders the host itself, mapped, in the title and the where-line, so a summary naming it is duplication that happens also to be unmappable. `{{ $labels.target }}` and `{{ $labels.system }}` stay — they carry information the template does not render and no vocabulary applies to them.
3. **Panel titles, descriptions and text panels** — the vocabulary in prose. Free; it is text this spec is writing anyway.
4. **The `$host` dropdown** — a **custom** variable with `label : value` pairs, `Capture primary : zcrypto, Capture secondary : zcrypto-red, Ops : ops, NAS : nas, Edge : zaccess`. This **supersedes the `label_values(up, host)` query form given in D2's variable table**: a query variable cannot carry display labels at all, so the query form and this goal are mutually exclusive. The custom list is also a *stronger* pin than the regex it replaces — it cannot admit a stray value in the first place — which is the same argument D4's engine `$host` already makes. The cost is real and stated: the option list is a second place to edit when a host joins the fleet, alongside the alert rules that name hosts.

**Where the vocabulary deliberately stops: panel legends.** They keep the raw `host` label. There is no Grafana mechanism that maps a label *value* to a display string in a legend — the options are nested `label_replace()` inside every expression, or a per-panel `fieldConfig` override repeated across ~20 multi-host panels, and the dashboard JSON here is **hand-written and committed, not generated** (verified: no generator exists in the tree), so either choice buys a cosmetic gain with a large, hand-maintained, error-prone surface. This is the "less, not none" boundary: a legend is read *inside* a board the operator opened on purpose, next to a `$host` picker that now shows the vocabulary — the hostname there is a precise identifier, not a leak to someone with nothing open. The surfaces that are read cold — the phone notification and the rule title — carry no hostname at all.

**Explicitly NOT changed:** metric label values, `external_labels`, the ansible inventory, ssh aliases, or any hostname. Renaming a label value changes series identity under `increase()` — the hazard the fleet took knowingly, once, at a chosen window, for one label on one host. Nothing here is worth a second one.

**A side benefit worth naming:** `zcrypto_reconcile_trade_deficit_rows_total`'s `host="primary"|"secondary"` values stop being an anomaly and become *the standard vocabulary* — the harmonization makes the outlier the rule. Its real defect is unchanged and still out of scope: it occupies the `host` label when it means a mirror *side*, so a `side` label is the correct fix and a future one.

## D7 — Every monotonic damage counter is paired with a recent-delta view

A cumulative damage counter is red forever after the first incident and cannot distinguish old damage from new. On 2026-07-20 the owner asked whether a red 44.4 min was alright; answering it required leaving the dashboard and tracing the reconcile ledger by hand to a single `both_streams_silent` entry from a week earlier.

So: **each monotonic damage counter gets `increase(<counter>[24h])` beside its cumulative value**, thresholded green at zero, so the board answers *"is this getting worse?"* and not only *"has this ever happened?"*. Applies to `zcrypto_reconcile_residual_gap_seconds_total`, `_healable_gap_seconds_total`, `_healed_gap_seconds_total`, the capture damage counters, and the engine's cumulative intent counters.

The alert layer already makes this distinction (`zcrypto-reconcile-healable-gap-rate` is a rate rule); the dashboard did not.

## D8 — The coverage invariant, enforced by a test

The owner's principle, verbatim: *"when an alert fires, we can visually find the clue at the dashboard, and the alert points to a visual panel."*

`tests/test_dashboards_cover_metrics.py` asserts three things:

1. **Family coverage of the alert layer.** Every metric family referenced by any rule expression in `infra/grafana/alerts.yaml` is referenced by at least one panel expression across the committed dashboards. **Family-level, never rule-level** — two rules on `node_filesystem_avail_bytes` (a 5% low and a 95% high watermark) are satisfied by one timeseries showing the trend with both thresholds marked, not by two stat panels.
2. **Family coverage of the app layer.** Every app-level `zcrypto_*` / `ops_*` family the fleet publishes appears in some panel expression.
3. **Keep-list admission of every alerted family, on the hosts its rule selects.** This is the assertion that mechanically catches the class of defect D10 fixes by hand.

Deliberate exclusions live in one commented constant, so each is a reviewed decision rather than silent drift.

**Why assertion 3 is the load-bearing one.** `tests/test_infra_alloy_series.py` already guards keep-regex admission in both directions — but from a **hand-curated per-host `required` list**. It therefore catches a *listed* family being dropped, and is blind to a family missing from the list. That blindness is exactly why the `zaccess` hole survived it. Assertion 3 derives its expectation from `alerts.yaml` instead of from a list a human maintains, so the omission cannot recur.

Per `agent-ops.md`, a guard is unproven until the defect it names is constructed and seen to trip it. Here the defect already exists in the tree: **reverting D10's keep-regex line must make assertion 3 fail**, and that is a required verification step, not an optional one.

## D9 — Every alert rule points at its panel

Grafana renders a direct panel link in a notification when a rule carries `__dashboardUid__` and `__panelId__` annotations. Today **no rule carries any pointer**: a grep for `__dashboardUid__` / `__panelId__` / `runbook_url` across `alerts.yaml` returns zero, and rules carry only `summary`.

Adding them is a **pure data edit with no tooling change**: `grafana-push.sh` walks the rule JSON substituting only its `${GRAFANA_*_UID}` placeholder tokens, and passes every other key through verbatim.

Rules whose signal is genuinely not panel-shaped (a pure log-content rule) carry a runbook reference instead; the test's assertion 3 companion check requires that every rule resolves to *either* an existing panel or a named runbook section — never neither.

## D10 — The two alerting holes

**(a) `zaccess` cannot fail its own collector alert.** `roles/access/files/config.alloy`'s keep-regex admits 13 families and omits `node_scrape_collector_success`, so `min by (host) (node_scrape_collector_success)` can never match `host="zaccess"`. The host is invisible to the rule that watches it. Fix: add the family to the regex, and to the access `required` list in `tests/test_infra_alloy_series.py`.

Scope discipline: the access regex also omits `node_memory_MemFree_bytes`, `node_filesystem_free_bytes`, `node_filesystem_files`, `node_filesystem_files_free`, and `node_scrape_collector_duration_seconds` relative to its siblings. **Only `node_scrape_collector_success` is added** — it is the one whose absence disables an existing alert. The others are a series-budget question with no rule behind them, and widening on aesthetics spends budget for nothing.

**Converge shape — and it differs from every other host.** Alloy on `zaccess` is a **native deb**, not a container: installed as `alloy={{ access_alloy_version }}`, held via `dpkg_selections`, and its `config.alloy` is an **ungated copy** — the task comment records that every converge ships it so a hand edit cannot outlive the next run. There is **no `access_alloy_digest`** and no drift-assert, unlike capture (`capture_alloy_digest`) and ops (`ops_alloy_digest`). So this converges with a plain `site.yml --limit` on that host: no digest operand, no bake owed, no canary gate. `fleet-deploys.md` does not cover this case — the finding lands in `docs/reference/fleet.md` in this same change, per `agent-ops.md`.

**(b) The capture staleness watchdog watches nothing.** `zcrypto_capture_seconds_since_last_book_message{pair}` is neither charted nor alerted, though its docstring names it the watchdog's proof-of-life signal. A new rule covers it. It is published and keep-list admitted already, so this is an `alerts.yaml` push with **no converge**.

Threshold, no-data semantics, and the rule's relationship to the existing per-pair desync rules are fixed in D-alerts below rather than here.

## D11 — New and corrected alert rules

Two holes, three label collapses. Following spec `00043`'s convention, **no-data handling is per-rule and never blanket** — each row's value below is argued from what absence of that specific series means, and from which other rule already owns that meaning.

| Rule | Expression | `for` | no-data | Severity | Why |
| --- | --- | --- | --- | --- | --- |
| **`Capture · every book stream on a host is silent`** *(new, `zcrypto-capture-all-streams-silent`)* | `min by (host) (zcrypto_capture_seconds_since_last_book_message{host=~"zcrypto\|zcrypto-red"})` > `60` | `0s` | `OK` | critical | On 2026-07-27 all 12 pairs went silent for ~209 s on **both** hosts while the WS reported connected, keepalive completed ≥11 round trips, and the gap counter read 0.0. The *minimum* across pairs is the discriminator: one thin leg being quiet is normal, all twelve simultaneously is not, and nothing in the capture path produces it — so the bar can be tight where a per-pair bar cannot be. **SUPERSEDED at execution (2026-08-28, [[T0129]]):** what does produce it is the venue on a published calendar — both firings in the rule's life fell inside an announced "Kraken Website and API Maintenance" window, so the class is identified rather than mysterious, and the rule now carries a runbook that says to read that calendar first. Absence is owned by the dead-man and by `Fleet · Alloy dark`, hence `OK`, matching every sibling capture rule. The gauge is 0 for every pair at process start, so a restart cannot false-fire. **`for: 0s`, and the pending period is the load-bearing number here rather than the bar**: the gauge is scraped every 60 s, so real silence at firing time is already `60 s bar + up to 60 s of scrape granularity + pending + the group's eval interval`. A `2m` pending period — the value this row first carried — put the *guaranteed* detection floor at 300 s against a 209 s motivating event, and a phase sweep over scrape × eval alignments caught that event in only **12.1 %** of them (180 s: 0 %). `1m` is not the fix either — it still misses 209 s in 12.9 %. At `0s` every blackout ≥180 s is caught in every alignment, and nothing but real silence can raise the minimum: a restart seeds `last_seen` before the collector registers, a stop→start replays the last healthy sample, a longer stop goes NoData which `OK` swallows, and remote-write lag can only delay firing. **Shipped at `> 120`, not 60 (2026-08-05, `ade2c019`, owner's call):** the same measurement that derived the per-pair bar found a 30.261266 s fleet-wide silence on the primary — every pair at once, that single event's cause never established — which left 60 only a 2× margin on the fleet's highest-severity capture signal. (The *gauge's* reading of that event has since aged out of the 14 d retention; the event itself remains measurable from the parquet archive, per the re-derivation note below.) 120 is 4× it, and the 209 s motivating event is still caught, though the slack is ~29 s against a ~180 s guaranteed detection floor rather than the 89 s a bar-only subtraction suggests. That 4× was over one week of data, not thirty days. **RE-DERIVED 2026-08-28 on the full 14 d retained ([[T0129]], resolved): both bars unchanged.** It also carries `execErrState: OK` — per-rule exec-error handling being now as argued as the no-data handling above: an execution error means the query never ran, so `Alerting` asserted a blackout rather than reporting one (24 such instances against 4 genuine). Over the 13 days containing no venue window the fleet-wide minimum peaked at 6.134482 s, making 120 ~20× the natural envelope; and the retention ceiling caps the *gauge*, never the phenomenon — the parquet archive holds the whole capture era at full resolution, which is where a future re-derivation starts. |
| **`Capture · a book stream has stopped delivering`** *(new, `zcrypto-capture-stream-silent`)* | `zcrypto_capture_seconds_since_last_book_message{host=~"zcrypto\|zcrypto-red"}` > `900` | `10m` | `OK` | warning | The single-stuck-stream class, which nothing else catches: one pair has stopped delivering while every other stream flows, and nothing in the daemon heals it — `_staleness_loop` only *books* the silence, while the resubscribe/reconnect ladder in `_desync_recovery_loop` skips any pair whose book is not `desynced`, so a silent-but-synced stream stays silent at any age (corrected 2026-08-05; the row first read "the resubscribe path failed", which assumes a recovery that never runs). No aggregation, so Grafana raises one instance per `(host, pair)` with the labels intact and the summary names the stream. **The 900 s bar is a starting threshold, not a measured one** — the same standing this file gives the reconciler's 600 — because `is_healthy()`'s own docstring is explicit that silence was booked first and thresholding "waits until the exported gauge shows a production distribution worth thresholding". That distribution now exists: derive the bar from `max_over_time(zcrypto_capture_seconds_since_last_book_message[30d])` per pair per host, and set it above the binding pair's natural maximum with the same ~2.4× margin the daemon's own 30 s constant uses, **before the rules push**. **The ~2.4× margin was SUPERSEDED at execution (2026-08-05, `ade2c019`)** — it lands at ~29 s, which is the daemon's own gap-booking threshold and *below* the 30.261266 s fleet-wide event the measurement found, i.e. twelve false instances on 07-29 alone; that multiplier was fitted to a *booking* threshold, whose false window costs a ledger entry, not to a *page* on the unbackfillable path. Shipped: **`> 300`, `for: 0s`** — ~25× the binding **natural** per-pair maximum (12.068981 s, the primary's AVAX/EUR) — **RE-DERIVED 2026-08-28 ([[T0129]], resolved): ~20×, and the bar is unchanged at 300.** That 12.068981 s was the same statistic over a seven-day window, which censored it; the full-resolution archive puts single-host natural quiescence at 14.78 s ([[T0039]] — three pairs over 136 h ending 2026-07-14, before the `/BTC` legs, so it brackets rather than pins the basket) and the 14 d gauge independently reaches 14.160757 s (`zcrypto-red` SOL/BTC, no capture restart within 26 h) and ~10× the 30 s mark. The base was also one week, not thirty days: the gauge shipped with the 2026-07-29 converges, so `[30d]` covered ~7.2 d (primary) / ~7.5 d (secondary) of samples. **Re-derived 2026-08-28 on the full 14 d retained ([[T0129]], resolved), and the retention ceiling caps the *gauge*, never the phenomenon — the parquet archive holds the whole capture era, so that is where a future re-derivation starts.** This rule also carries `execErrState: OK` (the row above argues it): an execution error means the query never ran, so `Alerting` named stuck streams nothing had observed — 240 such instances against 48 genuine ones. |
| **`Engine · cycles have stopped`** *(new, `zcrypto-engine-cycle-stale`)* | `time() - zcrypto_engine_cycle_completed_at_seconds{host="zcrypto"}` > `16500` | `5m` | **`Alerting`** | critical | **The larger of the two holes.** Nothing watches `zcrypto_engine_cycle_completed_at_seconds` or `_cycle_success`; the only engine rule is `changes(zcrypto_engine_active_sleeves[26h])`, which is about composition, not liveness — and a crash-looping engine leaves `active_sleeves` frozen at its last value, so no page ever fires while cycles silently stop. `16500` is spec `00043`'s own precedent (4 h 35 min from completion) and it is the cadence arithmetic, not a generic staleness number: with boundaries 00/04/08/12/16/20 UTC and completion inside `[B, B+30 min]`, the worst *healthy* age is 4 h 30 min = 16200 s, reached legitimately just before the next cycle lands, so 16500 leaves five minutes of margin and a flat 1 h/2 h bar would sit red through most of every gap. **`Alerting` on no-data, uniquely on this board:** the gauge is seeded at engine startup from the newest journal artifact and falls back to process start, so it is never legitimately absent while the engine runs — absence means the engine container is gone, and nothing else owns that (`Fleet · Alloy dark — capture primary` evaluates `count(up{host="zcrypto"}) < 1`, which stays ≥ 1 while Alloy is up and the engine target merely reads `up = 0`). Accepted cost, named: a genuine Alloy-dark event on the primary double-pages. |
| **`Engine · the last cycle failed`** *(new, `zcrypto-engine-cycle-failed`)* | `zcrypto_engine_cycle_success{host="zcrypto"}` < `1` | `0s` | `OK` | warning | **Liveness cannot cover this and the reason is load-bearing:** the metrics sink runs after every cycle *success or failure*, and it refreshes `cycle_completed_at` unconditionally — so an engine whose every cycle fails on schedule keeps the staleness rule silent forever. **`for: 0s`, because the outcome is already final the instant the gauge reads 0** — read from the source, not assumed: `cycle.py::_failed` writes `failed-cycle-<HH>.json` *before* it calls `_update_metrics`, and `node.py::startup_action` returns `None` for any boundary that already has a journal artifact (success record **or** failed sidecar), a check independent of the `[B, B+25 min]` window it sits behind. So `cycle_success == 0` ⟹ the sidecar exists ⟹ no re-run is possible, ever, and the next boundary is 4 h away. This row first carried `for: 35m` on the opposite premise — that a restart inside `B+25 min` could still flip the gauge back — which bought 35 minutes of silence and a summary telling a 03:00 responder the engine had already retried and failed again. Only `zcrypto engine cycle --at <B> --replace` can re-run the boundary. `OK` on no-data because this gauge is *deliberately* left unregistered until an outcome is actually known — a fresh deploy or an unreadable journal must not page — and the staleness rule above owns absence. |
| **`Access · WireGuard tunnel stale`** *(corrected)* | `max by (host) (zaccess_wireguard_handshake_age_seconds)` > `300` | `10m` | `OK` | warning | Today's `max(…)` carries **no host selector**, and the family is published by *both* ends — the bridgehead probe (`host="zaccess"`) and the ops-side probe (`host="ops"`) — so `max()` collapses them and the summary cannot name which end lost the link, which is the first question asked. `by (host)` raises one instance per end. **The summary MUST NOT interpolate `{{ $labels.host }}`** — Grafana bakes annotations at *evaluation* time, before any notification template runs, so D12's `zcrypto.host` mapping cannot reach it and the summary would ship the raw internal hostname to a phone; the summary says "the host this notification names" and leaves the naming to the template, which is why `host` is on that template's must-render list. Threshold, `for`, no-data and severity all unchanged. |
| **`Access · edge cert expiring`** *(corrected)* | `min by (host, target) (zaccess_tls_not_after_seconds) - time()` < `1209600` | `1h` | `OK` | warning | Today's `min(…)` collapses `host` **and** `target`, so the operator learns a certificate is expiring and not *which* — across `tmux` and `nas` from the bridgehead probe and `nas-dsm` from the ops probe. `by (host, target)` makes each certificate its own instance and the summary gains `{{ $labels.target }}`. Consequence, stated: alert-instance cardinality rises from 1 to up to 3, and the label change resolves the existing instance and re-fires under new labels at push time. |
| **`Capture · Kraken reports the venue is not online`** *(corrected)* | `sum by (host, system) (zcrypto_capture_venue_status_total{host=~"zcrypto\|zcrypto-red", system!="online"}) or on() vector(0)` > `0` | `5m` | `OK` | warning | The third instance of the same label-collapse class: today's `sum(…)` discards `system` entirely, and `maintenance` (planned — wait) versus `cancel_only` / `post_only` (degraded — act) demand opposite responses. Grouping preserves every documented property of the rule: the negative match still cannot miss an unobserved payload shape, presence-not-`increase()` is unchanged (the series is born at 1 and Prometheus inserts no implicit zero before a first sample), and the deliberate **latch** until daemon restart is unchanged. Adds the host scope its siblings all carry. **The fallback must be `or on() vector(0)`, never the bare `or vector(0)`** — `vector(0)` produces an *unlabelled* element, so a bare `or` suppresses it only while the left arm is unlabelled too; once `by (host, system)` gives the left arm labels the two stop sharing a signature and the 0 rides through as a permanent extra series beside the real one instead of a mutually-exclusive fallback. `on()` matches on the empty label set, which every element has. |

Three further points, each verified against `infra/grafana/alerts.yaml` rather than assumed.

**The two logship rules need no change.** Neither `increase(zcrypto_logship_dropped_lines_total[6h])` nor `time() - zcrypto_logship_last_cycle_timestamp_seconds` aggregates, so all labels ride through and Grafana already raises one instance per `(host, job)` — the alert *can* name the daemon today. The defect is presentational only, and P5's `{{host}}/{{job}}` legend fixes it on the panel.

**`Node · a node-exporter collector is failing` stays as written.** Its `min by (host)` collapses `collector`, which is a real gap, but D10(a) is already widening the access keep-regex in this iteration and the panel's second series names the failing collector. Changing the rule as well would fold a third moving part into the one converge that must be verifiable.

**Every rule gains a `__dashboardUid__` / `__panelId__` pointer in this same change** (D9), including the seven above. Where two panels could serve one rule, the pointer goes to the panel plotting the rule's expression (P1) and the other is marked context — the resolution is recorded per-rule in D2, D3 and D4's tables rather than left to whoever writes the JSON.

## D12 — Slack notification templates

The alert that reaches a phone is the one surface in this system read with nothing else open. Today it is Grafana's stock template, which spends sixteen lines saying what four could and omits the one thing a log alert exists to carry — the line. This section decides what the message says, how it is provisioned, and how it is verified.

### Current state — both receivers render the stock template

`grafana-push.sh` mints both Slack integrations as-code, with `settings: {url}` and nothing else, so Grafana falls back to `default.title` / `default.message` for every notification the fleet sends.

| | uid | receiver | `disableResolveMessage` | routing |
| --- | --- | --- | --- | --- |
| metrics | `zcrypto-slack-metrics` | `metrics` | `false` — resolve messages **ON** | the notification policy's **default route**, plus every metrics rule's `notification_settings` |
| logs | `zcrypto-slack-logs` | `logs` | `true` — resolve messages **OFF** (Loki alerts resolve by aging; a resolve ping is noise) | pinned per-rule by the Loki-sourced rules |

Both deliver to the **same** webhook, so both share its rate limit and its channel.

Measured against `infra/grafana/alerts.yaml`, and each number is load-bearing below — **counts are post-D11**, which adds four rules to the 58 measured at design time, plus the engine ERROR-log rule (`zcrypto-engine-error-logs`) this iteration adds: **63** rules, **52** on `metrics` and **11** on `logs`; the **only** annotation any rule carries is `summary` and the **only** label is `severity` (both on all 63); **8** summaries contain `>` and **none** contains `<` or `&`; **no** rule carries `__dashboardUid__`, `__panelId__` or `runbook_url`, so `.PanelURL` / `.DashboardURL` are empty on every alert until D9 lands. Everything else in a notification — `alertname`, `grafana_folder`, `instance`, `job`, `host` — is injected by Grafana or rides in from the series.

Node shapes matter for what a value line can honestly say: **51** rules are `A → C`, **11** are `A → B → C` where B is a `reduce: last` of A (a duplicate), and **exactly one** — `Ops · verify-replay backlog stuck` — is `A → B → C → D` with **two** PromQL queries, A the pending-hour count and B its 26 h delta.

`infra/grafana/notification-templates/` does not exist yet; `jq` on the workstation is 1.7, so `--rawfile` is available.

### What changes, and why

| element | today | after | why |
| --- | --- | --- | --- |
| status | `[FIRING:1]` in the title, `**Firing**` as the first body line (asterisks visible — Slack bold is single-asterisk) | one glyph: 🔴 / 🟠 firing, ✅ resolved | Grafana already colours the attachment red/green; the word is a third statement of the same fact, and it costs the line where the summary should be |
| `Value: A=…, C=…` | every refId dumped, unlabelled | `measured 2437 seconds of unrecoverable silence` — refId **A** only, unit from a new optional `unit:` annotation | B is a `reduce` duplicate on 10 rules and C is the threshold node's `1`; neither is information. **Named exception:** on `Ops · verify-replay backlog stuck` B is a second query, so an A-only line under-reports it — accepted, because A alone (the backlog size) is still the actionable number |
| `grafana_folder` | rendered in the label list *and* in the title | never rendered | one folder exists; a constant is not a discriminator |
| `host` / `instance` | both rendered, plus `job` | `host` hoisted to the title and to the front of the label line; `instance` and `job` dropped | `instance` **collides fleet-wide** — every Alloy binds `127.0.0.1:12345` (D6/P5) — so it discriminates nothing while reading as if it does; `host` is the real discriminator |
| `severity` | last word of a long title, after `grafana_folder`, `host`, `instance` and `job` | first glyph of the title, `🔴 CRITICAL ·` / `🟠 WARNING ·` | 28 of 63 rules are critical and 35 warning; the attachment colour is fixed red-firing / green-resolved by Grafana and **cannot** vary with severity, so the glyph is the only place the distinction can live |
| annotations | dumped as a list; a query-error alert additionally carries Grafana's own `datasource_uid` and `ref_id` keys | `summary` promoted to the first body line, once, from `.CommonAnnotations`; nothing is dumped generically, so `datasource_uid` cannot appear; `ref_id` is picked out by name and keyword-explained (`the query that failed is A`) | all 63 rules set `execErrState: Alerting`, so the error path is live for every rule, and a bare `datasource_uid=…` on a 3 a.m. page is noise where "which query broke" is the answer. Both are excluded from the generic label line **and** unreachable via annotations, so the rendering is correct whichever kind Grafana attaches them as — a detail settled by reading the first error fire, not by assumption |
| the log line (logs receiver) | **absent entirely** — the alert says "7" and the operator goes hunting | up to 5 distinct lines, each in a code fence under its own label line | this is the whole reason a log alert exists; see the rule-side change below, which the template cannot supply on its own |

**The template alone cannot carry the log line.** `count_over_time` returns a count, and the only labels reaching the notification are the ones named in the aggregation's `by` clause — so nothing a template does can recover the offending text. All eleven shipped logs rules aggregate `sum by (host, …)`, which is enough to name the machine but never the line. The message itself has to be minted as a label at query time, and that hoist is on the ERROR-log rules covering direct-ship daemons — **three** of the eleven (`zcrypto-capture-error-logs`, `zcrypto-ops-error-logs`, and `zcrypto-engine-error-logs`, which D11 adds with an identical shape):

```logql
topk(5, sum by (host, container, level, msg) (count_over_time(
  {host=~"zcrypto|zcrypto-red", container="capture", level=~"ERROR|CRITICAL"}
  | json message="message"
  | drop __error__, __error_details__
  | label_format msg=`{{ if .message }}{{ printf "%.200s" .message }}{{ else }}{{ printf "%.200s" __line__ }}{{ end }}` [15m])))
 or on() vector(0)
```

`topk(5, …)` is not optional: without it a log storm mints one alert instance per distinct line, straight past Slack's length limit.

**The message is parsed out of the line, not read raw** — the correction that matters most here, because the obvious form is wrong for this fleet. The three hoisted ERROR rules all cover **direct-ship** daemons, which push a JSON *body* rather than a rendered line: D5 records the shape (`JsonLineFormatter`, fields `ts` / `level` / `logger` / `file` / `line` / `message`), and it applies to the capture daemon, the liquidations poller and the engine alike. A bare `label_format msg=`{{ printf "%.200s" __line__ }}`` therefore spends roughly 150 of its 200 characters on the JSON preamble and truncates the message mid-sentence — a page that *looks* like it answered the question while carrying only metadata, which is worse than one carrying no line at all. `| json message="message"` extracts the field; the `{{ if .message }}` fallback keeps the raw line for streams Alloy has already flattened (the ops journal units, Alloy's own logfmt), so one expression serves both shapes. Measured against live Loki on both, not assumed.

**`| drop __error__, __error_details__` is load-bearing and must not be simplified away.** `| json` stamps `__error__="JSONParserErr"` on every line it cannot parse, and the query then fails with **HTTP 400** the moment one non-JSON line enters the pipeline — on `zcrypto-ops-error-logs`, whose selector spans both shapes, that is a live condition rather than a hypothetical, and it would take the whole rule to `execErrState`. Neither alternative works: Loki rejects `label_format __error__=…` outright ("`__error__` cannot be formatted"), and `| __error__=""` *drops* the offending lines instead of admitting them. `drop` is the only stage that keeps both shapes. All three behaviours were confirmed against live Loki, including the negative control — the shipped expression with the `drop` stage removed does 400.

`__line__` inside `label_format` was itself **medium confidence** at design time (documented for `line_format`, assumed to share the function map) and is **confirmed working**; it survives here as the fallback branch. The other eight rules — seven dead-canaries firing on *absence*, plus the NAS ERROR rule whose container is a single literal — get no `msg` by construction, and the template's own "this rule counts matching lines rather than carrying them" branch renders for them. `zcrypto-ops-error-logs` selected `{host="ops", level=~"ERROR|CRITICAL"}` with no container filter, making its distinct-line cardinality under a storm a Loki query-cost hazard as well as a Slack one; it is narrowed to an enumerated `container=~"alloy|liquidations|zcrypto-.*"`, the list measured from `sum by (container) (count_over_time({host="ops"}[7d]))` rather than guessed.

The nine bare-`sum()` rules should gain a `by` clause on their own merits — `sum(count_over_time({container="archive-pull", …}))` fires without saying which host, and `container="archive-pull"` is not host-scoped — but that is a rule change, not a template change, and it is listed here so it is decided rather than discovered.

### The five open calls, decided

Judged against one principle (owner's): **maximise information density without sacrificing readability.** The operational reading of that: a notification should let the responder decide *whether to get up* without opening anything, and know *where to go* if they do. Every element earns its line by moving one of those two, or it is cut. Density is not compression — a dense message is one where nothing is filler, not one where everything is abbreviated.

| # | Call | Decided | Reasoning |
| --- | --- | --- | --- |
| 1 | Carry the log line at all? | **Yes — the rule change rides** | The single largest density win available. A log alert that reports `7` and no line is the *definition* of low density: it establishes that something happened and forces a lookup to learn what. Confirming the hoist against live Loki was a five-minute precondition and is discharged — it also caught that the raw line is a JSON body on the direct-ship daemons, which is why the shipped form parses `message` out rather than reading `__line__`. |
| 2 | Narrow `Ops · ERROR logs` by container? | **Yes** | It selects `{host="ops", level=~"ERROR\|CRITICAL"}` with no container filter, so it cannot say *which service* errored — a lookup forced by the alert's own shape. It is also the storm-cardinality hazard, in Loki query cost as well as Slack length. Both problems have the same one-line fix. |
| 3 | Do the nine bare-`sum()` logs rules gain a `by` clause? | **Yes** | This is the **same defect class D11 already fixes three times** (the two zaccess collapses and the venue-status collapse): an aggregate that discards the label naming *where* it fired. Fixing three instances while leaving nine is not a scope boundary, it is an inconsistency — and `container="archive-pull"` is not even host-scoped, so today one of them cannot distinguish the two hosts that publish it. |
| 4 | How widely to apply the `unit:` annotation? | **Selectively — where a bare number is ambiguous** | Applying it to all 63 would add a line to rules whose summary already carries the meaning, which is filler, and filler is what kills density. Apply where the threshold is a quantity whose unit a reader cannot infer: durations in seconds, byte counts, ratios, row counts. Skip for boolean and presence rules, where the number is `0` or `1` and the unit is the rule. |
| 5 | Fire a probe into the live channel? | **Yes — the cheapest trip, and re-tune the caps from what renders** | Verification that does not exercise Slack's own rendering verifies nothing, and `00043` already set the precedent of a once-only test fire that does not break production. Use `count by (host)(up) > 0`: it touches no host, is trivially un-tripped by deleting the probe rule, and **fires five instances at once**, which exercises the multi-instance path — the one most likely to hit a length limit — rather than a flattering single-alert case. The 6-metric / 5-log truncation caps are explicitly starting values, re-tuned from the render. |

Two consequences of (1)–(3) worth stating plainly, since they widen the change: this iteration now edits **all ten** pre-existing logs rules rather than two, one of them twice, and the log-line hoist means two of them gain a `label_format` at query time — three carry it in the shipped file, counting the `zcrypto-engine-error-logs` rule added alongside. Both are rule-file edits pushed by the same script in the same step — no converge, no host contact — so the cost is review surface, not operational risk.

### The panel pointer

D9 puts `__dashboardUid__` / `__panelId__` on every rule; Grafana populates `.PanelURL` and `.DashboardURL` from exactly those two annotations, and the template renders the first one that exists:

```
.PanelURL      → 👉 open the panel
.DashboardURL  → 👉 open the board — this rule names a board but no panel
neither        → 👉 open the rule and its query — no dashboard panel is pinned on this rule
```

The third string is deliberately a nag: it is the only place a missing pointer becomes visible, and `.GeneratorURL` (always present on a Grafana-managed rule) still opens the query and its graph, so the operator is never stranded.

**`__panelId__` must be quoted in the YAML.** `grafana-push.sh` does `yaml.safe_load` → `json.dumps`; an unquoted `305` becomes a JSON *number*, and the provisioning API's annotations are string-valued, so the rule is rejected and `curl -fsS` under `set -euo pipefail` aborts the whole push. Loud rather than silent, but it aborts the run.

No time range is built into the link: Go templates have no arithmetic, so `StartsAt − 1h` is not expressible, and a just-fired alert's neighbourhood is the board's default range anyway. Whether Grafana appends `&from=…&to=…` to `.PanelURL` is **medium confidence** and is read off the first real fire rather than guessed at.

### Provisioning — a template object, referenced from `settings.title` / `settings.text`

**Decision: one provisioned template object (`PUT /api/v1/provisioning/templates/{name}`, body `{name, template}`) holding every `define`, with each contact point's `settings.title` / `settings.text` carrying a one-line `{{ template "…" . }}` reference.**

The decisive reason is structural, not stylistic: contact-point settings can only *reference* templates, never `{{ define }}` them, and the two receivers share the escaping, label-line, value and link partials. Inlining means implementing the escaping rules twice and watching them drift. Three supporting reasons: the body becomes a committed, diffable file beside `alerts.yaml` and the dashboard JSON, rather than a 70-line Go template with backticks and `{{ }}` embedded in a `jq -n --arg` string inside a `set -euo pipefail` script; it is **verifiable**, because Grafana redacts `settings.url` on contact-point read-back (the script's own comment records this) while `GET …/templates/{name}` returns the text in full; and the script already has the ordering discipline this needs — receivers before rules, now templates before receivers.

**Change A — a new push block, between the dashboard loop and the Slack contact-point section**, deliberately *outside* the webhook-gated branch, so a steady-state run with no webhook still ships template edits:

```bash
for tmpl in "${root}"/infra/grafana/notification-templates/*.tmpl; do
  [ -e "${tmpl}" ] || continue
  tname="$(basename "${tmpl}" .tmpl)"
  tmpl_payload=$(jq -n --arg name "${tname}" --rawfile template "${tmpl}" '{name: $name, template: $template}')
  curl -fsS -X PUT "${GRAFANA_URL}/api/v1/provisioning/templates/${tname}" \
    "${auth[@]}" -H "Content-Type: application/json" -H "X-Disable-Provenance: true" -d "${tmpl_payload}" >/dev/null
  live_tmpl=$(curl -fsS "${auth[@]}" "${GRAFANA_URL}/api/v1/provisioning/templates/${tname}" | jq -r '.template')
  [ "${live_tmpl}" = "$(cat "${tmpl}")" ] || { echo "grafana-push: template ${tname} did NOT read back byte-identical" >&2; exit 1; }
done
```

The read-back is the point: the API stores whatever it is given and never parses the Go template, so a truncated or mis-escaped push is invisible until an alert renders blank. Both `$( )` substitutions strip trailing newlines, so the file's final newline does not fail the comparison. `X-Disable-Provenance` matches the precedent already used on the policy tree and keeps the object editable in the UI for an emergency tweak.

**Change B — `upsert_slack_integration` gains two parameters** (`title_tmpl`, `body_tmpl`) which land in the payload as `settings: {url: $url, title: $title, text: $text}`, and the two call sites pass **single-quoted** references so `{{`, `}}` and the bare `.` survive bash untouched:

```bash
upsert_slack_integration "zcrypto-slack-metrics" "metrics" false \
  '{{ template "zcrypto.slack.title.metrics" . }}' '{{ template "zcrypto.slack.body.metrics" . }}'
upsert_slack_integration "zcrypto-slack-logs" "logs" true \
  '{{ template "zcrypto.slack.title.logs" . }}' '{{ template "zcrypto.slack.body.logs" . }}'
```

**Change C — the existing contact-point read-back verify asserts the reference is still there**, by adding to its `jq` predicate `((.settings.title // "") | test("zcrypto\\.slack\\.title"))` and the matching `.settings.text` clause. This is what catches a contact point silently reverted to the stock template — otherwise that reappears weeks later as "the messages look like they used to" with nobody sure when. Whether `title`/`text` read back unredacted is **medium confidence** (`url` is the integration's only secure field); if the first push shows them redacted, drop to a presence-only assertion and say so in the comment rather than deleting the guard.

Ordering is load-bearing: A before B. A contact point whose `{{ template }}` target does not exist renders an **empty** body, Grafana accepts that without complaint, and Slack then rejects the message.

Orphan handling stays out: renaming a `.tmpl` leaves the old object live, but unlike an orphaned *rule* — which keeps evaluating and paging, the reason the prune block exists — an orphaned template is inert because nothing references it. If a prune is ever added it must be scoped by a `zcrypto-` name prefix so a UI-authored template is never deleted.

### The templates

`infra/grafana/notification-templates/zcrypto-slack.tmpl`, in full. It carries no traceability tokens by construction — the reasoning lives here, and the file's own comments say only what the syntax requires — because a Slack message is the most operator-facing surface in the fleet (D13's guard is widened to `*.tmpl` in the same change).

````gotemplate
{{/* Slack notification templates for the metrics and logs receivers.                     */}}
{{/* Slack mrkdwn is NOT Markdown: bold is *single-asterisk*, links are <url|label>, and   */}}
{{/* & < > must be HTML-escaped in every human string -- inside code fences too. An        */}}
{{/* attachment TITLE is not mrkdwn at all: emoji and plain text only there.               */}}

{{/* ---------- shared partials ---------- */}}

{{- define "zcrypto.esc" -}}
{{ . | reReplaceAll "&" "&amp;" | reReplaceAll "<" "&lt;" | reReplaceAll ">" "&gt;" }}
{{- end -}}

{{- define "zcrypto.url" -}}
{{ . | reReplaceAll "&" "&amp;" }}
{{- end -}}

{{- define "zcrypto.where" -}}
{{- with .Labels.host }}`host={{ template "zcrypto.esc" . }}`{{ end }}
{{- range .Labels.SortedPairs }}
{{- if and (ne .Name "alertname") (ne .Name "grafana_folder") (ne .Name "severity") (ne .Name "instance") (ne .Name "job") (ne .Name "host") (ne .Name "msg") (ne .Name "datasource_uid") (ne .Name "ref_id") }}  `{{ .Name }}={{ template "zcrypto.esc" .Value }}`{{ end }}
{{- end }}
{{- end -}}

{{- define "zcrypto.value" -}}
{{- range $k, $v := .Values }}
{{- if eq $k "A" }}  measured {{ printf "%.4g" $v }}{{ with $.Annotations.unit }} {{ . }}{{ end }}{{ end }}
{{- end }}
{{- end -}}

{{- define "zcrypto.link" -}}
{{ if .PanelURL }}👉 <{{ template "zcrypto.url" .PanelURL }}|open the panel>
{{- else if .DashboardURL }}👉 <{{ template "zcrypto.url" .DashboardURL }}|open the board> -- this rule names a board but no panel
{{- else }}👉 <{{ template "zcrypto.url" .GeneratorURL }}|open the rule and its query> -- no dashboard panel is pinned on this rule
{{- end }}
{{- end -}}

{{- define "zcrypto.errctx" -}}
{{- with .Labels.ref_id }}
the query that failed is `{{ . }}` -- this is the rule's error state, not its condition
{{- end }}
{{- end -}}

{{- define "zcrypto.silence" -}}
{{- with .SilenceURL }}<{{ template "zcrypto.url" . }}|silence this alert>{{ end -}}
{{- end -}}

{{/* ---------- metrics receiver ---------- */}}

{{- define "zcrypto.slack.title.metrics" -}}
{{ if eq .Status "resolved" }}✅ {{ else if eq .CommonLabels.severity "critical" }}🔴 CRITICAL · {{ else }}🟠 WARNING · {{ end }}{{ .CommonLabels.alertname }}{{ with .CommonLabels.host }} · {{ . }}{{ end }}{{ if gt (len .Alerts.Firing) 1 }} ×{{ len .Alerts.Firing }}{{ end }}
{{- end -}}

{{- define "zcrypto.slack.body.metrics" -}}
{{ with .CommonAnnotations.summary }}{{ template "zcrypto.esc" . }}
{{ end }}
{{- range $i, $a := .Alerts }}{{ if eq $i 0 }}{{ template "zcrypto.link" $a }}{{ template "zcrypto.errctx" $a }}
{{ end }}{{ end }}
{{- range $i, $a := .Alerts }}{{ if lt $i 6 }}
• {{ template "zcrypto.where" $a }}{{ template "zcrypto.value" $a }}  · since {{ $a.StartsAt.UTC.Format "02 Jan 15:04 UTC" }}
{{- end }}{{ end }}
{{- if gt (len .Alerts) 6 }}
• …{{ len .Alerts }} instances in total; the first 6 are shown.
{{- end }}
{{ range $i, $a := .Alerts }}{{ if eq $i 0 }}{{ template "zcrypto.silence" $a }}{{ end }}{{ end }}
{{- end -}}

{{/* ---------- logs receiver ---------- */}}

{{- define "zcrypto.slack.title.logs" -}}
{{ if eq .Status "resolved" }}✅ {{ else if eq .CommonLabels.severity "critical" }}🔴 CRITICAL · {{ else }}🟠 WARNING · {{ end }}{{ .CommonLabels.alertname }}{{ with .CommonLabels.host }} · {{ . }}{{ end }}{{ if gt (len .Alerts.Firing) 1 }} · {{ len .Alerts.Firing }} distinct lines{{ end }}
{{- end -}}

{{- define "zcrypto.slack.body.logs" -}}
{{ with .CommonAnnotations.summary }}{{ template "zcrypto.esc" . }}
{{ end }}
{{- range $i, $a := .Alerts }}{{ if eq $i 0 }}{{ template "zcrypto.link" $a }}{{ template "zcrypto.errctx" $a }}
{{ end }}{{ end }}
{{- range $i, $a := .Alerts }}{{ if lt $i 5 }}
• {{ template "zcrypto.where" $a }}{{ template "zcrypto.value" $a }}
{{- with $a.Labels.msg }}
```
{{ template "zcrypto.esc" . }}
```
{{- end }}
{{- end }}{{ end }}
{{- if gt (len .Alerts) 5 }}
• …{{ len .Alerts }} distinct lines matched; the first 5 are shown.
{{- end }}
{{- range $i, $a := .Alerts }}{{ if and (eq $i 0) (not $a.Labels.msg) }}
This rule counts matching lines rather than carrying them, so there is no log text to quote — open the board above for the window shown.
{{- end }}{{ end }}
{{- end -}}
````

The inner triple-backtick pair is the Slack code fence the template emits around a log line; this block is fenced with four backticks so the file renders — the `.tmpl` itself carries three.

Three shapes are defensive rather than stylistic, and one of them corrects an earlier error in this section.

`{{ range $i, $a := .Alerts }}{{ if eq $i 0 }}` replaces `index .Alerts 0`, which **panics** on an empty slice — and a Go template execution error produces a mangled notification, not a retry.

**`not $a.Labels.msg`, never `eq $a.Labels.msg ""`.** This section previously asserted that a missing key on the label map returns the empty string rather than erroring. That is true only under `missingkey=zero`; under Go's **default** option a missing key yields an *invalid* value, and `eq` then returns **false without erroring** — so the dead-canary sentence became silently unreachable on exactly the seven unlabelled absence-fired alerts it exists for. Measured, not reasoned: the template was parsed and executed against Grafana-shaped structures under both options, independently by two agents. `not` reaches the branch under **both**, and suppresses correctly on a present `msg` under both. Which option Grafana sets is unverifiable offline, which is precisely why the form that does not depend on the answer is the right one.

**`{{ if }}…{{ else }}…{{ end }}` on the host line, never `with`.** `with` renders *nothing* when the label is absent, and two rule summaries lean on this field by name — `Capture · every book stream on a host is silent` says "check the capture container on the named host", `Access · WireGuard tunnel stale` says "the host this notification names". A blank there makes those summaries false; the `else` branch states the absence instead.

### Worked example — `Reconciler · residual gap increased (permanent loss)`

Critical, `for: 0s`, `A → C`, and the binary `and` in its expression preserves the left side's full label set — so this instance carries `host`, `instance` **and** `job`, which makes it the sharpest illustration of the dedupe decision. Payload: one firing alert, `Values {A: 2437, C: 1}`.

**Today** (Grafana's stock `default.title` / `default.message`; reconstructed, and confirmed byte-for-byte at the first test fire below):

```
[FIRING:1] Reconciler · residual gap increased (permanent loss) zcrypto (ops <instance> <job> critical)

**Firing**

Value: A=2437, C=1
Labels:
 - alertname = Reconciler · residual gap increased (permanent loss)
 - grafana_folder = zcrypto
 - host = ops
 - instance = 127.0.0.1:12345
 - job = <Alloy's default; the ops host-scrape component sets no job_name>
 - severity = critical
Annotations:
 - summary = Permanent L2 loss: silence that NEITHER capture host covered. …
Source: https://zcrypto2026.grafana.net/alerting/grafana/zcrypto-reconcile-residual-gap/view?orgId=1
Silence: https://zcrypto2026.grafana.net/alerting/silence/new?…
```

Sixteen lines. `**Firing**` renders with its asterisks visible. The folder name appears twice. `A=2437` has no unit and `C=1` means nothing. Severity is the last word of the title, behind two labels that identify nothing.

**After**, with `unit: "seconds of unrecoverable silence"` and the D9 pointer on the rule — this is the raw mrkdwn Grafana sends as the attachment's `text`, under the title `🔴 CRITICAL · Reconciler · residual gap increased (permanent loss) · ops`:

```
Permanent L2 loss: silence that NEITHER capture host covered. This cannot be healed or backfilled -- the data is gone. Check the reconcile ledger for the records behind it: both_streams_silent or total_loss for correlated loss, or a minted/would_mint hour whose splice left seconds unfilled -- any of the three can drive this.
👉 <https://zcrypto2026.grafana.net/d/zcrypto-integrity?viewPanel=<the gap panel's id on the rebuilt board>|open the panel>
• `host=ops`  measured 2437 seconds of unrecoverable silence  · since 04 Aug 09:14 UTC
<https://zcrypto2026.grafana.net/alerting/silence/new?…&amp;orgId=1|silence this alert>
```

Four lines instead of sixteen; `instance`, `job`, `grafana_folder`, `C=1` and the word "Firing" are gone; the number has a unit; the panel link is line two. Without the D9 annotations, line two would instead read `👉 <…/alerting/grafana/zcrypto-reconcile-residual-gap/view?orgId=1|open the rule and its query> -- no dashboard panel is pinned on this rule`.

### Verification — fire into the live channel and iterate from what Slack renders

**Owner's decision: the templates are verified by firing test alerts into the live channel the webhook posts to (`#zcrypto`) and reading the rendered message back**, iterating on what Slack actually shows rather than on what the template ought to produce. Spec `00043` set the precedent and the constraint: each rule is test-fired once during shakedown **without breaking production** — nothing on the unbackfillable capture path or the live trade path is stopped, degraded or restarted to make a rule fire.

**The cheapest deliberate trip is a throwaway probe rule**, because it needs no host to be touched at all: a rule with its own uid in `alerts.yaml`, receiver `metrics`, `severity: critical`, a representative `summary`, a `unit:` annotation and a D9 pointer, whose expression is `count by (host) (up) > 0`. It fires immediately with **five** instances, which exercises the ×N title, the label line, the value line, the panel link and the silence link in one message, and reads nothing but `up`. A second probe on receiver `logs`, expressed as the hoist query above over `{host="ops"}` with a short window, is what proves the `msg` label renders inside its code fence end-to-end — the one mechanism in this section that cannot be verified any other way. The query half needs no probe: the hoist is already confirmed against live Loki, on both line shapes, with a negative control on the `drop` stage. What remains unproven is Slack's rendering of it.

**Un-tripping is by expression, then by prune**: flip the probe's expression to one that cannot match (`vector(0)` under the same `> 0` threshold) and re-push — on `metrics` that is a genuine firing→resolved transition, so the ✅ resolved rendering gets verified deliberately rather than incidentally; then remove the rule from `alerts.yaml`, re-push, and delete the orphan with `GRAFANA_PRUNE=1` after confirming the orphan report names **exactly** that uid.

**The two receivers behave differently on recovery, and the test must show both**: `metrics` has resolve messages ON, so every firing alert is followed by a ✅ message whose title and body come from the *same* templates with `.Status == "resolved"`; `logs` has them OFF, so a logs alert never sends a recovery message and the ✅ branch of `zcrypto.slack.title.logs` is unreachable in production — it stays in the template as a safety net, and the test confirms silence rather than a message.

**The cheapest real rule to trip** — 00043's `logger.error` probe, for the half a synthetic rule cannot cover — is `Ops · ERROR logs`: warning, `for: 0s`, receiver `logs`, and its selector `{host="ops", level=~"ERROR|CRITICAL"}` matches an ERROR line from **any** ops container, so one harmless line on the compute tier trips it and the 15-minute `count_over_time` window un-trips it on its own. `Capture · daemon ERROR logs` is the same shape but lives on the unbackfillable host; prefer ops.

**Guard-proving is part of this, not after it** (`agent-ops.md`): truncate the `.tmpl` mid-file and confirm Change A exits non-zero; revert a contact point to `settings: {url}` only and confirm Change C exits non-zero. A guard that has not been seen to trip is unproven, and a red exit from the wrong check proves nothing.

### Failure modes pinned

Ranked by likelihood of biting, and each one is why some line above looks the way it does.

1. **`<`, `>`, `&` are Slack control characters** — `<foo>` is parsed as a link and vanishes, `&` can truncate — and Grafana does not escape for you. Eight summaries already carry `>`, and arbitrary log text carries all three. Hence `zcrypto.esc` on every human string, in the order **`&` first, then `<`, then `>`** (the reverse order double-escapes), **including inside code fences**, where Slack still parses `<…>`. URLs take `zcrypto.url` (`&` only) instead, which is what Slack documents for links; escaping a URL with `zcrypto.esc` breaks it.
2. **Slack mrkdwn is not Markdown.** Bold is single-asterisk, links are `<url|label>` and never `[label](url)`, and headings do not exist. A `>` at the *start* of a line is a blockquote; the `>` → `&gt;` escaping removes that hazard structurally rather than by luck.
3. **An attachment title is not mrkdwn at all** — no bold, no link syntax, no inline code — and Grafana sets `title_link` to the rule URL, so the title is expected to be clickable without help (confirm at the first fire before adding anything). Severity prominence therefore has to be a literal Unicode emoji, not a `:red_circle:` shortcode and not `*CRITICAL*`.
4. **Length limits, one of which fails silently-ish.** Legacy attachment `text` is truncated around 8 000 characters and the whole payload capped far higher; with `msg` labels that is reachable, hence `topk(5, …)` in the rule *and* the `lt $i 5` cap in the template — belt and braces, because `topk` protects the query and the template protects against a rule that forgets it. Separately: setting `mentionChannel` / `mentionUsers` / `mentionGroups` on either contact point switches Grafana's payload to Block Kit, where a section's text is hard-capped at 3 000 characters and Slack rejects the **entire** message — a page that is simply never delivered. Do not add mentions without re-checking the cap.
5. **Many instances at once is now the normal case, not the tail.** D11's label-ungrouping raises per-rule instance counts on purpose — `Access · edge cert expiring` from 1 to up to 3, `Access · WireGuard tunnel stale` to one per end, `Capture · Kraken reports the venue is not online` to one per `(host, system)` — and the new `Capture · a book stream has stopped delivering` does not aggregate at all, so it can raise **one instance per (host, pair): 12 pairs × 2 hosts = 24 in a single message**. That is what the 6-instance cap plus the `…N instances in total` line exists for, and it is why the caps are the first thing to re-tune from a real fire.
6. **One webhook, ~1 message/second, and a dropped notification is lost rather than queued.** Both receivers share the webhook, and a fleet-wide event bursts past it. Grouping is what keeps this survivable — one rule's N instances arrive as one message — so **`group_by` must not be widened to include `host` or `msg`**, which would turn the `msg` design into one message per log line. The root policy's grouping is **not managed by this repo** (`grafana-push.sh` mutates only `.receiver` on the tree), so read it back from `/api/v1/provisioning/policies` and record it rather than assuming Grafana's default still applies.
7. **`.CommonLabels.severity` is empty if a group ever spans mixed severities.** It cannot today — grouping includes `alertname`, and one rule carries exactly one severity — and the template's `else` branch falls through to 🟠 WARNING rather than erroring, which is the safe direction.
8. **`printf "%.4g"`, not `%v`.** `%v` on a float64 gives `1.2345678e+07` for large values and `0.30000000000000004` for ratios; `%.4g` gives `2437`, `0`, `1.5`, `0.3`. No rule in `alerts.yaml` produces raw byte counts, so scientific notation is not reachable in practice.
9. **A log line containing three consecutive backticks breaks the fence.** Unlikely in this fleet's Python output; noted rather than defended against, and it is one of the things a real fire would show.

## D13 — The operator-vocabulary guard has a naming trap; close it

`tests/test_internal_terms_not_operator_visible.py` walks `(REPO / "infra/grafana").glob("*dashboard*.json")`. Both current files happen to match. **A new board named `fleet-health.json` would sit silently outside the guard** — and the existing `assert out, "walked no dashboard text — the glob is broken, not the dashboards clean"` only fires if *all* dashboards vanish, never if one is added under a non-matching name.

Fix: **widen the glob to `*.json`** (the directory holds only dashboards and `alerts.yaml`). A guard whose coverage depends on nobody forgetting a filename convention is not a guard.

**A second, sharper naming trap sits underneath it, in the opposite direction.** `grafana-push.sh` iterates `infra/grafana/*-dashboard.json` — **narrower** than the test's glob. So a board named `fleet-health.json` would (after this fix) be vocabulary-checked and then **never pushed at all**, silently: the file is committed, the test is green, and the board simply does not exist in Grafana. That is worse than the leak this section started with, because nothing anywhere reports it.

So the three new boards are named to the push glob — `fleet-health-dashboard.json`, `data-integrity-dashboard.json`, `engine-dashboard.json` — and the test gains an assertion that closes the gap by construction: **every `*.json` under `infra/grafana/` matches the push script's `*-dashboard.json` pattern.** One file, two globs, and the wider one now proves the narrower one cannot be missed.

Consequence for this spec's own content: panel titles and descriptions are operator-visible surfaces under `operator-facing-text.md`, so no `T<NNNN>`, `spec <NNNNN>`, `iter-<N>`, or `Phase <N>` may appear in any of them. The reasoning behind a panel goes in this spec; the panel says what it shows.

## D14 — Series budget

Panels consume no series — they query families that already ship. The only series-adding change in this spec is D10(a): `node_scrape_collector_success` on one host, which node_exporter emits once per collector.

Measured at rollout against spec `00043`'s <1k target and `00069`'s per-host baseline (nas 144, ops 308, zcrypto 134, zcrypto-red 108), recorded in the closeout — measured, never assumed, per `00069` D9.

## D15 — Testing (TDD)

- **`tests/test_dashboards_cover_metrics.py`** (new, D8): the three assertions, each failing with the *specific* uncovered family and its origin — never a bare "coverage failed". Family extraction from PromQL must not mistake label values, function names, duration literals, or label keys for families; the approach and its failure modes are stated in the test's own docstring.
- **Guard proving** (D8, mandatory): revert D10(a)'s keep-regex line and confirm assertion 3 fails naming `node_scrape_collector_success` on `zaccess`; restore. A guard that has not been seen to trip is unproven.
- **`tests/test_infra_alloy_series.py`**: the access `required` list gains the new family.
- **`tests/test_internal_terms_not_operator_visible.py`**: the widened glob, plus a case proving a non-`*dashboard*`-named file is now walked.
- **Dashboard JSON validity**: every committed board parses, every panel target carries a non-empty `expr`, every `expr` is host-scoped (D6) — the machine-checkable half of the panel review. Plus: all three metric boards set `graphTooltip: 1` (D1), and no alert rule title or panel text contains a hostname (D6's naming table).
- **The two engine gauge fixes** (D4), against a fake registry with no live engine: a dropped asset's target-weight series is **gone** after the next cycle, not zeroed; `cycle_duration` is **absent** rather than `0` before the first cycle of a fresh process. Both fail on today's code, which is what makes them the fix's proof.

**Owner steps at closeout — the tooling cannot do these:**

- **Delete the deprecated `zcrypto-main` board** in the Grafana UI (D1). `grafana-push.sh` has no dashboard-delete path, so it survives every push. Do it *after* the new three are verified live, so no window exists with neither.
- **Confirm no saved Grafana silence** was keyed on one of the six retitled alert rules (D6). Rule uids are unchanged, so only silences matching on `alertname` are affected, and there are none today — this is a re-check at push time, not an expected failure.

## Out of scope

- **Executed order / position / PnL panels** — those families do not exist; they arrive with [[T0018]]'s 6b executor and join the `engine` board then. Registered in T0018, not deferred in prose.
- Widening the `zaccess` keep-regex beyond the one alert-backed family (D10a).
- Grafana Cloud retention/usage tuning; alert threshold re-tuning beyond the rules D11 adds or corrects.
- **Re-labelling the `host="primary"` / `host="secondary"` strays — now root-caused, and deliberately left alone.** Spec `00069` and [[T0020]] both recorded two anomalous `host` label values at one series each as un-root-caused. They are `zcrypto_reconcile_trade_deficit_rows_total`: `cli/archive/command.py` emits it with its **own** `host` label carrying a mirror *side* (`{host="primary"}`, `{host="secondary"}`), and `external_labels` only stamps a label that is absent, so `host="ops"` never lands on that family. Consequences are handled rather than fixed: D3's panel selects `host=~"primary|secondary"` and says why, and D2 pins the `$host` variable's regex so the two values stay out of every dropdown. **Renaming the label is out of scope** — it changes series identity under an `increase()`, which is the same hazard the fleet took knowingly and once, at a chosen window, for the NAS host label.

## Cross-topic records — updated at THIS iteration's closeout

Following `00069`'s convention: the closeout follows the rollout, so every update records measured facts.

- [[T0020]] — **resolves in full**. All sub-items land here: the dashboards package, the recent-delta pairing, the JSON-log render fix, and the 2026-07-21 untriaged additions (tags, titles, the stale per-node charts, both Slack template reworks).
- [[T0018]] — its metrics bullet gains the execution-panel handoff: the families it emits are charted on the `Engine` board; they must be **named so intent versus execution is unambiguous at `/metrics` level**, and the existing intent families must **not** be renamed to match — they are live series and a rename changes series identity.
- [[T0044]] — its correction-marker sub-item gains an **anchor** (added 2026-08-04, this branch): the emit site (`_write_textfile`'s `_emit` helper), the fact that the ops keep-regex's `zcrypto_reconcile_.*` wildcard needs no change, and the panel that would carry it. The decision itself stays T0044's. D7's `resets()`-guarded panels *raise* its value — after a correction those panels now correctly read zero, which also makes the correction invisible, which is the discontinuity the marker exists to explain.
- **No T0127.** The two engine gauge-lifecycle defects this design surfaced are **fixed in this iteration** (D4), not registered. Standing ruling, owner, 2026-08-04: a newly surfaced defect whose fix is in application logic or code is fixed in the iteration that finds it — an extra converge is a bounded cost, where a `ripe_when:` hanging on an unscheduled activity is an unarmed trigger that quietly makes the topic permanent. The topic file opened earlier on this branch is deleted in the same change that folds the work in.

**A topic deliberately NOT listed: [[T0106]].** It is resolved and archived, and this iteration neither reopens nor amends it. Recording it here would have implied a live caveat, and an earlier draft of D3 made exactly that error — describing the logship false red as an ongoing hazard the board renders visible. It is not: T0106 *replaced the signal* rather than documenting the caveat, and D3 now simply follows that resolution. **The general check this earns:** before listing a topic in a cross-topic section, confirm it is open — a resolved topic named as though it were live re-opens a settled question for whoever reads next.
