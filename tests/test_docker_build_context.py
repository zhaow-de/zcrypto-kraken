"""Every `COPY` source in the Dockerfile must survive `.dockerignore`.

This exists because the image build is NOT gated at PR time: `capture-image.yml` triggers on
`push` to develop/main, while `coverage.yml` runs on pull requests. So a Dockerfile or
`.dockerignore` change passes every PR check and breaks `develop` after the merge -- which is
exactly what happened on 2026-08-24, when a `COPY docs/reference/vouched-dataset-hashes.jsonl`
landed against a `.dockerignore` that excludes `docs/`.

This test costs no image build, so it runs in the ordinary suite and catches the class at PR time.
"""

import re
from fnmatch import fnmatch
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = ROOT / "infra" / "docker" / "Dockerfile"
DOCKERIGNORE = ROOT / ".dockerignore"


def _ignore_patterns():
    """(pattern, is_exception) in file order. Docker applies LAST match wins."""
    out = []
    for raw in DOCKERIGNORE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        negated = line.startswith("!")
        out.append((line.lstrip("!").rstrip("/"), negated))
    return out


def _excluded(relpath: str) -> bool:
    """Docker's rule: the LAST pattern matching a path decides, and a directory pattern covers
    everything beneath it."""
    verdict = False
    for pattern, negated in _ignore_patterns():
        if fnmatch(relpath, pattern) or relpath.startswith(pattern + "/") or fnmatch(relpath, pattern + "/*"):
            verdict = not negated
    return verdict


def _copy_sources():
    """Local COPY sources only. `COPY --from=<image>` reads another image, not the context."""
    sources = []
    for line in DOCKERFILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line.upper().startswith("COPY ") or "--from=" in line:
            continue
        parts = re.split(r"\s+", line)[1:]
        sources.extend(p for p in parts[:-1] if not p.startswith("--"))
    return sources


def test_the_dockerfile_has_copy_sources_to_check():
    # A parser that silently matches nothing would make every assertion below vacuous.
    assert len(_copy_sources()) >= 3


def test_every_copy_source_exists_in_the_repo():
    missing = [s for s in _copy_sources() if not (ROOT / s.rstrip("/")).exists()]
    assert not missing, f"Dockerfile COPYs paths that do not exist: {missing}"


def test_no_copy_source_is_excluded_by_dockerignore():
    # The failure mode this names: the build fails with "not found" for a file that is plainly
    # present in the repo, because the context never carried it.
    excluded = [s for s in _copy_sources() if _excluded(s.rstrip("/"))]
    assert not excluded, (
        f"Dockerfile COPYs {excluded}, which .dockerignore excludes from the build context — "
        f"the image build will fail with 'not found' even though the path exists in the repo"
    )


def test_the_exclusion_check_actually_detects_an_excluded_path():
    # True positive for the guard above: `docs/` is excluded, so a path under it that carries no
    # exception must read as excluded. Without this, an always-False checker would pass silently.
    assert _excluded("docs/research/00.master-plan.md")
    assert not _excluded("docs/reference/vouched-dataset-hashes.jsonl"), "the re-include must win"
    assert not _excluded("cli/data/sync.py")
