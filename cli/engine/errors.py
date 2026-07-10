class EngineError(Exception):
    """Raised on invalid concordance-core (journal/replay/compare/gate) inputs or state."""


class EngineJournalError(EngineError):
    """A CycleRecord violates its schema or the snapshot-boundary (no-peek) invariant."""
