# Spec 00062 — gate-cache rotating re-verification: keep the integrity check the cache removes (T0077)

## Goal

Make `gate-export --cache` safe to enable, by restoring — at bounded cost — the continuous parquet-byte verification that a cache hit currently skips. Until this lands, `--cache` must not be switched on in any deployment.

## Why

`replay_cycle` (`cli/engine/concordance.py:116`) is the **only** place the journal's parquet bytes are re-read and hash-verified. The chain that makes it load-bearing:

- the NAS pulls the journal with `--no-verify` and says why — *"no .sha256 sidecars, Role B verifies it via replay"* (`infra/nas/pull-entrypoint.sh:93`);
- `_run_rsync` is `rsync -a --chmod=D0775,F0664` — no `--checksum`, so a file altered in place at unchanged size+mtime is never re-transferred, and the tree is deliberately group-writable;
- a cache hit (`cli/engine/command.py:229-231`) returns the stored `CycleOutcome` without calling `_replay_one`;
- `evidence_fingerprint` digests the `content_hash` **recorded in the journal record**, never a fresh read — it fingerprints the claim about the bytes, not the bytes.

So enabling `--cache` turns *"every parquet re-verified ~24×/day forever"* into *"verified once, then trusted forever."* A snapshot altered after its first successful replay is served as a **PASS**, silently: `zcrypto_gate_mismatch_total` stays 0, `gate_status` stays 1, the streak climbs, the exporter stays fresh. The failure direction is a false pass on the artifact authorising real-money trading.

Note what this reframes: iter-109 characterised the per-cycle rebuild as pure waste. It is *also* the integrity monitor. An optimisation that removes redundancy must replace the monitoring the redundancy was silently providing.

## Decisions

- **D1 — bounded rotating re-verification, always on when the cache is active.** Each run force-replays a deterministic slice of otherwise cache-eligible cycles. Not a flag: a safety property that can be switched off is one that will be. With `_ROTATION_SLICES = 24` and an hourly loop, the whole journal is re-verified about daily at ~1/24 of today's per-run cost.

- **D2 — the slice is keyed on `cycle_ts`, not on loop index or position.** `slice_of(cycle_ts) = int(sha256(cycle_ts.isoformat()).hexdigest(), 16) % _ROTATION_SLICES`. Index-keyed rotation is wrong: the journal grows and its artifact ordering can shift, so a cycle's slice would move between runs and coverage would be neither uniform nor provable. `sha256` rather than `hash()` because the built-in is not guaranteed stable across processes or releases. A cycle's slice is therefore a fixed property of the cycle, for all time.

- **D3 — the current slice is derived from the run clock: `now.hour % _ROTATION_SLICES`.** Stateless — no rotation cursor to persist, corrupt, or reset. A skipped or repeated hour (the pull loop's period is `3600 + work`, so it drifts) costs at most a delayed slice and self-heals on the next pass; D5's metric makes any real starvation visible rather than silent.

- **D4 — a re-verification failure is a real gate failure, not a cache event.** A forced replay that raises `HashMismatchError` produces the same `CycleOutcome(mismatch=True)` any replay would, and flows into `JournalCounts` and `evaluate_gate` unchanged. Detecting corruption must move the gate, not merely log. Forced replays count as `replayed`, never as `from_cache`.

- **D5 — `verified_at` per entry, and an age metric.** Each cache entry stores when it was last *actually replayed*; a cache hit carries the stored value forward, a replay stamps `now`. Emit `zcrypto_gate_cache_oldest_verification_age_seconds = now - min(verified_at)`, alerting above ~3 days. Without it a rotation that silently stops looks exactly like a healthy cache — and `save_cache` already logs a warning and continues on write failure, so a full disk presents as a working cache with `invalidated` reading 0. This makes the cache's *staleness* observable, which is the property the whole design now rests on.

- **D6 — `CACHE_SCHEMA_VERSION` 1 → 2.** Adding `verified_at` changes the entry shape; the existing version check rejects v1 files wholesale, forcing one full replay and a rewrite. That is the intended fail-open behaviour, not a migration to write.

- **D7 — the per-run cache counters lose their `_total` suffix.** `zcrypto_gate_cache_replayed_total` → `zcrypto_gate_cache_replayed`, `_hits_total` → `_hits`. They are per-run gauges, not monotonic counters; enabling `--cache` drops `replayed` from N to ~1, which `rate()`/`increase()` reads as a counter reset. Rename now, while nothing consumes them — the running image predates the module. `zcrypto_gate_cache_invalidated` already lacks the suffix and is unchanged.

- **D8 — emit `zcrypto_gate_export_duration_seconds`** (wall). [[T0069]]'s entire budget table is a linear extrapolation from one datapoint on the Atom; the step's real cost has never been measured in production. This closes that, and makes the effect of enabling `--cache` observable rather than inferred. Both new metric names match the existing Alloy keep-regex `zcrypto_gate_.*`, so no infra change is required.

## Non-goals

- Not enabling `--cache` anywhere. This makes it *safe to enable*; the deployment change stays attended and is [[T0069]]'s sub-item.
- Not the [[T0075]] test-coverage gaps — those are unpinned guarantees in the same module, a different problem.
- Not verifying the parquet bytes at pull time (adding `--checksum` or sidecars to the journal channel). That is a plausible alternative remedy, deliberately not taken here: it would put the cost in the pull loop for every file every cycle, where this puts it on 1/24 of already-verified cycles.
- No change to `report`, which is never cached and must keep re-verifying in full.

## Test list (TDD)

1. **The keystone — a tampered parquet with an untouched journal record is caught within one full rotation.** Cache the cycle warm, alter the parquet bytes on disk (leaving the record's `content_hash` claim intact so the fingerprint is unchanged), then run for each of the 24 slice values; the cycle's own slice must force a replay that raises `HashMismatchError` and yields `mismatch=True`. **This test fails if rotation is removed** — it is the whole point of the spec.
2. **Slice assignment is stable and uniform** — `slice_of` is deterministic across calls and processes for the same `cycle_ts`, and distributes a realistic journal across all 24 slices without gross skew.
3. **Rotation is bounded** — with a warm cache and no tampering, a single run replays only its slice (≈ n/24), not the whole journal, and the rest are served from cache.
4. **Cache hits still equal fresh replays (spec `00060` D4 preserved)** — the `CycleOutcome` list and `evaluate_gate` status are identical warm vs cold, with rotation active.
5. **D4** — a forced re-verification that fails counts in `JournalCounts.mismatches` and moves `evaluate_gate`, and is counted as `replayed`, never `from_cache`.
6. **D5** — `verified_at` is carried forward on a hit and stamped on a replay; `oldest_verification_age` reflects the least-recently-replayed entry, and a full rotation drives it below one rotation period.
7. **D6** — a v1 cache file is rejected wholesale (full replay, `invalidated` true), not partially read.
8. **D7/D8** — the renamed gauges and `duration_seconds` appear in the textfile with plausible values; no `_total`-suffixed cache gauge remains.
9. **Real-journal (data-gated, orchestrator)** — on the ops mirror, no-cache / cold / warm produce **identical gate metrics** against the modified code. The existing iter-110 evidence covers the *unmodified* eligibility predicate and does not carry over.
