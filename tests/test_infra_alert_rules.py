"""Guard: `infra/grafana/alerts.yaml` is pushed to Grafana Cloud's provisioning API by
`infra/scripts/grafana-push.sh`, and the API rejects a malformed rule with a bare HTTP 400 whose
body the script discards. That failure mode is expensive out of proportion to its cause: it needs a
vaulted token and a TTY for the GPG pinentry, so it can only be discovered during an attended push,
and the operator sees `curl: (22) ... error: 400` with no indication of which rule or which field.

Every constraint pinned here is one the API enforces silently and the repo previously did not. The
40-char UID limit cost a full attended round-trip on 2026-07-20 (a 41-char uid); note that the
longest surviving uid is exactly 40, so the ceiling is real and routinely approached."""

import re
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
ALERTS = REPO / "infra/grafana/alerts.yaml"

# Grafana's alert-rule UID column is `varchar(40)`, and the provisioning API's OpenAPI spec declares
# `maxLength: 40`. A uid is IMMUTABLE once the rule exists, so an update never carries a new uid --
# the length is therefore only ever tested at creation, and a too-long uid breaks exactly once, on
# the run that first introduces it, which is when the diagnosis is hardest.
_UID_MAX = 40

# The provisioning API's enums. A value outside these is a 400, not a validation message.
_NO_DATA_STATES = {"Alerting", "NoData", "OK"}
_EXEC_ERR_STATES = {"Alerting", "Error", "OK"}


def _rules():
    return yaml.safe_load(ALERTS.read_text())["rules"]


def test_alert_rule_uids_fit_grafanas_column():
    over = [(r["uid"], len(r["uid"])) for r in _rules() if len(r["uid"]) > _UID_MAX]
    assert not over, f"uid longer than Grafana's {_UID_MAX}-char limit -- the create call will 400: {over}"


def test_alert_rule_uids_are_unique():
    uids = [r["uid"] for r in _rules()]
    dupes = sorted({u for u in uids if uids.count(u) > 1})
    assert not dupes, f"duplicate uid -- the second push silently overwrites the first: {dupes}"


@pytest.mark.parametrize("field,allowed", [("noDataState", _NO_DATA_STATES), ("execErrState", _EXEC_ERR_STATES)])
def test_alert_rule_states_are_valid_enums(field, allowed):
    bad = [(r["uid"], r.get(field)) for r in _rules() if r.get(field) not in allowed]
    assert not bad, f"{field} outside the API's enum {sorted(allowed)}: {bad}"


def test_every_rule_has_the_fields_the_api_requires():
    # Omitting any of these is a 400. `condition` must also name a refId that exists in `data`,
    # which the API checks but does not explain.
    required = ("uid", "title", "condition", "data", "noDataState", "execErrState", "for", "ruleGroup", "folderUID")
    problems = []
    for r in _rules():
        missing = [f for f in required if f not in r]
        if missing:
            problems.append((r.get("uid", "<no uid>"), f"missing {missing}"))
            continue
        refids = {d.get("refId") for d in r["data"]}
        if r["condition"] not in refids:
            problems.append((r["uid"], f"condition {r['condition']!r} not among data refIds {sorted(refids)}"))
    assert not problems, f"rules the provisioning API would reject: {problems}"


def test_datasource_uids_are_templated_not_hardcoded():
    # grafana-push.sh substitutes ${GRAFANA_*_DS_UID} at push time. A hardcoded uid silently
    # repoints a rule at another datasource -- the API accepts it and reports health=ok (T0034),
    # so the push-time read-back is the only other thing that would catch it.
    allowed = {"${GRAFANA_PROM_DS_UID}", "${GRAFANA_LOKI_DS_UID}", "__expr__"}
    bad = [(r["uid"], d.get("datasourceUid")) for r in _rules() for d in r["data"] if d.get("datasourceUid") not in allowed]
    assert not bad, f"datasourceUid neither templated nor the expression node: {bad}"


# --- A shipped metric that nothing watches ------------------------------------------------------
# T0008's content, generalized. Spec 00069 shipped `zcrypto_capture_book_desynced` and
# `zcrypto_capture_resubscribes_total`, both scraped and live on both hosts, and for two months no
# alert rule mentioned either -- the topic's own trigger was measurable but unwatched. The same gap
# hid T0100 (a producer shipping into a transport nobody reads) and, found by the review of this
# very commit, `zcrypto_capture_disk_watermark_breached` -- whose breach makes the daemon DISCARD
# unbackfillable L2.
#
# `test_infra_alloy_series.py` proves a metric REACHES Grafana; this proves something looks at it.
# Admitting a series and watching nothing is the more expensive half, and nothing else would
# surface it: the Grafana dashboard carries no `zcrypto_capture_*` or `zcrypto_engine_*` panel at
# all, so an unwatched app metric is invisible everywhere.
#
# The candidate set is DERIVED from the capture keep-regex, not hand-listed. A hand-list cannot
# catch the next unwatched metric, which is precisely the mechanism that let these sit for months:
# a new fault gauge added to the keep-regex tomorrow would be invisible to a fixed list. Every
# admitted series is therefore a candidate until explicitly excluded below, so omitting one is a
# conscious act with a written reason rather than an oversight.
CAPTURE_ALLOY = REPO / "infra/ansible/roles/capture/files/config.alloy"


def _admitted_series() -> list[str]:
    """Every metric name the capture hosts' keep-regex admits to remote_write."""
    line = next(ln for ln in CAPTURE_ALLOY.read_text().splitlines() if ln.strip().startswith("regex") and "node_load1" in ln)
    return line.split('"')[1].split("|")


# Not fault signals: context you read once something ELSE has paged, or state whose meaning is a
# level rather than an event. Each exclusion states why, because an unexamined exclusion is how the
# original defect would grow back.
NOT_A_FAULT_SIGNAL = {
    # Capacity/utilisation context. Read while diagnosing; alerting on them directly is noise, and
    # the conditions that matter already have their own rules (disk-low, load-high).
    "up",
    "node_load1",
    "node_load5",
    "node_load15",
    "node_memory_MemTotal_bytes",
    "node_memory_MemAvailable_bytes",
    "node_memory_MemFree_bytes",
    "node_filesystem_avail_bytes",
    "node_filesystem_size_bytes",
    "node_filesystem_free_bytes",
    "node_network_receive_bytes_total",
    "node_network_transmit_bytes_total",
    "node_cpu_seconds_total",
    "node_scrape_collector_duration_seconds",
    "node_textfile_mtime_seconds",  # the staleness INPUT; the rules keyed on it are the signal
    # Throughput counters -- healthy when RISING. Their failure mode is going flat, which the
    # dead-man and the log-dead rules already own.
    "zcrypto_capture_segments_written_total",
    "zcrypto_capture_segment_bytes_total",
    "zcrypto_capture_rows_held_total",
    "zcrypto_logship_shipped_lines_total",
    "zcrypto_logship_last_success_timestamp_seconds",
    # Reconnects run 32-35/week per host (measured 2026-07-26): that is BASELINE, not a fault, so a
    # naive threshold here is pure alarm fatigue. T0035's trigger is a reconnect counter RESET
    # alongside a process_start_time_seconds jump (a crash-restart), which needs the correlation,
    # not a raw count -- it stays that topic's work.
    "zcrypto_capture_reconnects_total",
    # Cumulative gap seconds. No rule reads THIS counter and none is owed: the paging half shipped
    # 2026-08-05 on `zcrypto_capture_seconds_since_last_book_message` instead, which never touches
    # `gap_monitor.is_healthy()` -- so a bad bar there costs a false page rather than darkening the
    # dead-man fleet-wide, the hazard that kept an unfitted threshold off this counter. The blackout
    # that falsified this exclusion's two original grounds (T0101) is told at the total-blackout
    # rule's own test below, where it is what the aggregation assertion rests on.
    "zcrypto_capture_gap_seconds_total",
    # Engine intent and execution LEVELS, plus the cycle's own duration. Every value any of them can
    # take is legitimate -- a weight that moved, an order that was placed, a cycle that ran long -- so
    # no threshold on them means anything; they are the detail read on the engine board once something
    # else has paged. The engine's two genuine fault signals, cycle liveness and the last cycle's
    # outcome, are NOT excluded: zcrypto-engine-cycle-stale and zcrypto-engine-cycle-failed watch them,
    # and this test is what keeps that true.
    "zcrypto_engine_cycle_duration_seconds",
    "zcrypto_engine_target_weight",
    "zcrypto_engine_orders_total",
    "zcrypto_engine_order_notional_eur",
    # Per-sleeve gross: a LEVEL, and one whose every value is legitimate -- a long-only sleeve
    # sitting flat through a downtrend is correct behaviour, not a fault, so no threshold on it
    # means anything. The event worth paging on is the active-sleeve COUNT stepping, which
    # zcrypto-engine-sleeve-count-changed owns; this series is the detail that page's responder
    # reads to see which sleeve moved.
    "zcrypto_engine_sleeve_gross",
    # Process self-metrics: diagnostic context, no fault semantics of their own.
    "process_cpu_seconds_total",
    "process_max_fds",
    "process_open_fds",
    "process_virtual_memory_bytes",
    # Prune bookkeeping -- the fault is the timer STOPPING, which the staleness rules own.
    "zcrypto_engine_journal_prune_deleted_days",
    "zcrypto_engine_journal_prune_kept_days",
    "zcrypto_engine_journal_prune_oldest_day_age_seconds",
    "zcrypto_engine_journal_prune_last_run_timestamp_seconds",
    # The execution safety envelope's three unwatched families -- the other three
    # (armed/kill_tripped/last_evaluation_timestamp_seconds) DO have rules, and this list is what
    # keeps that true.
    #   gate_level is the SUMMARY the other four inputs already reduce to (armed, kill switch,
    #   restart hold, venue) -- every value 0/1/2 is legitimate depending on which of those inputs
    #   is active, so no threshold on the level itself means anything on its own; the two inputs
    #   that matter enough to page on (an unexpected arm, a tripped kill switch) have their own
    #   rules instead.
    "zcrypto_exec_gate_level",
    # A LEVEL, not an event: HELD is the expected reading immediately after every restart and
    # self-clears only by a human decision, so no duration or presence threshold on it means
    # anything the two arming/kill rules do not already cover more precisely.
    "zcrypto_exec_restart_hold",
    # A gating INPUT, not the venue alert itself -- the underlying condition (Kraken reporting a
    # non-online system state) already pages from the capture side via
    # zcrypto-capture-venue-not-online, which reads the daemon's own zcrypto_capture_venue_status_total.
    # A second rule on this engine-side cached copy would only double-page the same event.
    # NOT covered by that reasoning: cli/engine/execgate.py's venue reader fails CLOSED to
    # status="unreachable"/"unreadable" on a raise or a garbage return, so an engine-side REST-read
    # failure parks this gauge at 0 while the venue is genuinely online -- a divergence the
    # capture-side rule cannot see, since it reads a different series entirely. Registered as a
    # deferred alert in docs/open-topics/T0018-phase6-build-sequence.md rather than covered here,
    # because before the first order-submission call site exists "the engine cannot trade" has no
    # operational meaning yet.
    "zcrypto_exec_venue_ok",
    # The execution instruments (spec 00090 D12). Attended-window instruments: arming is episodic
    # through the tracking-error report's own spec, so between windows every one of these is
    # legitimately flat and nothing here can fire unattended without being pure alarm fatigue. The
    # two states that OUTLIVE a window already page -- zcrypto-engine-exec-kill-tripped and
    # zcrypto-engine-exec-armed-too-long -- and during a window an operator is watching the board,
    # which is what these are for. `orders_total` by outcome, the fills, the fees paid, the per-leg
    # position and the realized PnL are all legitimate at any value: a rejection is normal venue
    # behaviour, a fee is the cost of trading, and PnL falls.
    "zcrypto_exec_orders_total",
    "zcrypto_exec_fills_total",
    "zcrypto_exec_fees_eur_total",
    "zcrypto_exec_position",
    "zcrypto_exec_realized_pnl_eur",
    # The external-events counter is a forensic instrument: `matched` rising is a restart-adopted
    # order filling, which is the feature working, and `unmatched` says an order event belonging to
    # no order this engine's ledger vouches for arrived and was acted on nowhere. It does NOT
    # inherit the attended-window reasoning unexamined -- the siblings above move only when THIS
    # engine acts, i.e. inside a window by construction, while `unmatched` can move on a third
    # party's action at any hour (the sanctioned hand settle, but equally activity nobody
    # sanctioned).
    #
    # NO rule, deliberately and not by omission (decided 2026-08-27, once the preconditions this
    # entry used to wait on were met: the family has live samples and the healthy-boot baseline is
    # 0). The candidate this entry previously named -- `unmatched` rising while `zcrypto_exec_armed`
    # is 0 -- is UNSOUND, and the reason is the sensor rather than the framing. Disarmed is the
    # right framing: the threat is a third party holding the key, whose access does not depend on
    # arming, and the armed path already has the ledger, overfill and divergence trips. But
    # `zcrypto_exec_armed` is published only when the gate is EVALUATED, which while disarmed is at
    # engine start and each 4-hourly cycle -- `engine.md` states the lag ("at most one cycle,
    # roughly four hours") and `zcrypto-engine-exec-not-evaluated` pages at 4.75h on exactly that
    # cadence. So the gauge is a 4-hourly snapshot, not an attendance signal, and it is stale in
    # BOTH directions: for up to ~4h after arming it still reads 0, so the rule pages on the
    # owner's own attended activity; for up to ~4h after disarming it still reads 1, so the rule is
    # mute through the highest-risk hour, when positions are fresh and nobody is watching. It is
    # loudest when a human is present and silent when one is not, which inverts its own purpose.
    # Measured consequences: the only non-zero this family has ever recorded -- the 2026-08-27
    # delivery-leg proof, one owner-placed post-only limit -- would have paged; and from rung 1
    # onward every disarmed converge is a candidate page, since it restarts the engine on a
    # non-flat account and startup reconciliation books `unmatched` while the gauge reads 0 by
    # construction. Widening the rule to compensate (a longer armed lookback, a post-boot mute)
    # buys quiet by opening exactly the two seams an intruder would fall into -- just after a
    # window closes, just after a converge -- so it would read as more rigorous while covering
    # less.
    #
    # Visibility is unaffected: panel 61 of the engine dashboard plots both dispositions. The
    # standard is rule => panel, never the converse. What is declined here is paging, not watching.
    # What would make a rule viable is one change, recorded so nobody re-derives this from scratch:
    # publish `zcrypto_exec_armed` at a cadence that makes it an attendance signal -- the executor
    # already has a 5s tick -- after which the candidate above works as written. That is engine
    # code on the live trade path plus a converge, so it is a decision of its own and is owed by
    # nothing here. The silent failure a rule could never catch either way -- an adopted order
    # whose events fail to key into `_attached`, where the working and broken worlds both read
    # `matched` 0 -- is registered as a by-value reading in T0018.
    "zcrypto_exec_external_events_total",
    # The weekly tracking-error verdict. NO rule, deliberately and not by omission: the only value
    # that is a fault -- the band breached -- latches the kill file, and `zcrypto-engine-exec-kill-
    # tripped` already pages on exactly that. A second rule here would double-page the one event and
    # would page on nothing else, since `not scored` is a refusal to decide (a week short of its
    # boundaries, a week held below the full level, the week the series started in) and `disarmed`
    # is the resting state of an engine that has never been given a band.
    "zcrypto_exec_tracking_state",
    # A level-shift detail read on the board: the §10 whole-book limits binding is the limits doing
    # their job, not a fault. What would be a fault -- the book they shape going somewhere it should
    # not -- is the intent-side gauges' business, not this counter's.
    "zcrypto_engine_limit_bound_total",
    # Venue-truth LEVELS (spec 00089 D6): loaded vs expected are the detail read once
    # zcrypto-venue-concordance-failed has already paged, not fault signals of their own -- the
    # failures count already reduces both into the one number that matters, and a threshold on
    # either directly would double-page the same event.
    "zcrypto_venue_instruments_loaded",
    "zcrypto_venue_instruments_expected",
}

FAULT_SIGNAL_METRICS = sorted(set(_admitted_series()) - NOT_A_FAULT_SIGNAL)


def test_the_exclusion_list_has_not_gone_stale():
    """Every exclusion must name a series the keep-regex still admits — otherwise a rename leaves a
    dead entry silently excusing nothing, and the metric it was renamed to is unguarded."""
    stale = NOT_A_FAULT_SIGNAL - set(_admitted_series())
    assert not stale, f"excluded but no longer admitted (rename? removal?): {sorted(stale)}"


@pytest.mark.parametrize("metric", FAULT_SIGNAL_METRICS)
def test_every_fault_signal_metric_is_watched_by_a_rule(metric):
    """A fault signal nobody alerts on is a metric that renders green while the fault is live."""
    # Word-boundary, not substring: `node_load1` is a strict prefix of `node_load15` (both admitted),
    # so a plain `in` lets a node_load15 rule satisfy a node_load1 entry. Same for
    # process_virtual_memory_bytes / _max_bytes.
    pattern = re.compile(rf"\b{re.escape(metric)}\b(?!_)")
    watching = [
        r["uid"] for r in _rules() if any(pattern.search(str(q.get("model", {}).get("expr", ""))) for q in r.get("data", []))
    ]
    assert watching, (
        f"{metric} is admitted to the capture keep-list but no alert rule queries it — nothing "
        f"would surface it, since no dashboard panel carries the app-metric families either. Add a "
        f"rule, or add it to NOT_A_FAULT_SIGNAL with the reason."
    )


# --- the summary must state the quantity the evaluator actually measures (T0103) -------------------


def _rule(uid):
    return next(r for r in _rules() if r["uid"] == uid)


def _threshold(rule):
    for node in rule["data"]:
        for cond in node.get("model", {}).get("conditions", []) or []:
            params = cond.get("evaluator", {}).get("params") or []
            if params:
                return params[0]
    raise AssertionError(f"no evaluator threshold in {rule['uid']}")


def test_the_healable_gap_rate_is_denominated_in_the_unit_its_summary_claims():
    """`zcrypto_reconcile_healable_gap_seconds_total` is summed ACROSS streams, so a bare threshold
    is in pair-seconds while the summary promises minutes -- at 12 pairs, `600` meant ~50 wall-clock
    seconds, and it tightened silently every time a pair was added. Dividing by the live pair count
    makes the threshold wall-clock seconds, which is what the summary already said.

    Pinned because the two halves live in different fields and nothing else compares them: the
    divisor could be dropped in a cleanup and the summary would keep asserting minutes."""
    rule = _rule("zcrypto-reconcile-healable-gap-rate")
    expr = " ".join(n.get("model", {}).get("expr", "") for n in rule["data"])
    summary = rule["annotations"]["summary"]

    assert "count by (pair)" in expr, "the threshold must be per-stream, not a cross-stream sum"
    minutes = _threshold(rule) / 60.0
    assert f"{minutes:.0f} minutes" in summary, f"summary claims a different quantity than {_threshold(rule)}s implies"


def test_the_permanent_loss_page_outlives_a_single_evaluation_hour():
    """It fires on `increase(...)` over a relative range, so the window IS how long the page stays
    up. At 1h the highest-severity signal for a permanent, unbackfillable condition self-resolved to
    MissingSeries an hour after firing -- which is how a real 2,437 s loss went quiet unnoticed."""
    rule = _rule("zcrypto-reconcile-residual-gap")
    ranges = [n["relativeTimeRange"]["from"] for n in rule["data"] if n.get("relativeTimeRange", {}).get("from")]
    expr = " ".join(n.get("model", {}).get("expr", "") for n in rule["data"])

    assert max(ranges) >= 86400, f"query range {max(ranges)}s is shorter than a day"
    assert "[24h]" in expr, "the increase() window must match the query range"


def test_the_new_breakage_window_matches_its_relative_time_range():
    """Same coupling as the residual-gap test above, for the rule that is the only one guarding NEW
    breakage in unbackfillable canonical data: `relativeTimeRange.from` and the `delta()` window must
    agree, or a future edit shortening one silently truncates what the other reads."""
    rule = _rule("zcrypto-ops-verify-replay-new-breakage")
    ranges = [n["relativeTimeRange"]["from"] for n in rule["data"] if n.get("relativeTimeRange", {}).get("from")]
    expr = " ".join(n.get("model", {}).get("expr", "") for n in rule["data"])

    assert max(ranges) >= 90000, f"query range {max(ranges)}s is shorter than 25h"
    assert "[25h]" in expr, "the delta() window must match the query range"


# --- the re-verification backlog rule: its two-night shape IS the rule ---------------------------
# The incremental sweep announces `pending` -- hours whose bytes changed that the nightly drain
# budget did not reach. A backlog is normal and self-clearing; one that stops shrinking means the
# instrument is degraded. Every number below is load-bearing and none of them is checkable by
# reading the rule, so each gets its own assertion with the failure it prevents written down.

_BACKLOG_STUCK = "zcrypto-ops-verify-replay-backlog-stuck"


def test_the_backlog_stuck_rule_exists_and_fits_the_uid_column():
    """Presence, pinned separately so the shape tests below fail on their own subject rather than on
    a `StopIteration` from the lookup helper. This uid sits one character under the 40-char
    ceiling."""
    assert _BACKLOG_STUCK in [r["uid"] for r in _rules()], "the re-verification backlog has no alert rule"
    assert len(_BACKLOG_STUCK) <= _UID_MAX, f"{len(_BACKLOG_STUCK)} chars -- the create call will 400"


def _duration_seconds(text: str) -> int:
    """Grafana durations as they appear in this file: `0s`, `15m`, `27h`."""
    unit = {"s": 1, "m": 60, "h": 3600}[text[-1]]
    return int(text[:-1]) * unit


def _backlog_window_seconds(rule) -> int:
    expr = " ".join(n.get("model", {}).get("expr", "") for n in rule["data"])
    return int(re.search(r"\[(\d+)h\]", expr).group(1)) * 3600


def test_the_backlog_stuck_window_sees_exactly_two_nightly_runs():
    """26h, and 26h in BOTH fields. The window's job is to span exactly the last two runs: wide
    enough that night two's sample is always inside it (24h + slack for a run that starts late),
    narrow enough that a THIRD run's history never is. Widening to 49h is the tempting edit and it is
    wrong -- it drags a third and fourth night into the same difference, so the sign of `delta` stops
    meaning "did the last run make progress"."""
    rule = _rule(_BACKLOG_STUCK)
    expr = " ".join(n.get("model", {}).get("expr", "") for n in rule["data"])
    windows = re.findall(r"\[(\d+)h\]", expr)

    assert windows == ["26"], f"expected exactly one 26h range selector, got {windows}"
    ranges = [n["relativeTimeRange"]["from"] for n in rule["data"] if n.get("relativeTimeRange", {}).get("from")]
    assert max(ranges) == 26 * 3600, f"relativeTimeRange {max(ranges)}s does not match the {windows[0]}h delta window"


def test_the_backlog_stuck_for_strictly_exceeds_a_healthy_drains_true_duration():
    """The invariant that decides this rule, stated as arithmetic rather than as a story.

    `ops_verify_replay_pending_hours` is a PERSISTENT textfile gauge: the runner prints it every run,
    so it is scraped continuously and holds its value between the daily runs. The condition goes true
    at the bump night's publish `T1` and CANNOT go false until the window's left edge passes `T1` --
    before then the window still contains a pre-bump sample, so `delta` stays positive even after
    night two's decrease has landed. A healthy drain therefore holds the condition true for exactly
    `max(24h, window)`, and `for` must STRICTLY exceed that or healthy and stuck fire identically.

    This is not hypothetical: `for: 25h` shipped in this rule's first draft against a 26h window --
    `25h < max(24h, 26h)` -- and paged on every healthy multi-night drain, the exact failure the rule
    exists to avoid. Equality is not enough either (`for: 26h` trips on a 26h true run)."""
    rule = _rule(_BACKLOG_STUCK)
    hold = max(24 * 3600, _backlog_window_seconds(rule))

    assert _duration_seconds(rule["for"]) > hold, (
        f"for: {rule['for']} does not strictly exceed the {hold / 3600:g}h a HEALTHY drain holds this "
        f"condition true -- healthy and stuck would page identically"
    )


def test_a_healthy_drain_stays_quiet_and_a_stuck_one_pages():
    """The timeline nobody simulated the first time, which is why the wrong `for` shipped green.

    Replays four nightly-gauge histories through the rule's OWN window and `for:` (read from
    `alerts.yaml`, never restated here, so this fails when the rule changes) and asserts the rule
    discriminates. The gauge model is the real one: a step function that holds its last published
    value, with `delta(pending[W])` read as `v(t) - v(t-W)` -- Prometheus extrapolates the edges, but
    the SIGN of the difference, which is all this rule reads, is unaffected."""
    rule = _rule(_BACKLOG_STUCK)
    window, hold_for = _backlog_window_seconds(rule), _duration_seconds(rule["for"])

    day, first_run = 24 * 3600, 3 * 3600 + 41 * 60  # the nightly timer's 03:41 start
    scenarios = {
        "steady state, nothing ever stale": [0, 0, 0, 0, 0, 0],
        "healthy drain, ~1500 hours a night": [4500, 3000, 1500, 0, 0, 0],
        "stuck flat -- budget zero or drain broken": [3500, 3500, 3500, 3500, 3500, 3500],
        "growing -- staleness outruns the drain": [1000, 2000, 3000, 4000, 5000, 6000],
    }

    def fires(published: list[int], hold_for: int) -> bool:
        events = [(first_run + n * day, v) for n, v in enumerate(published)]

        def value(t):  # the gauge holds its last published value; 0 before the first run
            return next((v for at, v in reversed(events) if at <= t), 0)

        run = 0
        for t in range(0, 10 * day, 60):
            if value(t) > 0 and value(t) - value(t - window) >= 0:
                run += 60
                if run >= hold_for:
                    return True
            else:
                run = 0
        return False

    verdicts = {name: fires(pub, hold_for) for name, pub in scenarios.items()}
    assert verdicts == {
        "steady state, nothing ever stale": False,
        "healthy drain, ~1500 hours a night": False,
        "stuck flat -- budget zero or drain broken": True,
        "growing -- staleness outruns the drain": True,
    }, f"the rule does not discriminate a healthy drain from a stuck one: {verdicts}"

    # And the discrimination is genuinely the `for`'s doing, not an artifact of this simulation: at
    # the 25h that first shipped, the healthy drain fires too -- indistinguishable from stuck.
    assert fires(scenarios["healthy drain, ~1500 hours a night"], 25 * 3600), (
        "the simulation cannot reproduce the defect it exists to prevent -- it is not proving anything"
    )


def test_the_backlog_stuck_rule_needs_both_a_live_backlog_and_a_non_shrinking_one():
    """Two halves, and dropping either one inverts the rule. Without `$A > 0` a drained-to-zero
    backlog reads `delta == 0` forever and pages permanently on a healthy fleet; without
    `$B >= 0` any nonzero backlog pages, which is every night of a legitimate multi-night drain."""
    rule = _rule(_BACKLOG_STUCK)
    by_ref = {n["refId"]: n.get("model", {}) for n in rule["data"]}

    assert by_ref["A"].get("expr") == "ops_verify_replay_pending_hours"
    assert by_ref["B"].get("expr") == "delta(ops_verify_replay_pending_hours[26h])"
    math = [m for m in by_ref.values() if m.get("type") == "math"]
    assert len(math) == 1, f"expected one math node combining the two halves, got {len(math)}"
    assert math[0]["expression"] == "$A > 0 && $B >= 0", f"the two halves are not both required: {math[0]['expression']!r}"


def test_the_backlog_stuck_rule_fires_in_the_direction_it_claims_to():
    """The whole conjunction is decorative unless the CONDITION reads the node that computes it and
    compares it the right way round. Two edits leave every other assertion in this file green while
    making the rule permanently wrong: `condition: A` drops the `delta` half entirely and pages on any
    nonzero backlog, and a `lt` evaluator can NEVER fire, because the math node emits only 0 or 1 and
    neither is below 0. A rule that cannot fire is indistinguishable from a healthy fleet."""
    rule = _rule(_BACKLOG_STUCK)
    by_ref = {n["refId"]: n.get("model", {}) for n in rule["data"]}

    assert rule["condition"] == "D", f"condition {rule['condition']!r} is not the node that combines both halves"
    assert by_ref["D"].get("expression") == "C", "the threshold must read the math node, not a raw query"
    assert by_ref["D"]["conditions"][0]["evaluator"] == {"type": "gt", "params": [0]}, (
        "the math node emits 0 or 1 -- anything but `gt 0` here makes the rule unable to fire"
    )


def test_the_backlog_stuck_rule_stays_quiet_on_a_host_that_has_never_swept():
    """`noDataState: OK` -- the dead-man owns "did the sweep run at all", so a missing series here is
    absence, not a stuck backlog, and Alerting on it would page every fresh host. `execErrState:
    Alerting` because a query that cannot evaluate leaves the backlog unwatched."""
    rule = _rule(_BACKLOG_STUCK)
    assert rule["noDataState"] == "OK", "a host with no sweep history would page"
    assert rule["execErrState"] == "Alerting", "a broken query would leave the backlog silently unwatched"


# --- the sleeve-composition rule: `changes`, not `delta`, is the whole rule ------------------------

_SLEEVE_CHANGED = "zcrypto-engine-sleeve-count-changed"


def test_the_sleeve_composition_rule_counts_steps_rather_than_netting_them():
    """`delta()` is the tempting edit here — every sibling rule in this file uses it — and it is
    wrong for this signal, silently. `zcrypto_engine_active_sleeves` is a non-monotone gauge, so
    `delta` reads the NET change across the window: a sleeve arming while another goes flat nets to
    zero, and so does a sleeve arming and going flat again inside one window. Both are exactly the
    events this rule exists to announce, and both would leave it quiet — indistinguishable from a
    composition that never moved. `changes()` counts the steps instead, which is why the evaluator
    can be a plain `gt 0` in either direction."""
    rule = _rule(_SLEEVE_CHANGED)
    expr = " ".join(n.get("model", {}).get("expr", "") for n in rule["data"])

    assert "changes(" in expr, f"the rule must count steps, not net them: {expr!r}"
    assert "delta(" not in expr, f"delta() nets an arm against a flat and reads zero: {expr!r}"
    assert _threshold(rule) == 0, "any step is the event -- a higher threshold would ignore single re-armings"


def test_the_sleeve_composition_window_matches_its_relative_time_range():
    """The same coupling the residual-gap and new-breakage rules pin: shortening one field without
    the other silently truncates what the rule reads."""
    rule = _rule(_SLEEVE_CHANGED)
    ranges = [n["relativeTimeRange"]["from"] for n in rule["data"] if n.get("relativeTimeRange", {}).get("from")]
    expr = " ".join(n.get("model", {}).get("expr", "") for n in rule["data"])

    assert re.findall(r"\[(\d+)h\]", expr) == ["26"], f"expected exactly one 26h range selector: {expr!r}"
    assert max(ranges) == 26 * 3600, f"relativeTimeRange {max(ranges)}s does not match the 26h changes() window"


def test_the_sleeve_composition_rule_stays_quiet_while_the_series_does_not_exist_yet():
    """`noDataState: OK` is load-bearing twice over: the series does not exist until the engine
    converge that ships it lands, and it is deliberately left unpublished until the first cycle
    measures a composition. Alerting on absence would page continuously through both, and the
    engine going dark is already the dead-man's and the cycle-staleness rule's job."""
    rule = _rule(_SLEEVE_CHANGED)
    assert rule["noDataState"] == "OK", "an engine that has not yet published a composition would page"
    assert rule["execErrState"] == "Alerting", "a broken query would leave the composition silently unwatched"
    assert rule["labels"]["severity"] == "warning", "this announces a change in the book, not a fault"


# --- the runbook link an alert sends an operator to must actually exist ---------------------------
# Nothing mechanically checks these: `grafana-push.sh` ships the summary verbatim, and a renamed or
# never-written anchor renders as a plain `#fragment` that scrolls nowhere. This repo has already
# shipped a runbook section that existed but was unreachable from the page it served, which is worth
# exactly as much as no runbook at all -- the responder is on a phone at 03:00 with nothing open.

RUNBOOKS = REPO / "infra/runbooks"
# The anchors are explicit `<a name=...>` tags rather than heading slugs precisely so the
# `-- ALERT` / `-- KNOWN LIMITATION` marker cannot become part of them; match that literal form.
_ANCHOR_TAG = re.compile(r'<a name="([A-Za-z0-9._-]+)"></a>')
# Path-agnostic across the runbook directory: the procedures live in per-subsystem files and the
# README is only the index, so a citation names whichever file holds the section. BOTH halves are
# captured, because a link resolves against the file it names -- an anchor that lives in a SIBLING
# file scrolls nowhere, which is exactly what a section moved without its citations looks like.
# The anchor half excludes `.` (the file half needs it): no anchor carries one, and the dashboard
# descriptions end the sentence right after the citation, which a dot-accepting class would swallow.
# Fail-closed if that ever changes -- a truncated anchor resolves to nothing and the test says so.
_RUNBOOK_LINK = re.compile(r"infra/runbooks/([A-Za-z0-9._-]+\.md)#([A-Za-z0-9_-]+)")
# The index's own rows link SIDEWAYS -- `](capture.md#anchor)`, relative, no `infra/runbooks/`
# prefix -- so `_RUNBOOK_LINK` structurally cannot see them. Matched separately for that reason.
_INDEX_LINK = re.compile(r"\]\(([A-Za-z0-9._-]+\.md)#([A-Za-z0-9_-]+)\)")


def _runbook_anchors() -> dict[str, list[str]]:
    """Every anchor under `infra/runbooks/`, mapped to the file name(s) that define it."""
    found: dict[str, list[str]] = {}
    for path in sorted(RUNBOOKS.glob("*.md")):
        for anchor in _ANCHOR_TAG.findall(path.read_text()):
            found.setdefault(anchor, []).append(path.name)
    return found


def test_every_runbook_anchor_is_defined_in_exactly_one_file():
    """Two files defining the same anchor makes every citation of it ambiguous -- and a section
    copied to its new subsystem file without being deleted from the old one is exactly how that
    happens, silently, while every citation still resolves."""
    dupes = {anchor: files for anchor, files in _runbook_anchors().items() if len(files) > 1}
    assert not dupes, f"a runbook anchor is defined in more than one file, so a citation of it is ambiguous: {dupes}"


def test_every_alert_rule_carries_a_resolving_runbook_link():
    """A rule with no runbook is read on a phone, in Slack, with nothing open -- the situation the
    runbook protocol exists for. Requiring the link on EVERY rule is what keeps a new rule from
    shipping without a procedure; the sibling test above only checks the links that are present."""
    anchors = _runbook_anchors()
    unlinked = []
    for rule in _rules():
        summary = (rule.get("annotations") or {}).get("summary") or ""
        links = _RUNBOOK_LINK.findall(summary)
        if not links or any(filename not in anchors.get(anchor, ()) for filename, anchor in links):
            unlinked.append(rule["uid"])
    assert not unlinked, (
        f"{len(unlinked)} rule(s) carry no resolving runbook link in their summary, so a paged "
        f"operator has nothing to open: {sorted(unlinked)}"
    )


def test_every_runbook_link_in_an_alert_summary_resolves():
    anchors = _runbook_anchors()
    cited, broken = [], []
    for rule in _rules():
        for filename, anchor in _RUNBOOK_LINK.findall(" ".join((rule.get("annotations") or {}).values())):
            cited.append(f"{filename}#{anchor}")
            if filename not in anchors.get(anchor, ()):
                broken.append((rule["uid"], f"{filename}#{anchor}", anchors.get(anchor) or "no runbook file"))

    assert cited, "no rule cites a runbook anchor -- the regex is broken, not the summaries"
    assert not broken, (
        f"an alert summary points at a runbook anchor the file it names does not define -- the "
        f"responder gets a fragment and no next step (uid, cited, actually defined in): {broken}"
    )


def test_every_runbook_link_in_a_dashboard_description_resolves():
    """The panel descriptions cite sections the same way the summaries do, and they are read at the
    same moment -- a responder who followed the notification's panel link is already on the board.
    Held to the same bar rather than left to the summaries' test, which reads `alerts.yaml` only."""
    anchors = _runbook_anchors()
    cited, broken = [], []
    for path in sorted((REPO / "infra/grafana").glob("*.json")):
        for filename, anchor in _RUNBOOK_LINK.findall(path.read_text()):
            cited.append(f"{filename}#{anchor}")
            if filename not in anchors.get(anchor, ()):
                broken.append((path.name, f"{filename}#{anchor}", anchors.get(anchor) or "no runbook file"))

    assert cited, "no dashboard cites a runbook anchor -- the regex is broken, not the descriptions"
    assert not broken, f"a dashboard description points at a runbook anchor its named file does not define: {broken}"


def test_the_index_routes_to_every_section_and_only_to_real_ones():
    """The README is a pure index, so its rows ARE the entry point: a summary's path resolves to
    that page, and the row is the responder's next tap. Its links are relative, which puts them
    outside every other guard here -- a move that updates the summaries and the panels and forgets
    the index misroutes exactly the page the responder lands on. Both directions are pinned: a row
    pointing at a file that does not define the anchor, and a section no row routes to at all,
    which is reachable only by someone who already knows which file to open."""
    anchors = _runbook_anchors()
    linked = _INDEX_LINK.findall((RUNBOOKS / "README.md").read_text())

    assert linked, "the index has no anchor-bearing rows -- the regex is broken, not the index"
    broken = [(f"{name}#{a}", anchors.get(a) or "no runbook file") for name, a in linked if name not in anchors.get(a, ())]
    assert not broken, f"an index row links at a section the file it names does not define (row, actually defined in): {broken}"

    unrouted = sorted(set(anchors) - {a for _, a in linked})
    assert not unrouted, f"a runbook section no index row routes to -- unreachable from the entry point: {unrouted}"


def test_the_backlog_stuck_summary_sits_where_the_vocabulary_guard_reads_it():
    """`test_internal_terms_not_operator_visible` joins `annotations.values()` and scans nothing
    else, so operator text parked anywhere but `annotations` ships unscanned. Pin that this rule's
    Slack message is inside what that guard reads, and that it is self-contained enough to act on:
    it names the runbook, so the responder is never left with a fragment and no next step."""
    rule = _rule(_BACKLOG_STUCK)
    summary = (rule.get("annotations") or {}).get("summary", "")

    assert summary.strip(), "no annotations.summary -- the vocabulary guard would scan an empty string"
    assert _RUNBOOK_LINK.search(summary), "the summary names no runbook, so the page carries no next step"


# --- a summary may never interpolate the internal hostname ----------------------------------------

# Every form Grafana's Go templater accepts for the same field. A summary is baked at EVALUATION
# time, before any notification template runs, so the `zcrypto.host` -> friendly-name mapping in the
# notification templates cannot reach it: an interpolated `host` ships the raw internal hostname
# straight to a phone. The runtime VALUE is unprotectable from here, but the interpolation TOKEN is
# literal text in the file and is therefore walkable -- which is the whole point, because this exact
# edit has been made, reverted, and then re-instructed by a stale spec row.
_HOST_INTERPOLATIONS = ("$labels.host", ".Labels.host", 'index $labels "host"')


def test_no_alert_summary_interpolates_the_internal_hostname():
    offenders = [
        (r["uid"], token)
        for r in _rules()
        for token in _HOST_INTERPOLATIONS
        if token in (r.get("annotations") or {}).get("summary", "")
    ]
    assert not offenders, (
        f"an alert summary interpolates the internal hostname: {offenders}. Summaries are rendered "
        f"before the notification template's host mapping, so say 'the host this notification names' "
        f"and let the template do the naming."
    )


# --- the total-blackout rule, pinned by uid because the family guard cannot see it ---------------

_ALL_STREAMS_SILENT = "zcrypto-capture-all-streams-silent"


def test_the_total_blackout_rule_exists_and_keeps_its_discriminating_aggregation():
    """On 2026-07-27 all 12 pairs went silent for ~209 s on BOTH capture hosts while the socket
    reported connected, the keepalive completed >=11 round trips and the cumulative gap counter read
    0.0 -- the dead-man, the desync rule and the gap counter all sat green through a total blackout
    of unbackfillable L2. This rule is the only thing that sees that shape, and the `min by (host)`
    IS the rule: the minimum across pairs is what distinguishes one quiet leg (normal at any hour)
    from the whole feed stopping, and it is what lets the bar be tight enough to matter.

    Pinned by uid rather than left to `test_every_fault_signal_metric_is_watched_by_a_rule`, which
    cannot cover it: that guard is FAMILY-level, and `zcrypto-capture-stream-silent` queries the same
    `zcrypto_capture_seconds_since_last_book_message`, so each rule excuses the other and deleting
    this one alone leaves that test green."""
    rule = _rule(_ALL_STREAMS_SILENT)
    expr = " ".join(n.get("model", {}).get("expr", "") for n in rule["data"])

    assert len(_ALL_STREAMS_SILENT) <= _UID_MAX, f"{len(_ALL_STREAMS_SILENT)} chars -- the create call will 400"
    assert "min by (host) (" in expr, (
        f"the cross-pair MINIMUM is the discriminator -- any other aggregation reads a healthy pair "
        f"and sits green through a total blackout: {expr!r}"
    )


_STREAM_SILENT = "zcrypto-capture-stream-silent"


@pytest.mark.parametrize("uid", [_ALL_STREAMS_SILENT, _STREAM_SILENT])
def test_the_capture_silence_rules_stay_quiet_when_the_query_itself_cannot_run(uid):
    """`execErrState: OK` on these two ALONE, and it is the same blindness class as their
    `noDataState: OK` rather than a relaxation of it.

    When Grafana cannot execute the query, the query did not run -- so `Alerting` cannot report a
    blackout, it ASSERTS one, in a summary that names a host and says every stream on it has been
    silent for minutes. Measured 2026-08-05..08-28 from Grafana's alert state history (NOT from
    metrics -- a different store, which is how the window outruns the 14 d metric retention; the
    runbook section names the endpoint and the truncation trap), these two rules raised 264
    execution-error instances against 52 genuine ones, every one of them Grafana Cloud failing to
    reach its own Prometheus. `for: 0s` is load-bearing for their detection arithmetic and is what
    made a one-minute platform hiccup page instantly.

    Two qualifications the choice rests on, both measured. It is NOT the guarded-summary form used
    on `zcrypto-capture-venue-state-recurrence` (2a899adb), which removes the same falseness but not
    the volume -- and here the per-pair rule mints 24 instances per error where that one mints one
    or two. And "nothing goes unwatched" holds for a CORRELATED outage only: six of the 22 rules in
    `zcrypto-capture` carry `for: 0s` and can fire on a hiccup that short, four of which keep
    `Alerting`. A RULE-SCOPED error on these two alone now pages nothing -- an accepted residual,
    named in the runbook rather than left to be discovered."""
    rule = _rule(uid)
    assert rule["execErrState"] == "OK", "a Grafana query failure would page a total-capture-blackout that nothing observed"
    assert rule["noDataState"] == "OK", "the sibling blindness state moved without its reason"
    assert rule["for"] == "0s", (
        "the execErrState reasoning above rests on `for: 0s` -- a pending period would already "
        "have absorbed the one-minute transients, and this pin should be re-derived"
    )


def test_no_other_rule_quietly_joins_the_execerrstate_exemption():
    """The exemption is justified by measurement on exactly two rules. A third arriving without its
    own evidence is how a deliberate, narrow choice becomes a silent default -- which is how all 75
    rules came to carry `Alerting` unexamined in the first place."""
    exempt = {r["uid"] for r in _rules() if r["execErrState"] == "OK"}
    assert exempt == {_ALL_STREAMS_SILENT, _STREAM_SILENT}, (
        f"execErrState: OK is measured-and-argued for the two capture silence rules only; found {sorted(exempt)}"
    )


# --- a self-declared provisional threshold must be registered here, not only in a comment ---------
# `grafana-push.sh` upserts unconditionally, so a bar whose own comment says "it must not reach a
# push in this state" is held back by plan prose alone unless something in the repo names it. Each
# entry states what derives the value, so the deferral is readable without opening the plan; when the
# real value lands, the comment and the entry are deleted together and the staleness test below is
# what forces the second half.

# An entry here declares a threshold this file ships knowing it is provisional; the paired staleness
# test refuses an entry whose rule no longer carries the marker, so a bar that has been derived
# cannot leave its excuse behind. A previous occupant, `zcrypto-capture-stream-silent`, was derived
# 2026-08-05 on a base one week deep rather than the month its `[30d]` selector implied; T0129
# re-derived it 2026-08-28 on the full 14 d retained and left the bar unchanged, so it is not
# provisional and does not belong here.
PROVISIONAL_THRESHOLDS: set[str] = {
    # Both bars come from a linear fit in `infra/scripts/bench-ledger-scan.py` -- ~3 microseconds and
    # ~1.2 KiB of resident memory per record, measured at 1,000,000 synthetic records -- not from a
    # ledger ever observed at that size. The live one holds ~100. The critical bar also encodes the
    # ops host's MemAvailable, so its percentage is true only of the day it was read. What derives
    # the real values: re-run that benchmark against the ledger's own record shape once it is large
    # enough for the fit to be checked rather than extrapolated, and read the operand live as
    # node_memory_MemAvailable_bytes{host="ops"} -- never MemFree, which is ~10x smaller.
    "zcrypto-reconcile-ledger-scan-slow",
    "zcrypto-reconcile-ledger-scan-critical",
    # 64 MiB of hourly-floor growth over 24 h. No leak has ever been measured on this fleet, so the
    # bar is sized for notice -- a week ahead of the headroom page from a ~150 MiB start -- not fitted
    # to a distribution. What derives the real value: the first leak it fires on, or thirty days of
    # floor deltas read from the fleet board's growth-per-day panel.
    "zcrypto-fleet-memory-leak",
}

_PROVISIONAL = "PROVISIONAL"


def _uids_with_a_provisional_marker() -> set[str]:
    """Attribute each `PROVISIONAL` comment line to the rule it sits inside. Comments are stripped by
    the YAML parser, so this walks the raw text -- the marker only ever lives in a comment."""
    uid, found = None, set()
    for line in ALERTS.read_text().splitlines():
        if line.startswith("  - uid:"):
            uid = line.split("uid:", 1)[1].strip()
        # config-selector-ok: scanning every line for a marker, not selecting a setting
        if _PROVISIONAL in line and uid is not None:
            found.add(uid)
    return found


def test_every_provisional_threshold_is_registered():
    unregistered = _uids_with_a_provisional_marker() - PROVISIONAL_THRESHOLDS
    assert not unregistered, (
        f"a rule declares its own threshold {_PROVISIONAL} but nothing outside that comment knows: "
        f"{sorted(unregistered)}. Add it to PROVISIONAL_THRESHOLDS with what derives the real value, "
        f"or derive the value and delete the marker."
    )


def test_the_provisional_register_has_not_gone_stale():
    """The other half, and the half that makes the register worth having: an entry outliving its
    marker is a deferral that reads live while the value it guarded was quietly settled, which is
    exactly the failure the register exists to prevent."""
    discharged = PROVISIONAL_THRESHOLDS - _uids_with_a_provisional_marker()
    assert not discharged, (
        f"registered as provisional but the rule no longer says so: {sorted(discharged)}. If the "
        f"threshold was derived, delete the entry in the same change."
    )


# --- Grafana's template parser is stricter than Go's ------------------------------------------
# A leading trim marker on a define declaration -- `{{- define "x" ... }}` -- parses fine in Go's
# own text/template and renders identically, but Grafana's provisioning API REJECTS it with
# `invalid template: unexpected <define> in command` and the whole push aborts under
# `set -euo pipefail`. Measured against the live API 2026-08-05, by probe: `{{ define` -> 202,
# `{{- define` -> 400, with trim markers everywhere else (`-}}`, `{{- end`, `{{- template`)
# accepted. So the trailing `-}}` that trims the define's BODY stays; only the leading one goes.
# A Go-based test cannot catch this -- Go accepts what Grafana refuses -- which is why it is here.
NOTIFICATION_TEMPLATES = sorted((REPO / "infra/grafana/notification-templates").glob("*.tmpl"))


@pytest.mark.parametrize("path", NOTIFICATION_TEMPLATES, ids=lambda p: p.name)
def test_no_define_carries_a_leading_trim_marker(path):
    offenders = [
        f"{path.name}:{i}: {line.strip()[:70]}"
        for i, line in enumerate(path.read_text().splitlines(), 1)
        if re.search(r"\{\{-\s*define\s", line)
    ]
    assert not offenders, (
        "Grafana's provisioning API rejects a define whose action opens with a trim marker, and the "
        "push aborts before any rule ships. Drop the leading `-` (keep the trailing `-}}`):\n  " + "\n  ".join(offenders)
    )


# --- the venue pair: a latch that cannot self-resolve, plus the recurrence signal that can --------
# `zcrypto-capture-venue-not-online` fires on PRESENCE of a non-online series and never falls until
# the capture daemon restarts. That latch is deliberate, but it means a repeat of an already-seen
# state only steps a counter whose alert instance is already Alerting, so nothing notifies. The
# recurrence rule below closes that, and the two only partition the space while each keeps its own
# form: presence catches a series born at 1, increase() catches every step thereafter. Swap either
# to the other's form and a real venue degradation goes unreported.

_VENUE_LATCH = "zcrypto-capture-venue-not-online"
_VENUE_RECURRENCE = "zcrypto-capture-venue-state-recurrence"


def test_the_venue_recurrence_rule_exists_and_fits_the_uid_column():
    """Pinned separately so the shape tests below fail on their own subject rather than on a
    `StopIteration` from the lookup helper."""
    assert _VENUE_RECURRENCE in [r["uid"] for r in _rules()], "a repeat venue degradation has no alert rule"
    assert len(_VENUE_RECURRENCE) <= _UID_MAX, f"{len(_VENUE_RECURRENCE)} chars -- the create call will 400"


def test_the_venue_recurrence_window_matches_its_relative_time_range():
    """Same coupling the residual-gap and new-breakage rules carry: `relativeTimeRange.from` and the
    `increase()` window must agree, or a future edit to one silently truncates what the other reads."""
    rule = _rule(_VENUE_RECURRENCE)
    ranges = [n["relativeTimeRange"]["from"] for n in rule["data"] if n.get("relativeTimeRange", {}).get("from")]
    expr = " ".join(n.get("model", {}).get("expr", "") for n in rule["data"])

    assert max(ranges) == 900, f"query range {max(ranges)}s is not the 15m the summary promises"
    assert "[15m]" in expr, "the increase() window must match the query range"


def test_the_two_venue_rules_keep_opposite_forms():
    """The whole point of the pair. increase() cannot lead -- a non-online series is born at 1 and
    Prometheus inserts no implicit zero, so it reports nothing on the first transition; presence
    cannot follow -- it is already firing, so a repeat produces no new notification. If a future edit
    makes both rules the same form, one of the two venue failures stops being reported and nothing
    else in this file would notice."""
    latch = " ".join(n.get("model", {}).get("expr", "") for n in _rule(_VENUE_LATCH)["data"])
    recurrence = " ".join(n.get("model", {}).get("expr", "") for n in _rule(_VENUE_RECURRENCE)["data"])

    assert "increase(" not in latch, "the latch must stay a PRESENCE form -- increase() is blind to a series born at 1"
    assert "increase(" in recurrence, "the recurrence rule must stay an increase() form -- presence cannot re-notify"


def test_both_venue_rules_group_by_the_label_the_responder_acts_on():
    """`maintenance` (planned, wait) and `cancel_only`/`post_only` (degraded, act) demand opposite
    responses, so collapsing `system` discards the one label the page is read for. The `on()` on the
    fallback is load-bearing for the same grouping: `vector(0)` is unlabelled, so a bare `or` stops
    being mutually exclusive once the left arm carries labels and rides through as a permanent series."""
    for uid in (_VENUE_LATCH, _VENUE_RECURRENCE):
        expr = " ".join(n.get("model", {}).get("expr", "") for n in _rule(uid)["data"])
        assert "by (host, system)" in expr, f"{uid} collapsed the label the responder acts on"
        assert "or on() vector(0)" in expr, f"{uid} lost the labelled-arm-safe NoData fallback"


# --- memory is watched as a routine, never as a rollout read ---------------------------------------
# The bake used to carry an RSS row read by hand at T+24 h, T+50 h ... against the host's own
# predecessor at equal process age. Every such read was a human scheduling a query, and the next
# converge voided it -- so the reads became a lock on the fleet. These three rules are that routine
# as telemetry: they run regardless of converges, and a bake owes no memory read at all.

_MEM_HEADROOM = "zcrypto-fleet-memory-headroom"
_MEM_LEAK = "zcrypto-fleet-memory-leak"
_DAEMON_RESTARTED = "zcrypto-fleet-daemon-restarted"
ANSIBLE = REPO / "infra/ansible"


def _compose_alloy_limit_bytes(path: Path) -> int:
    """The `memory:` limit under the grafana-alloy service in a compose file -- a literal in the three
    shared-cap legs this helper is actually called for (zcrypto and zcrypto-red, both the capture
    role's template, and nas, its own compose file). ops is deliberately excluded: its cap is the
    `ops_alloy_memory_limit` var, not a literal, so passing its template through here would trip the
    `assert m` below."""
    text = path.read_text()
    start = text.index("container_name: grafana-alloy")
    m = re.search(r"memory:\s*\"?(\d+)([gGmM])\"?", text[start:])
    assert m, f"no memory limit under grafana-alloy in {path}"
    return int(m.group(1)) * {"g": 1024**3, "m": 1024**2}[m.group(2).lower()]


def _ansible_memory_limit_bytes(path: Path, key: str) -> int:
    """`"2g"` / `"1g"` as docker reads them -- binary units, the only ones compose accepts here."""
    value = yaml.safe_load(path.read_text())[key]
    units = {"g": 1024**3, "m": 1024**2}
    return int(value[:-1]) * units[value[-1].lower()]


_GOMEMLIMIT_UNITS = {"b": 1, "kib": 1024, "mib": 1024**2, "gib": 1024**3, "tib": 1024**4}


def _parse_size_bytes(value: str) -> int:
    """`"920MiB"`, as Alloy's GOMEMLIMIT -- Go's own suffixes only (`B`/`KiB`/`MiB`/`GiB`/`TiB`).
    Docker's `m`/`g` (the `_ansible_memory_limit_bytes`/`_compose_alloy_limit_bytes` side) parse to
    the same bytes at the SAME value but are invalid GOMEMLIMIT syntax -- Go rejects them and Alloy
    crash-loops at startup, so accepting them here would let that defect read as a passing ratio."""
    m = re.match(r"(\d+)(TiB|GiB|MiB|KiB|B)$", value.strip())
    assert m, f"not a valid Go GOMEMLIMIT suffix: {value!r}"
    return int(m.group(1)) * _GOMEMLIMIT_UNITS[m.group(2).lower()]


def _compose_alloy_gomemlimit_bytes(path: Path) -> int:
    """The `GOMEMLIMIT:` literal under the grafana-alloy service -- sibling of
    `_compose_alloy_limit_bytes`, same container_name-scoped search, reading the Go soft limit
    instead of the container cap."""
    text = path.read_text()
    start = text.index("container_name: grafana-alloy")
    m = re.search(r'GOMEMLIMIT:\s*"?(\d+(?:TiB|GiB|MiB|KiB|B))"?', text[start:])
    assert m, f"no GOMEMLIMIT under grafana-alloy in {path}"
    return _parse_size_bytes(m.group(1))


def test_the_headroom_rule_encodes_the_limits_ansible_actually_deploys():
    """The ratio's denominators are literal bytes in the expr, because no metric carries the container
    limit (no cadvisor on the capture hosts). A literal drifts silently when the ansible var moves --
    the rule would then measure headroom against a ceiling the host no longer has. So the three
    constants are read from the vars that render the compose files, never from this test's memory."""
    rule = _rule(_MEM_HEADROOM)
    expr = " ".join(str(n.get("model", {}).get("expr", "")) for n in rule["data"])
    primary = _ansible_memory_limit_bytes(ANSIBLE / "roles/capture/defaults/main.yml", "capture_memory_limit")
    secondary = _ansible_memory_limit_bytes(ANSIBLE / "host_vars/zcrypto-red/vars.yml", "capture_memory_limit")
    engine = _ansible_memory_limit_bytes(ANSIBLE / "roles/engine/defaults/main.yml", "engine_memory_limit")
    legs = [("zcrypto", "capture_app", primary), ("zcrypto-red", "capture_app", secondary), ("zcrypto", "engine_app", engine)]
    for host, job, limit in legs:
        leg = re.search(
            rf'process_resident_memory_bytes\{{[^}}]*host="{host}"[^}}]*job="{job}"[^}}]*\}}\s*/\s*(\d+)', expr
        ) or re.search(rf'process_resident_memory_bytes\{{[^}}]*job="{job}"[^}}]*host="{host}"[^}}]*\}}\s*/\s*(\d+)', expr)
        assert leg, f"no headroom leg for host={host} job={job} in {expr!r}"
        assert int(leg.group(1)) == limit, f"{host}/{job}: expr divides by {leg.group(1)}, ansible deploys {limit}"
    cond = rule["data"][-1]["model"]["conditions"][0]["evaluator"]
    assert cond == {"type": "gt", "params": [0.7]}, "70% of the container limit is the owner's bar (2026-08-28)"
    assert rule["for"] == "5m" and rule["noDataState"] == "OK"


def test_the_leak_rule_reads_hourly_floors_a_day_apart():
    """The bake's own lessons, as PromQL: read the FLOOR not a sample (the rotation sawtooth spans MiB),
    compare across a 24 h band (steps arrive as ~4 h ramps and repeat at the same clock offset), and
    gate the whole thing OFF for a process younger than 30 h. That gate is load-bearing, not
    decoration: `offset 24h` addresses the series by labels, which a restart does not change, so an
    ungated subtraction reads the predecessor process's floor and compares a young process against it
    -- the cold-baseline read that once nearly rolled back a healthy image. 30 h = the 24 h band plus
    the 6 h pending period, so no evaluation inside the pending window can straddle the restart."""
    rule = _rule(_MEM_LEAK)
    expr = " ".join(str(n.get("model", {}).get("expr", "")) for n in rule["data"])
    assert expr.count("min_over_time(process_resident_memory_bytes") == 2, expr
    assert "[1h]" in expr and "offset 24h" in expr, expr
    assert re.search(r"and on\(host, job\)\s*\(\(time\(\) - process_start_time_seconds\{[^}]*\}\) > 108000\)", expr), (
        "the age gate is what makes the restart claim true -- without it the rule compares a young process against its predecessor"
    )
    assert rule["for"] == "6h" and rule["noDataState"] == "OK"
    assert rule["labels"]["severity"] == "warning"


def test_the_restart_rule_is_the_only_restart_signal_and_absorbs_a_datasource_hiccup():
    """No cadvisor, so `RestartCount` has no metric -- but `process_start_time_seconds` is kept and
    moves on every restart, which is the same fact. `changes(...[15m])` stays >0 for fifteen minutes,
    so a pending period costs no detection and keeps the rule out of the `for: 0s` set that a
    one-minute datasource error can fire (see the execErrState reasoning on the silence rules)."""
    rule = _rule(_DAEMON_RESTARTED)
    expr = " ".join(str(n.get("model", {}).get("expr", "")) for n in rule["data"])
    assert "changes(process_start_time_seconds" in expr and "[15m]" in expr, expr
    assert rule["for"] != "0s", "a pending period is what keeps a datasource hiccup from firing this"
    assert rule["noDataState"] == "OK" and rule["execErrState"] == "Alerting"


_ALLOY_HEADROOM = "zcrypto-fleet-alloy-memory-headroom"


def test_alloy_has_its_own_headroom_bar_because_it_runs_near_its_ceiling():
    """Measured 2026-08-28 over 24 h as a fraction of the 512 MiB each Alloy compose sets: ops
    0.7525-0.7795, zcrypto 0.5237-0.5708, zcrypto-red 0.2636, nas 0.1441. The app daemons sit at
    0.08-0.37. A shared 0.7 bar therefore pages ops on a healthy fleet every evaluation -- which is
    exactly what it did, on the rollout that first pushed it. The bar here clears steady state; the
    OOM it warns about is owned separately by `Fleet · Alloy dark`."""
    rule = _rule(_ALLOY_HEADROOM)
    expr = " ".join(str(n.get("model", {}).get("expr", "")) for n in rule["data"])
    # ops divides by its OWN cap. 399.1 MiB peak against a 117 MiB swing left only 113 MiB under the
    # 512m every other Alloy carries, and ops is the one host where margin is free (62.5 GiB, 47
    # available) -- the capture hosts hold 3.83 and 1.93 GiB and already commit 3.5 g / 1.5 g of caps.
    # Read the number back from the ansible var so raising the cap without the rule fails here.
    ops_cap = _ansible_memory_limit_bytes(ANSIBLE / "roles/ops/defaults/main.yml", "ops_alloy_memory_limit")
    assert re.search(rf'host="ops", job="integrations/self"\}}\s*/\s*{ops_cap}\b', expr), (
        f"the ops leg must divide by ops_alloy_memory_limit ({ops_cap}); a cap raised without this ratio lies: {expr!r}"
    )
    # The other three are LITERALS in their own compose sources, so read each back the same way --
    # asserting the rule merely contains 536870912 would let `memory: 512m` move in a template while
    # the ratio kept dividing by the old cap, which is the silent lie the ops pin above exists to stop.
    others = {
        "zcrypto": ANSIBLE / "roles/capture/templates/alloy-compose.yaml.j2",
        "zcrypto-red": ANSIBLE / "roles/capture/templates/alloy-compose.yaml.j2",
        "nas": REPO / "infra/nas/compose.yaml",
    }
    caps = {h: _compose_alloy_limit_bytes(p) for h, p in others.items()}
    assert len(set(caps.values())) == 1, f"the three shared-cap hosts no longer share a cap: {caps} -- split the leg"
    shared = next(iter(caps.values()))
    assert re.search(rf'host=~"zcrypto\|zcrypto-red\|nas", job="integrations/self"\}}\s*/\s*{shared}\b', expr), (
        f"the shared leg must divide by the compose literal ({shared}); found: {expr!r}"
    )
    assert rule["data"][-1]["model"]["conditions"][0]["evaluator"]["params"] == [0.9]
    assert rule["for"] != "0s" and rule["noDataState"] == "OK"


def test_ops_alloy_memory_limit_has_no_override_the_pin_above_would_miss():
    """`test_alloy_has_its_own_headroom_bar...` reads `ops_alloy_memory_limit` from
    `roles/ops/defaults/main.yml` only -- a `host_vars/zcrypto-ops/vars.yml` or `group_vars/*` entry
    would pass that test while the deployed cap diverged from the ratio's denominator, unseen. The
    sibling `capture_memory_limit` uses exactly that override shape for real, in
    `host_vars/zcrypto-red/vars.yml` -- so it is asserted absent here rather than assumed. This walks
    every `*.yml` under `host_vars/` and `group_vars/`, vault files included: this repo vaults
    per-VALUE, so a key's NAME stays plaintext even in a `vault.yml` (each such file's own header
    says so), and the substring search below reads it. Only a key hidden inside an already-encrypted
    value would be missed, which is not how ansible variables work."""
    hits = [
        path
        for base in (ANSIBLE / "host_vars", ANSIBLE / "group_vars")
        for path in base.rglob("*.yml")
        if "ops_alloy_memory_limit" in path.read_text()
    ]
    assert not hits, f"ops_alloy_memory_limit overridden outside roles/ops/defaults/main.yml: {hits}"


def test_gomemlimit_is_the_same_fraction_of_the_cap_on_every_alloy_host():
    """The 0.9 headroom bar means "the runtime lost its soft limit" only if GOMEMLIMIT sits at the
    same fraction of the container cap on every host -- ops's 920MiB/1g and the other three's
    460MiB/512m both land at 0.898. [0.88, 0.92] tolerates the MiB-vs-binary-GiB rounding without
    tolerating a cap raised (or a GOMEMLIMIT left behind) without its ratio partner."""
    ops_defaults = ANSIBLE / "roles/ops/defaults/main.yml"
    ops_soft = _parse_size_bytes(yaml.safe_load(ops_defaults.read_text())["ops_alloy_gomemlimit"])
    ops_cap = _ansible_memory_limit_bytes(ops_defaults, "ops_alloy_memory_limit")
    ops_template = ANSIBLE / "roles/ops/templates/alloy-compose.yaml.j2"
    assert 'GOMEMLIMIT: "{{ ops_alloy_gomemlimit }}"' in ops_template.read_text(), (
        "the ops template does not read GOMEMLIMIT from the var above -- the ratio this test proves "
        "would hold on paper while a literal left in the template ships something else entirely"
    )
    ratios = {"ops": ops_soft / ops_cap}
    for host, compose_path in (
        ("zcrypto", ANSIBLE / "roles/capture/templates/alloy-compose.yaml.j2"),
        ("zcrypto-red", ANSIBLE / "roles/capture/templates/alloy-compose.yaml.j2"),
        ("nas", REPO / "infra/nas/compose.yaml"),
    ):
        ratios[host] = _compose_alloy_gomemlimit_bytes(compose_path) / _compose_alloy_limit_bytes(compose_path)
    for host, ratio in ratios.items():
        assert 0.88 <= ratio <= 0.92, f"{host}: GOMEMLIMIT/cap = {ratio:.3f}, outside [0.88, 0.92]"


@pytest.mark.parametrize("uid", [_MEM_HEADROOM, _MEM_LEAK, _DAEMON_RESTARTED])
def test_the_memory_routine_rules_cover_both_capture_hosts_and_the_engine(uid):
    """All three rules cover both capture daemons and the engine (primary only -- nothing listens on
    9102 on the secondary, so `up{job="engine_app",host="zcrypto-red"}` has read 0 for every sample of
    its life). The leak and restart rules additionally cover the ops liquidations poller and Alloy
    itself on all four hosts under the `integrations/self` job its exporter.self metrics carry
    (measured 2026-08-28) -- the headroom rule excludes both, Alloy to its own bar below, the poller
    for want of a limit to measure against. A selector that names a series that never exists is not
    coverage."""
    rule = _rule(uid)
    expr = " ".join(str(n.get("model", {}).get("expr", "")) for n in rule["data"])
    if uid == _MEM_HEADROOM:  # the app daemons only: Alloy has its own bar, the poller has no limit
        for token in ("capture_app", "engine_app"):
            assert token in expr, f"{uid} does not cover {token}: {expr!r}"
        assert "integrations/self" not in expr, "Alloy runs near its ceiling; a shared bar pages it on a healthy fleet"
        assert "liquidations_app" not in expr, "the poller has no limit to measure against"
    else:
        for token in ("capture_app", "engine_app", "integrations/self", "liquidations_app", "|nas"):
            assert token in expr, f"{uid} does not cover {token}: {expr!r}"
    assert not re.search(r'job="engine_app"[^}]*host=~"zcrypto\|zcrypto-red"', expr), "engine_app must not select zcrypto-red"
    assert not re.search(r'host=~"zcrypto\|zcrypto-red"[^}]*job="engine_app"', expr), "engine_app must not select zcrypto-red"


def test_every_runbook_cross_reference_resolves():
    """A runbook that points at a section in another runbook must point at one that exists.

    The alert-to-runbook direction has been guarded since these files were written; the
    runbook-to-runbook direction had 119 references and no guard, and one of them was wrong — the
    dead-man map sent the liquidations poller to `ops-node.md` for a section living in
    `observability.md`. An operator at 03:00 follows that link and finds nothing, which is worse
    than no link at all because it costs them the time to go looking.
    """
    runbooks = Path(__file__).resolve().parents[1] / "infra/runbooks"
    anchors, refs = set(), []
    for path in runbooks.glob("*.md"):
        text = path.read_text()
        anchors |= {f"{path.name}#{a}" for a in re.findall(r'<a name="([^"]+)"></a>', text)}
        refs += [(path.name, f"{m.group(1)}#{m.group(2)}") for m in re.finditer(r"\b([a-z0-9-]+\.md)#([a-z0-9-]+)", text)]
    assert refs, "no cross-references found at all — the extraction broke, not the runbooks"
    broken = sorted({(src, ref) for src, ref in refs if ref not in anchors})
    assert not broken, f"runbook references pointing at sections that do not exist: {broken}"
