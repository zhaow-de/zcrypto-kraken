"""The recovered trial-43/44 runners must never change (T0148).

These files were recovered from a Claude session transcript's `Write`/`Edit` records. **That
transcript no longer exists** — the tooling's 30-day retention pruned it four minutes after it was
read, and 27 minutes before the commit that preserved these bytes. There is no other copy anywhere:
this git history is it, and the recovery can never be re-run.

That makes them strictly more fragile than `infra/nas/rrsync`, which has the same
"byte-identical or worthless" property and is guarded by `tests/test_vendored_rrsync_integrity.py`.
Both `ruff.toml` and `.pre-commit-config.yaml` exempt this directory so no hook can reformat them —
which also means no hook would *notice* a stray edit or a bad merge. This test is the tripwire that
closes that gap.

The five ORIGINALS are pinned hard: they are provenance, and any change is corruption. The two
recovery VARIANTS are pinned too, because the README documents their exact one- and two-hunk diffs
and a silent change would falsify that record — but if a future reader deliberately extends a
variant (e.g. to take T0148's maker-taker measurement), updating its hash here is the intended way
to say so out loud.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

RUNNERS = Path(__file__).resolve().parents[1] / "docs/reference/trial43-recovered-runners"

# sha256 of each file as recovered/derived on 2026-08-21.
EXPECTED = {
    "crossfreq_run.py": "5a1b1eb085ce09709baba98d07d0c12b1ebe73e1e7e9acea704ffaa41af2eeed",
    "crossfreq_run_nocache.py": "32b33a3dee7126db0b7d2cbf4d09da9b620bc9b36e6c91e4b76d001632ca6759",
    "crossfreq_run_rederived.py": "c8c2dfe1dbb67011f0465cc8b4f0a3c2d6448fc6471247f7e4dd3502ae8ed4a8",
    "crossfreq_stage2.py": "a23a22442c471caf9e9a0208dd507f6789613e60b8e760a1247df5661e2e7100",
    "stage1b_verify.py": "ec254492f51fe260e3f3a881e31a9f8334dcc2a698aa95b3694040edaa6478f6",
    "trial44_run.py": "16eb59a54a78e7d76b5fa361e668ce15981a08e34db404a1758e1f948ad11846",
    "trial44_write.py": "124df24519927bb917c98a72a1dd8b513b4e5eb965dc2071745e05cea3f3cf85",
}

ORIGINALS = frozenset(EXPECTED) - {"crossfreq_run_nocache.py", "crossfreq_run_rederived.py"}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_recovered_runner_is_byte_identical(name):
    """A recovered original whose bytes moved is corruption, not an update."""
    path = RUNNERS / name
    assert path.exists(), f"{name} is missing — this file has no other copy anywhere"
    assert _sha256(path) == EXPECTED[name], (
        f"{name} changed. These bytes were recovered from a transcript that has since been pruned, "
        f"so there is nothing to re-recover them from. If the change was deliberate, say so by "
        f"updating the hash here; otherwise restore from git history."
    )


def test_no_recovered_runner_has_appeared_or_vanished():
    """The set is fixed. A new .py here is either an undocumented artifact or a variant the README
    does not describe; a missing one is unrecoverable."""
    on_disk = {p.name for p in RUNNERS.glob("*.py")}
    documented = set(EXPECTED)
    assert on_disk == documented, f"unexpected: {sorted(on_disk - documented)}; missing: {sorted(documented - on_disk)}"


def test_the_hooks_that_would_rewrite_them_are_still_excluded():
    """The exemptions are what make this test necessary — if one is dropped, the artifacts become
    reformattable and this tripwire is the only thing that would catch it. Pin both."""
    repo = RUNNERS.parents[2]
    ruff = (repo / "ruff.toml").read_text()
    precommit = (repo / ".pre-commit-config.yaml").read_text()
    assert "docs/reference/trial43-recovered-runners/*" in ruff, "ruff exclude dropped"
    assert "trial43-recovered-runners" in precommit, "pre-commit top-level exclude dropped"
    # rrsync's guard shares both lines; a careless edit to ours can drop theirs.
    assert "infra/nas/rrsync" in ruff and "infra/nas/rrsync" in precommit, "the rrsync guard was weakened while editing this one"
