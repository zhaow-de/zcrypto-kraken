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
	# capture pull uses the capture channel's own least-privilege key
	if ! ARCHIVE_SSH_KEY="$CAPTURE_SSH_KEY" zcrypto archive pull "$CAPTURE_SOURCE" "$CAPTURE_DEST"; then
		echo "pull-entrypoint: capture pull failed (source=$CAPTURE_SOURCE dest=$CAPTURE_DEST), continuing" >&2
	fi
	# The journal pull only runs once JOURNAL_SOURCE is set (Role B). It uses its OWN
	# least-privilege key (JOURNAL_SSH_KEY) -- the capture and journal channels use distinct
	# keys, so a single ARCHIVE_SSH_KEY cannot serve both; `zcrypto archive pull` reads whichever
	# value ARCHIVE_SSH_KEY holds at call time (cli/archive/command.py's `_run_rsync`). In the
	# Increment-1 capture-only deploy JOURNAL_SOURCE is unset, so this whole block is skipped.
	if [ -n "${JOURNAL_SOURCE:-}" ]; then
		if ! ARCHIVE_SSH_KEY="$JOURNAL_SSH_KEY" zcrypto archive pull --no-verify "$JOURNAL_SOURCE" "$JOURNAL_DEST"; then
			echo "pull-entrypoint: journal pull failed (source=$JOURNAL_SOURCE dest=$JOURNAL_DEST), continuing" >&2
		fi
		# Role B: score the gate on the freshly-pulled journal and emit it as a Prometheus
		# textfile-collector metric (spec 00042/Task 1's `zcrypto engine gate-export`);
		# best-effort, same as the pulls above -- a failure here is logged but never exits the
		# loop.
		if ! zcrypto engine gate-export --journal-dir "$JOURNAL_DEST" --textfile "$GATE_TEXTFILE" \
				${GATE_HEALTHCHECK_URL:+--healthcheck-url "$GATE_HEALTHCHECK_URL"}; then
			echo "pull-entrypoint: gate-export failed (dest=$JOURNAL_DEST), continuing" >&2
		fi
	fi

	# Backgrounded + waited-on so the TERM/INT trap interrupts the sleep promptly (docker stop
	# stays graceful) instead of blocking until the interval elapses.
	sleep "${ARCHIVE_PULL_INTERVAL:-3600}" &
	sleep_pid=$!
	wait "$sleep_pid"
	sleep_pid=""
done
