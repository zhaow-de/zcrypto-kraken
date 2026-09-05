class EngineError(Exception):
    """Raised on invalid `cli.engine` inputs or state."""


class EngineJournalError(EngineError):
    """A journaled record violates its schema or a journal invariant."""
