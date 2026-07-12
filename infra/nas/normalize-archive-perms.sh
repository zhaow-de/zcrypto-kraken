#!/usr/bin/env bash
#
# Normalize the zcrypto data archive on the Synology NAS to plain POSIX permissions:
#   directories 0775, files 0664, group `zcrypto`, and NO Synology ACL.
#
# Why plain POSIX (not a synoacltool ACL): a Synology ACL delivers the same access, but
# DSM always *displays* ACL'd files as 666/777+ (the ACL mask), never the literal
# 0664/0775. `chmod` strips the ACL and yields the literal modes. The archive's real
# actors are all covered without an ACL: the NAS containers run `--user 1000:1000`
# (zcrypto:zcrypto), the workstation is uid/gid 1000 (→ zcrypto via the share's NFS
# "No mapping" squash), and the admin login `zcrypto-deploy` is a member of the `zcrypto`
# group — so owner + group `zcrypto` + other-read (0664/0775) grants everyone who needs it.
#
# New files then land at 0664/0775 automatically given a 0002 umask on the container and
# workstation (chmod strips the inheritable ACL, so children inherit no ACL).
#
# IDEMPOTENT — re-run any time the perms drift. Must run as root (the tree is owned by
# `zcrypto`, not the login user). The `ssh nas` account (`zcrypto-deploy`) has passwordless
# sudo, so from the workstation repo root:
#
#   ssh nas 'sudo bash -s' < infra/nas/normalize-archive-perms.sh
#
# or, with the script present on the NAS:
#
#   sudo bash normalize-archive-perms.sh [/volume1/ZhaoCrypto]
#
# Synology `@eaDir` metadata subtrees are skipped.
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

# In every pass: `-xdev` stays on this filesystem (never cross into a nested mount), the
# `@eaDir` prune skips Synology metadata subtrees, `xargs -0` handles odd names, and `--`
# stops a path beginning with `-` being read as an option.
# group -> zcrypto  (`-h`: a symlink's group is set on the link itself, never its target)
find "$TARGET" -xdev -name '@eaDir' -prune -o -print0 | xargs -0r chgrp -h "$GROUP" --
# directories -> 0775  (chmod also strips any Synology ACL on the entry)
find "$TARGET" -xdev -name '@eaDir' -prune -o -type d -print0 | xargs -0r chmod 0775 --
# files -> 0664
find "$TARGET" -xdev -name '@eaDir' -prune -o -type f -print0 | xargs -0r chmod 0664 --

echo "normalized $TARGET: dirs 0775, files 0664, group $GROUP, ACLs stripped"
