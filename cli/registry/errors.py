from __future__ import annotations


class RegistryError(Exception):
    """A trial-registry validation or integrity rule was violated."""


class RegistryCorruptionError(RegistryError):
    """A registry record in its stored form failed to parse or broke a stored-record or chain rule."""
