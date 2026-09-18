"""Declared readings for skip gates whose guard does not say what it reads.

A skip gate's guard matches one of `tests/test_live_venue_opt_in.py`'s forms, and a call into this
module is one of them: the call is the declaration, made where a reviewer greps for it. A function
here reads the filesystem, the repo, or the value it is handed, and nothing else --
`test_the_registry_reads_nothing_a_form_could_not` holds the module to that.
"""

import shutil
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def develop_resolves() -> bool:
    """`develop` is a ref this checkout can resolve; a shallow CI clone may lack it."""
    return subprocess.run(["git", "rev-parse", "--verify", "--quiet", "develop"], cwd=REPO, capture_output=True).returncode == 0


def no_binary(name: str) -> bool:
    """The named executable is not on PATH."""
    return shutil.which(name) is None


def nothing_found(rows: object) -> bool:
    """A local scan -- a glob, an index read, a registry filter -- found nothing. The caller declares
    the scan was local; this function only says whether it was empty."""
    return not rows
