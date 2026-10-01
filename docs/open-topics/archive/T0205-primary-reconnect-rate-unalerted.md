---
status: resolved
---

# The primary's clean-close reconnect rate is charted and never alerted

## Context — what

`zcrypto_capture_reconnects_total` counts every reconnect attempt of a capture daemon; the data-integrity board charts it and no rule in `infra/grafana/alerts.yaml` reads it. The reconciler's healable-gap counter, which `zcrypto-reconcile-healable-gap-rate` watches, books only primary silence longer than its 30 s floor, and a clean-close reconnect resubscribes in 2-8 s, so a rising reconnect rate is invisible to that rule at any magnitude.

## Why this matters

Over the 13 days to 2026-09-17 the primary reconnected 98 times, 7.5 a day against the roughly 8.2 a day `compute_backoff`'s docstring in `cli/capture/ws_client.py` records as the baseline, and moved the healable counter twice, both times at its own converges. The rate is ordinary today and nothing would say when it stops being: a host reconnecting ever more often is the degrading-primary shape the healable rule was written to reveal, and this is the arm of it that rule cannot see.

## Findings so far

- Measured 2026-09-17 from the workstation: `sum by (host) (increase(zcrypto_capture_reconnects_total[13d]))` read 98 on `zcrypto` and 91 on `zcrypto-red`; over `[24h]`, the day after a primary converge, 15 and 12. The counter counts loop iterations, so it bounds distinct drops from above.
- The two classes and their cost, from `cli/capture/ws_client.py` and the websockets library defaults: a clean close costs backoff plus handshake plus resubscribe, 2-8 s; a silent death is noticed by the keepalive 20-40 s after the last frame, 22-48 s in all, and only that class crosses the reconciler's floor.

## Resolution

**Resolved 2026-10-01 by `zcrypto-capture-reconnect-rate` in `infra/grafana/alerts.yaml`, its section `infra/runbooks/capture-daemon.md#zcrypto-capture-reconnect-rate` and `tests/test_infra_alert_rules.py::test_the_reconnect_rate_pages_per_host_over_a_day_at_the_count_its_summary_states`, the bar of 30 the owner's pick from the board's two fortnights.** The second, read per day on the trigger's date with `sum by (host) (increase(zcrypto_capture_reconnects_total{host=~"zcrypto|zcrypto-red"}[24h] offset Nd))` for N = 0..13 (the board retains 14 days): the primary 124 reconnects, 8.9 a day, the busiest day 17; the secondary 108, 7.7 a day, busiest 16. With the first fortnight's 7.5 and 7.0 a day, the baseline is 7 to 9 a day per host, and 30 is about 1.8 times the busiest day.
