---
status: open
ripe_when: any attended window on the respective host — every item is a small, reversible host mutation with no deploy coupling
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

## Suggested next steps

- **ops:** `sudo find / -xdev -user 988 -o -group 988` to confirm nothing meaningful is uid-988-owned beyond the empty state dir, then `userdel kraken-capture` and remove `/var/lib/zcrypto-capture`. One attended minute; reversible (recreating a system account is trivial).
- **NAS:** `stat /volume1/ZhaoCrypto/capture-reconciled` (and a sample child) — determine why it is 777 (the archive-pull container runs `--user 1000:1000`, which needs no world bits), then tighten to 755/644 unless something demonstrably needs otherwise; re-run one pull cycle and verify `checked/failed` unchanged.
