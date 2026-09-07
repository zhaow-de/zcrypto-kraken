from __future__ import annotations


class DataSyncError(Exception):
    """A `cli.data` step failed: sync (rsync error, manifest mismatch, missing set), rebuild, or a malformed attestation."""
