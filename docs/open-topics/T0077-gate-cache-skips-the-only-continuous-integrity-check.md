---
status: partial
ripe_when: the mitigation has landed, so what remains is (a) the >3-day staleness alert rule, ripe NOW and autonomous, (b) the cache-file siting decision, ripe when the `--cache` deployment is actually scheduled, and (c) the owner's threat-model judgement on in-place parquet alteration, which gates how much of (a)/(b) is warranted -- ask at the next attended session
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

## Done so far

**The mitigation landed** (spec/plan `00062`; PR into `develop`). `gate-export --cache` no longer trusts a cycle indefinitely: each run force-replays a deterministic rotating slice of otherwise cache-eligible cycles, so the whole journal's parquet bytes are re-verified about daily even with the cache warm.

- **Keyed on the cycle, not the position** — `slice_of(cycle_ts) = sha256(cycle_ts.isoformat()) % 24`, so a cycle's slice is a fixed property of the cycle. An index-keyed slice would move as the journal grows, making coverage neither uniform nor provable. `sha256` rather than the builtin `hash()`, which is not guaranteed stable across processes.
- **Stateless** — the current slice is `now.hour % 24`; no rotation cursor to persist, corrupt, or reset. A skipped hour costs a delayed slice and self-heals.
- **A forced re-verification failure is a GATE failure**, not a cache event (D4): same `CycleOutcome(mismatch=True)` any replay produces, into `JournalCounts`/`evaluate_gate` unchanged, counted as `replayed` and never `from_cache`.
- **Staleness is observable** — `verified_at` per entry, and `zcrypto_gate_cache_oldest_verification_age_seconds`, because a rotation that silently stops would otherwise look exactly like a healthy cache. `zcrypto_gate_export_duration_seconds` also lands, closing [[T0069]]'s "measure it rather than extrapolate" gap.

**Verified on the real journal** (ops mirror, 57 cycles), against the *modified* eligibility predicate — the iter-110 evidence covers the old one and does not carry over:

| run | wall | replayed | hits |
|---|---|---|---|
| no-cache | 94.52 s | 57 | 0 |
| `--cache` cold | 93.70 s | 57 | 0 |
| `--cache` warm | 2.45 s | **1** | 56 |
| warm again | 2.48 s | **1** | 56 |

**Gate metrics identical across all four** (`gate_status 0`, `streak_days 9`, `mismatch_total 0`). The `replayed 1 / hits 56` line is the load-bearing one: a fast warm run is exactly what a silently-disabled rotation would also produce, so the counters — not the runtime — are what prove the treatment engaged.

**Coverage proven, not inferred:** a 24-hour sweep re-verified **57/57 cycles, each in exactly one slice** (21/24 slices populated, final age 84,540 s < 86,400). Worst hour = 5 replays ≈ 8.1 s here, ≈ 54 s on the NAS Atom — about 1.5% of the 3600 s pull interval, against ~510 s for today's full replay.

**The guarantee was attacked, not just tested.** A reviewer confirmed eligibility depends only on `cycle_ts` and the run clock, reading nothing from the cache file — so an attacker with full control of that file can suppress the staleness metric but cannot suppress the rotation replay, and a failed `save_cache` cannot stop it either. Two latent traps were closed on the way: the emitted metrics' *values* were unpinned end-to-end (hardcoding them to `0.0` passed 72/72 until a test pinned the exact values), and `_ROTATION_SLICES > 24` would have left high slices permanently unreachable, silently — now an assert.

**Known and deliberate:** a mismatch outcome is itself cached, so after repairing corrupted evidence the gate can stay red for up to one rotation. Fail-closed by design; the README documents deleting the cache file as the immediate remedy.

## Suggested next steps

- **(Autonomous, ripe NOW — the metric ships, the RULE does not)** Add the Grafana alert on `zcrypto_gate_cache_oldest_verification_age_seconds` above ~3 days to `infra/grafana/alerts.yaml`. Emitting the number without alerting on it leaves the rotation's failure mode exactly as invisible as before: `save_cache` logs a warning and continues on write failure, so a full disk presents as a working cache with `invalidated` reading 0 and a quietly-ageing staleness number nobody is watching.
- **(Decision, then autonomous)** Site the cache file **container-ephemeral, never on `/archive`**. The NAS runs `polars-runtime-compat` while ops runs stock polars, and `replay_fingerprint` digests neither — so a cache file on a share both hosts can reach is mutually poisonable.
- **(For the owner, one judgement)** Confirm whether in-place alteration of an already-verified parquet is a threat worth defending against in this environment. If the answer is no, the rotating re-verification can be dropped to a weekly slice or dropped entirely with the reasoning recorded here — but that should be a decision, not an omission.
