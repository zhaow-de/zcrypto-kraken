"""The required status check on `develop` must name a job that actually runs on PRs into it.

A required context GitHub never receives blocks every pull request permanently, and this repo
sets `enforce_admins: true`, so that includes the owner -- recovery means hand-editing branch
protection outside the repo.
"""

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
SETTINGS = ROOT / ".github" / "settings.yml"
WORKFLOWS = ROOT / ".github" / "workflows"


def _required_contexts(branch: str) -> list[str]:
    data = yaml.safe_load(SETTINGS.read_text(encoding="utf-8"))
    for entry in data["branches"]:
        if entry["name"] == branch:
            checks = entry["protection"]["required_status_checks"]
            return [] if checks is None else list(checks["contexts"])
    raise AssertionError(f"no protection block for branch {branch!r} in {SETTINGS}")


def _conditional_trigger_reason(pr: object, branch: str) -> str | None:
    """Why a `pull_request` trigger might NOT fire for some PR into `branch`, or None if it always does.

    A required context has to arrive for EVERY pull request, so any filter that can skip a run is
    disqualifying -- not merely a branch mismatch. A `paths` filter added to save CI minutes would
    leave a doc-only PR with no check at all, BLOCKED with nothing red to explain why.
    """
    if not isinstance(pr, dict):
        return None  # bare `pull_request:` -- no filters, fires for everything
    if (targets := pr.get("branches")) is not None and branch not in targets:
        return f"its `branches` is {targets!r}, which excludes {branch!r}"
    if (excluded := pr.get("branches-ignore")) is not None and branch in excluded:
        return f"its `branches-ignore` {excluded!r} excludes {branch!r}"
    for key in ("paths", "paths-ignore"):
        if pr.get(key) is not None:
            return f"it has a `{key}` filter {pr[key]!r}, so a PR touching none of those files gets no run"
    if (types := pr.get("types")) is not None and not {"opened", "synchronize"} <= set(types):
        return f"its `types` is {types!r}, which does not cover both `opened` and `synchronize`"
    return None


def _job_disqualifier(job: dict) -> str | None:
    """Why a job's reported check-run name may not be exactly its `name:`, or None if it is."""
    if job.get("strategy") is not None:
        return "it has a `strategy:`, so GitHub appends the matrix values to the reported name"
    if job.get("uses") is not None:
        return "it delegates with `uses:`, so GitHub reports it as `caller / callee`"
    if job.get("if") is not None:
        return "it has a job-level `if:`, so it can report `skipped` -- which satisfies a required check without running"
    return None


def _check_names_reported_on_prs_into(branch: str) -> tuple[dict[str, Path], list[str]]:
    """Check-run names that ALWAYS report for a PR into `branch`, plus why any workflow was excluded.

    A job's `name:` is what GitHub reports; absent it, the job's id is.
    """
    names: dict[str, Path] = {}
    skipped: list[str] = []
    for path in sorted(WORKFLOWS.glob("*.yml")) + sorted(WORKFLOWS.glob("*.yaml")):
        wf = yaml.safe_load(path.read_text(encoding="utf-8"))
        # PyYAML parses the bare key `on:` as the boolean True (YAML 1.1), not the string.
        triggers = wf.get("on", wf.get(True)) or {}
        # `on: [push, pull_request]` and `on: pull_request` are equally valid; both carry no
        # filters, so they always fire. Normalising here keeps them out of the silent middle
        # ground of appearing in neither the reported names nor the skipped-with-a-reason list.
        if isinstance(triggers, str):
            triggers = {triggers: None}
        elif isinstance(triggers, list):
            triggers = dict.fromkeys(triggers)
        if not isinstance(triggers, dict) or "pull_request" not in triggers:
            continue
        if (reason := _conditional_trigger_reason(triggers["pull_request"], branch)) is not None:
            skipped.append(f"{path.name}: {reason}")
            continue
        for job_id, job in (wf.get("jobs") or {}).items():
            job = job or {}
            if (reason := _job_disqualifier(job)) is not None:
                skipped.append(f"{path.name} job {job_id!r}: {reason}")
                continue
            names[job.get("name") or job_id] = path
    return names, skipped


def test_settings_yml_is_parseable_and_pins_develop():
    assert SETTINGS.is_file(), f"{SETTINGS} is missing -- branch protection is managed by this file"
    assert _required_contexts("develop"), "develop must require at least one status check"


@pytest.mark.parametrize("context", _required_contexts("develop"))
def test_every_required_context_is_a_job_that_runs_on_prs_into_develop(context):
    reported, skipped = _check_names_reported_on_prs_into("develop")
    assert context in reported, (
        f"required context {context!r} is not UNCONDITIONALLY produced by a workflow running on "
        f"pull requests into develop, so some PR would wait for it forever and could never merge "
        f"(enforce_admins is true -- the owner could not override). "
        f"Names always reported: {sorted(reported)}. "
        f"Workflows excluded because their trigger is conditional: {skipped or 'none'}"
    )


def test_the_suite_check_is_required_so_a_red_run_cannot_merge():
    # The whole point of the branch rule: CI is the only place the full suite runs, so a green
    # merge button must mean a green suite. Named explicitly rather than inferred from the list,
    # so deleting it from settings.yml fails here rather than silently widening what can merge.
    assert "Full test suite" in _required_contexts("develop")
