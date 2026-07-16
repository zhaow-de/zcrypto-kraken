#!/usr/bin/env sh
# In-container scheduler for the NAS archive-pull stack (spec 00048 Role A/B). Runs as the
# container's ENTRYPOINT (infra/nas/compose.yaml) — no systemd, no DSM Task Scheduler, per the
# NAS-runtime constraint. Every $ARCHIVE_PULL_INTERVAL seconds it pulls+verifies the capture
# segments (own key: CAPTURE_SSH_KEY), and — only when JOURNAL_SOURCE is set (Role B) — pulls the
# engine journal with its OWN least-privilege key (JOURNAL_SSH_KEY; --no-verify: no .sha256
# sidecars, Role B verifies it via replay) and then runs `zcrypto engine gate-export` to score the
# gate and emit it as a Prometheus textfile-collector metric. The loop itself is the availability
# guarantee: a single failed pull or export is logged but never exits the loop; the pull-lag
# figure `zcrypto archive pull` logs on each run is the dead-man signal that a stuck pull gets
# noticed.
set -eu
umask 0002

# Emit the SAME line shape `zcrypto`'s Python logging emits (`<asctime> <LEVEL> <logger> [<file>] -
# <msg>`, UTC, comma before the milliseconds -- that comma is CPython's
# `logging.Formatter.default_msec_format`, not a locale artifact). Alloy's ingest stage keys on
# exactly this shape to attach the `level` label (infra/nas/config.alloy), and the alerting selects on
# that label -- so a bare `echo` here is invisible to it. These lines are the ONLY record when the CLI
# is killed before it can log for itself (OOM, signal), which is precisely when someone needs to know.
#
# Milliseconds the portable way: GNU date's width modifier (`%3N`) is a GNU extension that uutils'
# date -- the Rust coreutils some distros now ship -- silently ignores, emitting all 9 nanosecond
# digits and producing a line Alloy's regex would NOT label. Both implementations agree on a
# zero-padded 9-digit `%N`, so take that and drop the last 6 with POSIX parameter expansion.
log() {
	_ts=$(date -u +'%Y-%m-%d %H:%M:%S,%N')
	printf '%s %s zcrypto.pull-entrypoint [pull-entrypoint.sh] - %s\n' "${_ts%??????}" "$1" "$2" >&2
}

sleep_pid=""

on_term() {
	log INFO "received TERM/INT, exiting loop"
	if [ -n "$sleep_pid" ]; then
		kill "$sleep_pid" 2>/dev/null || true
	fi
	exit 0
}
trap on_term TERM INT

while true; do
	# capture pull uses the capture channel's own least-privilege key
	capture_ok=1
	if ! ARCHIVE_SSH_KEY="$CAPTURE_SSH_KEY" zcrypto archive pull "$CAPTURE_SOURCE" "$CAPTURE_DEST"; then
		log ERROR "capture pull failed (source=$CAPTURE_SOURCE dest=$CAPTURE_DEST), continuing"
		capture_ok=0
	fi

	# Role C (spec 00050): the redundant secondary's mirror, over its OWN key into its OWN root.
	# Best-effort like every other step -- a failed secondary pull must never stop the loop, because
	# the primary mirror is still canonical and still arriving. Skipped entirely when CAPTURE_RED_SOURCE
	# is unset, so a NAS without the red channel runs this script unchanged.
	secondary_ok=1
	if [ -n "${CAPTURE_RED_SOURCE:-}" ]; then
		if ! ARCHIVE_SSH_KEY="$CAPTURE_RED_SSH_KEY" zcrypto archive pull "$CAPTURE_RED_SOURCE" "$CAPTURE_RED_DEST"; then
			log ERROR "secondary capture pull failed (source=$CAPTURE_RED_SOURCE dest=$CAPTURE_RED_DEST), continuing"
			secondary_ok=0
		fi
	fi
	# The journal pull only runs once JOURNAL_SOURCE is set (Role B). It uses its OWN
	# least-privilege key (JOURNAL_SSH_KEY) -- the capture and journal channels use distinct
	# keys, so a single ARCHIVE_SSH_KEY cannot serve both; `zcrypto archive pull` reads whichever
	# value ARCHIVE_SSH_KEY holds at call time (cli/archive/command.py's `_run_rsync`). In the
	# Increment-1 capture-only deploy JOURNAL_SOURCE is unset, so this whole block is skipped.
	if [ -n "${JOURNAL_SOURCE:-}" ]; then
		if ! ARCHIVE_SSH_KEY="$JOURNAL_SSH_KEY" zcrypto archive pull --no-verify "$JOURNAL_SOURCE" "$JOURNAL_DEST"; then
			log ERROR "journal pull failed (source=$JOURNAL_SOURCE dest=$JOURNAL_DEST), continuing"
		fi
		# Role B: score the gate on the freshly-pulled journal and emit it as a Prometheus
		# textfile-collector metric (spec 00042/Task 1's `zcrypto engine gate-export`);
		# best-effort, same as the pulls above -- a failure here is logged but never exits the
		# loop.
		if ! zcrypto engine gate-export --journal-dir "$JOURNAL_DEST" --textfile "$GATE_TEXTFILE" \
				${GATE_HEALTHCHECK_URL:+--healthcheck-url "$GATE_HEALTHCHECK_URL"}; then
			log ERROR "gate-export failed (dest=$JOURNAL_DEST), continuing"
		fi
	fi

	# OPS-2 (spec 00051): the ops node's liquidations tree -- Binance force-orders are not
	# backfillable (T0023-class), so the NAS mirrors them under no-sole-custody (D10) with the same
	# hash-verified pull as the capture channels (the recorder's SegmentWriter writes .sha256
	# manifests -- never --no-verify here). Own least-privilege key, and its own per-call SSH port:
	# the ops node is a home-LAN box on port 22, not the VPS's 10022, and `zcrypto archive pull`
	# reads ARCHIVE_SSH_PORT at call time exactly like ARCHIVE_SSH_KEY. Skipped entirely when
	# LIQUIDATIONS_SOURCE is unset, so a NAS without the ops channel runs this script unchanged.
	# Best-effort like every other pull -- and deliberately NOT an input to the reconcile gate
	# below, which reasons only about the two capture mirrors.
	if [ -n "${LIQUIDATIONS_SOURCE:-}" ]; then
		if ! ARCHIVE_SSH_KEY="$LIQUIDATIONS_SSH_KEY" ARCHIVE_SSH_PORT="${LIQUIDATIONS_SSH_PORT:-22}" \
				zcrypto archive pull "$LIQUIDATIONS_SOURCE" "$LIQUIDATIONS_DEST"; then
			log ERROR "liquidations pull failed (source=$LIQUIDATIONS_SOURCE dest=$LIQUIDATIONS_DEST), continuing"
		fi
	fi

	# OPS-4 (spec 00052 D7): the ops node's L2 primitive panel tree -- convenience-durability only
	# (the panel is recomputable from raw, so this copy is not custody-critical, unlike the
	# liquidations tree above). Own least-privilege key, and its own per-call SSH port -- the ops
	# node is a home-LAN box on port 22, not the VPS's 10022, same as the liquidations pull. Skipped
	# entirely when PANEL_SOURCE is unset, so a NAS without the panel channel runs this script
	# unchanged. Best-effort like every other pull -- and deliberately NOT an input to the reconcile
	# gate below, which reasons only about the two capture mirrors.
	if [ -n "${PANEL_SOURCE:-}" ]; then
		if ! ARCHIVE_SSH_KEY="$PANEL_SSH_KEY" ARCHIVE_SSH_PORT="${PANEL_SSH_PORT:-22}" \
				zcrypto archive pull "$PANEL_SOURCE" "$PANEL_DEST"; then
			log ERROR "panel pull failed (source=$PANEL_SOURCE dest=$PANEL_DEST), continuing"
		fi
	fi

	# Role C: reconcile the two raw mirrors into the healed overlay. DETECT-ONLY by default -- it
	# ledgers every `would_mint` and writes no parquet until T0039's soak has pinned
	# --min-gap-seconds from real cross-host data (see RECONCILE_MIN_GAP_SECONDS in compose.yaml).
	#
	# SKIPPED on any cycle whose PRIMARY **or SECONDARY** pull failed. The reconciler reasons from the
	# two LOCAL mirrors, and it cannot tell "this hour does not exist" from "this hour did not arrive".
	# A failed pull -- on either channel -- makes local absence uninformative:
	#
	#   * primary pull broken: hours look primary-dark but are not. Reconciling would mint "healed"
	#     full-secondary hours for data that was never lost, quietly substituting one host's stream for
	#     the other's in an archive that cannot be backfilled, and inflating healed_gap_seconds so the
	#     very metric meant to flag a degrading primary reports success instead.
	#   * secondary pull broken: the witness looks dark too. A real primary outage -- the exact event
	#     Role C exists to heal -- would then be classified `both_streams_silent` / `total_loss`:
	#     PERMANENT loss, paged, and booked into a monotone counter that can never be walked back, for
	#     an hour the secondary actually captured and could have healed. The correlated-loss detectors
	#     run unconditionally (they are not gated by --mint), so this bites even in detect-only mode,
	#     and the ledger's dedupe means the false verdict is never revisited.
	#
	# Skipping keeps the ledger honest for free: the hours simply reconcile on the next healthy cycle,
	# against complete mirrors. An unhealed hour costs nothing; a wrong verdict is forever.
	if [ -n "${CAPTURE_RED_SOURCE:-}" ]; then
		if [ "$capture_ok" -eq 0 ] || [ "$secondary_ok" -eq 0 ]; then
			log WARNING "reconcile skipped: a capture pull failed this cycle (primary_ok=$capture_ok secondary_ok=$secondary_ok), so a mirror's absence cannot be told apart from a pull that has not landed yet"
		elif ! zcrypto archive reconcile "$CAPTURE_DEST" "$CAPTURE_RED_DEST" "$RECONCILED_DEST" \
				--window-hours "${RECONCILE_WINDOW_HOURS:-48}" \
				--min-gap-seconds "${RECONCILE_MIN_GAP_SECONDS:-30}" \
				--textfile "$RECONCILE_TEXTFILE"; then
			log ERROR "reconcile failed (primary=$CAPTURE_DEST secondary=$CAPTURE_RED_DEST overlay=$RECONCILED_DEST), continuing"
		fi
	fi

	# Trade backfill (spec 00053; T0053): heal the canonical trade stream to a contiguous,
	# duplicate-free trade_id sequence by fetching gaps from Kraken's public REST /Trades and
	# minting healed hours into the reconciled overlay ($RECONCILED_DEST, same destination the
	# reconciler above writes to). DAILY, not per-cycle -- the detector's scan is O(archive), a
	# per-cycle cost T0028 already flags on this host and which this must not compound; there is
	# also no urgency cliff (Kraken serves ~18 months of /Trades). Gated on a stamp file holding
	# the last UTC day it ran; the stamp is written UNCONDITIONALLY -- success or failure. A
	# PERMANENT error (an unmapped pair, a structural residual) exits non-zero on every attempt, and
	# writing the stamp only on success once meant that ran the full O(archive) scan plus hundreds
	# of REST calls every hour, forever -- exactly the per-cycle cost this step exists to avoid.
	# Stamping unconditionally makes the daily cost bound absolute; the failure is then carried by
	# the metric below and its alert (infra/grafana/alerts.yaml), not by a retry. The metric is the
	# signal, not the retry -- a transient now waits up to 24h, which is fine given the no-urgency-
	# cliff reasoning above.
	# Best-effort like every other step above: a non-zero exit (1 = recorded errors, 2 = primary
	# root missing) is recorded in the metric below, never fatal to the loop.
	backfill_stamp=/archive/.trade-backfill-last-utc-day
	backfill_today="$(date -u +%Y-%m-%d)"
	if [ "$(cat "$backfill_stamp" 2>/dev/null || echo none)" != "$backfill_today" ]; then
		echo "$backfill_today" > "$backfill_stamp"
		if zcrypto archive backfill-trades "$CAPTURE_DEST" "$RECONCILED_DEST"; then
			backfill_rc=0
		else
			backfill_rc=$?
			log ERROR "trade backfill failed (primary=$CAPTURE_DEST reconciled=$RECONCILED_DEST, exit=$backfill_rc), continuing"
		fi
		backfill_textfile="${TRADE_BACKFILL_TEXTFILE:-/textfile/trade-backfill.prom}"
		printf 'zcrypto_trade_backfill_exit_code %d\n' "$backfill_rc" > "$backfill_textfile.tmp"
		printf 'zcrypto_trade_backfill_last_run_timestamp %d\n' "$(date -u +%s)" >> "$backfill_textfile.tmp"
		if [ "$backfill_rc" -eq 0 ]; then
			printf 'zcrypto_trade_backfill_last_success_timestamp %d\n' "$(date -u +%s)" >> "$backfill_textfile.tmp"
		fi
		mv "$backfill_textfile.tmp" "$backfill_textfile"
	fi

	# Backgrounded + waited-on so the TERM/INT trap interrupts the sleep promptly (docker stop
	# stays graceful) instead of blocking until the interval elapses.
	sleep "${ARCHIVE_PULL_INTERVAL:-3600}" &
	sleep_pid=$!
	wait "$sleep_pid"
	sleep_pid=""
done
