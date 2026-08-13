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
# the run that first introduces it, which is when the diagnosis is hardest. (It is not that updates
# skip a validation: they simply never present a fresh uid to validate.)
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
    line = next(ln for ln in CAPTURE_ALLOY.read_text().splitlines() if "regex" in ln and "node_load1" in ln)
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
    # Cumulative gap seconds. BOTH of this exclusion's original grounds were falsified on 2026-07-27
    # (T0101) and are rewritten rather than left standing, because as written they argue against the
    # fix. It said the metric measured zero across all 24 series -- that ZERO WAS THE BLIND SPOT: the
    # daemon booked nothing through a total 12-pair blackout on both hosts. And it said an open gap
    # is covered twice over by the dead-man and the desync rule -- NEITHER saw it, because
    # `is_healthy()` consults open gap windows and a connected-but-silent stream opened none.
    # Spec 00073 makes the silence observable; alerting on it is deliberately deferred to T0105,
    # since an unfitted threshold in `is_healthy()` darkens the dead-man fleet-wide on both hosts.
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
    "process_resident_memory_bytes",
    "process_start_time_seconds",
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
    a `StopIteration` from the lookup helper. The 40-char ceiling is the same one that cost an
    attended round-trip; this uid sits one character under it."""
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

RUNBOOK = REPO / "infra/runbooks/README.md"
# The anchors are explicit `<a name=...>` tags rather than heading slugs precisely so the
# `-- ALERT` / `-- KNOWN LIMITATION` marker cannot become part of them; match that literal form.
_RUNBOOK_LINK = re.compile(r"infra/runbooks/README\.md#([A-Za-z0-9._-]+)")


def test_every_runbook_link_in_an_alert_summary_resolves():
    text = RUNBOOK.read_text()
    cited, broken = [], []
    for rule in _rules():
        for anchor in _RUNBOOK_LINK.findall(" ".join((rule.get("annotations") or {}).values())):
            cited.append(anchor)
            if f'<a name="{anchor}"></a>' not in text:
                broken.append((rule["uid"], anchor))

    assert cited, "no rule cites a runbook anchor -- the regex is broken, not the summaries"
    assert not broken, f"alert summary points at a runbook anchor that does not exist: {broken}"


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


# --- a self-declared provisional threshold must be registered here, not only in a comment ---------
# `grafana-push.sh` upserts unconditionally, so a bar whose own comment says "it must not reach a
# push in this state" is held back by plan prose alone unless something in the repo names it. Each
# entry states what derives the value, so the deferral is readable without opening the plan; when the
# real value lands, the comment and the entry are deleted together and the staleness test below is
# what forces the second half.

# Empty by design. An entry here declares a threshold this file ships knowing it is provisional;
# the paired staleness test refuses an entry whose rule no longer carries the marker, so a bar that
# has been derived cannot leave its excuse behind. `zcrypto-capture-stream-silent` was the last
# occupant, derived on 2026-08-05 from the gauge's WHOLE LIFE -- ~7.2 d (primary) / ~7.5 d
# (secondary) of samples, not the 30 days the `[30d]` selector reads as, because the series only
# started reaching Cloud with the 2026-07-29 converges. Re-derivation on a genuinely full 30 d
# window is T0129; the bar itself is not provisional, its base is just younger than a month.
PROVISIONAL_THRESHOLDS: set[str] = set()

_PROVISIONAL = "PROVISIONAL"


def _uids_with_a_provisional_marker() -> set[str]:
    """Attribute each `PROVISIONAL` comment line to the rule it sits inside. Comments are stripped by
    the YAML parser, so this walks the raw text -- the marker only ever lives in a comment."""
    uid, found = None, set()
    for line in ALERTS.read_text().splitlines():
        if line.startswith("  - uid:"):
            uid = line.split("uid:", 1)[1].strip()
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
