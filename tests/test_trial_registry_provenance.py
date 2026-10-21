"""Every registered trial must name provenance that is actually committed (T0125). Two layers,
deliberately split: `validate_caller_fields` runs on every append and so may not shell out -- it can
only check that a `run_ref` path exists; here, over the real registry, "committed" is checkable for
real. Git is required, not skipped-if-absent: a provenance guard that silently skips is the failure class T0125 is about."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from collections.abc import Callable, Mapping
from dataclasses import asdict, replace
from pathlib import Path

import pytest

from cli.registry import ReadingLedger, TrialRegistry, budget
from cli.registry.attempts import parse_allowlist
from cli.registry.budget import BUCKET_OF, BUDGET
from cli.registry.record import run_ref_path_candidates, validate_caller_fields
from cli.research.subjects import LEGACY_INCUMBENTS, SUBJECTS, Subject

REPO = Path(__file__).resolve().parents[1]
REGISTRY = REPO / "docs" / "reference" / "trial-registry.jsonl"
LEDGER = REPO / "docs" / "reference" / "reading-ledger.jsonl"
ALLOWLIST_FILE = REPO / "docs" / "reference" / "trial-attempt-logs.txt"

# These trials name scratchpad scripts that were never committed and are gone. The registry is
# append-only and hash-chained, so the records can never be repaired -- and the exemption may never
# grow: a new record with an uncommitted run_ref must fail.
LEGACY_UNCOMMITTED = frozenset(range(33, 47))

# These records pin the PRE-amendment sha256 of their spec: the spec was edited after both appends,
# so no committed spec file hashes to their `spec_hash` and the pin can never be recomputed.
# Append-only, so unrepairable; same freeze discipline as above.
LEGACY_SPEC_HASH_ORPHANS = frozenset({34, 35})

# Every subject a committed record's invocation names, at the n_trials its records deflated at.
LANDED_N_TRIALS: dict[str, int] = {
    "b1-hourly-rv": 3,
    "b1-volume-confirmation": 4,
    "b1-hourly-channel-exits": 5,
    "b2-funding-derisk-full": 1,
    "b2-oi-derisk": 2,
    "b2-ratio-derisk": 3,
    "b2-liq-derisk": 4,
}


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


def _ref(log: str, attempt_id: int) -> str:
    return f"{log[:8]}#{attempt_id}"


def _attempt_findings(
    trials: dict[int, dict],
    readings: dict[int, dict],
    *,
    subjects: dict,
    bucket_of: Mapping[str, str | None],
    budget: Mapping[str, int],
    allowlist: frozenset[str],
) -> list[str]:
    """Checks (vii)-(xii) of docs/specs/00133-t0222-trial-attempts-design.md over the records past 48 and the readings past
    1, the store's attempt floors, the records from trial 1 counting in (ix) and (x). An entry past the floors naming a
    subject `subjects` lacks yields nothing here, since `_findings` refuses it."""
    records = [(f"trial-{n}", n, entry) for n, entry in sorted(trials.items())]
    ledger = [(f"reading-{n}", n, entry) for n, entry in sorted(readings.items())]
    subject_of = {label: subjects.get((entry.get("invocation") or {}).get("subject")) for label, _, entry in records + ledger}
    skipped = {label for label, n, _ in records if n > 48 and subject_of[label] is None}
    skipped |= {label for label, n, _ in ledger if n > 1 and subject_of[label] is None}
    held = [(label, n, entry) for label, n, entry in records if n > 48 and label not in skipped]
    held_readings = [(label, n, entry) for label, n, entry in ledger if n > 1 and label not in skipped]
    found: list[str] = []

    def finding(label: str, check: str, text: str) -> None:
        if label not in skipped:
            found.append(f"{label} ({check}): {text}")

    lands: dict[tuple[str, int], list[tuple[str, str, dict]]] = {}
    for label, _, entry in records + ledger:
        if (attempt := entry.get("attempt")) is not None:
            for reference in (attempt, *attempt.get("absorbs", ())):
                lands.setdefault((attempt["log"], reference["id"]), []).append((label, reference["begin"], entry))
    listings: dict[tuple[str, int], list[tuple[str, dict]]] = {}
    for label, _, entry in records:
        for listed in (entry.get("attempt") or {}).get("counted", ()):
            listings.setdefault((listed["log"], listed["id"]), []).append((label, listed))

    for label, trial_id, entry in held:
        subject, family, n_trials = subject_of[label], entry["family"], entry["n_trials_in_family"]
        counted = (entry.get("attempt") or {}).get("counted", ())
        if family != subject.family:
            finding(label, "vii", f"its family {family} is not {subject.family}, the family {subject.name} declares")
        if n_trials != subject.n_trials:
            finding(
                label,
                "viii",
                f"its n_trials_in_family {n_trials} is not {subject.n_trials}, the count {subject.name} declares and its "
                "verdict deflates at",
            )
        before = sum(earlier["family"] == family for earlier_id, earlier in trials.items() if earlier_id < trial_id)
        listed_in_family = sum(listed["family"] == family for listed in counted)
        if n_trials < before + listed_in_family + 1:
            finding(
                label,
                "ix",
                f"its n_trials_in_family {n_trials} is below the {before + listed_in_family + 1} family {family} needs: "
                f"{before} records of it before this one, {listed_in_family} counted entries of it, and this one",
            )
        bucket = bucket_of.get(family)
        carried = {(listed["log"], listed["id"]): listed["begin"] for listed in counted}
        dropped: dict[tuple[str, int, str], str] = {}
        for earlier_label, earlier_id, earlier in records:
            in_scope = (bucket_of.get(earlier["family"]) == bucket) if bucket is not None else (earlier["family"] == family)
            if earlier_id >= trial_id or not in_scope:
                continue
            for listed in (earlier.get("attempt") or {}).get("counted", ()):
                pair = (listed["log"], listed["id"])
                if pair not in lands and carried.get(pair) != listed["begin"]:
                    dropped.setdefault((*pair, listed["begin"]), earlier_label)
        scope = f"bucket {bucket}" if bucket is not None else f"family {family}"
        for (log, attempt_id, begin), earlier_label in dropped.items():
            finding(
                label,
                "xii",
                f"its counted drops {_ref(log, attempt_id)} with begin {begin}, which {earlier_label}'s counted lists and no "
                f"record or reading lands: each record of {scope} carries every orphan an earlier one listed",
            )

    for label, _, entry in held + held_readings:
        if (attempt := entry.get("attempt")) is None:
            continue
        if attempt["log"] not in allowlist:
            finding(label, "xi", f"its attempt's log {attempt['log']} is not a row of docs/reference/trial-attempt-logs.txt")
        for listed in attempt.get("counted", ()):
            if listed["log"] not in allowlist:
                finding(
                    label,
                    "xi",
                    f"its counted entry {_ref(listed['log'], listed['id'])} names the log {listed['log']}, which is not a row "
                    "of docs/reference/trial-attempt-logs.txt",
                )
    for pair, carriers in lands.items():
        if len(carriers) > 1:
            for label, _, _ in carriers[1:]:
                finding(
                    label,
                    "xi",
                    f"carries attempt {_ref(*pair)}, which {carriers[0][0]} already carries: an attempt lands once, as one "
                    "record's or reading's attempt or absorbs entry",
                )
    for label, _, entry in held_readings:
        subject, attempt = subject_of[label], entry.get("attempt")
        if attempt is None and subject.verdict is not None:
            finding(
                label,
                "xi",
                f"carries no attempt, but {subject.name} declares a rule, so the reading is a stop and carries its run's attempt",
            )
        if attempt is not None and subject.verdict is None:
            finding(
                label,
                "xi",
                f"carries an attempt, but {subject.name} declares no rule, so its reading is no attempt and carries none",
            )
    for pair, listers in listings.items():
        landers = lands.get(pair, [])
        by_reading = next((label for label, _, _ in landers if label.startswith("reading-")), None)
        by_record = next(((label, begin, entry) for label, begin, entry in landers if label.startswith("trial-")), None)
        if by_reading is not None:
            finding(
                by_reading,
                "xi",
                f"lands attempt {_ref(*pair)}, which {listers[0][0]}'s counted lists, and a reading holds a stop, never the "
                "verdict a listed orphan stored",
            )
        elif by_record is not None:
            label, begin, entry = by_record
            for lister, listed in listers:
                landing = {
                    "begin": begin,
                    "subject": (entry.get("invocation") or {}).get("subject"),
                    "spec_hash": entry["spec_hash"],
                    "verdict": entry["verdict"],
                    "metrics": entry["metrics"],
                }
                if differs := sorted(key for key, value in landing.items() if value != listed[key]):
                    finding(
                        label,
                        "xi",
                        f"lands attempt {_ref(*pair)}, which {lister}'s counted lists, but its {', '.join(differs)} differ "
                        "from that entry's: a listed attempt lands only as itself, the same run landing late or a run "
                        "absorbing it on equal numbers, never as an id a restored or forked log minted again",
                    )
                    break

    for name, allowed in budget.items():
        members = [entry for _, _, entry in records if bucket_of.get(entry["family"]) == name]
        listed_pairs = [
            (listed["log"], listed["id"]) for entry in members for listed in (entry.get("attempt") or {}).get("counted", ())
        ]
        unlanded = {pair for pair in listed_pairs if pair not in lands}
        if len(members) + len(unlanded) > allowed:
            finding(
                f"bucket-{name}",
                "x",
                f"bucket {name} spends {len(members) + len(unlanded)} of its {allowed} trials: {len(members)} records and "
                f"{len(unlanded)} listed attempts no record or reading lands; an expansion is the owner's ruling, written "
                "into cli/registry/budget.py by a pull request that quotes it",
            )
    unbucketed: dict[str, str] = {}
    for label, _, entry in records:
        if label not in skipped and entry["family"] not in bucket_of:
            unbucketed.setdefault(entry["family"], label)
    for family, label in unbucketed.items():
        finding(
            label,
            "x",
            f"its family {family} is no key of BUCKET_OF in cli/registry/budget.py, so no budget counts it: add it with its "
            "bucket in a reviewed pull request",
        )
    return found


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
            attempt={"log": "e" * 32, "id": n, "begin": f"{n:064x}", "absorbs": [], "counted": []},
        )
    return path


def test_live_entries_holds_exactly_the_records_past_47(tmp_path):
    registry = _forty_eight_trials(tmp_path / "trials.jsonl")

    entries = live_entries(registry, tmp_path / "readings.jsonl")

    assert [(label, kind, entry["trial_id"]) for label, kind, entry in entries] == [("trial-48", "trial", 48)]


def test_live_entries_holds_every_reading_beside_the_records_past_47(tmp_path):
    registry, ledger = _forty_eight_trials(tmp_path / "trials.jsonl"), tmp_path / "readings.jsonl"
    ReadingLedger(ledger).append(
        iteration="iter-001",
        spec_hash="s",
        invocation=_INVOCATION,
        datasets=_DATASETS,
        metrics={"sharpe": 0.3},
        outcome=None,
        attempt=None,
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


def test_the_budgets_and_buckets_are_the_master_plans_literals():
    growth = (
        "an expansion is the owner's ruling and a new family joins with its bucket: each lands in a pull request that "
        "changes this literal and quotes the ruling"
    )
    assert budget.BUDGET == {"A": 40, "B": 25, "C": 10}, growth
    assert budget.BUCKET_OF == {"A1": "A", "B1": "B", "B2": "B", "P1": None}, growth
    assert {bucket for bucket in budget.BUCKET_OF.values() if bucket is not None} <= set(budget.BUDGET), growth


def test_the_allowlist_rows_are_ids_and_hosts_each_id_once():
    assert parse_allowlist(ALLOWLIST_FILE.read_text(encoding="utf-8")), (
        "the allowlist lists every trial-attempts log ever created, one row each, and no row is ever removed"
    )


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


_L = "f" * 32
_FOLLOW = "b2-follow"
_B1_FOLLOW = "b1-follow"
# Frozen, so a raise a correct PR makes in cli/research/subjects.py never moves a row; the live test reads SUBJECTS.
_TABLE_SUBJECTS = {
    _B2: replace(SUBJECTS[_B2], family="B2", n_trials=1),
    _ARM_A_BAR: replace(SUBJECTS[_ARM_A_BAR], verdict=None, family=None, n_trials=None),
}
_WITH_FOLLOWER = {
    **_TABLE_SUBJECTS,
    _FOLLOW: replace(_TABLE_SUBJECTS[_B2], name=_FOLLOW, n_trials=2),
    _B1_FOLLOW: replace(SUBJECTS["b1-hourly-rv"], name=_B1_FOLLOW, family="B1", n_trials=4),
}


def _begin_hash(attempt_id: int) -> str:
    return f"{attempt_id:064x}"


def _trial6(trial_id: int, *, family="B2", n=1, subject=_B2, attempt_id=1, absorbs=(), counted=(), begin=None) -> dict:
    return {
        **_b2_trial(trial_id, subject),
        "schema_version": 6,
        "family": family,
        "n_trials_in_family": n,
        "attempt": {
            "log": _L,
            "id": attempt_id,
            "begin": begin or _begin_hash(attempt_id),
            "absorbs": [{"id": a, "begin": _begin_hash(a)} for a in absorbs],
            "counted": list(counted),
        },
    }


# By default the begin, verdict and numbers a clean b2 trial records, so a record landing the attempt late matches its entry.
def _listed(attempt_id: int, family: str = "B2", log: str = _L, *, subject: str = _B2, metrics: dict | None = None) -> dict:
    return {
        "log": log,
        "id": attempt_id,
        "begin": _begin_hash(attempt_id),
        "family": family,
        "subject": subject,
        "spec_hash": _spec_sha256(_B2_SPEC),
        "verdict": "reject",
        "metrics": _b2_trial(attempt_id)["metrics"] if metrics is None else metrics,
    }


def _reading2(reading_id: int, subject: str, attempt: dict | None) -> dict:
    return {"reading_id": reading_id, "schema_version": 2, "invocation": {"subject": subject}, "attempt": attempt}


def _reading_attempt(attempt_id: int) -> dict:
    return {"log": _L, "id": attempt_id, "begin": _begin_hash(attempt_id), "absorbs": []}


# Append-only, so a row's figures stay fixed as entries land past the floors, which the live test holds.
def _floor_world() -> tuple[dict[int, dict], dict[int, dict]]:
    trials, readings = _trials(), _readings()
    return {n: trials[n] for n in trials if n <= 48}, {n: readings[n] for n in readings if n <= 1}


def _count_check(
    trials=(), readings=(), *, subjects=_TABLE_SUBJECTS, bucket_of=BUCKET_OF, budget=BUDGET, allowlist=frozenset({_L})
) -> list[str]:
    committed_trials, committed_readings = _floor_world()
    committed_trials.update({trial["trial_id"]: trial for trial in trials})
    committed_readings.update({reading["reading_id"]: reading for reading in readings})
    return _attempt_findings(
        committed_trials, committed_readings, subjects=subjects, bucket_of=bucket_of, budget=budget, allowlist=allowlist
    )


def test_every_record_past_48_holds_to_its_count_family_budget_log_and_carry_forward():
    allowlist = frozenset(parse_allowlist(ALLOWLIST_FILE.read_text(encoding="utf-8")))
    assert (
        _attempt_findings(_trials(), _readings(), subjects=SUBJECTS, bucket_of=BUCKET_OF, budget=BUDGET, allowlist=allowlist) == []
    )


def test_a_clean_schema_6_trial_yields_no_finding():
    assert _count_check([_trial6(49)]) == []


def test_a_raise_of_a_live_subjects_n_trials_leaves_the_clean_row_clean(monkeypatch):
    monkeypatch.setitem(SUBJECTS, _B2, replace(SUBJECTS[_B2], n_trials=2))

    assert _count_check([_trial6(49)]) == []


def test_an_entry_landing_past_the_floors_leaves_the_clean_row_clean(monkeypatch):
    log = next(iter(parse_allowlist(ALLOWLIST_FILE.read_text(encoding="utf-8"))))
    trials, readings = _trials(), _readings()
    landed = _trial6(50, attempt_id=2)
    landed["attempt"]["log"] = log
    stop = _reading2(2, _B2, {**_reading_attempt(3), "log": log})
    module = sys.modules[__name__]
    monkeypatch.setattr(module, "_trials", lambda: {**trials, 50: landed})
    monkeypatch.setattr(module, "_readings", lambda: {**readings, 2: stop})

    assert _count_check([_trial6(49)]) == []


@pytest.mark.parametrize(
    ("trials", "readings", "over", "finding"),
    [
        pytest.param(
            [_trial6(49)],
            [],
            {"subjects": {**_TABLE_SUBJECTS, _B2: replace(_TABLE_SUBJECTS[_B2], family="B1")}},
            "trial-49 (vii):",
            id="family-off-the-subject",
        ),
        pytest.param([_trial6(49, n=2)], [], {}, "trial-49 (viii):", id="n-off-the-subject"),
        pytest.param([_trial6(49, counted=[_listed(5)])], [], {}, "trial-49 (ix):", id="below-the-count"),
        pytest.param([_trial6(49), _trial6(50, attempt_id=2)], [], {}, "trial-50 (ix):", id="a-second-record-of-the-family"),
        pytest.param([_trial6(49)], [], {"budget": {"A": 40, "B": 3, "C": 10}}, "(x):", id="over-the-budget"),
        pytest.param(
            [_trial6(49)], [], {"bucket_of": {k: v for k, v in BUCKET_OF.items() if k != "B2"}}, "(x):", id="a-family-in-no-bucket"
        ),
        pytest.param([_trial6(49)], [], {"allowlist": frozenset()}, "trial-49 (xi):", id="a-log-off-the-allowlist"),
        pytest.param(
            [_trial6(49, counted=[_listed(5, "B1", "e" * 32)])], [], {}, "trial-49 (xi):", id="a-counted-log-off-the-allowlist"
        ),
        pytest.param(
            [_trial6(49, attempt_id=2, absorbs=[1])],
            [_reading2(2, _B2, _reading_attempt(1))],
            {},
            "(xi):",
            id="an-attempt-landed-twice",
        ),
        pytest.param([_trial6(49)], [_reading2(2, _B2, None)], {}, "reading-2 (xi):", id="a-ruled-reading-without-its-attempt"),
        pytest.param(
            [_trial6(49)],
            [_reading2(2, "b2-arm-a-bar", _reading_attempt(3))],
            {},
            "reading-2 (xi):",
            id="a-ruleless-reading-with-an-attempt",
        ),
        pytest.param(
            [_trial6(49, counted=[_listed(5, "B1")]), _trial6(50, subject=_FOLLOW, n=2, attempt_id=2)],
            [],
            {"subjects": _WITH_FOLLOWER},
            "trial-50 (xii):",
            id="a-listed-orphan-dropped",
        ),
        pytest.param(
            [_trial6(49, family="B1", n=4, subject=_B1_FOLLOW, counted=[_listed(5)]), _trial6(50, attempt_id=2)],
            [],
            {"subjects": _WITH_FOLLOWER},
            "trial-50 (xii):",
            id="a-bucket-mates-orphan-dropped",
        ),
        pytest.param(
            [_trial6(49, counted=[_listed(5, "B1")]), _trial6(50, subject=_FOLLOW, n=2, attempt_id=2, counted=[_listed(5, "B1")])],
            [],
            {"subjects": _WITH_FOLLOWER},
            None,
            id="a-listed-orphan-carried",
        ),
        pytest.param(
            [
                _trial6(49, counted=[_listed(5, "B1", subject=_FOLLOW)]),
                _trial6(50, subject=_FOLLOW, n=2, attempt_id=6, absorbs=[5]),
            ],
            [],
            {"subjects": _WITH_FOLLOWER},
            None,
            id="a-listed-orphan-landed-since",
        ),
        pytest.param(
            [_trial6(49, counted=[_listed(5, "B1")]), _trial6(50, subject=_FOLLOW, n=2, attempt_id=2, counted=[_listed(5, "B1")])],
            [],
            {"subjects": _WITH_FOLLOWER, "budget": {"A": 40, "B": 6, "C": 10}},
            None,
            id="an-orphan-two-records-list-spends-once",
        ),
        pytest.param(
            [
                _trial6(49, counted=[_listed(5, "B1", subject=_FOLLOW)]),
                _trial6(50, subject=_FOLLOW, n=2, attempt_id=6, absorbs=[5]),
            ],
            [],
            {"subjects": _WITH_FOLLOWER, "budget": {"A": 40, "B": 5, "C": 10}},
            None,
            id="a-landed-orphan-spends-nothing-more",
        ),
        pytest.param(
            [
                _trial6(49, counted=[_listed(5, "B1", subject=_FOLLOW, metrics={"sharpe": 0.1})]),
                _trial6(50, subject=_FOLLOW, n=2, attempt_id=5),
            ],
            [],
            {"subjects": _WITH_FOLLOWER},
            "trial-50 (xi):",
            id="a-listed-id-landed-with-other-numbers",
        ),
        pytest.param(
            [
                _trial6(49, counted=[_listed(5, "B1", subject=_FOLLOW)]),
                _trial6(50, subject=_FOLLOW, n=2, attempt_id=5, begin="e" * 64),
            ],
            [],
            {"subjects": _WITH_FOLLOWER},
            "trial-50 (xi):",
            id="a-listed-id-landed-under-another-begin",
        ),
        pytest.param(
            [_trial6(49, counted=[_listed(5, "B1")]), _trial6(50, subject=_FOLLOW, n=2, attempt_id=2)],
            [_reading2(2, _B2, _reading_attempt(5))],
            {"subjects": _WITH_FOLLOWER},
            "reading-2 (xi):",
            id="a-reading-landing-a-listed-orphan",
        ),
        pytest.param(
            [
                _trial6(49, counted=[_listed(5, "B1")]),
                _trial6(50, subject=_FOLLOW, n=2, attempt_id=2, counted=[{**_listed(5, "B1"), "begin": "e" * 64}]),
            ],
            [],
            {"subjects": _WITH_FOLLOWER},
            "trial-50 (xii):",
            id="a-listed-orphan-swapped-for-another-begin",
        ),
    ],
)
def test_one_change_to_a_clean_schema_6_trial_yields_exactly_its_finding(trials, readings, over, finding):
    found = _count_check(trials, readings, **over)

    if finding is None:
        assert found == []
    else:
        assert len(found) == 1 and finding in found[0], found


def test_each_landed_subjects_n_trials_is_frozen_at_its_literal():
    growth = (
        "a subject's n_trials is frozen once a record of it lands: a further trial declares a new subject, and a subject's "
        "first landed record adds its row here in the PR that lands it"
    )
    landed: dict[str, set[int]] = {}
    for entry in _trials().values():
        if entry["invocation"] is not None:
            landed.setdefault(entry["invocation"]["subject"], set()).add(entry["n_trials_in_family"])
    assert LANDED_N_TRIALS == {
        "b1-hourly-rv": 3,
        "b1-volume-confirmation": 4,
        "b1-hourly-channel-exits": 5,
        "b2-funding-derisk-full": 1,
        "b2-oi-derisk": 2,
        "b2-ratio-derisk": 3,
        "b2-liq-derisk": 4,
    }, growth
    assert landed == {subject: {n} for subject, n in LANDED_N_TRIALS.items()}, growth
    assert all(SUBJECTS[subject].n_trials == n for subject, n in LANDED_N_TRIALS.items()), growth
