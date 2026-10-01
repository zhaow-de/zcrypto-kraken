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
- The healable rule's comment names this blind spot since the 2026-09-17 re-derivation of its bar.

## Resolution

**Resolved 2026-10-01 by `zcrypto-capture-reconnect-rate`, the bar the owner's pick from the board's two fortnights.** The second fortnight, read per day on the trigger's date with `sum by (host) (increase(zcrypto_capture_reconnects_total{host=~"zcrypto|zcrypto-red"}[24h] offset Nd))` for N = 0..13 (the board retains 14 days): the primary 124 reconnects, 8.9 a day, the busiest day 17, the quietest 1; the secondary 108, 7.7 a day, busiest 16, quietest 3. With the first fortnight's 7.5 and 7.0 a day, the baseline is 7 to 9 a day per host, and the high days came in pairs on both hosts (14 and 16, 12 and 14, 14 and 12 on 2026-09-30, a converge day for both) — the venue or our own converges, never one host alone.

- **The rule**, in `infra/grafana/alerts.yaml`: `increase(zcrypto_capture_reconnects_total{host=~"zcrypto|zcrypto-red"}[1d]) > 30` per host, `for: 30m`, `noDataState: OK`, a warning on the metrics receiver, linked to the integrity board's panel 103 that already charted the counter. 30 is about 1.8 times the busiest day measured. The healable-gap rule's comment now names it in place of the blind spot.
- **The runbook**, `infra/runbooks/capture-daemon.md#zcrypto-capture-reconnect-rate`, with its `Retire when`: both hosts read first — both high is the venue, one high is that host — our own converge days ruled out from the deploy log, the close reasons read from the daemon's log, and the daemon kept running, since its drops are covered by the other host and a restart costs live L2.
- **The test**, `tests/test_infra_alert_rules.py::test_the_reconnect_rate_pages_per_host_over_a_day_at_the_count_its_summary_states`, pins the expression and that the summary states the threshold's count; `infra/scripts/mutate-probe.sh` with the bar moved to 31, and again with the window narrowed to `[6h]`: KILLED both times, control proven.

The rule reaches Grafana Cloud by the push from merged `develop` that follows this PR's merge, its first sample read by value on both hosts.
