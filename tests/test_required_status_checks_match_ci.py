"""The required status check on `develop` must name a job that actually runs on PRs into it.

A required context GitHub never receives blocks every pull request permanently, and this repo
sets `enforce_admins: true`, so that includes the owner -- recovery means hand-editing branch
protection outside the repo. The coupling is invisible: the context string lives in
`.github/settings.yml` and the name it must match is a `name:` field in a workflow file.
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


def _check_names_reported_on_prs_into(branch: str) -> dict[str, Path]:
    """Every check-run name a PR into `branch` can produce, mapped to its workflow file.

    A job's `name:` is what GitHub reports; absent it, the job's id is. Only workflows whose
    `pull_request` trigger admits this branch can report at all -- one that does not is exactly
    the never-arrives case this guards.
    """
    names: dict[str, Path] = {}
    for path in sorted(WORKFLOWS.glob("*.yml")) + sorted(WORKFLOWS.glob("*.yaml")):
        wf = yaml.safe_load(path.read_text(encoding="utf-8"))
        # PyYAML parses the bare key `on:` as the boolean True (YAML 1.1), not the string.
        triggers = wf.get("on", wf.get(True)) or {}
        pr = triggers.get("pull_request") if isinstance(triggers, dict) else None
        if pr is None:
            continue
        targets = (pr or {}).get("branches") if isinstance(pr, dict) else None
        if targets is not None and branch not in targets:
            continue
        for job_id, job in (wf.get("jobs") or {}).items():
            names[(job or {}).get("name") or job_id] = path
    return names


def test_settings_yml_is_parseable_and_pins_develop():
    assert SETTINGS.is_file(), f"{SETTINGS} is missing -- branch protection is managed by this file"
    assert _required_contexts("develop"), "develop must require at least one status check"


@pytest.mark.parametrize("context", _required_contexts("develop"))
def test_every_required_context_is_a_job_that_runs_on_prs_into_develop(context):
    reported = _check_names_reported_on_prs_into("develop")
    assert context in reported, (
        f"required context {context!r} is not produced by any workflow that runs on pull requests "
        f"into develop. GitHub would wait for it forever and no PR could merge. "
        f"Names actually reported: {sorted(reported)}"
    )


def test_the_suite_check_is_required_so_a_red_run_cannot_merge():
    # The whole point of the branch rule: CI is the only place the full suite runs, so a green
    # merge button must mean a green suite. Named explicitly rather than inferred from the list,
    # so deleting it from settings.yml fails here rather than silently widening what can merge.
    assert "Full test suite" in _required_contexts("develop")
