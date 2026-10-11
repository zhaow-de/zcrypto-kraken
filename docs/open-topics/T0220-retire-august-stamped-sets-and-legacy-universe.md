---
status: open
ripe_when: 'a universe refresh newer than 2026-08-13 is published to the hub — check: `ls /mnt/zhao-crypto/hot | grep -E "^universe-[0-9]{8}$" | sort | tail -1` prints a stamp above `universe-20260813`'
---

# Retire the August stamped sets and the legacy universe fallback at the next universe refresh

## Context — what

Two stamped sets from the 2026-08-13 pre-live sitting stay on the hub and in the local data root after the 2026-10-11 retirements: `universe-20260813`, the live point-in-time universe the resolver selects (`cli/capture/command.py`, the newest complete `universe-<stamp>` set), and `ohlc-reach-20260813`, the daily reach set that universe was built from, named by its artifact's provenance (`ohlc_dataset_dir`, `ohlc_dataset_hash`), cited by `docs/universe/point-in-time-universe.md` and read by `tests/test_data_manifest.py` from the local root. Beside them the unstamped `universe/` stays frozen at its 2026-07-07 content, deliberately not a fallback, kept only because `push_hot` raises without every set of `authored_sets`; spec `00093` D5 registered its retirement as the remainder of T0093. Neither stamped set can be merged into an unstamped one while that universe is live: the artifact is immutable and names the reach set by directory. The next universe refresh is built from the rolling canonical (spec `00125`), after which the August pair has no live reader.

## Why this matters

Three dangling sets on `hot/` and under `data/` read as live data to every fetch, catalog line and operator who lists them, and the catalog has to keep explaining why they stay; a retirement with a wrong order (the reach set before the universe that names it) breaks the live universe's provenance.

## Findings so far

- 2026-10-11: the owner retired `ohlc-reach-20261007`, `ohlc-full-20261007` and `ohlc-15m-20261007` to `/volume1/ZhaoCrypto/backup-ohlc-squash-2026-10-11/` (plan `00125` R8) and asked whether the two August sets could be absorbed into the unstamped ones; they cannot while `universe-20260813` is the resolver's pick, for the reasons above.
- `docs/reference/data-catalog-full.md`'s `ohlc-reach` section records why the two reach sets stay; `tests/test_data_gated_run.py` names the local reach manifest's path in a message.

## Suggested next steps

- When the trigger reads true: read the new artifact's provenance, `python3 -I -c 'import json; print(json.load(open("data/universe-<stamp>/point-in-time-universe.json"))["provenance"])'` after `uv run zcrypto data fetch`, and confirm `ohlc_dataset_dir` names `ohlc-rolling`.
- One PR: move `tests/test_data_manifest.py`'s `_LOCAL_REACH` and `tests/test_data_gated_run.py`'s message off `ohlc-reach-20260813`; re-true the catalog's "two reach sets stay" line and `docs/universe/point-in-time-universe.md` (the August citation stays as dated history); retire the legacy `universe/` from `authored_sets` in `zcrypto.toml` and from `push_hot`'s requirement (T0093's remainder, spec `00093` D5); every consumer test of the files changed run before the first commit.
- After the merge, by the owner's hand on the NAS: `mv /volume1/ZhaoCrypto/hot/ohlc-reach-20260813 /volume1/ZhaoCrypto/hot/universe-20260813 /volume1/ZhaoCrypto/hot/universe /volume1/ZhaoCrypto/backup-ohlc-squash-<date>/`, then the local copies under `data/` copied aside and removed, and `ls /mnt/zhao-crypto/hot` read back; then this topic resolved with the PR and the move's instant.
