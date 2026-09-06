"""Every registered trial must name provenance that is actually committed (T0125). Two layers,
deliberately split: `validate_caller_fields` runs on every append and so may not shell out -- it can
only check that a `run_ref` path exists; here, over the real registry, "committed" is checkable for
real. Git is required, not skipped-if-absent: a provenance guard that silently skips is the failure class T0125 is about."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from cli.registry.record import run_ref_path_candidates, validate_caller_fields

REPO = Path(__file__).resolve().parents[1]
REGISTRY = REPO / "docs" / "reference" / "trial-registry.jsonl"

# These trials name scratchpad scripts that were never committed and are gone. The registry is
# append-only and hash-chained, so the records can never be repaired -- and the exemption may never
# grow: a new record with an uncommitted run_ref must fail.
LEGACY_UNCOMMITTED = frozenset(range(33, 47))

# These records pin the PRE-amendment sha256 of their spec: the spec was edited after both appends,
# so no committed spec file hashes to their `spec_hash` and the pin can never be recomputed.
# Append-only, so unrepairable; same freeze discipline as above.
LEGACY_SPEC_HASH_ORPHANS = frozenset({34, 35})


def _git_tracked() -> frozenset[str]:
    """Every path git tracks, repo-relative."""
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
    """sha256 of every committed spec file: the registry carries no spec PATH, so set membership is what
    "the spec this record pins still exists unaltered" means."""
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
    # Constructive proof that the guard bites rather than merely being asserted.
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
    tracked = _git_tracked()
    for spelling in ("cli/registry/record.py", "./cli/registry/record.py", "cli/./registry/record.py"):
        candidates = run_ref_path_candidates(spelling)
        assert candidates == ["cli/registry/record.py"], spelling
        assert candidates[0] in tracked, spelling  # layer 2 agrees
        validate_caller_fields(_caller(run_ref=spelling))  # layer 1 agrees: no raise

    assert run_ref_path_candidates("cli/../../outside.py") == []


def test_no_record_outside_the_frozen_orphan_set_has_a_dangling_spec_hash():
    # A record's spec_hash is its provenance: edit the spec after the append and the pin silently stops
    # recomputing, with nothing in the commit gate catching it.
    records = _records()
    assert _spec_hash_orphan_ids(records, _committed_spec_hashes()) - LEGACY_SPEC_HASH_ORPHANS == set()


def test_the_spec_hash_orphan_exemption_is_not_vacuous_and_is_frozen():
    # Both directions, as for the run_ref freeze.
    orphans = _spec_hash_orphan_ids(_records(), _committed_spec_hashes())
    assert orphans == LEGACY_SPEC_HASH_ORPHANS
    assert len(LEGACY_SPEC_HASH_ORPHANS) == 2


def test_committed_spec_hash_lookup_is_sane():
    # Guards the predicate, as `test_git_tracked_lookup_is_sane` does for the tracked set.
    hashes = _committed_spec_hashes()
    assert len(hashes) > 50
    deployable = next(r for r in _records() if r["trial_id"] == 44)
    assert deployable["spec_hash"] in hashes  # the deployable's own pin must be live, not exempted
