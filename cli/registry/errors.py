from __future__ import annotations


class RegistryError(Exception):
    pass


class RegistryCorruptionError(RegistryError):
    """A registry record in its stored form failed to parse or broke a stored-record or chain rule."""
