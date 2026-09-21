"""Declared readings for skip gates whose guard does not say what it reads.

A skip gate's guard matches one of `tests/test_live_venue_opt_in.py`'s forms, and a call into this
module is one of them: the call is the declaration, made where a reviewer greps for it. A function
here reads the filesystem, the repo, the local config, or the value it is handed, and nothing else --
`test_the_registry_reads_nothing_a_form_could_not` holds the module to that. The matcher checks what
it can of each call's argument: a scan's root is held literal-rooted the way a path receiver is, and
a config-rooted form's name is held a literal, so those declarations are judged at the gate;
`nothing_found` alone is a declaration the call site owns, and its docstring says for which gates.
"""

import shutil
import subprocess
from pathlib import Path

from cli.config import load_config, resolve_hot_source

REPO = Path(__file__).resolve().parents[1]


def develop_resolves() -> bool:
    """`develop` is a ref this checkout can resolve; a shallow CI clone may lack it."""
    return subprocess.run(["git", "rev-parse", "--verify", "--quiet", "develop"], cwd=REPO, capture_output=True).returncode == 0


def no_binary(name: str) -> bool:
    """The named executable is not on PATH."""
    return shutil.which(name) is None


def nothing_found(rows: object) -> bool:
    """The declaration the call site owns: a collection no path scan produces is empty. Kept for the
    three gates whose rows come from somewhere other than a glob -- a registry filter
    (`tests/test_registry_conformance.py`), an index of archived days and the heal-complete day chosen
    from it (`tests/test_tape_bars_rest_control.py`)."""
    return not rows


def nothing_found_under(root: Path, pattern: str) -> bool:
    """A glob for `pattern` under `root` found nothing; the matcher holds `root` literal-rooted, as
    it holds a path receiver."""
    return not any(Path(root).glob(pattern))


def scan(root: Path, pattern: str) -> list[Path]:
    """The glob a test body needs, sorted by name so a stamped filename orders it."""
    return sorted(Path(root).glob(pattern))


def substrate_root(name: str) -> Path | None:
    """A derivatives substrate's root as the local config names it: the NFS hot mount, else the
    promoted local copy, else None -- `data/` is per-checkout and a worktree's is empty, so a gate on
    the local copy alone skips wherever the suite runs from a worktree."""
    return next((p for p in (Path(resolve_hot_source(load_config()), name), Path("data", name)) if Path(p).is_dir()), None)


def substrate_absent(name: str) -> bool:
    """No root of the named substrate is on this machine, by `substrate_root`'s reading; the matcher
    holds `name` a literal."""
    return next((p for p in (Path(resolve_hot_source(load_config()), name), Path("data", name)) if Path(p).is_dir()), None) is None


def mount_absent(relative: str) -> bool:
    """`relative` under the NFS mount the local config names does not exist."""
    return not Path(load_config().nfs_mount_dir, relative).exists()
