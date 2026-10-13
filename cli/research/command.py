"""Provenance is never caller-supplied --
the fit reads through `ObservedReader` and the block that reader accumulated is what the record
carries, so what was fitted and what was recorded cannot drift apart."""

from __future__ import annotations

import json
import subprocess
import traceback
from pathlib import Path
from typing import Optional

import typer

from cli.data import rolling
from cli.registry import TrialRegistry
from cli.registry.errors import RegistryError
from cli.registry.observed import ObservedReader
from cli.research.subjects import EVALUATION_ERRORS, SUBJECTS, SubjectError, required_relpaths

# Repo-anchored, never cwd-relative: a dataset name must mean one directory from any working directory, and a cwd-relative
# `_REGISTRY` default would silently mint a fresh, chainless registry on a WRITE instead of appending to the real one.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_DATA_ROOT = _REPO_ROOT / "data"
_REGISTRY = _REPO_ROOT / "docs" / "reference" / "trial-registry.jsonl"

# The append-time provenance guard (`_validate_run_ref`) refuses a run_ref with no path-like token that resolves in the repo.
_RUN_REF = "cli/research/command.py — docs/specs/00086-verifiable-dataset-provenance-design.md"

_REGISTER_FIELDS = (
    ("--iteration", "iteration"),
    ("--family", "family"),
    ("--spec-hash", "spec_hash"),
    ("--verdict", "verdict"),
    ("--n-trials", "n_trials"),
)

research_app = typer.Typer(
    no_args_is_help=True,
    help="Evaluate a committed system over a frozen dataset or the rolling dataset as of a day, and register the trial "
    "it produced.",
)


def _abort(message: str) -> typer.Exit:
    """Echo a refusal on stderr and return the exit-1 error the caller raises: `raise _abort(...)`.

    Echoed rather than logged: a refusal answers the command the operator just typed and must be
    visible whatever the log configuration is."""
    typer.echo(message, err=True)
    return typer.Exit(code=1)


def _tree_state(root: Path) -> tuple[str, str]:
    def git(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)

    head = git("rev-parse", "HEAD")
    if head.returncode != 0:
        raise _abort(f"{root} is not a git checkout, and a record names its code by commit")
    # --untracked-files=all overrides a status.showUntrackedFiles that would hide an untracked file; a damaged index
    # exits 128 printing nothing, so a non-zero exit is refused and never read as a clean tree.
    status = git("status", "--porcelain", "--untracked-files=all")
    if status.returncode != 0:
        raise _abort(f"{root}: git status failed, so the tree cannot be read clean: {status.stderr.strip()}")
    return head.stdout.strip(), status.stdout


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
    register: bool = typer.Option(False, "--register", help="Append the result to the trial registry."),
    iteration: Optional[str] = typer.Option(None, "--iteration", help="Iteration label of the run (with --register)."),
    family: Optional[str] = typer.Option(None, "--family", help="Trial family this run belongs to (with --register)."),
    spec_hash: Optional[str] = typer.Option(None, "--spec-hash", help="Hash of the design this run implements (with --register)."),
    verdict: Optional[str] = typer.Option(None, "--verdict", help="One of adopt, reject, park (with --register)."),
    n_trials: Optional[int] = typer.Option(
        None,
        "--n-trials",
        help="Trials in this family INCLUDING this one; must exceed the count already recorded (with --register).",
    ),
    variant: Optional[str] = typer.Option(None, "--variant", help="Variant label within the family."),
    notes: str = typer.Option("", "--notes", help="Free-text notes stored with the record."),
    seed: Optional[list[int]] = typer.Option(None, "--seed", help="Seed used by the run; repeat for several."),
    registry: Optional[Path] = typer.Option(None, "--registry", help="Registry file to append to. Defaults to the committed one."),
) -> None:
    """Run a committed system over a frozen dataset or the rolling dataset as of a day, reporting the metrics, what
    identifies the data the run actually read -- a frozen dataset's bytes, the rolling dataset's index line for that
    day -- and what vouched for it: the dataset's own freeze record, or the index chain."""
    known = SUBJECTS.get(subject)
    if known is None:
        raise _abort(f"unknown subject {subject!r}; known subjects: {', '.join(sorted(SUBJECTS))}")

    # Caller fields are checked BEFORE the fit: a missing flag must not cost a full evaluation.
    if register:
        supplied = {"iteration": iteration, "family": family, "spec_hash": spec_hash, "verdict": verdict, "n_trials": n_trials}
        missing = [flag for flag, key in _REGISTER_FIELDS if supplied[key] is None]
        if missing:
            raise _abort(f"--register needs {', '.join(missing)}")

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
    reader = ObservedReader(_DATA_ROOT)
    try:
        metrics = known.build(reader, dataset, bounds, as_of=as_of, accept_holes=accept_holes)
        block = reader.block()
    except (RegistryError, OSError, SubjectError) as exc:
        remedy = " (--accept-holes leaves the day out)" if isinstance(exc.__cause__, rolling.HoleError) else ""
        raise _abort(f"{exc}{remedy}") from exc
    except EVALUATION_ERRORS as exc:
        # These classes are also raised on a bad config or argument: the class and the raise site tell a fault in the code
        # from a refusal of the window or the data.
        span = "the full history" if bounds is None else f"the window {bounds[0]} .. {bounds[1]}"
        read = dataset if as_of is None else f"{dataset} as of {as_of}"
        raise _abort(f"{subject} over {span} of {read}: {exc} ({type(exc).__name__} raised at {_raise_site(exc)})") from exc

    typer.echo(f"subject: {subject}")
    typer.echo(f"dataset: {dataset}")
    typer.echo("window: " + ("full history" if bounds is None else f"{bounds[0]} .. {bounds[1]}"))
    if as_of is not None:
        typer.echo(f"as of: {as_of}")
    for hole in reader.holes().get(dataset, []):
        typer.echo(f"hole: {hole}")
    typer.echo(json.dumps({"metrics": metrics, "datasets": block, "vouched": reader.vouched_status()}, indent=2))

    if not register:
        return
    try:
        record = TrialRegistry(registry or _REGISTRY).append(
            iteration=iteration,
            family=family,
            spec_hash=spec_hash,
            seeds=list(seed or []),
            metrics=metrics,
            n_trials_in_family=n_trials,
            verdict=verdict,
            run_ref=_RUN_REF,
            notes=notes,
            variant=variant,
            datasets=block,
            invocation={
                "subject": subject,
                "dataset": dataset,
                "window": None if bounds is None else list(bounds),
                "as_of": as_of,
                "accept_holes": accept_holes,
                "comparator_trial": None,
                "commit": _tree_state(_REPO_ROOT)[0],
            },
        )
    except RegistryError as exc:
        raise _abort(f"the registry refused this record: {exc}") from exc
    typer.echo(f"recorded trial {record.trial_id} in family {record.family}")
