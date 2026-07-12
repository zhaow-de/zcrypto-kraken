#!/usr/bin/env sh
# In-container scheduler for the NAS archive-pull stack (spec 00048 Role A). Runs as the
# container's ENTRYPOINT (infra/nas/compose.yaml) — no systemd, no DSM Task Scheduler, per the
# NAS-runtime constraint. Every $ARCHIVE_PULL_INTERVAL seconds it pulls+verifies the capture
# segments, then the engine journal. The loop itself is the availability guarantee: a single
# failed pull is logged but never exits the loop; the pull-lag figure `zcrypto archive pull`
# logs on each run is the dead-man signal that a stuck pull gets noticed.
set -eu
umask 0002

sleep_pid=""

on_term() {
	echo "pull-entrypoint: received TERM/INT, exiting loop" >&2
	if [ -n "$sleep_pid" ]; then
		kill "$sleep_pid" 2>/dev/null || true
	fi
	exit 0
}
trap on_term TERM INT

while true; do
	if ! zcrypto archive pull "$CAPTURE_SOURCE" "$CAPTURE_DEST"; then
		echo "pull-entrypoint: capture pull failed (source=$CAPTURE_SOURCE dest=$CAPTURE_DEST), continuing" >&2
	fi
	if ! zcrypto archive pull "$JOURNAL_SOURCE" "$JOURNAL_DEST"; then
		echo "pull-entrypoint: journal pull failed (source=$JOURNAL_SOURCE dest=$JOURNAL_DEST), continuing" >&2
	fi

	# Backgrounded + waited-on so the TERM/INT trap interrupts the sleep promptly (docker stop
	# stays graceful) instead of blocking until the interval elapses.
	sleep "${ARCHIVE_PULL_INTERVAL:-3600}" &
	sleep_pid=$!
	wait "$sleep_pid"
	sleep_pid=""
done
