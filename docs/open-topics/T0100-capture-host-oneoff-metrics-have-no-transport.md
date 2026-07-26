---
status: open
ripe_when: NOW — it is being closed by the T0027 iteration (spec 00071); it is registered separately because it is a distinct defect with its own victims, and because archiving T0021 while it was live was a miss
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

## Suggested next steps

- **Add the textfile collector to the capture-host Alloy** via the existing `/host/root` mount, admit the new series (and `node_textfile_scrape_error`) to the keep-list, and add them to `tests/test_infra_alloy_series.py`'s `CAPTURE_REQUIRED` so the regex edit is TDD-gated. Closed by spec `00071`.
- **Retro-fix T0021**: pass `--textfile` in the prune unit and restore its `ReadWritePaths` entry; add `zcrypto-engine-journal-prune.service` to the journal keep-regex so its log line ships too.
- **Alert on freshness, not just value** — a prune-liveness rule on `_last_run_timestamp_seconds`, which is the alert whose absence made this gap invisible.
- **Correct the durable record**: spec `00070` D5, the archived [[T0021]] resolution, and the phase-6 changelog entry all currently argue *for* the wrong conclusion and would mislead the next reader. Rewrite in place, never appended-to.
