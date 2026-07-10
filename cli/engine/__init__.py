from cli.engine.concordance import (
    CompareResult,
    CycleOutcome,
    FailureDetail,
    GateStatus,
    HashMismatchError,
    compare_targets,
    evaluate_gate,
    replay_cycle,
)
from cli.engine.cycle import CycleResult, run_cycle
from cli.engine.errors import EngineError, EngineJournalError
from cli.engine.journal import (
    SCHEMA_VERSION,
    CycleRecord,
    SnapshotEntry,
    from_json,
    snapshot_content_hash,
    to_json,
    validate_record,
)
from cli.engine.store import (
    GRID_INTERVALS,
    PAIR_KEYS,
    RefreshEntry,
    RefreshReport,
    SeedEntry,
    SeedReport,
    read_store_series,
    refresh_store,
    seed_store,
)

# cli.engine.node imports nautilus-trader (~1 s), so its symbols are re-exported lazily (PEP 562):
# importing cli.engine (e.g. via cli.engine.command at `zcrypto --help` time) must never pay the
# nautilus import; the first actual attribute access does.
_NODE_EXPORTS = ("ShadowStrategy", "build_shadow_node", "most_recent_boundary", "next_boundary", "startup_action")


def __getattr__(name: str):
    if name in _NODE_EXPORTS:
        from cli.engine import node

        return getattr(node, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "GRID_INTERVALS",
    "PAIR_KEYS",
    "SCHEMA_VERSION",
    "CompareResult",
    "CycleOutcome",
    "CycleRecord",
    "CycleResult",
    "EngineError",
    "EngineJournalError",
    "FailureDetail",
    "GateStatus",
    "HashMismatchError",
    "RefreshEntry",
    "RefreshReport",
    "SeedEntry",
    "SeedReport",
    "ShadowStrategy",
    "SnapshotEntry",
    "build_shadow_node",
    "compare_targets",
    "evaluate_gate",
    "from_json",
    "most_recent_boundary",
    "next_boundary",
    "read_store_series",
    "refresh_store",
    "replay_cycle",
    "run_cycle",
    "seed_store",
    "snapshot_content_hash",
    "startup_action",
    "to_json",
    "validate_record",
]
