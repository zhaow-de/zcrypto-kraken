"""Provenance is never caller-supplied --
the fit reads through `ObservedReader` and the block that reader accumulated is what the record
carries, so what was fitted and what was recorded cannot drift apart."""

from __future__ import annotations

import hashlib
import json
import subprocess
import traceback
from pathlib import Path
from typing import Optional

import typer

from cli.data import rolling
from cli.registry import VERDICTS, ReadingLedger, TrialRegistry, attempts, budget
from cli.registry.errors import RegistryError
from cli.registry.observed import ObservedReader
from cli.registry.record import validate_metrics
from cli.research.subjects import EVALUATION_ERRORS, LEGACY_INCUMBENTS, SUBJECTS, Subject, SubjectError, required_relpaths

# Repo-anchored, never cwd-relative: a dataset name must mean one directory from any working directory, and a cwd-relative
# `_REGISTRY` or `_LEDGER` default would silently mint a fresh, chainless file on a WRITE instead of appending to the real one.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_DATA_ROOT = _REPO_ROOT / "data"
_REGISTRY = _REPO_ROOT / "docs" / "reference" / "trial-registry.jsonl"
_LEDGER = _REPO_ROOT / "docs" / "reference" / "reading-ledger.jsonl"

# The append-time provenance guard (`_validate_run_ref`) refuses a run_ref with no path-like token that resolves in the repo.
_RUN_REF = "cli/research/command.py — docs/specs/00086-verifiable-dataset-provenance-design.md"

_REGISTER_FIELDS = (
    ("--iteration", "iteration"),
    ("--family", "family"),
    ("--n-trials", "n_trials"),
)
_READING_FIELDS = (("--iteration", "iteration"),)

_RESTORE = (
    "restore it from a backup if one exists; otherwise create a new log with zcrypto research attempts-init and add its id "
    "to docs/reference/trial-attempt-logs.txt by PR, saying what was lost"
)
_LOG_REMEDY = f"rename it aside, then {_RESTORE}"

research_app = typer.Typer(
    no_args_is_help=True,
    help="Evaluate a committed system over a frozen dataset or the rolling dataset as of a day, and register the trial "
    "it produced or keep the reading.",
)


def _abort(message: str) -> typer.Exit:
    """Echo a refusal on stderr and return the exit-1 error the caller raises: `raise _abort(...)`.

    Echoed rather than logged: a refusal answers the command the operator just typed and must be
    visible whatever the log configuration is."""
    typer.echo(message, err=True)
    return typer.Exit(code=1)


def _no_file_there(flag: str, path: Path) -> typer.Exit | None:
    if path.is_dir():
        return _abort(f"{flag} {path} is a directory: pass the path of a file in it")
    if not path.parent.is_dir():
        return _abort(f"{flag} {path}: {path.parent} is no directory: create it, or pass a path whose directory exists")
    return None


def _tree_state(root: Path) -> tuple[str, str]:
    def git(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)

    head = git("rev-parse", "HEAD")
    if head.returncode != 0:
        raise _abort(f"{root} is not a git checkout, and a record names its code by commit")
    # --untracked-files=all overrides a status.showUntrackedFiles that would hide an untracked file.
    status = git("status", "--porcelain", "--untracked-files=all")
    if status.returncode != 0:
        raise _abort(f"{root}: git status failed, so the tree cannot be read clean: {status.stderr.strip()}")
    return head.stdout.strip(), status.stdout


def _status_paths(status: str) -> str:
    return ", ".join(line[3:] for line in status.splitlines())


def _refuse_an_unbacked_comparator(registry: Path, known: Subject, comparator_trial: int) -> None:
    """Accepts the id as `_comparator_finding` in tests/test_trial_registry_provenance.py does, so a record this command
    writes passes that check."""
    try:
        trials = {record.trial_id: record for record in TrialRegistry(registry).records}
    except RegistryError as exc:
        raise _abort(f"--comparator-trial {comparator_trial}: the registry {registry} cannot be read: {exc}") from exc
    backing = trials[comparator_trial].invocation if comparator_trial in trials else None
    through_trials = backing is not None and backing["subject"] == known.incumbent
    through_legacy = LEGACY_INCUMBENTS.get(comparator_trial) == known.incumbent
    if not (through_trials or through_legacy):
        raise _abort(
            f"--comparator-trial {comparator_trial} names neither a trial in {registry} registered by {known.incumbent}, "
            f"{known.name}'s incumbent, nor a legacy record {known.incumbent} reproduces: pass the id of the {known.incumbent} "
            "trial this run compares against"
        )


def _echo_replay_case(label: str) -> None:
    typer.echo(f"replay it before each push that carries this line: uv run pytest tests/test_registry_replay.py -k '[{label}]'")
    typer.echo(
        "  it passes with nothing skipped only with data/ohlc-full linked beside the sets the line cites, since the replay "
        "skips without it"
    )


def _named(landed: attempts.Landed, subject: str) -> list[dict]:
    """The landed records `subject` registered; a legacy record carries no invocation, or a null one."""
    return [record for record in landed.records if (record.get("invocation") or {}).get("subject") == subject]


def _frozen_by(landed: attempts.Landed, subject: str) -> int | None:
    return max((record["trial_id"] for record in _named(landed, subject)), default=None)


def _short_count(subject: str, declared: int, family: str, shown: attempts.Count, this_run: str, frozen_by: int | None) -> str:
    """`shown` holds out the open attempts of this run's subject, arguments and spec_hash whose process is gone when the
    remedy asks for a raise, since the raised run absorbs each, and nothing when it asks for a new subject; after the print
    it classifies this run as any other attempt."""
    records = sum(1 for record in shown.records if record["family"] == family)
    orphans = [orphan for orphan in shown.orphans if orphan.family == family]
    head = (
        f"{subject} declares n_trials {declared}, and family {family} needs at least {shown.required_n(family)}: "
        f"{records} records, {this_run}, and {len(orphans)} attempts that never landed"
    )
    if frozen_by is not None:
        tail = f"{subject}'s n_trials is frozen by its trial {frozen_by}: declare a new subject (a new name) for the further trial"
    else:
        tail = f"raise {subject}'s n_trials, which its deflated Sharpe uses, commit, then run again"
    listed = [", ".join(orphan.describe() for orphan in orphans)] if orphans else []
    return " — ".join([head, *listed, tail])


def _over_budget(bucket: str, count: attempts.Count) -> str:
    records = sum(1 for record in count.records if count.bucket_of.get(record["family"]) == bucket)
    orphans = sum(1 for orphan in count.orphans if count.bucket_of.get(orphan.family) == bucket)
    return (
        f"bucket {bucket} has spent {count.spent(bucket)} of its {budget.BUDGET[bucket]} trials ({records} records, {orphans} "
        "attempts that never landed), so this trial would exceed it: an expansion is the owner's ruling, written into "
        "cli/registry/budget.py by a pull request that quotes it"
    )


def _end_failed(log, attempt: int | None, failed: str) -> None:
    """Ends the run's attempt, when it began one, before an exit that prints no number. An error the log raises here ends
    the command in a traceback over the exit's own, the attempt left open for a retry of the same arguments to absorb."""
    if attempt is not None:
        log.end(attempt, failed=failed)


def _keep_reading(ledger: Path, **reading) -> None:
    """A subject with no rule, or a rule that stops: a reading, its outcome the stop's text or none."""
    try:
        kept = ReadingLedger(ledger).append(**reading)
    except RegistryError as exc:
        raise _abort(f"the ledger refused this reading: {exc}") from exc
    if kept.outcome is None:
        typer.echo(f"recorded reading {kept.reading_id}")
    else:
        typer.echo(f"no verdict — {kept.outcome}: recorded reading {kept.reading_id}; no trial spent")
    _echo_replay_case(f"reading-{kept.reading_id}")


def _raise_site(exc: BaseException) -> str:
    frame = traceback.extract_tb(exc.__traceback__)[-1]
    path = Path(frame.filename)
    return f"{path.relative_to(_REPO_ROOT) if path.is_relative_to(_REPO_ROOT) else path}:{frame.lineno}"


@research_app.command("eval")
def eval_subject(
    subject: str = typer.Option(..., "--subject", help=f"System to evaluate. One of: {', '.join(SUBJECTS)}."),
    dataset: str = typer.Option(
        ...,
        "--dataset",
        help=f"Dataset directory name under the repo's data root: a frozen dataset, or the rolling one, {rolling.ROLLING_SET}, "
        "read with --as-of.",
    ),
    window: tuple[str, str] = typer.Option(
        (None, None),
        "--window",
        help="Restrict every series to START END (ISO-8601 timestamps, inclusive). Default: full history.",
    ),
    as_of: Optional[str] = typer.Option(
        None,
        "--as-of",
        help="Read the rolling dataset as of this UTC day, YYYY-MM-DD: required for it, refused for a frozen dataset.",
    ),
    accept_holes: bool = typer.Option(
        False,
        "--accept-holes",
        help="Read the rolling dataset across a day it records as a hole, leaving that day out and printing it; "
        "without it such a read is refused. Refused for a frozen dataset.",
    ),
    register: bool = typer.Option(
        False,
        "--register",
        help="Append the result to the trial registry as a trial whose verdict is the subject's rule and whose seeds are its "
        "declared ones; a rule that gives no verdict keeps the run as a reading instead, spending no trial. The run's first "
        "line goes to the clone's trial-attempts log before the fit and its last before the print, so a run whose branch "
        "never merges still counts. Refused for a subject with no rule, from a tree with uncommitted changes, and for an "
        "absent, unlisted or damaged log; a subject with a rule is refused a run without it.",
    ),
    reading: bool = typer.Option(
        False,
        "--reading",
        help="Append the result to the readings ledger: a run of a subject with no rule, kept without spending a trial. "
        "Refused with --register, for a subject with a rule, and from a tree with uncommitted changes.",
    ),
    iteration: Optional[str] = typer.Option(None, "--iteration", help="Iteration label of the run (with --register or --reading)."),
    family: Optional[str] = typer.Option(
        None,
        "--family",
        help="Trial family this run belongs to (with --register): the family the subject declares, which must be in a bucket "
        "of cli/registry/budget.py.",
    ),
    spec_hash: Optional[str] = typer.Option(
        None,
        "--spec-hash",
        help="The sha256 of the subject's spec, asserted: refused unless it equals the one computed (with --register or "
        "--reading).",
    ),
    verdict: Optional[str] = typer.Option(
        None,
        "--verdict",
        help="The verdict asserted: refused unless it equals the subject's rule's (with --register; refused with --reading).",
    ),
    comparator_trial: Optional[int] = typer.Option(
        None,
        "--comparator-trial",
        help="The trial of the subject's incumbent this run compares against: required for a subject that declares one, "
        "refused for any other (with --register or --reading).",
    ),
    n_trials: Optional[int] = typer.Option(
        None,
        "--n-trials",
        help="Trials in this family INCLUDING this one (with --register): the count the subject declares, which must cover "
        "the family's records, this run and its attempts that never landed; frozen once a record of the subject has landed, "
        "when a further trial declares a new subject.",
    ),
    variant: Optional[str] = typer.Option(None, "--variant", help="Variant label within the family."),
    notes: str = typer.Option("", "--notes", help="Free-text notes stored with the record."),
    registry: Optional[Path] = typer.Option(
        None,
        "--registry",
        help="Registry file to append to. Defaults to the committed one. A run with a rule writes its attempt to the clone's "
        "trial-attempts log whatever this names, so a run whose record lands in another file counts as an attempt that never "
        "landed until a later run into the committed registry, with the same subject, arguments and spec file, returns its "
        "numbers and verdict and absorbs it.",
    ),
    ledger: Optional[Path] = typer.Option(
        None,
        "--ledger",
        help="Readings ledger to append to, by --reading or by a --register run whose rule gives no verdict. Defaults to "
        "the committed one.",
    ),
) -> None:
    """Run a committed system over a frozen dataset or the rolling dataset as of a day, reporting the metrics, what
    identifies the data the run actually read -- a frozen dataset's bytes, the rolling dataset's index line for that
    day -- and what vouched for it: the dataset's own freeze record, or the index chain."""
    known = SUBJECTS.get(subject)
    if known is None:
        raise _abort(f"unknown subject {subject!r}; known subjects: {', '.join(sorted(SUBJECTS))}")
    if known.verdict is not None and not (register or reading):
        raise _abort(
            f"{subject} declares a verdict rule, so every run of it is a trial: run it with --register; a ruleless pre-flight "
            "subject reads the inputs without the trial's result"
        )

    # Every refusal that needs no data comes before any read: a refusal must not cost a full evaluation.
    target = registry or _REGISTRY
    ledger_target = ledger or _LEDGER
    records = register or reading
    log = None
    if records:
        if register and reading:
            raise _abort("--register and --reading are exclusive: a subject with a rule registers, one without keeps a reading")
        if register and known.verdict is None:
            raise _abort(f"{subject} declares no verdict rule, so it registers no trial: keep the run with --reading instead")
        if reading and known.verdict is not None:
            raise _abort(
                f"{subject} declares a verdict rule, so its run is a trial, or a reading its rule's stop keeps: run it with "
                "--register instead"
            )
        if reading and verdict is not None:
            raise _abort(f"--verdict {verdict} asserts a trial's verdict, and a reading stores none: drop --verdict")
        if verdict is not None and verdict not in VERDICTS:
            raise _abort(
                f"--verdict {verdict} is none of {', '.join(sorted(VERDICTS))}: pass one, or drop --verdict to take the rule's"
            )
        if known.incumbent is not None and comparator_trial is None:
            raise _abort(
                f"{subject} compares against its incumbent, {known.incumbent}: pass --comparator-trial N, the id of the "
                f"{known.incumbent} trial this run compares against"
            )
        if known.incumbent is None and comparator_trial is not None:
            raise _abort(f"{subject} declares no incumbent, so it compares against no trial: drop --comparator-trial")
        supplied = {"iteration": iteration, "family": family, "n_trials": n_trials}
        missing = [flag for flag, key in (_REGISTER_FIELDS if register else _READING_FIELDS) if supplied[key] is None]
        if missing:
            raise _abort(f"{'--register' if register else '--reading'} needs {', '.join(missing)}")
        if register:
            if family != known.family:
                raise _abort(
                    f"--family {family} is not {known.family}, the family {subject} declares: pass --family {known.family}"
                )
            if n_trials != known.n_trials:
                raise _abort(
                    f"--n-trials {n_trials} is not {known.n_trials}, the count {subject} declares and deflates at: pass "
                    f"--n-trials {known.n_trials}"
                )
            if family not in budget.BUCKET_OF:
                raise _abort(
                    f"family {family} is in no bucket of cli/registry/budget.py: add it with its bucket in a reviewed pull request"
                )
        if refused := _no_file_there("--ledger", ledger_target) or _no_file_there("--registry", target):
            raise refused
        before = _tree_state(_REPO_ROOT)
        if before[1]:
            raise _abort(
                f"{_REPO_ROOT} has uncommitted changes, and a record names its code by commit: commit or remove "
                f"{_status_paths(before[1])}, then run again"
            )
        if comparator_trial is not None:
            _refuse_an_unbacked_comparator(target, known, comparator_trial)
        computed_spec_hash = hashlib.sha256((_REPO_ROOT / known.spec).read_bytes()).hexdigest()
        if spec_hash is not None and spec_hash != computed_spec_hash:
            raise _abort(
                f"--spec-hash {spec_hash} is not {computed_spec_hash}, the sha256 of {known.spec}, the spec {subject} "
                "declares, at this commit: read what changed in the spec since that hash, then run again without "
                "--spec-hash or with the spec's own"
            )
    if register:
        # Read after the clean-tree refusal: `attempts.landed` reads the target through the store, which heals a torn tail
        # that refusal leaves byte-identical.
        try:
            log_file = attempts.log_path(_REPO_ROOT)
        except attempts.AttemptLogError as exc:
            raise _abort(str(exc)) from exc
        if not log_file.exists():
            raise _abort(f"no trial-attempts log at {log_file}: {_RESTORE}")
        try:
            log = attempts.AttemptLog(log_file)
        except attempts.AttemptLogError as exc:
            raise _abort(f"{exc}: {_LOG_REMEDY}") from exc
        except OSError as exc:
            raise _abort(f"the trial-attempts log {log_file} refused the run's first line: {exc}; nothing ran") from exc
        # Before the allowlist: an unresolvable origin/develop reads as an empty one, whose refusal names the wrong remedy.
        try:
            landed = attempts.landed(_REPO_ROOT, target, ledger_target)
        except RegistryError as exc:
            raise _abort(str(exc)) from exc
        if log.log_id not in attempts.allowed_log_ids(_REPO_ROOT):
            raise _abort(
                f"the trial-attempts log {log.path} has id {log.log_id}, which docs/reference/trial-attempt-logs.txt on "
                "origin/develop does not list: restore the listed log from a backup if one exists; otherwise add this id to "
                "docs/reference/trial-attempt-logs.txt by PR, saying what was lost, and run again once it has merged and "
                "origin/develop is fetched"
            )
        lacked = attempts.lacking(log.lines, landed, log.log_id)
        if lacked:
            carrier, lost = lacked[0]
            raise _abort(
                f"{log.path} lacks attempt {lost}, which {carrier} carries: the log was truncated, replaced, restored from an "
                f"older backup or forked; {_LOG_REMEDY}"
            )
        moved = [record for record in _named(landed, subject) if record["n_trials_in_family"] != known.n_trials]
        if moved:
            last = max(moved, key=lambda record: record["trial_id"])
            raise _abort(
                f"{subject} declares n_trials {known.n_trials}, and its trial {last['trial_id']} landed at n_trials "
                f"{last['n_trials_in_family']}, which that record's deflated Sharpe used, so its n_trials is frozen: declare "
                "a new subject (a new name) for the further trial"
            )

    dataset_dir = _DATA_ROOT / dataset
    if not dataset_dir.is_dir():
        raise _abort(f"dataset {dataset!r} is absent: no directory {dataset_dir}; zcrypto data fetch mirrors the hub's datasets")
    chained = rolling.is_chained(dataset_dir)
    if chained and as_of is None:
        raise _abort(f"dataset {dataset!r} is read as of a day: pass --as-of YYYY-MM-DD")
    if not chained and (as_of is not None or accept_holes):
        raise _abort(f"dataset {dataset!r} is frozen: --as-of and --accept-holes read the rolling dataset alone")
    if chained:
        try:
            held = rolling.pairs(dataset_dir)
        except (rolling.RollingError, OSError) as exc:
            raise _abort(f"dataset {dataset!r}: {exc}") from exc
        absent = [pair for pair in (f"{a}/EUR" for a in known.assets) if pair not in held]
    else:
        absent = [rel for rel in required_relpaths(known) if not (dataset_dir / rel).is_file()]
    if absent:
        raise _abort(f"dataset {dataset!r} is missing {len(absent)} series {subject!r} requires: {', '.join(absent)}")

    bounds = None if window == (None, None) else (window[0], window[1])
    attempt = own = None
    if records:
        invocation = {
            "subject": subject,
            "dataset": dataset,
            "window": None if bounds is None else list(bounds),
            "as_of": as_of,
            "accept_holes": accept_holes,
            "comparator_trial": comparator_trial,
            "commit": before[0],
        }
    if register:
        hold = (subject, attempts.arguments(invocation), computed_spec_hash)
        bucket = budget.BUCKET_OF[family]

        def admit(lines: tuple[dict, ...]) -> None:
            try:
                seen = attempts.landed(_REPO_ROOT, target, ledger_target)
            except RegistryError as exc:
                raise _abort(str(exc)) from exc
            count = attempts.reconcile(lines, seen, log_id=log.log_id, bucket_of=budget.BUCKET_OF, hold=hold)
            if known.n_trials < count.required_n(family):
                frozen_by = _frozen_by(seen, subject)
                shown = attempts.reconcile(
                    lines,
                    seen,
                    log_id=log.log_id,
                    bucket_of=budget.BUCKET_OF,
                    hold=None if frozen_by is not None else hold,
                    hold_finished=False,
                )
                raise _abort(_short_count(subject, known.n_trials, family, shown, "this run", frozen_by))
            if bucket is not None:
                strict = attempts.reconcile(
                    lines, seen, log_id=log.log_id, bucket_of=budget.BUCKET_OF, hold=hold, hold_finished=False
                )
                if strict.spent(bucket) + 1 > budget.BUDGET[bucket]:
                    raise _abort(_over_budget(bucket, strict))

        try:
            attempt = log.begin(
                admit,
                invocation=invocation,
                spec_hash=computed_spec_hash,
                family=family,
                bucket=bucket,
                n_trials=n_trials,
                worktree=_REPO_ROOT,
                branch=attempts.current_branch(_REPO_ROOT),
                registry=target,
                ledger=ledger_target,
            )
        except (OSError, RegistryError) as exc:
            raise _abort(f"the trial-attempts log {log.path} refused the run's first line: {exc}; nothing ran") from exc

    reader = ObservedReader(_DATA_ROOT)
    try:
        metrics = known.build(reader, dataset, bounds, as_of=as_of, accept_holes=accept_holes)
        block = reader.block()
    except (RegistryError, OSError, SubjectError) as exc:
        _end_failed(log, attempt, f"{type(exc).__name__}: {exc}")
        remedy = " (--accept-holes leaves the day out)" if isinstance(exc.__cause__, rolling.HoleError) else ""
        raise _abort(f"{exc}{remedy}") from exc
    except EVALUATION_ERRORS as exc:
        _end_failed(log, attempt, f"{type(exc).__name__}: {exc}")
        # These classes are also raised on a bad config or argument: the class and the raise site tell a fault in the code
        # from a refusal of the window or the data.
        span = "the full history" if bounds is None else f"the window {bounds[0]} .. {bounds[1]}"
        read = dataset if as_of is None else f"{dataset} as of {as_of}"
        raise _abort(f"{subject} over {span} of {read}: {exc} ({type(exc).__name__} raised at {_raise_site(exc)})") from exc

    report = {"metrics": metrics, "datasets": block, "vouched": reader.vouched_status()}
    ruled = None
    if records:
        keys = set(metrics)
        if keys != known.metric_keys:
            refusal = (
                f"{subject}'s build returned keys other than the ones it declares: missing "
                f"{sorted(known.metric_keys - keys)}, unknown {sorted(keys - known.metric_keys)}; make the build and its "
                "declared metric keys agree, commit, then run again"
            )
            _end_failed(log, attempt, f"SubjectError: {refusal}")
            raise _abort(refusal)
        # The rule the store applies after the print, applied before the end line: an end holding a leaf the store refuses
        # would stand in the log as a look no record can carry.
        try:
            validate_metrics(metrics, "metrics")
        except RegistryError as exc:
            _end_failed(log, attempt, f"RegistryError: {exc}")
            raise _abort(f"{subject}'s build returned metrics the registry refuses: {exc}") from exc
        if known.verdict is not None:
            ruled = known.verdict(metrics)
            report["verdict"] = ruled
    if attempt is not None:
        try:
            log.end(attempt, verdict=ruled, stop=known.no_verdict if ruled is None else None, metrics=metrics)
        except (OSError, RegistryError) as exc:
            raise _abort(
                f"the trial-attempts log {log.path} refused the run's last line: {exc}; the numbers are withheld and the "
                "attempt stays open: run again with the same arguments, which absorbs it"
            ) from exc
        own = {"log": log.log_id, "id": attempt, "begin": attempts.begin_hash(log.lines, attempt)}

    typer.echo(f"subject: {subject}")
    typer.echo(f"dataset: {dataset}")
    typer.echo("window: " + ("full history" if bounds is None else f"{bounds[0]} .. {bounds[1]}"))
    if as_of is not None:
        typer.echo(f"as of: {as_of}")
    for hole in reader.holes().get(dataset, []):
        typer.echo(f"hole: {hole}")
    typer.echo(json.dumps(report, indent=2))

    if not records:
        return
    after = _tree_state(_REPO_ROOT)
    if after != before:
        raise _abort(
            f"{_REPO_ROOT} changed during the fit (HEAD {before[0]}, then {after[0]}; uncommitted after it: "
            f"{_status_paths(after[1]) or 'none'}), so no commit names the code that ran: run again once nothing else "
            "writes to the checkout"
        )
    if verdict is not None and verdict != ruled:
        raise _abort(
            f"--verdict {verdict} disagrees with {subject}'s rule, which gives {ruled or 'no verdict'} on these metrics, so "
            "nothing is recorded: drop --verdict to take the rule's"
        )
    reading_fields = {
        "iteration": iteration,
        "spec_hash": computed_spec_hash,
        "invocation": invocation,
        "datasets": block,
        "metrics": metrics,
        "outcome": known.no_verdict,
        "notes": notes,
    }
    if log is None:
        _keep_reading(ledger_target, **reading_fields, attempt=None)
        return
    # One critical section from the count to the append: what another session began, ended or landed during the fit is
    # counted, and nothing lands between the two. After the end, a held attempt is classified as any other.
    with log.locked() as lines:
        try:
            settled = attempts.landed(_REPO_ROOT, target, ledger_target)
        except RegistryError as exc:
            raise _abort(str(exc)) from exc
        count = attempts.reconcile(lines, settled, log_id=log.log_id, bucket_of=budget.BUCKET_OF, own=attempt)
        if known.n_trials < count.required_n(family):
            frozen_by = _frozen_by(settled, subject)
            shown = attempts.reconcile(
                lines,
                settled,
                log_id=log.log_id,
                bucket_of=budget.BUCKET_OF,
                hold=None if frozen_by is not None else hold,
                hold_finished=False,
            )
            raise _abort(_short_count(subject, known.n_trials, family, shown, "the next run", frozen_by))
        if bucket is not None and count.spent(bucket) + 1 > budget.BUDGET[bucket]:
            raise _abort(_over_budget(bucket, count))
        if ruled is None:
            _keep_reading(ledger_target, **reading_fields, attempt={**own, "absorbs": list(count.absorbs)})
            return
        try:
            record = TrialRegistry(target).append(
                iteration=iteration,
                family=family,
                spec_hash=computed_spec_hash,
                seeds=list(known.seeds),
                metrics=metrics,
                n_trials_in_family=n_trials,
                verdict=ruled,
                run_ref=_RUN_REF,
                notes=notes,
                variant=variant,
                datasets=block,
                invocation=invocation,
                attempt={**own, "absorbs": list(count.absorbs), "counted": count.counted(family)},
            )
        except RegistryError as exc:
            raise _abort(f"the registry refused this record: {exc}") from exc
    typer.echo(f"recorded trial {record.trial_id} in family {record.family}")
    _echo_replay_case(f"trial-{record.trial_id}")


@research_app.command("attempts-init")
def attempts_init() -> None:
    """Create this clone's trial-attempts log, once, and print the row its id takes in the committed allowlist."""
    try:
        path = attempts.log_path(_REPO_ROOT)
        attempts.init_log(path)
        log = attempts.AttemptLog(path)
    except attempts.AttemptLogError as exc:
        raise _abort(str(exc)) from exc
    typer.echo(f"created {path}; add this row to docs/reference/trial-attempt-logs.txt by PR:")
    typer.echo(f"{log.log_id} {log.host}")
