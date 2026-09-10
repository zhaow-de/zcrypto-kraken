# Change index

One row per merged pull request that carries at least one key. A key is an `iter-NNN` iteration serial, a 5-digit spec serial, or a `T<NNNN>` topic id, read from the pull request's own title, branch name and `## Spec / Plan` section — a topic key case-insensitively, since a branch spells it `t0189`, and written with an upper-case T; a cell with no key of that kind is an em dash. The backfilled rows also drew on two sources a pull request does not hold — the iterations-history entry git keeps for the row's iteration, and the trial registry's `spec_hash` resolved through the digest of the spec file it pins — so a cell can name a spec or topic the title does not spell. No file path appears in this file (`test_change_index` asserts it), so a rename sweep has nothing to edit here — a path-shaped title has its `/` written as `-`, a bare `long/flat` keeps it, and titles are truncated to 72 characters. `date` is the date the pull request was created, UTC — the day the row is written. Rows are sorted by pull-request number ascending. The row is written by the `open-pr` skill when the pull request is created, which is also where an iteration's serial comes from: this file's highest `iter` plus one. `test_change_index` guards its shape and its completeness against git.

| PR | date | title | iter | spec | topic |
|---|---|---|---|---|---|
| #3 | 2026-07-07 | feat(registry): iter-1 — trial registry (Phase 0 P0-1) | iter-001 | 00000 | T0000 |
| #4 | 2026-07-07 | feat(snapshot): iter-2 — Kraken reference-data snapshot register (Phase | iter-002 | 00001 | T0000 |
| #5 | 2026-07-07 | docs(research): iter-3 — NautilusTrader Kraken adapter smoke-test memo ( | iter-003 | — | T0000 |
| #6 | 2026-07-07 | feat(ohlc): iter-4 — OHLC ingestion → canonical Parquet (Phase 1 v0) | iter-004 | 00002 | T0001 |
| #7 | 2026-07-07 | feat(universe): iter-5 — rule-driven universe finalization (Phase 1) | iter-005 | 00003 | T0002 |
| #8 | 2026-07-07 | feat(ohlc): iter-6 — OHLC dataset QA report (Phase 1) | iter-006 | 00004 | — |
| #9 | 2026-07-07 | chore: resolve open topics T0000–T0002 (T0002 done; T0000/T0001 partial) | — | — | T0000, T0001, T0002 |
| #12 | 2026-07-07 | feat(backfill): iter-8 — full-history OHLCVT backfill from Kraken 1-minu | iter-008 | 00005 | T0001 |
| #13 | 2026-07-07 | docs: iter-9 — full-history dataset QA report + gap characterization | iter-009 | — | — |
| #14 | 2026-07-07 | feat(ohlc): iter-10 — corporate-action ledger + price-discontinuity audi | iter-010 | — | — |
| #15 | 2026-07-07 | feat(ohlc): iter-11 — empty-interval reconstruction (fill_gaps) | iter-011 | — | — |
| #16 | 2026-07-07 | feat(xcheck): iter-12 — Binance cross-venue cross-check | iter-012 | — | — |
| #18 | 2026-07-07 | feat(validation): iter-13 — CPCV splitter (purge + embargo) | iter-013 | 00006 | — |
| #19 | 2026-07-07 | feat(validation): iter-14 — deflated & probabilistic Sharpe ratio | iter-014 | 00007 | — |
| #20 | 2026-07-07 | feat(validation): iter-15 — PBO (probability of backtest overfitting) | iter-015 | 00008 | — |
| #21 | 2026-07-08 | feat(validation): iter-16 — stationary block bootstrap CIs | iter-016 | 00009 | T0006 |
| #22 | 2026-07-08 | feat(costs): iter-17 — Kraken cost model (fees + margin) | iter-017 | 00010 | — |
| #23 | 2026-07-08 | feat(validation): iter-18 — performance statistics | iter-018 | 00011 | — |
| #24 | 2026-07-08 | feat(registry): iter-19 — trial-registry hash chain | iter-019 | 00012 | — |
| #25 | 2026-07-08 | feat(validation): iter-20 — acceptance suite (recovery + null) | iter-020 | 00013 | — |
| #26 | 2026-07-08 | fix(validation): iter-21 — numeric-param type guards (T0006) | iter-021 | — | T0006 |
| #27 | 2026-07-08 | feat(validation): iter-22 — injected-leak acceptance test | iter-022 | 00014 | — |
| #28 | 2026-07-08 | feat(validation): iter-23 — SPA / White reality check | iter-023 | 00015 | T0003 |
| #30 | 2026-07-08 | feat(backtest): iter-24 — explicit-cost backtester engine | iter-024 | 00016 | — |
| #31 | 2026-07-08 | feat(benchmark): iter-25 — B0 buy-and-hold + B1 vol-target | iter-025 | 00017 | — |
| #32 | 2026-07-08 | feat(benchmark): iter-26 — B0/B1 bar-to-beat report on real BTC | iter-026 | 00018 | — |
| #33 | 2026-07-08 | feat(benchmark): iter-27 — 200-day regime gate (prior survivor) | iter-027 | 00019 | — |
| #34 | 2026-07-08 | docs(benchmark): iter-28 — gated BTC benchmark panel | iter-028 | 00020 | — |
| #35 | 2026-07-08 | feat(benchmark): iter-29 — §9.6 cost-stress panel on the BTC benchmarks | iter-029 | 00021 | — |
| #36 | 2026-07-08 | feat(benchmark): iter-30 — inverse-vol majors basket generator (B2) | iter-030 | 00022 | T0007 |
| #37 | 2026-07-08 | feat(benchmark): iter-31 — B2 inverse-vol basket bar-to-beat (basket vs | iter-031 | 00023 | T0007 |
| #38 | 2026-07-08 | feat(benchmark): iter-32 — complete the basket family (B3 gate + B4 shor | iter-032 | 00024 | T0010 |
| #39 | 2026-07-08 | feat(benchmark): iter-33 — bootstrap-CI significance sections (Phase-3 e | iter-033 | 00025 | T0007 |
| #40 | 2026-07-08 | feat(benchmark): iter-34 — calendar-year regime slices (Phase-3 exit bar | iter-034 | 00026 | — |
| #43 | 2026-07-08 | docs(open-topics): elevate T0007 — full-history basket is A1's opening A | — | — | T0007 |
| #46 | 2026-07-08 | feat(infra): iter-38 — T0003 D2 capture pipeline live (partial) | iter-038 | 00027 | T0003 |
| #47 | 2026-07-08 | feat(tick): iter-39 — tick-derived bar reconciliation + true VWAP | iter-039 | 00028 | T0004 |
| #48 | 2026-07-08 | fix(capture): heal book desync via unsubscribe-then-resubscribe | — | — | T0003 |
| #49 | 2026-07-08 | feat(features): iter-40 — A1 causal feature primitives | iter-040 | 00029 | — |
| #50 | 2026-07-08 | feat(features): iter-41 — complete A1 feature substrate (trend_agreement | iter-041 | 00030 | — |
| #51 | 2026-07-08 | feat(tick): iter-42 — complete-dataset reader + full-history BTC/EUR rec | iter-042 | 00028 | T0004 |
| #52 | 2026-07-08 | docs(tick): iter-43 — full-universe full-history tick reconciliation | iter-042, iter-043 | — | T0004 |
| #53 | 2026-07-08 | docs(alpha): iter-44 — spec the A1 vol-targeted long/flat/short trend bo | iter-044 | — | T0004, T0007, T0010 |
| #54 | 2026-07-08 | docs(capture): T0003 incident resolved + host re-aligned to CI GHCR imag | — | — | T0003 |
| #61 | 2026-07-08 | docs(open-topics): resolve T0004 (reconciliation exit-bar confirmed) | — | — | T0004 |
| #62 | 2026-07-09 | feat(benchmark): iter-44 — full-history dynamic-composition basket + fin | iter-044 | 00032 | T0004, T0007, T0010 |
| #63 | 2026-07-09 | feat(alpha): iter-45 — A1 book assembler + kill-bar harness | iter-045, iter-046 | 00031 | T0009 |
| #64 | 2026-07-09 | feat(alpha): iter-46 — A1 kill-bar verdict (first validated Bucket-A sur | iter-046 | 00031 | T0009 |
| #65 | 2026-07-09 | docs(research): iter-47 — A1 net-of-cost reality (gated-B1 stays deploya | iter-047 | 00031 | T0009 |
| #66 | 2026-07-09 | docs(research): iter-48 — cost-optimized A1 (the short's carry is the ki | iter-048 | — | — |
| #67 | 2026-07-09 | docs(research): iter-49 — A1 long/flat capstone (net-of-cost superior, 2 | iter-049 | — | T0009 |
| #68 | 2026-07-09 | feat(alpha): iter-50 — net-of-cost head-to-head verdict helper | iter-050 | — | T0009 |
| #69 | 2026-07-09 | docs(research): iter-51 — A2 orientation informed by A1's cost arc | iter-051 | — | — |
| #70 | 2026-07-09 | feat(alpha): iter-52 — A2 Donchian TSMOM ensemble book | iter-052 | 00033 | — |
| #71 | 2026-07-09 | docs(research): iter-53 — A2 kill-bar verdict + two instrument findings | iter-053 | 00033 | T0009, T0011 |
| #72 | 2026-07-09 | feat(alpha): iter-54 — benchmark-relative worst-slice diagnostic | iter-054 | — | T0009 |
| #74 | 2026-07-09 | docs(research): iter-55 — dynamic B3/B4 catch-up; the benchmark family r | iter-055 | — | T0010 |
| #75 | 2026-07-09 | feat(registry): iter-56 — schema v3, first-class variant field (T0013) | iter-056 | — | T0013, T0015 |
| #76 | 2026-07-09 | docs(research): iter-57 — phase-4 close-out, decisions drain, T0016 | iter-057 | — | T0016 |
| #77 | 2026-07-09 | feat(risk): iter-58 — §10 drawdown governor + threshold backtest on the | iter-058 | 00034 | — |
| #78 | 2026-07-09 | feat(risk): iter-59 — combination trial P1 adopted (cap + governor on th | iter-059 | 00035 | T0016 |
| #79 | 2026-07-09 | docs(research): iter-60 — phase-5 stress suite on the adopted combined s | iter-055, iter-060 | — | T0010, T0016 |
| #80 | 2026-07-09 | docs(research): iter-61 — final system spec, runbook draft & pre-registe | iter-061 | — | T0017 |
| #81 | 2026-07-09 | feat(registry): iter-62 — exact key-set validation (T0015) | iter-056, iter-062 | — | T0013, T0015 |
| #82 | 2026-07-09 | feat(portfolio): iter-63 — combined-system builder (record 33's pipeline | iter-063 | 00036 | — |
| #83 | 2026-07-09 | docs(research): iter-64 — holdout-procedure dry-run; paired-index CI con | iter-064 | — | — |
| #84 | 2026-07-09 | docs(research): iter-65 — 2026 partial-year-stub probe (feeds T0009) | iter-065 | — | T0009, T0011 |
| #85 | 2026-07-09 | docs(research): iter-66 — T0009 consequence tables + A2 scaling-bug corr | iter-066 | — | T0009 |
| #87 | 2026-07-09 | docs(research): iter-68 — PBO selection-inflation read on the benchmark | iter-068 | — | — |
| #88 | 2026-07-09 | docs(research): iter-69 — A1-long/flat start-date sensitivity (feeds T00 | iter-069 | — | T0009 |
| #89 | 2026-07-09 | docs(research): iter-70 — A1-long/flat cost-stress read (completes the T | iter-070 | — | T0009 |
| #90 | 2026-07-09 | docs(research): iter-71 — night-audit fixes across iters 057-070 | iter-071 | — | T0016 |
| #91 | 2026-07-09 | feat(alpha): iter-72 — ratified kill bar, trials 34/35, holdout look pre | iter-072 | 00037 | T0009, T0017 |
| #92 | 2026-07-09 | docs(research): iter-73 — holdout look (EQUALS), GO to paper, phase-5 cl | iter-073 | — | T0017, T0018 |
| #95 | 2026-07-10 | docs(research): iter-74 — A2 native-4h arms: three adopts, first family- | iter-053, iter-074 | 00033 | T0009, T0011 |
| #96 | 2026-07-10 | docs(research): iter-75 — cadence sweep closes the A family at 40/40 | iter-075 | 00033 | — |
| #97 | 2026-07-10 | docs(research): iter-76 — cross-frequency combination design (T0011 unbl | iter-076 | 00038 | T0011 |
| #98 | 2026-07-10 | feat(portfolio): iter-77 — cross-frequency helpers (daily→intraday expan | iter-077 | 00038 | — |
| #99 | 2026-07-10 | docs(research): iter-78 — night-audit fixes (T0011 index sync) | iter-078 | — | T0011 |
| #101 | 2026-07-10 | feat(config): iter-079 — phase-6 kickoff: adapter verification, key cere | iter-079 | 00039 | T0005, T0014, T0018 |
| #102 | 2026-07-10 | feat(portfolio): iter-080 — cross-frequency combination adopted (trial 4 | iter-072, iter-076, iter-080 | 00037, 00038 | T0009, T0011, T0017, T0018, T0019 |
| #103 | 2026-07-10 | feat(portfolio): iter-081 — fixed-weight combination adopted (trial 44) | iter-081 | 00038 | T0018, T0019 |
| #104 | 2026-07-10 | feat(portfolio): iter-082 — record-44 builder + concordance core | iter-082 | 00040 | — |
| #105 | 2026-07-10 | feat(engine): iter-083 — the shadow node (store, cycle, node, CLI) + wor | iter-083 | 00041 | T0018 |
| #106 | 2026-07-11 | feat(engine): iter-084 — the engine on the VPS (role, watchdog, gate ops | iter-084 | 00042, 00043 | T0018, T0020, T0021 |
| #107 | 2026-07-11 | feat(backfill): iter-085 — the 15m bar substrate for Bucket B (T0012) | iter-085 | 00044 | T0012, T0022 |
| #108 | 2026-07-11 | feat(alpha): iter-086 — B1 family opening (conditioning overlay; trial 4 | iter-086 | 00045 | T0016, T0022 |
| #109 | 2026-07-11 | feat(alpha): iter-087 — B1 trial 46 (window-only, reject); both overlay | iter-087 | 00045 | T0022 |
| #110 | 2026-07-11 | feat(risk): iter-088 — §10 portfolio limits (gross, net band, margin flo | iter-088 | 00046 | T0016 |
| #111 | 2026-07-11 | docs(open-topics): iter-089 — T0023 B2 derivatives-positioning data sour | iter-089 | — | T0023 |
| #112 | 2026-07-11 | feat(derivatives): iter-090 — B2 funding substrate (Binance Vision backf | iter-090 | 00047 | T0023 |
| #116 | 2026-07-12 | feat(config): iter-093 — three-tier topology Role A (always-on NAS pull/ | iter-093 | 00048 | T0003, T0028, T0029 |
| #117 | 2026-07-12 | feat(config): iter-094 — Role B (NAS gate-verify + telemetry) | iter-094 | 00049 | T0003, T0020, T0029, T0030 |
| #120 | 2026-07-13 | fix(capture): stop the dead-man reporting green while the disk is full ( | — | — | T0032 |
| #121 | 2026-07-13 | fix(capture): keep the book congruent with Kraken's depth window (T0008) | — | — | T0008 |
| #122 | 2026-07-14 | fix(capture): make the capture writer restart-safe — T0036/T0037 + T0032 | — | — | T0032, T0035, T0036, T0037 |
| #123 | 2026-07-14 | docs(infra): spec 00050 v2 — redundant capture rewrite + T0036 resolutio | — | 00050 | T0036 |
| #127 | 2026-07-14 | feat(infra): iter-096 — Role C redundant capture (spec 00050) (1 of 2) | iter-096 | 00050, 00051 | T0033, T0039 |
| #129 | 2026-07-15 | feat(infra): iter-097 — ops-node compute tier OPS-1…3 (spec 00051) | iter-097 | 00051 | T0045, T0046, T0047 |
| #130 | 2026-07-15 | feat(infra): Grafana alerts to Slack alongside email (T0047, phase one) | — | — | T0047 |
| #131 | 2026-07-15 | feat(capture): wall-clock hour finalization for sparse segment trees (T0 | — | — | T0046 |
| #132 | 2026-07-15 | feat(infra): iter-098 — the 1-second L2 primitive panel (spec 00052, OPS | iter-098 | 00052 | T0014 |
| #133 | 2026-07-15 | docs(open-topics): T0048 — Alloy tailer dies on container recreation | — | — | T0048 |
| #137 | 2026-07-16 | docs(config): iter-099 — capture exit bar verified, T0003 closed | iter-099 | — | T0003, T0050 |
| #138 | 2026-07-16 | feat(trades): iter-100 — REST trade-backfill, a provably complete trade | iter-100 | 00053 | T0052, T0053, T0054 |
| #139 | 2026-07-16 | refactor(trades): derive the Kraken altname instead of hardcoding it (re | — | 00053 | T0055 |
| #141 | 2026-07-17 | feat(config): iter-101 — OPS-5 offload + T0058 NFS pivot: the overlay wr | iter-101 | 00054 | T0044, T0056, T0057, T0058, T0059, T0061, T0062 |
| #143 | 2026-07-17 | fix(liquidations): iter-102 — the poller stops re-submitting at source ( | iter-102 | 00055 | T0060 |
| #144 | 2026-07-17 | docs(config): resolve T0060 — poller fix deployed to ops and verified | — | 00055 | T0060 |
| #145 | 2026-07-17 | feat(infra): iter-096 — Role C redundant capture (spec 00050) (2 of 2) | iter-096 | 00050 | T0039 |
| #146 | 2026-07-17 | docs(config): register T0063 + T0064 + T0065 (strategy-provenance + data | — | — | T0063, T0064, T0065 |
| #147 | 2026-07-18 | feat(data): iter-103 — OPS-6 Loop: dataset topology + zcrypto data excha | iter-103 | 00056, 00057 | T0067, T0068 |
| #148 | 2026-07-18 | feat(infra): fleet users/groups migration — ops + capture/engine (spec 0 | — | 00057 | — |
| #149 | 2026-07-19 | docs(open-topics): pre-6a topic-state sync — T0063 resolved, gate-export | — | — | T0063 |
| #152 | 2026-07-19 | fix(panel): settle-watermark so an un-healed hour is never permanently c | iter-106 | 00052 | T0014, T0024, T0065, T0066 |
| #153 | 2026-07-19 | chore(open-topics): resolve T0070 (host-cruft cleaned) + record T0066 op | — | — | T0066, T0070 |
| #154 | 2026-07-19 | feat(engine): iter-107 — zcrypto engine soak-check (realized-OOS-vs-back | iter-107 | 00058 | T0064, T0072, T0073 |
| #155 | 2026-07-20 | feat(engine): iter-108 — soak-check gates the realized governor/cap fing | iter-108 | 00059 | T0072, T0073 |
| #156 | 2026-07-20 | docs(open-topics): iter-109 — gate-export profiled, super-linear hypothe | iter-109 | — | T0069 |
| #157 | 2026-07-20 | feat(engine): iter-110 — gate-export incremental scoring (T0069 structur | iter-110 | 00060 | T0069, T0074 |
| #158 | 2026-07-20 | fix(engine): fold the execution environment into the gate-cache fingerpr | — | 00060 | T0074 |
| #159 | 2026-07-20 | feat(cli): iter-111 — soak-check's secondary null and instrument-fragili | iter-111 | 00058, 00061 | T0073 |
| #161 | 2026-07-20 | docs(open-topics): register the gate-guarantee mutation audits (T0075, T | — | — | T0075, T0076 |
| #162 | 2026-07-20 | test(cli): pin the gate streak threshold and the dead-engine reset (T007 | — | — | T0076 |
| #163 | 2026-07-20 | docs(open-topics): T0076 → partial after PR #162 | — | — | T0076 |
| #165 | 2026-07-20 | feat(cli): iter-112 — rotating re-verification so the gate cache never t | iter-112 | 00062 | T0069, T0077 |
| #167 | 2026-07-20 | test(cli): iter-113 — pin the concordance gate's arithmetic guarantees ( | iter-113 | 00063 | T0075, T0076 |
| #168 | 2026-07-20 | test(cli): iter-112 — pin the gate-evidence guarantees and make fingerpr | iter-112 | 00060, 00062, 00064, 00065 | T0069, T0075, T0077 |
| #172 | 2026-07-21 | claude(config): grooming + auto-exec skills, memo guard, PR-open gate, a | — | 00062 | — |
| #173 | 2026-07-21 | fix(trades): total fetch-failed ids in the backfill summary (T0078) | — | — | T0078 |
| #175 | 2026-07-21 | docs(reference): T0071 — capture-era data-hygiene map (full-window verdi | — | — | T0071 |
| #176 | 2026-07-21 | feat(infra): T0086 — workspace-transport script (workstation↔ops continu | — | — | T0086 |
| #177 | 2026-07-21 | docs(open-topics): T0082 — parked-items review closes; T0088 registers t | — | — | T0082, T0088 |
| #178 | 2026-07-21 | feat(infra): T0079 — per-host Alloy-dark dead-man rules, pushed + live-v | — | — | T0079 |
| #179 | 2026-07-21 | feat(infra): T0083 — healthchecks retag + the Grafana-hc.io mutual watch | — | — | T0083 |
| #180 | 2026-07-21 | docs(open-topics): correct T0089 — the log wedge is a marginal race, not | — | — | T0089 |
| #181 | 2026-07-21 | fix(infra): drop the copytruncate logrotate policy wedging docker's log | — | 00043 | T0089 |
| #182 | 2026-07-21 | docs(open-topics): retract T0089's byte-offset model, falsified by measu | — | — | T0089 |
| #183 | 2026-07-21 | fix(infra): repair workspace-transport after its first real run + 13 rev | — | — | T0086 |
| #184 | 2026-07-22 | feat(costs): calibrate the missing spread term from our own L2 capture ( | iter-114 | 00066 | T0014, T0090, T0091 |
| #185 | 2026-07-22 | feat(universe): iter-115 — retire the spread_cap placeholder with a cali | iter-115 | 00067 | T0014, T0024, T0092, T0093 |
| #186 | 2026-07-22 | fix(data): fail closed when the universe rebuild's OHLC set is stale (T0 | — | — | T0093 |
| #187 | 2026-07-22 | fix(data): make the universe artifact name the OHLC set it was built fro | — | — | T0093 |
| #190 | 2026-07-22 | feat(logging): iter-116 — direct-ship the app's logs, retire docker.sock | iter-116 | 00068 | — |
| #191 | 2026-07-22 | feat(obs): iter-117 — app /metrics endpoints, process self-metrics, no c | iter-117 | 00069 | T0020, T0042, T0048, T0089 |
| #192 | 2026-07-23 | docs(open_topics): 2026-07-22/23 grooming — three rulings, a split, a re | — | — | T0088 |
| #193 | 2026-07-23 | docs(open-topics): verify the primary's first real prune deletion pass ( | — | 00050 | T0032 |
| #194 | 2026-07-23 | claude(skills): /zcrypto-bump-alloy — the codified fleet Alloy bump (T00 | — | 00068, 00069 | T0081 |
| #195 | 2026-07-23 | feat(costs): restamp the spread calibration on a 14.68-day window (T0091 | — | — | T0091 |
| #196 | 2026-07-23 | fix(data): fail closed when the universe rebuild's OHLC set has no usabl | — | — | T0093, T0094 |
| #197 | 2026-07-23 | feat(data): carry the canonical OHLC basket forward from the REST window | — | — | T0065 |
| #198 | 2026-07-23 | docs(research): assemble the 6b session brief and re-point four unsatisf | — | — | T0018 |
| #201 | 2026-07-24 | feat(derivatives): open-interest substrate backfill from Binance Vision | — | 00047 | T0023 |
| #202 | 2026-07-24 | claude(rules): topic updates ride the completing PR; done sub-items move | — | — | T0023 |
| #204 | 2026-07-26 | feat(capture): capture the two BTC-quoted universe legs (T0092) | — | — | T0092 |
| #206 | 2026-07-26 | fix(obs): derive the gate journal-pull lag threshold; drop the T0069 rel | — | — | T0069 |
| #207 | 2026-07-26 | feat(engine): bound the VPS engine journal at a 60-day tail (T0021, spec | — | 00070 | T0021 |
| #208 | 2026-07-26 | feat(capture): attended reboots on the capture VPSes, and a metrics tran | — | 00071 | T0027, T0100 |
| #209 | 2026-07-26 | feat(obs): watch the eight capture fault signals, six of which nothing d | — | — | T0008 |
| #210 | 2026-07-27 | feat(obs): keep internal traceability vocabulary off operator-visible su | — | — | T0096 |
| #211 | 2026-07-27 | feat(obs): bump Alloy to v1.18.0 across the fleet (T0081, the skill's fi | — | — | T0081 |
| #212 | 2026-07-27 | feat(capture): prove the reconnect path runs, then make desync recovery | — | 00072 | T0008 |
| #213 | 2026-07-27 | feat(capture): see a stream that is connected, subscribed, and silent | — | 00070, 00072, 00073 | T0101 |
| #214 | 2026-07-27 | claude(skills): the captures-rollout skill, and the event-coverage bake | — | — | T0084 |
| #219 | 2026-07-28 | docs(ops): resolve T0095 by redistribution, and make T0018's next steps | — | — | T0018, T0095 |
| #220 | 2026-07-28 | fix(infra): continuity.py prints the threshold it derived, and survives | — | — | T0097 |
| #221 | 2026-07-28 | docs(ops): the 2026-07-28 capture re-pin — record, and T0084's validatio | — | — | T0084 |
| #223 | 2026-07-28 | feat(archive): T0101's remediation — the instruments that measured the b | — | 00072, 00073 | T0101 |
| #224 | 2026-07-28 | fix(panel): the generation guard checks the tree, not just its manifest | — | 00052 | T0104 |
| #226 | 2026-07-29 | fix(config): mount the alloy config directory, so a config change reache | — | 00071 | T0109 |
| #227 | 2026-07-29 | fix(config): the alloy config that never reached the process — and the s | — | 00073 | T0101, T0109 |
| #230 | 2026-07-30 | docs(reference): correct the 00075 closeout entry — G2 live in-iteration | — | 00075 | — |
| #231 | 2026-07-30 | claude(config): refine-rules round 2 — graduations, guard-class sweep, s | — | — | T0111 |
| #232 | 2026-07-30 | fix(infra): iter closeout — the archive verification instruments, re-fit | — | 00076 | T0097 |
| #233 | 2026-07-30 | docs(ops): resolve T0032 and close Stage 6a — exit bar derived, residual | — | — | T0032 |
| #235 | 2026-07-31 | fix(infra): verify-replay pages on NEW breakage, not on exit code (spec | — | 00077 | — |
| #236 | 2026-08-01 | docs(reference): spec 00077 deploy record — converged, pruned, and an Al | — | 00077 | — |
| #237 | 2026-08-01 | feat(archive): verify-replay goes incremental — checkpoint raw facts, re | — | 00078 | T0114 |
| #239 | 2026-08-01 | docs(reference): spec 00078 deploy record + T0115 — converged, verificat | — | 00078 | T0115 |
| #240 | 2026-08-02 | fix(infra): continuity.py refuses a contaminated tail instead of trustin | — | 00079 | T0112 |
| #241 | 2026-08-02 | docs(topics): resolve T0043 — loss attribution ruled on measured evidenc | — | — | T0043 |
| #242 | 2026-08-02 | fix(ohlc): close T0098's three reach-review residuals (spec 00080) | — | 00080 | T0098 |
| #243 | 2026-08-02 | docs(topics): register the Stage 6b gap set — T0116–T0123 + the executor | — | — | T0116, T0123 |
| #244 | 2026-08-02 | feat(engine): the two Stage-6b feeder measurements, answered (spec 00081 | — | 00081 | — |
| #246 | 2026-08-02 | feat(engine): rule T0124 and publish the sleeve-occupancy gauges it requ | — | 00081 | T0124 |
| #247 | 2026-08-02 | docs(research): ratify the §12 Stage-6b amendment — the three-rung ladde | — | 00081 | T0116, T0124 |
| #248 | 2026-08-02 | feat(cli): iter-119 — wire the §10 whole-book limits, ZEUR spot reportin | iter-119 | — | T0120, T0121, T0122, T0124 |
| #250 | 2026-08-03 | refactor(portfolio): iter-120 — rule the deployable's cost basis, split | iter-120 | — | T0090 |
| #251 | 2026-08-03 | docs(reference): iter-119 converge record — the sleeve gauge is live and | iter-118, iter-119 | — | T0120, T0121, T0124 |
| #252 | 2026-08-03 | docs(research): amend §12 — the go/no-go band carries two uncertainties, | — | — | T0116 |
| #253 | 2026-08-03 | feat(registry): require run_ref to name provenance that exists (T0125 pa | — | — | T0125 |
| #254 | 2026-08-03 | docs(research): T0064 — accept the missing out-of-time evidence, narrow | — | — | T0064 |
| #255 | 2026-08-03 | docs(specs): T0073 — drop soak-check's regime-context section on a measu | — | — | T0073 |
| #256 | 2026-08-03 | feat(portfolio): T0125 — re-ground the go/no-go on a basis that can be r | — | — | T0125 |
| #258 | 2026-08-03 | feat(config): iter-124 — converge discipline becomes refusable: wave-1 g | iter-124 | 00082 | T0111 |
| #259 | 2026-08-03 | docs(reference): record the iter-119 T+24h RSS re-read — flat on both ho | iter-119 | — | T0120, T0121, T0124 |
| #260 | 2026-08-04 | feat(config): iter-125 — the converge path becomes refusable: wave-2 scr | iter-125 | 00083 | T0111 |
| #264 | 2026-08-04 | docs(topics): T0126 accepted into T0085's pre-go-live carrier — rotation | — | — | T0085, T0126 |
| #265 | 2026-08-04 | docs(reference): iter-126 — the reference-data sweep gets a home, a trig | iter-126 | — | T0113 |
| #267 | 2026-08-05 | docs(infra): iter-125 closeout — both converge paths drilled live, and t | iter-125 | 00082, 00083 | T0111 |
| #268 | 2026-08-05 | feat(grafana): iter-127 — every family that can page you is visible, and | iter-127 | 00043, 00084 | T0020, T0128, T0129, T0130 |
| #269 | 2026-08-06 | feat(infra): iter-128 — make the panel regeneration's closing checklist | iter-128 | — | T0111 |
| #272 | 2026-08-06 | feat(grafana): iter-127 — the rollout: boards, rules and all four conver | iter-127 | 00043, 00084 | T0020, T0128, T0129, T0130 |
| #273 | 2026-08-06 | feat(capture): iter-129 — resolve the venue pre-drain decision from its | iter-129 | — | T0018, T0105 |
| #276 | 2026-08-08 | feat(cli): iter-131 — the quote-aware notional ladder and the /BTC sprea | iter-131 | 00085 | T0092 |
| #277 | 2026-08-08 | docs(reference): the T+24h RSS re-read — converging, not yet dischargeab | — | — | T0131 |
| #278 | 2026-08-08 | feat(grafana): iter-132 — a dead canary for the engine's log plane | iter-132 | — | T0128 |
| #279 | 2026-08-09 | docs(reference): discharge the capture bake's RSS residual — no leak | — | — | T0131 |
| #280 | 2026-08-09 | docs(open-topics): T0018's Stage-6a gate is met — 28 clean days, measure | — | — | T0018 |
| #281 | 2026-08-09 | fix(engine): the dispose race reaches production — correct T0115's safet | — | — | T0115 |
| #282 | 2026-08-10 | feat(registry): iter-133 — dataset provenance is the bytes the run read, | iter-133 | 00086 | T0065 |
| #283 | 2026-08-10 | docs(open_topics): T0085 owns the nautilus bump, its real-money probe an | — | — | T0085 |
| #285 | 2026-08-10 | feat(tick): iter-134 — tape-bars, 15m bars from the captured trade tape | iter-134 | 00087 | T0065 |
| #288 | 2026-08-11 | feat(engine): iter-135 — the execution safety envelope | iter-135 | 00088 | T0018 |
| #289 | 2026-08-12 | docs(reference): pin the fleet to 6c5151d9f3af — spec 00088's execution | — | 00088 | — |
| #290 | 2026-08-12 | feat(data): iter-136 — the universe refresh's volume source reaches the | iter-136 | 00093 | T0093 |
| #291 | 2026-08-13 | feat(grafana): alert on a repeat venue degradation the latch cannot repo | — | — | T0135 |
| #293 | 2026-08-13 | feat(universe): iter-137 — the attended refresh, and the legacy fallback | iter-137 | 00093 | T0024, T0065, T0093 |
| #294 | 2026-08-14 | feat(engine): iter-138 — venue truth: the instrument map, constraint siz | iter-138 | 00089 | T0018, T0130, T0134 |
| #295 | 2026-08-14 | docs(open-topics): resolve T0136 — the capture bake's RSS residual conve | — | — | T0136 |
| #297 | 2026-08-15 | feat(engine): iter-139 — the /BTC widening: a twelve-leg symbol-keyed pi | iter-139 | 00094, 00095 | T0018, T0137, T0138, T0139 |
| #299 | 2026-08-17 | docs(reference): record the twelve-leg deploy, and resolve T0139 on the | — | 00094 | T0139 |
| #301 | 2026-08-18 | feat(engine): iter-140 — the rung-1 order path, the engine's first real | iter-140 | 00088, 00090, 00092, 00094 | T0018, T0120, T0141, T0142 |
| #302 | 2026-08-18 | refactor(runbooks): split the runbook by subsystem, and make the README | — | — | T0141 |
| #305 | 2026-08-20 | docs(reference): the 00090 deploy record, and fleet-pins becomes a state | — | 00090 | — |
| #306 | 2026-08-20 | feat(archive): iter-141 — a venue-silence discriminator for the residual | iter-141 | 00096 | T0143, T0144 |
| #308 | 2026-08-21 | docs(archive): Kraken published every venue outage days ahead — correct | — | 00096 | T0144 |
| #312 | 2026-08-21 | docs(reference): the spread calibration discloses both frozen intervals, | — | — | T0146 |
| #313 | 2026-08-21 | docs(reference): schedule the fleet around Kraken's published maintenanc | — | — | T0145 |
| #314 | 2026-08-21 | feat(archive): the reconcile cycle stops scaling with market volume (spe | — | 00097 | T0147 |
| #315 | 2026-08-21 | docs(reference): the 00097 rollout, measured — T0147 resolved at 90.9× i | — | 00097 | T0147 |
| #316 | 2026-08-22 | feat(portfolio): trial 43 recovered and absorbed — the 43-vs-44 ordering | — | — | T0148 |
| #317 | 2026-08-22 | feat(engine): iter-143 — adopted orders' fills become observable, withou | iter-143 | 00098 | T0142 |
| #318 | 2026-08-22 | docs(engine): the one-sleeve era ended — every number derived under it r | iter-144 | — | T0149 |
| #320 | 2026-08-23 | feat(engine): iter-145 — the weekly tracking-error report, the ledger re | iter-145 | 00091 | T0090, T0150 |
| #321 | 2026-08-23 | feat(engine): 1.231.0 fixes the abort, and its attended order-semantics | — | 00039 | T0115 |
| #324 | 2026-08-23 | docs(open_topics): T0103 resolves by re-homing its routine — and the dro | — | — | T0103, T0113 |
| #326 | 2026-08-24 | feat(engine): the cycle record journals the NAV it priced against, and t | — | — | T0150 |
| #329 | 2026-08-24 | feat(data): the frozen holdout gets verified — attestations, fail-closed | — | — | T0133 |
| #330 | 2026-08-24 | feat(data): one manifest contract — the zoo is removed rather than read | — | 00099 | T0132 |
| #332 | 2026-08-24 | docs(open_topics): T0151 resolved — the capture RSS step is attributed, | — | — | T0151 |
| #340 | 2026-08-27 | feat(engine): iter-147 — the external-order delivery leg is proven, and | iter-147 | — | T0018, T0085, T0152 |
| #341 | 2026-08-28 | fix(archive): iter-148 — the reconcile ledger scan is measured, cheaper, | iter-148 | — | T0044 |
| #342 | 2026-08-28 | fix(capture): iter-149 — the capture silence bars survive their re-deriv | iter-149 | 00084 | T0129 |
| #343 | 2026-08-28 | feat(infra): iter-150 — the rollout gate closes at gate-close, memory be | iter-150 | — | — |
| #345 | 2026-08-28 | feat(snapshot): iter-151 — the refdata sweep refuses on a corporate acti | iter-151 | — | T0025 |
| #346 | 2026-08-29 | feat(archive): iter-152 — bound the NAS pull's verify cost, and measure | iter-152 | 00102 | T0028 |
| #347 | 2026-08-29 | feat(capture): iter-153 — make T0037's accepted residuals observable | iter-153 | 00103 | T0037 |
| #348 | 2026-08-29 | feat(engine): iter-154 — decompose keeps the whole-book limits' share | iter-119, iter-154 | — | T0120, T0121, T0124 |
| #349 | 2026-08-29 | docs(research): iter-155 — the sleeve-promotion path, ruled and then re- | iter-155 | — | T0123 |
| #350 | 2026-08-29 | docs(open-topics): split T0049 — the drill program (spec 00105) and day- | — | 00104, 00105 | T0049, T0157 |
| #351 | 2026-08-29 | docs(specs): 00106 — zcrypto engine flatten, the red button; T0158/T0159 | — | 00104, 00105, 00106 | T0158, T0159 |
| #352 | 2026-08-30 | feat(obs): iter-156 — every alert has a runbook, and a daily pass reads | iter-156 | 00104 | T0157 |
| #356 | 2026-08-30 | fix(ops_daily): what day one showed, folded back — and T0157 resolved | — | 00104 | T0157 |
| #357 | 2026-08-30 | feat(ops_daily): iter-157 — the signals that were silently absent | iter-157 | 00107 | T0037 |
| #361 | 2026-08-31 | docs(plans): point 00040 and 00084 at committed artifacts, not vanished | — | 00040, 00084 | — |
| #363 | 2026-08-31 | feat(drill_program): iter-158 — the go-live drill program, built and run | iter-158 | 00105 | — |
| #364 | 2026-09-01 | feat(engine): iter-159 — the red button, one command that flattens the w | iter-159 | 00106 | T0159, T0160 |
| #368 | 2026-09-01 | feat(engine): iter-160 — the rest-hold plan mode, an order that stays | iter-160 | 00108 | T0158 |
| #373 | 2026-09-02 | feat(plan_review): iter-162 — the spec+plan review as a skill, battle-te | iter-162 | — | — |
| #374 | 2026-09-02 | fix(capture): iter-163 — the past-dated detector counts only a never-cap | iter-163 | 00103, 00109 | T0037, T0161 |
| #377 | 2026-09-02 | docs(open_topics): T0065's trigger names its source, and separates NAS c | — | — | T0065 |
| #378 | 2026-09-03 | fix(ops_daily): iter-164 — the daily pass reports what it measured | iter-164 | 00104 | — |
| #379 | 2026-09-03 | fix(runbooks): iter-165 — the venue-halt prose the fourth Kraken mainten | iter-165 | — | — |
| #380 | 2026-09-03 | feat(features): iter-091 — the B2 derivatives-positioning feature harnes | iter-091 | 00110 | T0023 |
| #381 | 2026-09-03 | fix(observability): iter-166 — four Grafana surfaces the venue halt disp | iter-166 | — | — |
| #382 | 2026-09-03 | docs(reference): iter-167 — the fourth venue outage gets its provenance | iter-167 | — | — |
| #386 | 2026-09-04 | fix(engine): iter-168 — the flatten verdict and the trip's sweep say wha | iter-168 | 00111 | T0160, T0162 |
| #388 | 2026-09-04 | docs(open_topics): the unpark condition for a parked pair is registered, | — | 00111 | — |
| #392 | 2026-09-04 | docs(runbooks): the read-only dry run that proves the five reads gets it | — | — | T0159, T0160 |
| #396 | 2026-09-04 | docs: the fleet doc names both vaulted-key wrappers, and spec 00106's co | — | 00106 | — |
| #399 | 2026-09-05 | docs(open-topics): T0162 — the Loki dead-men announce their clears; dril | — | — | T0162 |
| #400 | 2026-09-05 | test(engine): T0164 — the first tests and infra batch under prose.md, fo | — | — | T0164 |
| #401 | 2026-09-05 | claude(skills): cron fields are UTC on the ops host, and T0164's worklis | — | — | T0164 |
| #403 | 2026-09-05 | feat(obs): T0165–T0167 — the claims asserted only in prose become tests, | — | — | T0165, T0167 |
| #404 | 2026-09-05 | test(config): T0164 — the second tests and infra batch under prose.md, e | — | — | T0164 |
| #407 | 2026-09-05 | docs(iterations-history): T0164 — the docs batch under prose.md, seven c | — | — | T0164 |
| #408 | 2026-09-05 | docs(open-topics): T0037 — stage 1 of spec 00109 D7 is discharged, both | — | 00109 | T0037 |
| #409 | 2026-09-05 | refactor(cli): T0164 — the cli batch under prose.md, 77 files prose-only | — | — | T0164 |
| #410 | 2026-09-06 | chore(infra): T0164 — the infra code-and-config batch under prose.md, 59 | — | — | T0164 |
| #411 | 2026-09-06 | docs(infra): T0164 — the fifteen infra docs and runbook pages under pros | — | — | T0164 |
| #412 | 2026-09-06 | feat(ops): T0170 — the Kraken CLI's reads in the harness allowlist, the | — | — | T0170 |
| #413 | 2026-09-06 | test(prose): T0164 — the tests- group brought to prose.md's code bar, pr | — | — | T0164 |
| #414 | 2026-09-06 | test(infra): T0168 wave 1 — the second cleanup batch's claims carry asse | — | — | T0168 |
| #415 | 2026-09-06 | test(prose): T0164 — the tests- remainder: the nine held files and the t | — | — | T0164 |
| #416 | 2026-09-06 | fix(tests): T0169 — the cleanup's residue outside a prose commit: a sile | — | — | T0169 |
| #417 | 2026-09-06 | feat(ops): T0172 — the daily pass resolves a content read's file operand | — | — | T0168, T0172 |
| #418 | 2026-09-06 | docs(reference): T0164 — README and the docs-reference pages brought to | — | — | T0164 |
| #420 | 2026-09-06 | test(infra): T0168 wave 2 — the remaining prose-only claims asserted, th | — | — | T0168 |
| #422 | 2026-09-06 | docs(runbooks): T0173 — the ten operator procedures moved to their runbo | — | — | T0164, T0173 |
| #423 | 2026-09-06 | fix(cli): T0171 — the date-directory parsers catch the year a C int cann | — | — | T0171 |
| #424 | 2026-09-06 | feat(tooling): T0164 — the prose tripwire becomes a pre-commit ratchet, | — | — | T0164 |
| #425 | 2026-09-06 | test(infra): T0174 — the nine tests-remainder claims the prune never saw | — | — | T0168, T0174 |
| #426 | 2026-09-06 | fix(engine): T0169 — the cleanup residue closed in full: the host side m | — | — | T0169 |
| #431 | 2026-09-07 | docs(open_topics): T0176 resolved by measurement — no instrument separat | — | — | T0176 |
| #432 | 2026-09-07 | fix(capture): T0175 — a finalize failure is reported and withholds the l | — | — | T0175 |
| #435 | 2026-09-07 | fix(capture): the quarantined-rows count survives the process that spill | — | — | T0161 |
| #440 | 2026-09-07 | docs(reference): C7 — the capture pair on 06998998e876, and T0037 resolv | — | — | T0037, T0161 |
| #442 | 2026-09-07 | fix(archive): refuse an hour at a non-zero UTC offset at both boundaries | — | — | T0177 |
| #458 | 2026-09-08 | docs(open_topics): install T0180's pre-push stage and discharge the defe | — | — | T0180 |
| #461 | 2026-09-08 | fix(capture): T0185 — a daemon with nothing to capture is refused, at th | — | — | T0185 |
| #462 | 2026-09-09 | feat(engine): iter-169 — the soak's null is judged over the complete-bas | iter-169 | 00112 | T0184 |
| #463 | 2026-09-09 | fix(engine): a reconciliation that compared nothing reports no number in | — | — | T0183 |
| #469 | 2026-09-09 | test(infra): T0187's replay gains a never-observed history, and the topi | — | — | T0187 |
| #470 | 2026-09-09 | docs(tests): engine_executor — the docstring pass re-run, and T0192 regi | — | — | T0192 |
| #471 | 2026-09-09 | docs(tests): engine_flatten — the docstring pass, and T0191 registered | — | — | T0191 |
| #473 | 2026-09-09 | test(engine): T0192 — the week-boundary fixture reaches the arm it is na | — | — | T0192 |
| #474 | 2026-09-09 | docs(open_topics): T0197 closes as a measured non-issue — the OI null gu | — | — | T0197 |
| #475 | 2026-09-09 | fix(tests): T0196 — the kill-bar can_fail_alone fixtures prove isolation | — | — | T0196 |
| #476 | 2026-09-09 | fix(prose_tripwire): T0195 — a scoped --write-baseline refuses instead o | — | — | T0195 |
| #477 | 2026-09-09 | fix(engine): 00113 — the soak identity check refuses a NaN comparison in | — | 00113 | T0188 |
| #478 | 2026-09-09 | docs(engine): T0191 — the zero-price refusal's comment says what a carri | — | — | T0191 |
| #479 | 2026-09-09 | docs(open_topics): T0191 closes — the update #478 should have carried | — | — | T0191 |
| #481 | 2026-09-09 | fix(prose_tripwire): a shrink stops lowering the ceiling | — | — | T0189 |
