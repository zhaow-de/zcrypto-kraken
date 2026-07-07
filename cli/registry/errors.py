from __future__ import annotations


class RegistryError(Exception):
    """A trial-registry validation or integrity rule was violated."""


class RegistryCorruptionError(RegistryError):
    """A persisted registry line is malformed or carries a non-finite JSON token."""
