---
status: resolved
---

# Is the NFS export's filesystem btrfs or ext4? — the readdir-consistency probe

## Context — what

Split from [[T0058]] at its close (iter-101): the one suggested step the attended NFS-migration window did not run. The T0058 pivot has the ops node's readdir-driven consumers — the reconciler's `scan_hours()` availability glob and the panel's watermark sweep — listing directories the NAS is **concurrently writing**, over NFSv3, where the retired local rsync mirror used to guarantee a "sorted prefix per directory" invariant. Whether that concurrent listing is safe depends on `/volume1`'s filesystem, which is unrecorded.

## Why this matters

On an **ext4** export, a paged NFS READDIR spanning an htree bucket split can transiently omit an existing *older* entry while showing newer ones — turning that omission into a permanent `would_mint` ledger verdict (polluting the [[T0039]] soak whose analysis pins `--min-gap-seconds`) or a silently skipped panel hour. On **btrfs**, readdir cookies are stable/monotonic and the prefix property survives, so the concern evaporates. (Review finding 2026-07-17, recorded on T0058 before its close.)

## Findings so far

- No probe has been run yet; the full reasoning lives in [[T0058]] (archived) and above.
- The reconciler is still detect-only ([[T0039]]), so today's worst case is a polluted soak ledger or a skipped panel hour, not a wrong mint — but the soak analysis is exactly what pins `--min-gap-seconds`, so the pollution matters before the `--mint` flip.

## Done so far

- **Probed 2026-07-17 (read-only, `mount | grep /volume1`):** `/dev/mapper/cachedev_0 on /volume1 type btrfs (rw,nodev,noatime,ssd,synoacl,space_cache=v2,…)` — **btrfs**, the stable-readdir-cookie case. NFSv3 READDIR against the ops mount is safe from the ext4-hash-collision cookie instability this probe existed to rule out. No client-side workaround needed; the mount options stand as deployed.

## Suggested next steps

- On the NAS run `mount | grep -w /volume1` (or `df -T /volume1`) and record here whether `/volume1` is **btrfs** or **ext4**. Expected result: one line naming the filesystem type. **btrfs** → record the answer and resolve this topic. **ext4** → keep it open and design a by-name stat re-probe before any absence-derived verdict (name lookups bypass readdir cookies entirely), gating the [[T0039]] `--mint` flip on it.
