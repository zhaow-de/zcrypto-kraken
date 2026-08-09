"""The `zcrypto research` Typer sub-app: evaluate a committed system over a frozen dataset and,
optionally, register the trial.

This is the registry's door (spec 00086 D3). Before it existed, `TrialRegistry.append` had no
committed caller at all -- every record was written by a scratchpad script, which is why most of
their dataset pins can no longer be resolved to anything. Here provenance is not supplied by the
caller: the fit reads through `ObservedReader`, and the block that reader accumulated is what the
record carries, so "what was fitted" and "what was recorded" cannot drift apart.

Two module constants are deliberately REPO-ANCHORED rather than cwd-relative (the `record44_legs`
pattern): `_DATA_ROOT`, so a dataset name means the same directory from any working directory, and
`_REGISTRY`, because a cwd-relative default on a registry WRITE would silently mint a fresh,
chainless registry somewhere else instead of appending to the real one.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import typer

from cli.registry import TrialRegistry
from cli.registry.errors import RegistryError
from cli.registry.observed import ObservedReader
from cli.research.subjects import SUBJECTS, required_relpaths

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DATA_ROOT = _REPO_ROOT / "data"
_REGISTRY = _REPO_ROOT / "docs" / "reference" / "trial-registry.jsonl"

# Names this file and the design it implements; the append-time provenance guard resolves the first
# token against the repo, which is the whole point of recording it.
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
    help="Evaluate a committed system over a frozen dataset, and register the trial it produced.",
)


def _abort(message: str) -> typer.Exit:
    """A clean one-line refusal on stderr + exit code 1. Usage: `raise _abort(...)`.

    Echoed rather than logged: a refusal is the answer to the command the operator just typed, and
    it must be visible whatever the log configuration is.
    """
    typer.echo(message, err=True)
    return typer.Exit(code=1)


@research_app.command("eval")
def eval_subject(
    subject: str = typer.Option(..., "--subject", help=f"System to evaluate. One of: {', '.join(SUBJECTS)}."),
    dataset: str = typer.Option(..., "--dataset", help="Frozen dataset directory name under the repo's data root."),
    window: tuple[str, str] = typer.Option(
        (None, None),
        "--window",
        help="Restrict every series to START END (ISO-8601 timestamps, inclusive). Default: full history.",
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
    """Run a committed system over a frozen dataset, reporting the metrics, the dataset bytes the run
    actually read, and whether those bytes were vouched for by the dataset's own freeze record."""
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
    absent = [rel for rel in required_relpaths(known) if not (dataset_dir / rel).is_file()]
    if absent:
        raise _abort(f"dataset {dataset!r} is missing {len(absent)} series {subject!r} requires: {', '.join(absent)}")

    bounds = None if window == (None, None) else (window[0], window[1])
    reader = ObservedReader(_DATA_ROOT)
    try:
        metrics = known.build(reader, dataset, bounds)
        block = reader.block()
    except RegistryError as exc:
        raise _abort(str(exc)) from exc

    typer.echo(f"subject: {subject}")
    typer.echo(f"dataset: {dataset}")
    typer.echo("window: " + ("full history" if bounds is None else f"{bounds[0]} .. {bounds[1]}"))
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
        )
    except RegistryError as exc:
        raise _abort(f"the registry refused this record: {exc}") from exc
    typer.echo(f"recorded trial {record.trial_id} in family {record.family}")
