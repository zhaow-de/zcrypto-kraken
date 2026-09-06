"""Guard the byte-identity of the vendored rrsync.

`infra/nas/rrsync` is rsync 3.4.1's upstream python3 rrsync, vendored VERBATIM and byte-identical
to the fleet's own /usr/bin/rrsync. It is the sole write-jail confining the NAS pull, so a rewrite
both destroys the provenance and edits security code into custody (spec 00056 D2).

Nothing in the repo stops that rewrite by itself: the file has no `.py` suffix but a python3
shebang, so tools identify it as Python. Its protection is a set of exclusions -- pre-commit's
top-level `exclude:` (which covers EVERY hook) plus ruff's own `exclude` -- and a deleted line in
either file silently un-protects it.
"""

import hashlib
from pathlib import Path

# rsync 3.4.1 upstream python3 rrsync; matches the fleet's /usr/bin/rrsync and the hash recorded in
# .pre-commit-config.yaml's header comment. Update ONLY when deliberately re-vendoring upstream.
EXPECTED_SHA256 = "d4739b6f82a93894aeb027dc55b02ff655eca7b8dd06accd733eada5865585f1"

RRSYNC = Path(__file__).resolve().parents[1] / "infra" / "nas" / "rrsync"


def test_vendored_rrsync_is_byte_identical():
    assert RRSYNC.is_file(), f"{RRSYNC} is missing -- the NAS write-jail is vendored here"
    digest = hashlib.sha256(RRSYNC.read_bytes()).hexdigest()
    assert digest == EXPECTED_SHA256, (
        f"{RRSYNC.relative_to(RRSYNC.parents[2])} changed: expected {EXPECTED_SHA256}, got {digest}. "
        "It is vendored verbatim -- do not reformat it. A formatter or whitespace hook most likely "
        "reached it because an exclusion was dropped from .pre-commit-config.yaml or ruff.toml; "
        "restore the file (git checkout) and the exclusion. Only update EXPECTED_SHA256 when "
        "deliberately re-vendoring upstream rrsync."
    )
