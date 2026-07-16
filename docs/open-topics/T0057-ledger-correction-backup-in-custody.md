---
status: open
ripe_when: the reconcile ledger is corrected again (the [[T0044]] runbook is run), or the overlay's ops->NAS pull fails on a permission error
---

# The ledger-correction backup lives inside the canonical overlay, and it breaks the sync

## Context — what

`reconcile-ledger.jsonl.bak-20260714-220209` sits in the root of the `capture-reconciled` overlay, beside the live `reconcile-ledger.jsonl`. It is the backup [[T0044]]'s ledger-correction runbook (shipped in `b22d3e2`) takes before editing the ledger. Because it lives *inside* the tree, it is replicated into custody along with the data — and on 2026-07-16 it **broke the new ops→NAS overlay channel**.

## Why this matters

- **It blocked the channel.** `rsync` failed with `failed to set permissions on ".../reconcile-ledger.jsonl.bak-20260714-220209": Operation not permitted (1)` → `code 23` → the whole overlay pull reported failure, every cycle. The NAS's copy was `root:root 0555` with a Synology ACL while the pulling container runs as uid 1000; rsync could not make it match the source's mode. One stray file failed the entire tree's replication.
- **It is evidence, and it nearly got deleted.** During spec `00054` this file was initially written off as "a stray root-owned mode-777 file" and filed as a deletion candidate. It is not: it has **12 lines to the live ledger's 11**, and the line the live ledger lacks is
  `{"state": "total_loss", "pair": "LINK/EUR", "kind": "trades", "hour": "2026-07-14T02:00:00+00:00", "residual_seconds": 3600.0, ...}`
  — i.e. it is the **only record that an append-only ledger was edited**, and of what was removed. Deleting it to unblock the sync would have destroyed the audit trail of a correction to the one artifact whose whole value is being append-only.
- The general shape: an **operational artifact** living inside a **canonical, replicated, immutable-by-convention tree**. It will be copied to every consumer of the overlay, forever, and any permission mismatch anywhere breaks replication for everything.

## Findings so far

- Unblocked non-destructively on 2026-07-16 by `chown zcrypto:zcrypto` + `chmod 664` on the NAS's copy; the file's **content is byte-unchanged** (sha `1da63f1cce679d6e`, 2990 bytes). The overlay then replicated cleanly (1175 files, list sha `0b684ce3bf0b3774`, identical on both hosts).
- The ops-side copy is `deploy:deploy 0777`; the mode asymmetry across hosts is what rsync tried, and failed, to reconcile.
- This is the only `.bak` in the tree today, so the failure is currently one file wide — but the runbook creates one per correction, so the next correction adds another.

## Suggested next steps

- **Decide where correction backups belong.** They should almost certainly live *outside* the replicated tree (e.g. a sibling `overlay-corrections/` dir on the host that ran the runbook, or committed to the repo as evidence since they are small and text). Update [[T0044]]'s runbook accordingly — it currently writes the `.bak` in place, which is what put it here.
- **Decide what to do with this one.** It is evidence of a real correction; do not delete it without recording its content somewhere durable first. Preferred: commit its diff (one JSON line) into the repo as part of the T0044 record, then remove it from the tree.
- Consider whether the overlay's replication should tolerate a non-canonical file at all (e.g. pull with an exclude), or whether the tree should simply contain nothing but data + manifests + the ledger — the stricter invariant is the easier one to keep.
