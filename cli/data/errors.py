from __future__ import annotations


class DataSyncError(Exception):
    """A hot-cluster sync step failed (rsync error, manifest mismatch, missing set)."""
