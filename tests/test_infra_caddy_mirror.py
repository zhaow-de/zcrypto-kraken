"""The bridgehead's Caddy apt mirror and the Caddy sources that read it: what the access role syncs, serves and installs
from, and what every role pins Caddy's candidates to."""

from __future__ import annotations

import hashlib
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ANSIBLE = REPO / "infra/ansible"
KEYRING = ANSIBLE / "files/caddy-archive-keyring.gpg"
KEYRING_SHA256 = "c17cd5298a0bab02fda439fff278d9a55df2120cf9dac790c6ce71930db90b37"


# --- the key ----------------------------------------------------------------------------------------------------------
def test_the_vendored_keyring_is_the_vendor_key_as_measured():
    assert hashlib.sha256(KEYRING.read_bytes()).hexdigest() == KEYRING_SHA256
