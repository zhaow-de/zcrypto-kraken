---
status: resolved
---

# One-off timer metrics have no transport on the capture hosts

## Context — what

The capture hosts (`zcrypto`, `zcrypto-red`) run **no node-exporter textfile collector**: `infra/ansible/roles/capture/files/config.alloy:27-30` drops it, and the compose file mounts no textfile directory. Spec `00069` moved **long-lived** services to `/metrics` endpoints Alloy scrapes, and the collector was dropped alongside — for a reason that was **contingent, not principled**, stated in that same comment: *"there is no gate/replay/archive timer on them."*

A **one-off** timer has no process to scrape. `/metrics` cannot express it. The ops node still runs the textfile collector for exactly this reason (its four ephemeral timers). So the moment a one-off timer landed on a capture host, it had nowhere to publish — and one has.

## Why this matters

Two independent surfaces were already affected before this was noticed, and both failed **silently**:

1. **T0021's engine-journal prune (spec `00070`, deployed 2026-07-26) is observable through nothing.** It was built with a `--textfile` flag, which was then deliberately not passed on the reasoning that no collector would read it. The reasoning was correct and the conclusion was backwards — the fix is to add the reader. The fallback claimed in its place is *also* false: `config.alloy:161`'s journal keep-regex admits only `zcrypto-capture-prune.service` and Alloy's own stream, so the prune's log line reaches host journald and is **never shipped to Loki**.
2. **T0027's attended-reboot detector** was specified against a transport that does not exist on its target hosts ("the same `integrations/unix` transport that already carries the NAS `gate.prom`" — and `integrations/unix` is static-mode Grafana Agent vocabulary this flow-mode fleet does not use).

There is a third, quieter hazard: `config.alloy:132`'s `write_relabel_config` is an explicit `__name__` **allow-list with no `node_.*` wildcard**. Even once a `.prom` is published and scraped, an unadmitted series is dropped at the remote-write boundary — indistinguishable from a producer that never ran. `node_textfile_scrape_error` is likewise absent from the capture keep-list, though ops and nas both carry it.

## Findings so far

- Verified directly, not inferred: `set_collectors = ["cpu", "loadavg", "meminfo", "filesystem", "netdev"]` — no `textfile`; `grep -rn textfile infra/ansible/roles/capture/` returns only comments.
- **The fix needs no compose edit.** Alloy already mounts `/:/host/root:ro` (`alloy-compose.yaml.j2:62`), and the textfile collector's `directory` is just a container path it globs — unrelated to `rootfs_path`. Pointing it at `/host/root/var/lib/...` avoids recreating the Alloy container.
- **Precedent: this exact failure already happened once, on ops.** `roles/ops/files/config.alloy:67-69` records its four timers' textfiles as *"written since OPS-3/OPS-4 into `ops_textfile_dir` but scraped by nothing until this task"* — producer shipped, reader forgotten.
- A **stale** `.prom` is not a `node_textfile_scrape_error` (that fires only on malformed input). A stopped timer leaves its last file in place and the collector serves those values forever — so freshness must be its own gauge.

## Resolution

**Resolved 2026-07-26** by spec `00071`, deployed and verified the same evening.

The textfile collector is enabled on both capture hosts, pointed at `/host/root/var/lib/zcrypto-node-textfile` through the **already-present** `/:/host/root:ro` mount — so no compose edit and no volume change. One-off timers publish a `.prom`; long-lived services keep `/metrics`. That rule is now stated in `config.alloy` itself, replacing the expired premise that justified dropping the collector.

**Three failure modes, three rules** — the design turned on the fact that each defeats the rule catching the others. A *stale* `.prom` is not a scrape error (the collector serves the last values forever); an *unreadable* one is; and an *absent* series defeats both, because a staleness rule cannot fire on something that does not exist and `noDataState: OK` renders that silence green. So: `node_textfile_mtime_seconds` per publisher (1 h for the 15-minute reboot probe, 26 h for the daily prune — one shared window would have let the attended-reboot net sit dead for a day), `node_textfile_scrape_error`, and `count(node_reboot_required) < 2`.

**The review caught the defect reproducing itself one layer down.** `mktemp` creates `0600` and `mv` *preserves* it, so the retro-fixed prune published root-only while Alloy reads as non-root — measured `600` against the new detector's `644`, because the `chmod` was written into the new script and not into the one being retro-fixed. It would have shipped inert, and the staleness rule could not have surfaced it: the collector skips an unreadable file *before* stamping its mtime, so there was no series to go stale. Both suites now pin the mode.

**Verified end-to-end against Grafana Cloud**, not inferred from a converge exit code:

- `zcrypto_engine_journal_prune_kept_days{host="zcrypto"} = 16` and `oldest_day_age_seconds = 1377233` — [[T0021]]'s prune is observable at last, including the fourth series the allow-list had been dropping silently.
- `node_reboot_required` = 0 on **both** capture hosts; touching `/run/reboot-required` flipped it to 1 and removing it returned it to 0.
- `node_textfile_mtime_seconds` carries the `file` label the staleness rules key on, for all three published files.
- `node_textfile_scrape_error` = 0 on all four hosts.

The journal keep-regex now also admits `zcrypto-engine-journal-prune` and `zcrypto-reboot-check`, so their log lines reach Loki too. `zcrypto-capture-prune` still publishes no metric — it predates the transport and is outside the staleness alerts' coverage, recorded in `infra/runbooks/hosts.md`.
