---
status: resolved
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

## Done so far

Resolved 2026-07-17 (iter-101, `feat/ops5-offload`) — all three suggested steps executed, evidence-first:

- **The evidence is committed**: `infra/nas/ledger-correction-20260714-link-eur.md` (commit `18ec391`) records the [[T0044]] correction — the removed LINK/EUR `total_loss` line and its circumstances — so the audit trail no longer depends on a stray file inside custody.
- **The `.bak` is removed from custody, evidence-then-remove**: sha-verified `1da63f1cce679d6e` on **both** hosts first, then removed from both; the trees are identical at **1174 files** after (from 1175 with the `.bak`).
- **The runbook now writes backups outside the replicated tree** (`18ec391`), closing the general shape — the overlay again contains nothing but data + manifests + the ledger, which is the stricter (and easier-kept) invariant the last suggested step asked for. No future correction can re-create this failure.
