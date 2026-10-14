"""Every record past 47 and every reading replayed at HEAD: block, metrics and verdict or outcome equal, no tolerance."""

from __future__ import annotations

import json
import math
import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from cli.__main__ import app
from cli.data.sync import _VOUCHED_SIDECAR
from cli.registry.observed import ObservedReader
from cli.research import subjects
from cli.research.subjects import SubjectError
from cli.validation import ValidationError
from tests.test_research_command import (
    _CLEAN_HEAD,
    _anchor,
    _clean_tree,  # noqa: F401 -- autouse: this import is what applies it in this module
    _git_repo,
    _ledger_default_off_the_committed_file,  # noqa: F401 -- autouse, applied here by this import as `_clean_tree` is
    _register_args,
    _registry_default_off_the_committed_ledger,  # noqa: F401 -- autouse, applied here by this import as `_clean_tree` is
    _stub_dataset,
    _stub_eval,
    _stub_subject,
    _write_series,
    runner,
)
from tests.test_trial_registry_provenance import LEDGER, REGISTRY, REPO, _outcome_finding, _readings, _trials, live_entries

pytestmark = pytest.mark.data

_CANONICAL = Path(__file__).resolve().parents[1] / "data" / "ohlc-full"
_DATA_ROOT = REPO / "data"

# The code and what configures it, then each committed file a replay's reads go through, taken from the constant naming it.
_REPLAY_READS: tuple[str, ...] = (
    "cli/",
    "tests/",
    "pyproject.toml",
    "uv.lock",
    ".python-version",
    "zcrypto.toml",
    *(path.relative_to(REPO).as_posix() for path in (REGISTRY, LEDGER, _VOUCHED_SIDECAR)),
)

_ENUMERATED = ((REGISTRY, "trial_id"), (LEDGER, "reading_id"))

# "<label>": "<commit>: <reason>", a record whose numbers moved on purpose, grown by a reviewed PR.
REPLAY_MOVED: dict[str, str] = {}


class ReplayDiffers(Exception):
    """The one exception a `REPLAY_MOVED` case's xfail absorbs: a dirty tree, an absent set or a failing assert is never a
    difference."""


_ABSENT = object()


def _shown(value) -> str:
    return "absent" if value is _ABSENT else repr(value)


def replay(entry: dict, kind: str, data_root: Path) -> list[str]:
    """What differs between the record and its subject's build at HEAD over the recorded invocation."""
    label, invocation = f"{kind}-{entry[f'{kind}_id']}", entry["invocation"]
    subject = subjects.SUBJECTS[invocation["subject"]]
    reader = ObservedReader(data_root)
    window = None if invocation["window"] is None else tuple(invocation["window"])
    try:
        metrics = subject.build(
            reader, invocation["dataset"], window, as_of=invocation["as_of"], accept_holes=invocation["accept_holes"]
        )
    except subjects.EVALUATION_ERRORS + (SubjectError,) as exc:
        return [f"{label}: {subject.name} refuses the recorded invocation at HEAD: {type(exc).__name__}: {exc}"]
    found = []
    if (block := reader.block()) != entry["datasets"]:
        found.append(f"{label}: the block read at HEAD is {block}, and the record's is {entry['datasets']}")
    commit, stored = invocation["commit"], entry["metrics"]
    for key in sorted(metrics.keys() | stored.keys()):
        at_head, recorded = metrics.get(key, _ABSENT), stored.get(key, _ABSENT)
        if at_head != recorded:
            found.append(
                f"{label}: {key} is {_shown(at_head)} at HEAD and {_shown(recorded)} in the record, made at {commit}; "
                f"`git log {commit}..HEAD -- uv.lock` lists any bump since"
            )
    if kind == "trial":
        if (ruled := subject.verdict(metrics)) != entry["verdict"]:
            found.append(
                f"{label}: {subject.name}'s rule gives the verdict {ruled!r} at HEAD, and the record stores {entry['verdict']!r}"
            )
    elif (wrong := _outcome_finding(subject, metrics, entry["outcome"])) is not None:
        found.append(f"{label}: at HEAD, {wrong}")
    return found


def _tracked_dirt(root: Path) -> str:
    status = subprocess.run(
        ["git", "-C", str(root), "status", "--porcelain", "--untracked-files=no", "--", *_REPLAY_READS],
        capture_output=True,
        text=True,
    )
    if status.returncode != 0:
        pytest.fail(f"git status failed in {root}, so the paths a replay reads cannot be read clean: {status.stderr.strip()}")
    return status.stdout


def _ids(text: str, id_key: str) -> set[int]:
    return {json.loads(line)[id_key] for line in text.splitlines() if line.strip()}


def _behind(head_text: str, develop_text: str, id_key: str) -> set[int]:
    return _ids(develop_text, id_key) - _ids(head_text, id_key)


def _git(*args: str) -> str:
    done = subprocess.run(["git", "-C", str(REPO), *args], capture_output=True, text=True)
    if done.returncode != 0:
        pytest.fail(f"git {' '.join(args)} failed in {REPO}: {done.stderr.strip()}")
    return done.stdout


def _replay_cases() -> list:
    moved = {label: pytest.mark.xfail(strict=True, raises=ReplayDiffers, reason=why) for label, why in REPLAY_MOVED.items()}
    return [pytest.param(kind, entry, id=label, marks=moved.get(label, ())) for label, kind, entry in live_entries()]


@pytest.mark.skipif(not _CANONICAL.is_dir(), reason="data/ohlc-full absent — the replay runs on the data host only")
@pytest.mark.parametrize(("kind", "entry"), _replay_cases())
def test_every_record_past_47_replays_at_head(kind, entry):
    if dirt := _tracked_dirt(REPO):
        pytest.fail(
            f"{REPO} has uncommitted changes under the paths a replay reads, so a replay would measure them and not HEAD: "
            f"{', '.join(line[3:] for line in dirt.splitlines())}. Moving that work to its own branch and a PR, this "
            "checkout back on develop, clears it: never the stash, which every session shares"
        )
    if found := replay(entry, kind, _DATA_ROOT):
        raise ReplayDiffers("\n".join(found))


@pytest.mark.skipif(not _CANONICAL.is_dir(), reason="data/ohlc-full absent — the replay runs on the data host only")
def test_this_checkout_holds_every_record_origin_develop_holds():
    _git("rev-parse", "--verify", "origin/develop")
    behind = {}
    for path, id_key in _ENUMERATED:
        relpath = path.relative_to(REPO).as_posix()
        held = _git("ls-tree", "--name-only", "origin/develop", "--", relpath)
        develop_text = _git("show", f"origin/develop:{relpath}") if held else ""
        head_text = path.read_text(encoding="utf-8") if path.exists() else ""
        if ids := _behind(head_text, develop_text, id_key):
            behind[relpath] = sorted(ids)
    if behind:
        pytest.fail(
            f"origin/develop holds ids this checkout's files lack, so no replay here reads them: {behind}; pull develop into "
            f"{REPO} (`git -C {REPO} pull --ff-only` on develop) before the replay runs again"
        )


def test_a_record_leaves_the_head_replay_only_once_the_script_replaying_it_at_its_commit_exists():
    assert not REPLAY_MOVED or (REPO / "infra" / "scripts" / "replay-at-commit.py").is_file(), (
        "REPLAY_MOVED lists a record, and infra/scripts/replay-at-commit.py, which replays it at its own commit, is absent: "
        "the PR that first lists a record carries that script"
    )
    assert set(REPLAY_MOVED) <= {label for label, _, _ in live_entries()}


def _registered(tmp_path, monkeypatch) -> tuple[dict, Path]:
    root, registry = _stub_dataset(tmp_path), tmp_path / "registry.jsonl"
    _anchor(monkeypatch, root, registry)
    _stub_subject(monkeypatch)
    result = runner.invoke(app, [*_stub_eval(), *_register_args(registry, n_trials=1)])
    assert result.exit_code == 0, result.output
    (record,) = _trials(registry).values()
    return record, root


def test_a_record_the_command_registered_replays_with_no_finding(tmp_path, monkeypatch):
    record, root = _registered(tmp_path, monkeypatch)

    assert replay(record, "trial", root) == []


def test_a_metric_one_ulp_off_is_a_finding_naming_the_key_and_the_records_commit(tmp_path, monkeypatch):
    record, root = _registered(tmp_path, monkeypatch)
    record["metrics"]["sharpe"] = math.nextafter(record["metrics"]["sharpe"], math.inf)

    found = replay(record, "trial", root)

    assert len(found) == 1 and "sharpe" in found[0] and _CLEAN_HEAD in found[0], found


def test_a_cited_file_rewritten_with_other_rows_is_a_finding_naming_the_block(tmp_path, monkeypatch):
    record, root = _registered(tmp_path, monkeypatch)
    _write_series(root, "ohlc-test", "BTC/EUR/1440.parquet", 12)

    found = replay(record, "trial", root)

    assert len(found) == 1 and "block" in found[0], found


def test_a_stored_verdict_the_rule_does_not_give_is_a_finding_naming_the_verdict(tmp_path, monkeypatch):
    record, root = _registered(tmp_path, monkeypatch)
    record["verdict"] = "reject"

    found = replay(record, "trial", root)

    assert len(found) == 1 and "verdict" in found[0] and "'reject'" in found[0], found


def _kept_as_a_reading(tmp_path, monkeypatch) -> tuple[dict, Path]:
    root, registry, ledger = _stub_dataset(tmp_path), tmp_path / "registry.jsonl", tmp_path / "ledger.jsonl"
    _anchor(monkeypatch, root, registry)
    _stub_subject(monkeypatch, verdict=lambda metrics: None, no_verdict="the stub's stop")
    result = runner.invoke(app, [*_stub_eval(), *_register_args(registry, n_trials=1, ledger=ledger)])
    assert result.exit_code == 0, result.output
    (reading,) = _readings(ledger).values()
    return reading, root


def test_a_stop_the_command_kept_as_a_reading_replays_with_no_finding(tmp_path, monkeypatch):
    reading, root = _kept_as_a_reading(tmp_path, monkeypatch)

    assert replay(reading, "reading", root) == []


def test_a_stored_outcome_other_than_the_rules_stop_is_a_finding_naming_the_outcome(tmp_path, monkeypatch):
    reading, root = _kept_as_a_reading(tmp_path, monkeypatch)
    reading["outcome"] = "another stop"

    found = replay(reading, "reading", root)

    assert len(found) == 1 and "outcome" in found[0] and "'another stop'" in found[0], found


def _build_raising(monkeypatch, error: type[BaseException]) -> None:
    def build(reader, dataset, window, as_of=None, accept_holes=False):
        raise error("the stub's cause")

    monkeypatch.setitem(subjects.SUBJECTS, "stub", replace(subjects.SUBJECTS["stub"], build=build))


@pytest.mark.parametrize("error", [SubjectError, ValidationError], ids=lambda error: error.__name__)
def test_a_build_refusing_the_invocation_at_head_is_one_finding_naming_its_class(tmp_path, monkeypatch, error):
    record, root = _registered(tmp_path, monkeypatch)
    _build_raising(monkeypatch, error)

    found = replay(record, "trial", root)

    assert len(found) == 1 and error.__name__ in found[0] and "the stub's cause" in found[0], found


@pytest.mark.parametrize("error", [FileNotFoundError, AssertionError], ids=lambda error: error.__name__)
def test_any_other_exception_of_the_build_propagates_out_of_the_replay(tmp_path, monkeypatch, error):
    record, root = _registered(tmp_path, monkeypatch)
    _build_raising(monkeypatch, error)

    with pytest.raises(error, match="the stub's cause"):
        replay(record, "trial", root)


@pytest.mark.parametrize(
    ("path", "text", "listed"),
    [
        pytest.param("cli/m.py", "changed under cli\n", " M cli/m.py\n", id="a-modified-module"),
        pytest.param("docs/research/log.md", "changed\n", "", id="a-modified-research-log"),
        pytest.param("cli/new.py", "untracked\n", "", id="an-untracked-module"),
    ],
)
def test_tracked_dirt_lists_a_tracked_change_under_the_paths_a_replay_reads_alone(tmp_path, path, text, listed):
    root = tmp_path / "repo"
    _git_repo(root, "cli/m.py", "docs/research/log.md")
    (root / path).write_text(text)

    assert _tracked_dirt(root) == listed


def test_tracked_dirt_fails_the_case_when_status_fails_never_reading_it_clean(tmp_path):
    root = tmp_path / "repo"
    _git_repo(root, "cli/m.py")
    with open(root / ".git" / "index", "r+b") as index:
        index.truncate(20)

    with pytest.raises(pytest.fail.Exception, match="git status"):
        _tracked_dirt(root)


def test_behind_is_the_ids_develops_file_holds_and_heads_lacks():
    def lines(*ids: int) -> str:
        return "".join(json.dumps({"trial_id": n}) + "\n" for n in ids)

    assert _behind(lines(1, 2), lines(1, 2, 3), "trial_id") == {3}
    assert _behind(lines(1, 2, 3), lines(1, 2), "trial_id") == set()
