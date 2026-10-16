"""Every registered trial must name provenance that is actually committed (T0125). Two layers,
deliberately split: `validate_caller_fields` runs on every append and so may not shell out -- it can
only check that a `run_ref` path exists; here, over the real registry, "committed" is checkable for
real. Git is required, not skipped-if-absent: a provenance guard that silently skips is the failure class T0125 is about."""

from __future__ import annotations

import hashlib
import json
import subprocess
from collections.abc import Callable
from dataclasses import asdict, replace
from pathlib import Path

import pytest

from cli.registry import ReadingLedger, TrialRegistry
from cli.registry.record import run_ref_path_candidates, validate_caller_fields
from cli.research.subjects import LEGACY_INCUMBENTS, SUBJECTS, Subject

REPO = Path(__file__).resolve().parents[1]
REGISTRY = REPO / "docs" / "reference" / "trial-registry.jsonl"
LEDGER = REPO / "docs" / "reference" / "reading-ledger.jsonl"

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
    record_44 = next(r for r in _records() if r["trial_id"] == 44)
    assert record_44["spec_hash"] in hashes  # 44 is outside LEGACY_SPEC_HASH_ORPHANS, so its pin must resolve here


def _is_ancestor(commit: str) -> bool:
    return (
        subprocess.run(["git", "-C", str(REPO), "merge-base", "--is-ancestor", commit, "HEAD"], capture_output=True).returncode == 0
    )


def _spec_sha256(path: str) -> str:
    return hashlib.sha256((REPO / path).read_bytes()).hexdigest()


def _trials(registry: Path = REGISTRY) -> dict[int, dict]:
    return {record.trial_id: asdict(record) for record in TrialRegistry(registry).records}


def _readings(ledger: Path = LEDGER) -> dict[int, dict]:
    return {record.reading_id: asdict(record) for record in ReadingLedger(ledger).records}


def live_entries(registry: Path = REGISTRY, ledger: Path = LEDGER) -> list[tuple[str, str, dict]]:
    """The one enumeration of what CI holds to its subject and of what the replay parametrises over: a new kind of entry
    joins here, never in a second list."""
    trials = [(f"trial-{trial_id}", "trial", entry) for trial_id, entry in _trials(registry).items() if trial_id > 47]
    readings = [(f"reading-{reading_id}", "reading", entry) for reading_id, entry in _readings(ledger).items()]
    return trials + readings


def _comparator_finding(invocation: dict, subject: Subject, legacy: dict, trials: dict[int, dict]) -> str | None:
    comparator, incumbent = invocation["comparator_trial"], subject.incumbent
    if incumbent is None:
        if comparator is None:
            return None
        return f"comparator_trial {comparator}, but {subject.name} declares no incumbent, so it compares against no trial"
    if comparator is None:
        return f"no comparator_trial, but {subject.name} declares the incumbent {incumbent}, whose trial it must name"
    backing = trials.get(comparator, {}).get("invocation")
    through_trials = backing is not None and backing["subject"] == incumbent
    through_legacy = legacy.get(comparator) == incumbent
    if through_trials or through_legacy:
        return None
    return (
        f"comparator_trial {comparator} names neither a record whose invocation names {incumbent}, {subject.name}'s "
        "incumbent, nor a LEGACY_INCUMBENTS entry mapping to it"
    )


def _outcome_finding(subject: Subject, metrics: dict, outcome: str | None) -> str | None:
    if subject.verdict is None:
        if outcome is None:
            return None
        return f"its outcome is {outcome!r}, and {subject.name} declares no rule, so a reading of it carries none"
    if outcome != subject.no_verdict:
        return f"its outcome is {outcome!r}, and a reading of {subject.name} carries its stop, {subject.no_verdict!r}"
    if (ruled := subject.verdict(metrics)) is not None:
        return f"{subject.name}'s rule gives the verdict {ruled!r} on its metrics, so the run is a trial and never a reading"
    return None


def _findings(
    entry: dict,
    kind: str,
    *,
    subjects: dict,
    legacy: dict,
    trials: dict[int, dict],
    is_ancestor: Callable[[str], bool],
    spec_sha256: Callable[[str], str],
) -> list[str]:
    name = f"{kind}-{entry[f'{kind}_id']}"
    invocation = entry["invocation"]
    subject = subjects.get(invocation["subject"])
    if subject is None:
        return [
            f"{name}: names the subject {invocation['subject']!r}, which SUBJECTS does not hold; a subject a record names is "
            "never deleted or renamed"
        ]
    found = []
    keys = set(entry["metrics"])
    if keys != subject.metric_keys:
        found.append(
            f"{name}: its metric keys are not {subject.name}'s: missing {sorted(subject.metric_keys - keys)}, "
            f"unknown {sorted(keys - subject.metric_keys)}"
        )
    if not is_ancestor(invocation["commit"]):
        found.append(
            f"{name}: its commit {invocation['commit']} is not an ancestor of HEAD; if its PR was squash- or rebase-merged, "
            "open a PR into develop that merges that PR's head with `-s ours` (`git fetch origin refs/pull/<N>/head`, then "
            "`git merge -s ours FETCH_HEAD`), which makes the commit an ancestor and changes no file"
        )
    if entry["spec_hash"] != spec_sha256(subject.spec):
        found.append(f"{name}: its spec_hash is not the sha256 of {subject.spec}, the spec {subject.name} declares")
    if kind == "trial":
        if subject.verdict is None:
            found.append(
                f"{name}: names {subject.name}, which declares no verdict rule, and an evaluate-only subject registers no trial"
            )
        elif entry["verdict"] != (ruled := subject.verdict(entry["metrics"])):
            found.append(
                f"{name}: its verdict {entry['verdict']!r} is not {ruled!r}, what {subject.name}'s rule gives on its metrics"
            )
    elif (wrong := _outcome_finding(subject, entry["metrics"], entry["outcome"])) is not None:
        found.append(f"{name}: {wrong}")
    if (wrong := _comparator_finding(invocation, subject, legacy, trials)) is not None:
        found.append(f"{name}: {wrong}")
    return found


def test_every_record_past_47_holds_to_the_subject_it_names():
    trials = _trials()
    found = [
        finding
        for _, kind, entry in live_entries()
        for finding in _findings(
            entry,
            kind,
            subjects=SUBJECTS,
            legacy=LEGACY_INCUMBENTS,
            trials=trials,
            is_ancestor=_is_ancestor,
            spec_sha256=_spec_sha256,
        )
    ]
    assert found == []


_DATASETS = {
    "ohlc-test": {
        "files": {"BTC/EUR/1440.parquet": "c" * 64},
        "rows": 10,
        "span": ["2020-01-01 00:00:00+00:00", "2020-01-10 00:00:00+00:00"],
    }
}
_INVOCATION = {
    "subject": "stub",
    "dataset": "ohlc-test",
    "window": None,
    "as_of": None,
    "accept_holes": False,
    "comparator_trial": None,
    "commit": "a" * 40,
}


def _forty_eight_trials(path: Path) -> Path:
    for n in range(1, 49):
        TrialRegistry(path).append(
            iteration="iter-001",
            family="A1",
            spec_hash="s",
            datasets=_DATASETS,
            invocation=_INVOCATION,
            seeds=[0],
            metrics={"sharpe": 0.3},
            n_trials_in_family=n,
            verdict="reject",
            run_ref="cli/registry/record.py",
        )
    return path


def test_live_entries_holds_exactly_the_records_past_47(tmp_path):
    registry = _forty_eight_trials(tmp_path / "trials.jsonl")

    entries = live_entries(registry, tmp_path / "readings.jsonl")

    assert [(label, kind, entry["trial_id"]) for label, kind, entry in entries] == [("trial-48", "trial", 48)]


def test_live_entries_holds_every_reading_beside_the_records_past_47(tmp_path):
    registry, ledger = _forty_eight_trials(tmp_path / "trials.jsonl"), tmp_path / "readings.jsonl"
    ReadingLedger(ledger).append(
        iteration="iter-001", spec_hash="s", invocation=_INVOCATION, datasets=_DATASETS, metrics={"sharpe": 0.3}, outcome=None
    )

    assert {label for label, _, _ in live_entries(registry, ledger)} == {"trial-48", "reading-1"}


def test_the_legacy_incumbents_are_frozen_each_backed_by_a_subject_and_a_record_at_or_below_47():
    growth = (
        "LEGACY_INCUMBENTS grows only as a legacy id joins with its subject and a data-gated test proving that subject "
        "reproduces the record, in one PR that also changes this literal"
    )
    assert LEGACY_INCUMBENTS == {
        33: "record33-combined",
        44: "record44-crossfreq",
        45: "b1-conditioning",
        46: "b1-window-only",
        47: "record44-crossfreq",
    }, growth
    assert set(LEGACY_INCUMBENTS.values()) <= set(SUBJECTS), growth
    committed = {record["trial_id"] for record in _records()}
    assert all(trial_id <= 47 and trial_id in committed for trial_id in LEGACY_INCUMBENTS), growth


_B2 = "b2-funding-derisk"
_B2_SPEC = "docs/specs/00128-b2-family-opening-design.md"
_COMBINED_SPEC = "docs/specs/00035-combination-trial-design.md"
_STUB = "b2-against-record44"
_WITH_INCUMBENT = {**SUBJECTS, _STUB: replace(SUBJECTS[_B2], name=_STUB, incumbent="record44-crossfreq")}


def _head() -> str:
    return subprocess.run(["git", "-C", str(REPO), "rev-parse", "HEAD"], capture_output=True, check=True, text=True).stdout.strip()


def _b2_trial(trial_id: int, subject: str = _B2) -> dict:
    metrics = dict.fromkeys(SUBJECTS[_B2].metric_keys, 0.0) | {"passes": 0, "arm_a_passes": 1, "engaged_per_year": {"2021": 3}}
    return {
        "trial_id": trial_id,
        "schema_version": 5,
        "spec_hash": _spec_sha256(_B2_SPEC),
        "invocation": {
            "subject": subject,
            "dataset": "ohlc-rolling",
            "window": None,
            "as_of": "2026-10-10",
            "accept_holes": True,
            "comparator_trial": None,
            "commit": _head(),
        },
        "metrics": metrics,
        "verdict": "reject",
    }


def _check(entry: dict, *, kind: str = "trial", subjects: dict = SUBJECTS, trials: dict[int, dict] | None = None) -> list[str]:
    return _findings(
        entry,
        kind,
        subjects=subjects,
        legacy=LEGACY_INCUMBENTS,
        trials=_trials() if trials is None else trials,
        is_ancestor=_is_ancestor,
        spec_sha256=_spec_sha256,
    )


def test_a_clean_b2_trial_yields_no_finding():
    assert _check(_b2_trial(49)) == []


def _as_record33(entry: dict) -> None:
    entry["invocation"]["subject"] = "record33-combined"
    entry["metrics"] = dict.fromkeys(SUBJECTS["record33-combined"].metric_keys, 0.0)
    entry["spec_hash"] = _spec_sha256(_COMBINED_SPEC)


def _against(comparator: int | None) -> Callable[[dict], None]:
    return lambda entry: entry["invocation"].update(subject=_STUB, comparator_trial=comparator)


@pytest.mark.parametrize(
    ("change", "subjects", "trial_48_subject", "finding"),
    [
        pytest.param(
            lambda e: e["invocation"].update(subject="no-such-subject"),
            SUBJECTS,
            None,
            "SUBJECTS does not hold",
            id="unknown-subject",
        ),
        pytest.param(lambda e: e["metrics"].update(not_a_b2_key=0.0), SUBJECTS, None, "unknown ['not_a_b2_key']", id="a-key-added"),
        pytest.param(lambda e: e["metrics"].pop("turnover_a"), SUBJECTS, None, "missing ['turnover_a']", id="a-key-removed"),
        pytest.param(
            lambda e: e["invocation"].update(commit="f" * 40), SUBJECTS, None, "not an ancestor of HEAD", id="commit-off-head"
        ),
        pytest.param(
            lambda e: e.update(spec_hash=_spec_sha256(_COMBINED_SPEC)),
            SUBJECTS,
            None,
            "is not the sha256 of",
            id="another-specs-hash",
        ),
        pytest.param(lambda e: e.update(verdict="adopt"), SUBJECTS, None, "rule gives", id="verdict-off-the-rule"),
        pytest.param(_as_record33, SUBJECTS, None, "declares no verdict rule", id="a-trial-of-a-ruleless-subject"),
        pytest.param(_against(None), _WITH_INCUMBENT, None, "no comparator_trial", id="incumbent-without-comparator"),
        pytest.param(
            lambda e: e["invocation"].update(comparator_trial=44),
            SUBJECTS,
            None,
            "declares no incumbent",
            id="comparator-without-incumbent",
        ),
        pytest.param(_against(44), _WITH_INCUMBENT, None, None, id="44-accepted-through-the-map"),
        pytest.param(_against(48), _WITH_INCUMBENT, "record44-crossfreq", None, id="accepted-through-the-trials"),
        pytest.param(_against(33), _WITH_INCUMBENT, None, "names neither", id="33-mapped-to-another-subject"),
        pytest.param(_against(43), _WITH_INCUMBENT, None, "names neither", id="43-in-no-map-and-no-invocation"),
        pytest.param(_against(48), _WITH_INCUMBENT, _B2, "names neither", id="a-trial-of-another-subject"),
    ],
)
def test_one_change_to_a_clean_trial_yields_exactly_its_finding(change, subjects, trial_48_subject, finding):
    entry, trials = _b2_trial(49), _trials()
    if trial_48_subject is not None:
        trials[48] = _b2_trial(48, trial_48_subject)
    change(entry)

    found = _check(entry, subjects=subjects, trials=trials)

    if finding is None:
        assert found == []
    else:
        assert len(found) == 1 and finding in found[0], found


_ARM_A_BAR = "b2-arm-a-bar"
_ARM_A_BAR_METRICS = dict.fromkeys(SUBJECTS[_ARM_A_BAR].metric_keys, 0)
# `_b2_trial`'s metrics, on which the rule gives `reject`, with arm A failing its bar, on which it stops.
_B2_STOPPED = {"arm_a_passes": 0}


@pytest.mark.parametrize(
    ("subject", "change", "outcome", "finding"),
    [
        pytest.param(_ARM_A_BAR, None, None, None, id="a-ruleless-subjects-clean-reading"),
        pytest.param(_B2, _B2_STOPPED, "no_verdict", None, id="a-ruled-subjects-clean-stop"),
        pytest.param(_ARM_A_BAR, None, "a stop", "declares no rule", id="a-ruleless-subjects-reading-with-an-outcome"),
        pytest.param(
            _B2, {}, "no_verdict", "gives the verdict 'reject'", id="a-ruled-subjects-reading-its-rule-gives-a-verdict-on"
        ),
    ],
)
def test_a_reading_carries_the_outcome_its_subjects_rule_gives_and_no_other(subject, change, outcome, finding):
    trial = _b2_trial(49, subject)
    metrics = _ARM_A_BAR_METRICS if change is None else trial["metrics"] | change
    stop = SUBJECTS[subject].no_verdict if outcome == "no_verdict" else outcome
    entry = {
        "reading_id": 1,
        "spec_hash": trial["spec_hash"],
        "invocation": trial["invocation"],
        "metrics": metrics,
        "outcome": stop,
    }

    found = _check(entry, kind="reading")

    if finding is None:
        assert found == []
    else:
        assert len(found) == 1 and found[0].startswith("reading-1: ") and finding in found[0], found
