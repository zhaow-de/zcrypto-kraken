---
status: open
ripe_when: 'a universe refresh newer than 2026-08-13 is published to the hub — check: `ls /mnt/zhao-crypto/hot | grep -E "^universe-[0-9]{8}$" | sort | tail -1` prints a stamp above `universe-20260813`'
---

# Retire the August stamped sets and the legacy universe at the next universe refresh

## Context — what

Two stamped sets from the 2026-08-13 sitting stay on the hub and in the local data root: `universe-20260813`, the universe `resolve_universe_path` in `cli/capture/command.py` selects, and `ohlc-reach-20260813`, the reach set its artifact's provenance names by directory and hash, which `docs/universe/point-in-time-universe.md` cites and `tests/test_data_manifest.py` reads locally. Beside them the unstamped `universe/`, frozen at its 2026-07-07 content and no longer a fallback, stays because `universe` is in `authored_sets` — `push_hot` raises without the directory and `tests/test_data_rebuild.py::test_every_rebuildable_dataset_is_an_authored_set` requires the name there — and `tests/test_capture_command.py` reads its artifact. Neither stamped set can be merged into an unstamped one while that universe is live: the artifact is immutable and names the reach set by directory. The next universe refresh is built from the rolling canonical (spec `00125`), after which the August pair has no live reader.

## Why this matters

Three dangling sets on `hot/` and under `data/` read as live data to every fetch, catalog line and operator who lists them, and the catalog has to keep explaining why they stay; a retirement with a wrong order (the reach set before the universe that names it) breaks the live universe's provenance.

## Findings so far

- 2026-10-11: the owner retired `ohlc-reach-20261007`, `ohlc-full-20261007` and `ohlc-15m-20261007` to `/volume1/ZhaoCrypto/backup-ohlc-squash-2026-10-11/` (plan `00125` R8) and asked whether the two August sets could be absorbed into the unstamped ones; they cannot while `universe-20260813` is the resolver's pick, for the reasons above.

## Suggested next steps

- When the trigger reads true: read the new artifact's provenance, `python3 -I -c 'import json; print(json.load(open("data/universe-<stamp>/point-in-time-universe.json"))["provenance"])'` after `uv run zcrypto data fetch`, and confirm `ohlc_dataset_dir` names `ohlc-rolling`.
- One PR: move `tests/test_data_manifest.py`'s `_LOCAL_REACH`, `tests/test_data_gated_run.py`'s message and `tests/test_capture_command.py`'s `_REPO_UNIVERSE` off the sets this topic retires; re-true the catalog's "two reach sets stay" line and `docs/universe/point-in-time-universe.md`'s fallback line; drop `universe` from `authored_sets` in `zcrypto.toml`, which `tests/test_data_rebuild.py::test_every_rebuildable_dataset_is_an_authored_set` refuses until it is changed; every consumer test of the files changed run before the first commit.
- After the merge, by the owner's hand on the NAS: `mv /volume1/ZhaoCrypto/hot/ohlc-reach-20260813 /volume1/ZhaoCrypto/hot/universe-20260813 /volume1/ZhaoCrypto/hot/universe /volume1/ZhaoCrypto/backup-ohlc-squash-<date>/`, then the local copies under `data/` copied aside and removed, and `ls /mnt/zhao-crypto/hot` read back; then this topic resolved with the PR and the move's instant.
