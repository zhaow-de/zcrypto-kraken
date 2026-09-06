#!/usr/bin/env sh
# In-container scheduler for the NAS archive-pull stack (spec 00048 Role A/B). It is the container's
# ENTRYPOINT rather than a systemd unit or a DSM task, per the NAS-runtime constraint. The loop
# itself is the availability guarantee: a single failed pull or export is logged and never exits it,
# and the pull-lag figure `zcrypto archive pull` logs each run is the dead-man signal that a stuck
# pull gets noticed.
set -eu
umask 0002

# Emit the SAME line shape `zcrypto`'s Python logging emits, down to the comma before the
# milliseconds -- that comma is CPython's `logging.Formatter.default_msec_format`, not a locale
# artifact. Alloy's ingest stage keys on exactly this shape to attach the `level` label and the
# alerting selects on that label, so a bare `echo` here is invisible to it. These lines are the ONLY
# record when the CLI is killed before it can log for itself, which is precisely when someone needs
# them.
#
# Milliseconds the portable way: GNU date's `%3N` width modifier is an extension that uutils' date
# silently ignores, emitting all nine nanosecond digits and producing a line Alloy's regex would NOT
# label. Both implementations agree on a zero-padded nine-digit `%N`, so take that and drop the last
# six with POSIX parameter expansion.
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

# Spec 00102 D3: the 1/24 slice index is a COUNTER, never the clock. The loop's real period is
# interval+work, so a slice keyed on now.hour starves a fixed subset of slices forever whenever
# that drifted period divides 24h -- segments silently never re-verified.
cycle=0
# Hoisted and read once: five call sites must not carry separate literals. The `:-full` fallback
# stays -- this entrypoint is bind-mounted and can outrun an older compose file.
hash_scope="${ARCHIVE_PULL_HASH_SCOPE:-full}"

while true; do
	cycle=$((cycle + 1))
	slice=$((cycle % 24))

	# capture pull uses the capture channel's own least-privilege key
	# Spec 00102: the verify cost is published per channel (one .prom each -- five pulls share
	# /textfile). ARCHIVE_PULL_HASH_SCOPE picks full (re-hash every segment) or incremental
	# (rsync's transfers plus this loop's 1/24 slice); compose.yaml documents flipping it.
	capture_ok=1
	if ! ARCHIVE_SSH_KEY="$CAPTURE_SSH_KEY" zcrypto archive pull \
			--hash-scope "$hash_scope" --slice "$slice" \
			--textfile /textfile/archive-pull-capture.prom --channel capture \
			"$CAPTURE_SOURCE" "$CAPTURE_DEST"; then
		log ERROR "capture pull failed (source=$CAPTURE_SOURCE dest=$CAPTURE_DEST), continuing"
		capture_ok=0
	fi

	# Role C (spec 00050): the redundant secondary's mirror, over its OWN key into its OWN root.
	# Best-effort like every other step -- a failed secondary pull must never stop the loop, because
	# the primary mirror is still canonical and still arriving. Skipped entirely when CAPTURE_RED_SOURCE
	# is unset, so a NAS without the red channel runs this script unchanged.
	secondary_ok=1
	if [ -n "${CAPTURE_RED_SOURCE:-}" ]; then
		if ! ARCHIVE_SSH_KEY="$CAPTURE_RED_SSH_KEY" zcrypto archive pull \
				--hash-scope "$hash_scope" --slice "$slice" \
				--textfile /textfile/archive-pull-capture_red.prom --channel capture_red \
				"$CAPTURE_RED_SOURCE" "$CAPTURE_RED_DEST"; then
			log ERROR "secondary capture pull failed (source=$CAPTURE_RED_SOURCE dest=$CAPTURE_RED_DEST), continuing"
			secondary_ok=0
		fi
	fi

	# T0058: the reconcile gate's ground truth. The ops-node writer reads this file through the read-
	# only NFS mount and skips its whole cycle unless both flags are 1 and the stamp is younger than
	# 4h and not future-stamped beyond a small skew -- fail closed, so missing, unreadable, stale or
	# skewed all mean skip.
	#
	# Writing it HERE is what makes it the actual pull exit codes rather than "the NAS-to-ops rsync
	# succeeded": that rsync succeeds even when this host's own VPS pulls are broken, so a frozen
	# mirror would ledger permanent false verdicts. tmp+mv so the ops reader never sees a partial
	# file. If-guarded like every other step: unguarded, a failed redirection or mv under `set -eu`
	# kills the container mid-cycle, every later channel is skipped, and `restart: unless-stopped` re-
	# runs the capture pulls back-to-back with no interval pacing. A failed write instead lets the
	# existing status age, which is the gate's designed fail-closed degraded mode.
	if ! {
		printf 'capture_ok=%s\n' "$capture_ok"
		printf 'secondary_ok=%s\n' "$secondary_ok"
		printf 'ts_epoch=%s\n' "$(date -u +%s)"
	} > /archive/.pull-status.tmp 2>/dev/null \
			|| ! mv /archive/.pull-status.tmp /archive/.pull-status 2>/dev/null; then
		log ERROR "pull-status write failed (dest=/archive/.pull-status), continuing"
	fi

	# The journal pull runs only once JOURNAL_SOURCE is set (Role B), with its OWN least-privilege
	# key: the capture and journal channels use distinct keys, so one ARCHIVE_SSH_KEY cannot serve
	# both, and `zcrypto archive pull` reads whichever value it holds at call time.
	if [ -n "${JOURNAL_SOURCE:-}" ]; then
		if ! ARCHIVE_SSH_KEY="$JOURNAL_SSH_KEY" zcrypto archive pull --no-verify "$JOURNAL_SOURCE" "$JOURNAL_DEST"; then
			log ERROR "journal pull failed (source=$JOURNAL_SOURCE dest=$JOURNAL_DEST), continuing"
		fi
		# Role B: score the gate on the freshly-pulled journal and emit it as a Prometheus textfile
		# metric, best-effort like the pulls above.
		#
		# `--cache` bounds the per-run cost to the journal's NEW cycles instead of replaying all of them
		# (spec 00060). It is safe to enable ONLY because spec 00062 added rotating re-verification, so
		# each run still force-replays a slice and every parquet is re-hashed periodically -- without
		# that, a cache hit would skip the only re-read of the journal's bytes, since this pull uses
		# --no-verify and delegates verification to the replay. The path is deliberately INSIDE the
		# container and never under /archive: that share is reachable by both hosts, which run different
		# polars runtimes that `replay_fingerprint` does not digest, so a shared cache file would be
		# mutually poisonable (00062 D9). The cost is one cold rebuild after each container recreate.
		#
		# `--lag-fail-seconds` is passed EXPLICITLY rather than left to the CLI default, so the value
		# reaches production with a converge instead of an image rebuild and the deployed threshold is
		# visible here. It gates the dead-man ping, so it must equal the evaluator in
		# infra/grafana/alerts.yaml's rule, where it is derived -- change them together.
		if ! zcrypto engine gate-export --journal-dir "$JOURNAL_DEST" --textfile "$GATE_TEXTFILE" \
				--cache /tmp/gate-cache.json --lag-fail-seconds 21600 \
				${GATE_HEALTHCHECK_URL:+--healthcheck-url "$GATE_HEALTHCHECK_URL"}; then
			log ERROR "gate-export failed (dest=$JOURNAL_DEST), continuing"
		fi
	fi

	# OPS-2 (spec 00051): the ops node's liquidations tree. Binance force-orders are not backfillable,
	# so the NAS mirrors them under no-sole-custody (D10) with the same hash-verified pull as the
	# capture channels -- never --no-verify here. Own least-privilege key and its own per-call SSH
	# port, since the ops node is a home-LAN box rather than a VPS. Skipped entirely when
	# LIQUIDATIONS_SOURCE is unset, and deliberately NOT an input to the reconcile gate below, which
	# reasons only about the two capture mirrors.
	if [ -n "${LIQUIDATIONS_SOURCE:-}" ]; then
		if ! ARCHIVE_SSH_KEY="$LIQUIDATIONS_SSH_KEY" ARCHIVE_SSH_PORT="${LIQUIDATIONS_SSH_PORT:-22}" \
				zcrypto archive pull \
				--hash-scope "$hash_scope" --slice "$slice" \
				--textfile /textfile/archive-pull-liquidations.prom --channel liquidations \
				"$LIQUIDATIONS_SOURCE" "$LIQUIDATIONS_DEST"; then
			log ERROR "liquidations pull failed (source=$LIQUIDATIONS_SOURCE dest=$LIQUIDATIONS_DEST), continuing"
		fi
	fi

	# OPS-4 (spec 00052 D7): the ops node's L2 primitive panel tree, convenience durability only --
	# the panel is recomputable from raw, so unlike the liquidations tree above this copy is not
	# custody-critical. Own least-privilege key and its own SSH port, skipped when PANEL_SOURCE is
	# unset, and deliberately NOT a reconcile-gate input.
	if [ -n "${PANEL_SOURCE:-}" ]; then
		if ! ARCHIVE_SSH_KEY="$PANEL_SSH_KEY" ARCHIVE_SSH_PORT="${PANEL_SSH_PORT:-22}" \
				zcrypto archive pull \
				--hash-scope "$hash_scope" --slice "$slice" \
				--textfile /textfile/archive-pull-panel.prom --channel panel \
				"$PANEL_SOURCE" "$PANEL_DEST"; then
			log ERROR "panel pull failed (source=$PANEL_SOURCE dest=$PANEL_DEST), continuing"
		fi
	fi

	# OPS-5 (spec 00054 D4): the healed overlay, PRODUCED on the ops node and pulled here -- custody
	# stays on the NAS (D3), only the computation moved. Hash-verified, though `verify_tree` walks
	# parquet only, so the unsidecar'd ledger rides along unchecked. Best-effort: the overlay is
	# recomputable on ops, so a missed cycle costs a delay rather than data.
	if [ -n "${RECONCILED_SOURCE:-}" ]; then
		if ! ARCHIVE_SSH_KEY="$RECONCILED_SSH_KEY" ARCHIVE_SSH_PORT="${RECONCILED_SSH_PORT:-22}" \
				zcrypto archive pull \
				--hash-scope "$hash_scope" --slice "$slice" \
				--textfile /textfile/archive-pull-reconciled.prom --channel reconciled \
				"$RECONCILED_SOURCE" "$RECONCILED_DEST"; then
			log ERROR "reconciled pull failed (source=$RECONCILED_SOURCE dest=$RECONCILED_DEST), continuing"
		fi
	else
		# Optional-by-design, but never silently: an unset channel on a NAS that SHOULD carry the
		# overlay means custody quietly stops re-acquiring it (review finding, 2026-07-17).
		log WARNING "reconciled channel unwired (RECONCILED_SOURCE unset) — custody is not re-acquiring the overlay"
	fi

	# OPS-6 (spec 00056 D2/D4): the hot-cluster working set the ops node authors, pulled into the hot/
	# hub. A RAW rsync, NOT `zcrypto archive pull`: hot sets are append-only-at-file and need
	# --ignore-existing, which the wrapper never passes, and they carry manifest.json rather than the
	# sidecars verify_tree expects -- so this rebuilds the same pinned SSH options the wrapper uses.
	# `--archive --ignore-existing`, never --delete: a content-changed file is simply untransmittable,
	# so the append-only contract is enforced by the transport itself.
	#
	# Skipped SILENTLY when HOT_SOURCE is unset, deliberately unlike the reconciled channel's warning:
	# hot is optional secondary durability for ops-authored artifacts and is legitimately unset until
	# ops authors any, whereas an unwired reconciled overlay is anomalous because its writer lives on
	# ops.
	#
	# `--chmod` because the Synology share is plain POSIX with no ACL inheritance and this container
	# is non-root, so without it pulled dirs keep the source's non-group-writable mode and the
	# workstation push could not append into a shared subtree. It is D2775 here and D0775 on every
	# other channel -- the one place the fleet's channels diverge -- because the role sets hot/ setgid
	# so both writers' children inherit group zcrypto, and D0775 forces every directory rsync writes
	# to exactly 0775, STRIPPING that bit on each pull. Siblings keep D0775 correctly: single-writer,
	# egid already zcrypto.
	if [ -n "${HOT_SOURCE:-}" ]; then
		if ! rsync --archive --ignore-existing --chmod=D2775,F0664 \
				-e "ssh -i $HOT_SSH_KEY -p ${HOT_SSH_PORT:-22} -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes -o CheckHostIP=no -o UserKnownHostsFile=$ARCHIVE_SSH_KNOWN_HOSTS" \
				"$HOT_SOURCE" "$HOT_DEST"; then
			log ERROR "hot pull failed (source=$HOT_SOURCE dest=$HOT_DEST), continuing"
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
