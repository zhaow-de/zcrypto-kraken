"""Every registered trial must name provenance that is actually committed (T0125).

The defect this closes: registry record 44 is the deployable, and its verdict is ADOPT *vs incumbent
trial 43* — but trial 43's construction was never committed, and its `run_ref` names scratchpad
scripts that no longer exist. The criterion that selected the live system can never be re-examined.

Two layers guard against a repeat, deliberately split:

- **Append time** (`cli/registry/record.py::validate_caller_fields`) rejects a `run_ref` that resolves
  to no file in the repo. It runs on every append, so it may not shell out — it can only check that a
  path *exists*, not that it is committed.
- **Here**, over the real registry, where git is available and "committed" is checkable for real.

The load path is deliberately NOT strict: the registry is append-only, so the 14 records written
before the guard existed must keep loading or everything that reads the file breaks. That is why the
historical exemption lives in this test rather than in the store.

**The exemption is frozen and asserted in both directions.** A one-directional assertion would let the
pinned set quietly cover a record that had started passing, turning the exemption into a decoration
over a regression. So this file asserts both that no record outside the set fails *and* that every
member of the set genuinely fails today.

Git is required, not skipped-if-absent: a provenance guard that silently skips is the failure class
this topic is about.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from cli.registry.record import run_ref_path_candidates, validate_caller_fields

REPO = Path(__file__).resolve().parents[1]
REGISTRY = REPO / "docs" / "reference" / "trial-registry.jsonl"

# Trials 33-46 (contiguous) name scratchpad scripts that were never committed and are gone. The registry
# is append-only and hash-chained, so these records can never be repaired -- they are exempted here, and
# the exemption may never grow: a new record with an uncommitted run_ref must fail.
LEGACY_UNCOMMITTED = frozenset(range(33, 47))

# Records 34-35 pin the PRE-amendment sha256 of their spec: the spec was edited after both appends, so
# no committed spec file hashes to their `spec_hash` and the pin can never be recomputed. Append-only,
# so unrepairable. Same freeze discipline as above -- a NEW record whose spec_hash matches no committed
# spec must fail, and this exemption may not grow to cover it.
LEGACY_SPEC_HASH_ORPHANS = frozenset({34, 35})


def _git_tracked() -> frozenset[str]:
    """Every path git tracks, repo-relative. One invocation, not one per candidate path."""
    out = subprocess.run(
        ["git", "-C", str(REPO), "ls-files", "-z"],
        capture_output=True,
        check=True,
        text=True,
    ).stdout
    return frozenset(p for p in out.split("\0") if p)


def _records() -> list[dict]:
    return [json.loads(line) for line in REGISTRY.read_text(encoding="utf-8").splitlines() if line.strip()]


def _has_committed_provenance(run_ref, tracked: frozenset[str]) -> bool:
    return any(c in tracked for c in run_ref_path_candidates(run_ref or ""))


def _failing_ids(records: list[dict], tracked: frozenset[str]) -> set[int]:
    return {r["trial_id"] for r in records if not _has_committed_provenance(r.get("run_ref"), tracked)}


def _committed_spec_hashes() -> frozenset[str]:
    """sha256 of every committed spec file. A record's `spec_hash` must equal one of these; the registry
    carries no spec PATH, so membership is what "the spec this record pins still exists unaltered" means."""
    return frozenset(
        __import__("hashlib").sha256((REPO / p).read_bytes()).hexdigest()
        for p in _git_tracked()
        if p.startswith("docs/specs/") and p.endswith(".md")
    )


def _spec_hash_orphan_ids(records: list[dict], spec_hashes: frozenset[str]) -> set[int]:
    return {r["trial_id"] for r in records if r.get("spec_hash") not in spec_hashes}


def test_no_record_outside_the_frozen_legacy_set_lacks_committed_provenance():
    unexpected = _failing_ids(_records(), _git_tracked()) - LEGACY_UNCOMMITTED
    assert unexpected == set(), (
        f"trial(s) {sorted(unexpected)} have a run_ref naming no git-tracked path. Commit the code that "
        f"produced the run and reference its repo-relative path; do not add these ids to LEGACY_UNCOMMITTED."
    )


def test_the_legacy_exemption_is_not_vacuous_and_is_frozen():
    # Every pinned id must GENUINELY fail the check today. Otherwise the exemption is decorating a pass
    # and would silently absorb a future regression on that id.
    failing = _failing_ids(_records(), _git_tracked())
    not_actually_failing = LEGACY_UNCOMMITTED - failing
    assert not_actually_failing == set(), (
        f"trial(s) {sorted(not_actually_failing)} are exempted but pass the check -- drop them from "
        f"LEGACY_UNCOMMITTED so a real regression on them cannot hide behind the exemption."
    )
    assert len(LEGACY_UNCOMMITTED) == 14
    assert LEGACY_UNCOMMITTED == frozenset(range(33, 47))


def test_a_new_record_without_committed_provenance_would_fail_this_test():
    # Constructive proof that the guard bites rather than merely being asserted: the next trial id, added
    # with a scratchpad run_ref, lands outside the exemption and so trips the assertion above.
    tracked = _git_tracked()
    records = _records()
    next_id = max(r["trial_id"] for r in records) + 1

    scratchpad = {"trial_id": next_id, "run_ref": "b1_trial3_run.py + b1_trial3_write.py (scratchpad)"}
    assert _failing_ids([*records, scratchpad], tracked) - LEGACY_UNCOMMITTED == {next_id}

    uncommitted = {"trial_id": next_id, "run_ref": "cli/registry/not_a_real_runner.py"}
    assert _failing_ids([*records, uncommitted], tracked) - LEGACY_UNCOMMITTED == {next_id}

    committed = {"trial_id": next_id, "run_ref": "cli/registry/record.py"}
    assert _failing_ids([*records, committed], tracked) - LEGACY_UNCOMMITTED == set()


def test_git_tracked_lookup_is_sane():
    # Guards the predicate itself: an empty or bogus tracked-set would make every record "fail" and every
    # exemption look non-vacuous, which is how a broken check passes for the wrong reason.
    tracked = _git_tracked()
    assert "cli/registry/record.py" in tracked
    assert "docs/reference/trial-registry.jsonl" in tracked
    assert "cli/registry/not_a_real_runner.py" not in tracked


def _caller(**over):
    f = dict(
        iteration="iter-001",
        family="A1",
        spec_hash="s",
        seeds=[0],
        metrics={"sharpe": 0.3},
        n_trials_in_family=1,
        verdict="adopt",
        run_ref="cli/registry/record.py",
    )
    f.update(over)
    return f


def test_both_layers_agree_on_path_spelling():
    # The two layers resolve differently -- the filesystem normalizes `./x`, `git ls-files` does not -- so
    # a non-canonical spelling of a genuinely committed file could pass the append guard and then fail
    # this test FOREVER: the registry is append-only, so the offending record can never be edited out.
    # Extraction therefore canonicalizes, and both layers must accept every spelling of the same path.
    tracked = _git_tracked()
    for spelling in ("cli/registry/record.py", "./cli/registry/record.py", "cli/./registry/record.py"):
        candidates = run_ref_path_candidates(spelling)
        assert candidates == ["cli/registry/record.py"], spelling
        assert candidates[0] in tracked, spelling  # layer 2 agrees
        validate_caller_fields(_caller(run_ref=spelling))  # layer 1 agrees: no raise

    # and canonicalization must not smuggle an escape back in
    assert run_ref_path_candidates("cli/../../outside.py") == []


def test_no_record_outside_the_frozen_orphan_set_has_a_dangling_spec_hash():
    # A record's spec_hash is its provenance: edit the spec after the append and the pin silently stops
    # recomputing, with nothing in the commit gate catching it. That has happened twice -- once in Phase 5
    # (records 34-35, exempted above) and once caught in review before landing.
    records = _records()
    assert _spec_hash_orphan_ids(records, _committed_spec_hashes()) - LEGACY_SPEC_HASH_ORPHANS == set()


def test_the_spec_hash_orphan_exemption_is_not_vacuous_and_is_frozen():
    # Both directions, as for the run_ref freeze: every exempted id must genuinely dangle today (so the
    # exemption covers real breaks rather than decorating passes), and nothing outside it may dangle.
    orphans = _spec_hash_orphan_ids(_records(), _committed_spec_hashes())
    assert orphans == LEGACY_SPEC_HASH_ORPHANS
    assert len(LEGACY_SPEC_HASH_ORPHANS) == 2


def test_committed_spec_hash_lookup_is_sane():
    # Guards the predicate: an empty or bogus hash set would make every record "dangle" and every
    # exemption look non-vacuous -- a broken check passing for the wrong reason.
    hashes = _committed_spec_hashes()
    assert len(hashes) > 50
    deployable = next(r for r in _records() if r["trial_id"] == 44)
    assert deployable["spec_hash"] in hashes  # the deployable's own pin must be live, not exempted
