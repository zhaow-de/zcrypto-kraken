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

	# OPS-5 (spec 00054 D4): the healed overlay, now PRODUCED on the ops node and pulled here.
	# Custody stays on the NAS (D3) -- only the computation moved. Own least-privilege key and its
	# own per-call SSH port, exactly like the panel/liquidations channels above. Hash-verified: the
	# overlay's minted hours carry .sha256 sidecars (verify_tree walks *.parquet only, so the
	# unsidecar'd ledger rides along unchecked). Best-effort like every other pull -- a failure is
	# logged and the loop continues; the overlay is recomputable on ops, so a missed cycle costs a
	# delay, not data. Skipped entirely when RECONCILED_SOURCE is unset.
	if [ -n "${RECONCILED_SOURCE:-}" ]; then
		if ! ARCHIVE_SSH_KEY="$RECONCILED_SSH_KEY" ARCHIVE_SSH_PORT="${RECONCILED_SSH_PORT:-22}" \
				zcrypto archive pull "$RECONCILED_SOURCE" "$RECONCILED_DEST"; then
			log ERROR "reconciled pull failed (source=$RECONCILED_SOURCE dest=$RECONCILED_DEST), continuing"
		fi
	fi

	# The reconcile + trade-backfill steps MOVED to the ops node (spec 00054 D2/OPS-5): this host
	# kept custody, Role A's pull/prune, and its Alloy (D3), and shed the computation -- the Atom tax
	# on every step sharing this clock had stretched the "hourly" loop to ~103 minutes. The healed
	# overlay now arrives via the RECONCILED_SOURCE pull above instead of being written here.

	# Backgrounded + waited-on so the TERM/INT trap interrupts the sleep promptly (docker stop
	# stays graceful) instead of blocking until the interval elapses.
	sleep "${ARCHIVE_PULL_INTERVAL:-3600}" &
	sleep_pid=$!
	wait "$sleep_pid"
	sleep_pid=""
done
