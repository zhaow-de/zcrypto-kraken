# Ledger correction evidence — 2026-07-14 false `total_loss` (LINK/EUR trades, hour 02)

The durable record of the one correction made to the append-only `reconcile-ledger.jsonl` to date, committed to the repo on 2026-07-17 (T0057 resolution) so the on-host backup could be removed from the replicated overlay. The procedure that produced it is the "Correcting the reconcile ledger (T0044)" runbook in `README.md` beside this file (shipped in `b22d3e2`).

## The removed record (verbatim)

```json
{"state": "total_loss", "pair": "LINK/EUR", "kind": "trades", "hour": "2026-07-14T02:00:00+00:00", "residual_seconds": 3600.0, "at": "2026-07-14T21:07:57.453076+00:00"}
```

## Why it was removed

The record was false — the hour was **not** a total loss. `is_total_loss` (`cli/archive/settle.py`) used to classify any bracketed absence as a permanent loss, and fired on LINK/EUR trades hour 02: LINK printed 8 trades in hour 01 and 9 in hour 04 with zero in hour 02, while its **book** final for that same hour existed throughout — the connection was alive, nobody traded (the T0043 classifier bug; see `docs/open-topics/archive/T0043-lost-trades-file-with-surviving-book-is-invisible.md`, where the classifier fix also lives). The false record had logged at ERROR (so it paged) and booked 3600 s into the monotone `residual_gap_seconds_total`; the correction dropped that counter from 6261.8 to 2661.8 s — the Prometheus counter reset that the `resets(...) == 0` alert guards exist for (`docs/open-topics/T0044-reconcile-ledger-correction-resets-counters.md`). With the owner's approval the record was purged on 2026-07-14 by the exact-match filter procedure later committed as the runbook: back up verbatim, exact-match predicate, `len(dropped) == 1` asserted.

## The backup file

- `reconcile-ledger.jsonl.bak-20260714-220209` — the pre-correction ledger, copied verbatim by the runbook's step 1.
- sha256 `1da63f1cce679d6e`, 2990 bytes, **12 lines vs the live ledger's 11** — the extra line is the record above, which made the `.bak` the only on-host record that the append-only ledger was ever edited, and of what was removed.
- It lived **inside** the canonical `capture-reconciled` overlay, in the tree root beside the live ledger, in both overlay copies: the ops node's `/var/lib/zcrypto-ops/capture-reconciled/` (`deploy:deploy 0777`) and the NAS's `/volume1/ZhaoCrypto/capture-reconciled/` (`root:root 0555` with a Synology ACL).

## How it broke the overlay sync (2026-07-16, T0057)

Because it sat inside the replicated tree, the new ops→NAS overlay pull (spec `00054`'s `sync_reconciled` channel) had to reconcile the two copies' modes and could not: rsync failed with `failed to set permissions on ".../reconcile-ledger.jsonl.bak-20260714-220209": Operation not permitted (1)` → exit code 23 → the **whole** overlay pull reported failure, every cycle. One stray file failed the entire tree's replication. It was unblocked non-destructively the same day (`chown zcrypto:zcrypto` + `chmod 664` on the NAS's copy; content byte-unchanged, sha `1da63f1cce679d6e`), after which the overlay replicated cleanly: 1175 files, file-list sha `0b684ce3bf0b3774`, identical on both hosts. Full account: `docs/open-topics/T0057-ledger-correction-backup-in-custody.md`.

## Removal record (2026-07-17)

Owner decision on T0057: commit this evidence to the repo, then remove the `.bak` from the tree. Executed attended on 2026-07-17:

- the `.bak`'s sha256 was re-verified as `1da63f1cce679d6e` on **both** hosts before deletion;
- the file was removed from both overlay copies;
- the trees were re-verified identical afterwards at **1174 files** (the prior 1175 minus the `.bak`).

The overlay again carries data + manifests + the ledger, nothing else. This file is now the sole durable record of the correction; the runbook no longer writes backups into the tree (see its backup rules).
