---
status: open
ripe_when: ripe NOW, and it BLOCKS enabling `gate-export --cache` in any deployment — the mitigation is autonomous and must land before the flag is switched on anywhere
---

# Enabling `gate-export --cache` removes the only continuous integrity check on the gate's evidence

## Context — what

`gate-export --cache` (spec `00060`, iter-110) skips `replay_cycle` for any journaled cycle whose evidence fingerprint is unchanged. That replay is the **only** place the journal's parquet bytes are re-read and hash-verified. So enabling the flag converts *"every parquet in the journal is re-verified ~24×/day, forever"* into *"verified once, in the first hour after it arrives, then trusted forever."*

The trust is anchored to the wrong thing: `evidence_fingerprint` digests the `content_hash` **recorded in the journal record**, not a fresh hash of the file on disk. It fingerprints the claim about the bytes, not the bytes. A snapshot altered in place after its first successful replay therefore produces an identical fingerprint, hits the cache, and is served as a **PASS**.

## Why this matters

The chain, each link verified in the tree:

- `infra/nas/pull-entrypoint.sh:93` pulls the journal with `--no-verify`, and states the reason: *"no .sha256 sidecars, Role B verifies it via replay."* The pull deliberately delegates verification to the replay.
- `_run_rsync` (`cli/archive/command.py`) is `rsync -a --chmod=D0775,F0664` — no `--checksum`. rsync's size+mtime quick-check never re-transfers a file corrupted in place, and `--chmod` deliberately makes the archived tree group-writable.
- The parquet bytes are verified in exactly one place: `cli/engine/concordance.py:116` — `snapshot_content_hash(ts, closes) != entry.content_hash` → `HashMismatchError`.
- A cache hit (`cli/engine/command.py:229-231`) returns the stored `CycleOutcome` and never calls `_replay_one`.
- `evidence_fingerprint` (`cli/engine/gate_cache.py`) hashes `s.content_hash` from the record — never a fresh read.

**The failure direction is a false PASS on the artifact that authorises real-money trading**, and it is silent: `zcrypto_gate_mismatch_total` stays 0, `zcrypto_gate_status` stays 1, the streak keeps climbing, the exporter stays fresh. Every green signal an operator has stays green.

Two further points sharpen it:

- **One of the same day's decisions already depends on the invariant this removes.** Commit `21d777f` excluded polars from `replay_fingerprint` on the stated grounds that *"the snapshot decode path … already fails loudly via the content-hash check."* A cache hit skips that check.
- **Spec `00060` D2 never modelled this axis.** It scoped the fingerprint to "everything a replay's verdict depends on **from the journal side**" — meaning the record's own fields. The design's governing asymmetry ("over-invalidation is safe, under-invalidation silently corrupts gate evidence") was therefore never argued over the parquet-bytes axis, which is the one that breaks.

This reframes iter-109's original finding. That iteration characterised the per-cycle full rebuild as pure waste — *"each hourly run re-verifies the entire journal from scratch, redoing work the previous run already did."* It is not only waste: **it is also the continuous integrity monitor.** Any optimisation that removes the redundancy must replace the monitoring it was silently providing.

## Findings so far

- No live defect today: `--cache` is not enabled in any deployment (`pull-entrypoint.sh` invokes `gate-export` without it), so the hourly full replay — and its verification — is still running. The code ships inert, exactly as [[T0069]] states.
- Blast radius is bounded by design in two ways worth keeping: the flag is opt-in, and `report` is never cached (it is the human-facing *verification* tool and must genuinely re-verify).
- Related but distinct: [[T0075]] found 8 unpinned *guarantees* in the same module. Those are coverage gaps in the tests; this topic is a gap in the **design**, present regardless of test coverage.
- The threat model is not primarily malice. The plausible vectors are bit-rot on a spinning-disk RAID, a partial or interrupted write, and any process holding group-write on the share (`--chmod=D0775,F0664` grants it deliberately, so members of group `zcrypto` can write into it).

## Suggested next steps

- **(Autonomous — the mitigation, and the precondition for ever enabling the flag)** Add **bounded rotating re-verification** to `_evaluate_journal`: each run, force a full `_replay_one` on a deterministic, stateless slice of otherwise cache-eligible cycles — e.g. re-replay cycle *i* when `i % 24 == (hour of run) % 24`. The whole journal is then re-verified about daily at roughly 1/24th of today's per-run cost. Deterministic and stateless so it needs no extra persisted state and behaves identically across restarts. Pin it with a test that a tampered parquet whose journal record is untouched is still caught within one full rotation.
- **(Autonomous)** Emit `zcrypto_gate_cache_oldest_verification_age_seconds` and alert above ~3 days, so the rotation stopping is visible rather than silent. Without it, a rotation that silently stops looks exactly like a healthy cache. Note `save_cache` currently logs a warning and continues on write failure — on a full disk that presents as a working cache with `invalidated` reading 0.
- **(Autonomous, do it in the same change)** Rename `zcrypto_gate_cache_replayed_total` / `_hits_total` off the `_total` suffix — they are per-run gauges, and enabling `--cache` drops `replayed` from N to ~1, which `rate()`/`increase()` reads as a counter reset. Cheap now, breaking later once someone is reading them.
- **(Autonomous)** Re-run the three-way no-cache / cold / warm comparison on the ops journal mirror **against the modified code** and require identical gate metrics. The existing "gate metrics IDENTICAL" evidence covers the *unmodified* predicate on a failure-free 39-cycle journal; it does not carry over to a changed cache-eligibility rule.
- **(Decision, then autonomous)** Site the cache file **container-ephemeral, never on `/archive`**. The NAS runs `polars-runtime-compat` while ops runs stock polars, and `replay_fingerprint` digests neither — so a cache file on a share both hosts can reach is mutually poisonable.
- **(For the owner, one judgement)** Confirm whether in-place alteration of an already-verified parquet is a threat worth defending against in this environment. If the answer is no, the rotating re-verification can be dropped to a weekly slice or dropped entirely with the reasoning recorded here — but that should be a decision, not an omission.
