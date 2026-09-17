---
status: open
ripe_when: 2026-10-01 — a second fortnight of reconnects on the board to set the bar against, read as `uv run python infra/scripts/grafana-query.py 'sum by (host) (increase(zcrypto_capture_reconnects_total[13d]))'`
---

# The primary's clean-close reconnect rate is charted and never alerted

## Context — what

`zcrypto_capture_reconnects_total` counts every reconnect attempt of a capture daemon; the data-integrity board charts it and no rule in `infra/grafana/alerts.yaml` reads it. The reconciler's healable-gap counter, which `zcrypto-reconcile-healable-gap-rate` watches, books only primary silence longer than its 30 s floor, and a clean-close reconnect resubscribes in 2-8 s, so a rising reconnect rate is invisible to that rule at any magnitude.

## Why this matters

Over the 13 days to 2026-09-17 the primary reconnected 98 times, 7.5 a day against the roughly 8.2 a day `compute_backoff`'s docstring in `cli/capture/ws_client.py` records as the baseline, and moved the healable counter twice, both times at its own converges. The rate is ordinary today and nothing would say when it stops being: a host reconnecting ever more often is the degrading-primary shape the healable rule was written to reveal, and this is the arm of it that rule cannot see.

## Findings so far

- Measured 2026-09-17 from the workstation: `sum by (host) (increase(zcrypto_capture_reconnects_total[13d]))` read 98 on `zcrypto` and 91 on `zcrypto-red`; over `[24h]`, the day after a primary converge, 15 and 12. The counter counts loop iterations, so it bounds distinct drops from above.
- The two classes and their cost, from `cli/capture/ws_client.py` and the websockets library defaults: a clean close costs backoff plus handshake plus resubscribe, 2-8 s; a silent death is noticed by the keepalive 20-40 s after the last frame, 22-48 s in all, and only that class crosses the reconciler's floor.
- The healable rule's comment names this blind spot since the 2026-09-17 re-derivation of its bar.

## Suggested next steps

- Decide the shape: a warning on `increase(zcrypto_capture_reconnects_total[24h]) > <bar>` per host, the bar a multiple of the baseline read from two fortnights of the board's reconnect panel (`infra/grafana/data-integrity-dashboard.json`, the targets naming `zcrypto_capture_reconnects_total`), with a runbook section under `infra/runbooks/capture.md` carrying its `Retire when`.
- Read the secondary's rate beside the primary's before choosing the bar: both hosts share the venue edge, so a rise on both is the venue and a rise on one is the host.
