#!/usr/bin/env bash
# Normalizes the zcrypto data archive on the NAS to plain POSIX perms (dirs 0775, files 0664, group
# `zcrypto`, no ACL): DSM DISPLAYS an ACL'd file as the mask, 666 or 777+, where `chmod` yields the
# literal mode. Idempotent:
#   ssh nas 'sudo bash -s' < infra/nas/normalize-archive-perms.sh   [/volume1/ZhaoCrypto]
set -euo pipefail

TARGET="${1:-/volume1/ZhaoCrypto}"
GROUP="zcrypto"

if [ "$(id -u)" != "0" ]; then
	echo "error: must run as root (sudo) — chmod/chgrp on ${GROUP}-owned files needs it" >&2
	exit 1
fi
if [ ! -d "$TARGET" ]; then
	echo "error: target is not a directory: $TARGET" >&2
	exit 1
fi

# Guard against a mistyped / too-shallow target: this runs as root and recurses, so a
# stray `/` or `/volume1` would rewrite the whole volume. Require >= 2 path components
# (e.g. /volume1/ZhaoCrypto), counting slashes in the resolved path.
RESOLVED="$(readlink -f "$TARGET")"
if [ "$(printf '%s' "$RESOLVED" | tr -cd / | wc -c)" -lt 2 ]; then
	echo "error: refusing a too-shallow target (need >= /volumeX/share): $RESOLVED" >&2
	exit 1
fi

# Stripping the inheritable ACL is also what lands new files at 0664/0775, given the 0002 umask on
# both writers. The `@eaDir` prune skips Synology metadata.
# group -> zcrypto  (`-h`: a symlink's group is set on the link itself, never its target)
find "$TARGET" -xdev -name '@eaDir' -prune -o -print0 | xargs -0r chgrp -h "$GROUP" --
# directories -> 0775  (chmod also strips any Synology ACL on the entry)
find "$TARGET" -xdev -name '@eaDir' -prune -o -type d -print0 | xargs -0r chmod 0775 --
# files -> 0664
find "$TARGET" -xdev -name '@eaDir' -prune -o -type f -print0 | xargs -0r chmod 0664 --

echo "normalized $TARGET: dirs 0775, files 0664, group $GROUP, ACLs stripped"
