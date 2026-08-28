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

# Spec 00102 D3: the pull loop's own rotation index for the incremental-verify 1/24 slice -- a
# COUNTER, never the clock. `sleep $ARCHIVE_PULL_INTERVAL` makes the loop's real period
# interval+work, which drifts past the nominal interval, so a slice keyed on now.hour skips clock
# hours and can starve a fixed subset of slices forever whenever the drifted period divides 24h.
cycle=0

while true; do
	cycle=$((cycle + 1))

	# capture pull uses the capture channel's own least-privilege key
	# Spec 00102: the verify cost is published per channel (one .prom each -- five pulls share
	# /textfile), and ARCHIVE_PULL_HASH_SCOPE decides whether every segment is re-hashed (full) or
	# only rsync's transfers plus a 1/24 slice keyed on this loop's cycle counter (incremental). The value is rendered into
	# .env from nas_archive_pull_hash_scope, so flipping it is a config-only converge on the running
	# image -- and the rollback is the same flip.
	capture_ok=1
	if ! ARCHIVE_SSH_KEY="$CAPTURE_SSH_KEY" zcrypto archive pull \
			--hash-scope "${ARCHIVE_PULL_HASH_SCOPE:-full}" --slice $((cycle % 24)) \
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
				--hash-scope "${ARCHIVE_PULL_HASH_SCOPE:-full}" --slice $((cycle % 24)) \
				--textfile /textfile/archive-pull-capture_red.prom --channel capture_red \
				"$CAPTURE_RED_SOURCE" "$CAPTURE_RED_DEST"; then
			log ERROR "secondary capture pull failed (source=$CAPTURE_RED_SOURCE dest=$CAPTURE_RED_DEST), continuing"
			secondary_ok=0
		fi
	fi

	# T0058: the reconcile gate's ground truth. The ops-node writer reads this file THROUGH the
	# read-only NFS mount and skips its whole writer cycle (reconcile AND backfill) unless both
	# flags are 1 AND ts_epoch is younger than 4h (and not future-stamped beyond a small skew
	# tolerance) — fail closed: missing/unreadable/stale/skewed = skip.
	# Writing it here restores the original gate semantics (the actual pull exit codes) that the
	# OPS-5 cutover had silently reduced to "the NAS-to-ops rsync succeeded" (final-review
	# finding, 2026-07-17) — that rsync succeeds even when this host's own VPS pulls are broken,
	# so a frozen mirror would have ledgered permanent false verdicts. This also finally gives
	# capture_ok/secondary_ok a READER again — an earlier review noted they had become
	# write-only. tmp+mv so the ops reader never sees a partial file (the same atomic pattern the
	# trade-backfill textfile used before OPS-5 moved that step to the ops node). If-guarded like
	# every other step in this loop (review 2026-07-17): unguarded, a failed redirection or mv
	# under `set -eu` (ENOSPC/EIO/read-only volume) killed the whole container mid-cycle — every
	# channel after this block skipped, and `restart: unless-stopped` re-ran the capture pulls
	# back-to-back with no interval pacing. A failed write just lets the existing status age,
	# which is exactly the ops gate's designed fail-closed degraded mode.
	if ! {
		printf 'capture_ok=%s\n' "$capture_ok"
		printf 'secondary_ok=%s\n' "$secondary_ok"
		printf 'ts_epoch=%s\n' "$(date -u +%s)"
	} > /archive/.pull-status.tmp 2>/dev/null \
			|| ! mv /archive/.pull-status.tmp /archive/.pull-status 2>/dev/null; then
		log ERROR "pull-status write failed (dest=/archive/.pull-status), continuing"
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
		# --cache bounds the per-run cost to the journal's NEW cycles instead of replaying all of
		# them (spec 00060): ~10 min -> ~1 min on this Atom, and FLAT as the journal grows rather
		# than climbing. It is safe to enable only because spec 00062 added rotating
		# re-verification -- each run still force-replays a ~1/24 slice, so every parquet is
		# re-hashed about daily. Without that, a cache hit would skip the ONLY re-read of the
		# journal's bytes (this pull uses --no-verify and delegates verification to the replay).
		# The path is deliberately INSIDE the container, never under /archive: that share is
		# reachable by both hosts, which run different polars runtimes that replay_fingerprint
		# does not digest, so a shared cache file would be mutually poisonable (00062 D9). Cost of
		# ephemerality: one cold rebuild after each container recreate.
		# --lag-fail-seconds is passed EXPLICITLY, not left to the CLI default: this script is
		# bind-mounted and ansible-deployed, so the value reaches production with a converge
		# instead of an image rebuild, and the deployed threshold is visible here rather than
		# hidden in a default. 21600 (6h) is derived in infra/grafana/alerts.yaml's rule comment
		# and archived T0069; it gates the hc.io dead-man ping, so it must equal that rule's
		# evaluator -- change them together.
		if ! zcrypto engine gate-export --journal-dir "$JOURNAL_DEST" --textfile "$GATE_TEXTFILE" \
				--cache /tmp/gate-cache.json --lag-fail-seconds 21600 \
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
				zcrypto archive pull \
				--hash-scope "${ARCHIVE_PULL_HASH_SCOPE:-full}" --slice $((cycle % 24)) \
				--textfile /textfile/archive-pull-liquidations.prom --channel liquidations \
				"$LIQUIDATIONS_SOURCE" "$LIQUIDATIONS_DEST"; then
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
				zcrypto archive pull \
				--hash-scope "${ARCHIVE_PULL_HASH_SCOPE:-full}" --slice $((cycle % 24)) \
				--textfile /textfile/archive-pull-panel.prom --channel panel \
				"$PANEL_SOURCE" "$PANEL_DEST"; then
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
				zcrypto archive pull \
				--hash-scope "${ARCHIVE_PULL_HASH_SCOPE:-full}" --slice $((cycle % 24)) \
				--textfile /textfile/archive-pull-reconciled.prom --channel reconciled \
				"$RECONCILED_SOURCE" "$RECONCILED_DEST"; then
			log ERROR "reconciled pull failed (source=$RECONCILED_SOURCE dest=$RECONCILED_DEST), continuing"
		fi
	else
		# Optional-by-design, but never silently: an unset channel on a NAS that SHOULD carry the
		# overlay means custody quietly stops re-acquiring it (review finding, 2026-07-17).
		log WARNING "reconciled channel unwired (RECONCILED_SOURCE unset) — custody is not re-acquiring the overlay"
	fi

	# OPS-6 (spec 00056 D2/D4): the hot-cluster working set the ops node authors, pulled into the
	# hot/ hub. A RAW rsync, NOT `zcrypto archive pull`: hot sets are append-only-at-file (D1c needs
	# --ignore-existing, which the wrapper never passes) and carry manifest.json, not the .sha256
	# sidecars verify_tree expects -- so this rebuilds the same pinned SSH options the wrapper uses.
	# --archive --ignore-existing, never --delete: a content-changed file is simply untransmittable,
	# so the append-only contract is enforced by the transport itself. Own least-privilege key +
	# home-LAN port 22, like panel/reconciled. Best-effort; NOT a reconcile-gate input. Skipped
	# entirely (silently, like PANEL -- deliberately NOT the reconciled channel's else-WARNING) when
	# HOT_SOURCE is unset: hot is optional secondary durability for ops-AUTHORED artifacts and is
	# legitimately unset until ops authors any, whereas an unwired reconciled overlay is anomalous
	# (its writer moved to ops in OPS-5, so it is expected wired). A NAS not given the channel runs on.
	# --chmod: the Synology share is plain POSIX with no ACL inheritance and this container is
	# non-root (uid 1000, cannot chown), so without it pulled dirs keep the ops source's
	# non-group-writable 0755 and the workstation push (zcrypto-deploy, group zcrypto) could not
	# append into a shared subtree. hot/ is the fleet's only two-writer dir, so keeping the pulled
	# tree group-writable is load-bearing.
	#
	# D2775, NOT the D0775 every other channel uses -- the ONE place the fleet's channels diverge.
	# The nas role sets /volume1/ZhaoCrypto/hot to 02775 precisely so both writers' children inherit
	# group zcrypto (roles/nas/tasks/main.yml), but D0775 forces every directory rsync writes to
	# exactly 0775 and STRIPS that setgid bit on each pull. The role restored it on converge, the
	# next pull removed it again, and the drift was invisible until an --check --diff happened to
	# run between the two. Siblings keep D0775 correctly: they are single-writer and their writer's
	# egid is already zcrypto, so they need no setgid and the role declares them plain 0775.
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
