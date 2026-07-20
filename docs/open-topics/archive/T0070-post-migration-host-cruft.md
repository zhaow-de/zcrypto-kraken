---
status: resolved
---

# Post-migration host cruft — vestigial account + permissions left by the identity migrations

## Context — what

The spec-`00057` fleet users/groups migrations (iter-104 ops, iter-105 capture/engine) and their surrounding incidents left a small residue of host-local cruft that no role manages and no converge will ever clean. Verified live 2026-07-19; parked here so it survives until an attended window on each host.

## Why this matters

Each item is harmless today but is exactly the kind of unowned state that confuses a future incident investigation ("why does uid 988 exist?") or silently widens permissions. Cheap to clean; worth doing consciously rather than leaving to archaeology.

## Findings so far

- **ops (`hp`): vestigial `kraken-capture` account** — uid 988, `nologin`, home `/var/lib/zcrypto-capture` (an empty dir it owns). Left from the pre-guard era when the `base` role created the capture user on every host it ran on; since the capture-host guard (`roles/base/tasks/main.yml`, 2026-07-19) no role manages it on ops. The ops node never runs capture, so the account is pure residue.
- **NAS: `capture-reconciled` tree permissions** — the owner observed (work journal, 2026-07-16) the `capture-reconciled` folder at mode 777. The `.bak` file that shared the observation was removed by [[T0057]] (2026-07-17); the folder-mode question was never separately answered: whether 777 is rsync-receiver behavior, a manual artifact, or load-bearing for the pull/NFS path.
- **Verified already clean (2026-07-19, root-side listing on all three hosts):** the cutover-era `authorized_keys` backups (`.bak-t0068` on the capture hosts, `.pre-cutover.bak` on the NAS) no longer exist — that deferred cleanup is done; recorded here so it is not re-chased.

## Resolution (2026-07-19)

- **ops vestigial `kraken-capture` account — REMOVED.** `find / -xdev \( -uid 988 -o -gid 988 \)` confirmed uid/gid-988 owned **only** the empty `/var/lib/zcrypto-capture` home (nothing else); a `/etc` scan found no sudoers/cron/systemd/mount reference (only the passwd/group DB entries themselves, group memberless). `userdel kraken-capture` + `rmdir /var/lib/zcrypto-capture` — user, group, and dir all gone. The base-role capture-host guard (`roles/base/tasks/main.yml`, 2026-07-19) means no future ops converge recreates it.
- **NAS `capture-reconciled` — no action needed; it is 775, NOT 777.** `stat` showed `mode=775 owner=zcrypto-data:zcrypto` (children the same): owner + group (`zcrypto`) write for the archive-pull container (which runs `--user 1000:1000`), and **no world-write** toward custody. The work-journal "777" was stale/mis-observed (or normalized by the T0057 sweep); 775 is the correct, safe state — group-write is what the container needs, so tightening to 755 would buy nothing and risks a container-write regression. Left as-is.
- **`.bak` backups** — already confirmed absent on all three hosts (2026-07-19); no action.
