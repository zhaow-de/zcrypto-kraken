from __future__ import annotations

from pathlib import Path

from cli.config import CONFIG_FILENAME, load_config
from cli.data.rolling import ROLLING_SET
from cli.registry import ReadingLedger, TrialRegistry

REPO = Path(__file__).resolve().parents[1]
REGISTRY = REPO / "docs" / "reference" / "trial-registry.jsonl"
LEDGER = REPO / "docs" / "reference" / "reading-ledger.jsonl"


# The hub pass in tests/test_registry_conformance.py reads hot/ only where the NAS is mounted; this is its CI-run
# precondition: a cited set is an authored set, which `data push` sends, or the rolling set, which the ops outbox carries.
def test_every_set_a_record_or_reading_cites_has_a_channel_to_the_hub():
    config = REPO / CONFIG_FILENAME
    assert config.is_file(), f"{config} is absent, so no authored set would be read"
    channels = {*load_config(config).data.authored_sets, ROLLING_SET}
    cited = [(f"trial {r.trial_id}", r.datasets) for r in TrialRegistry(REGISTRY).records if r.schema_version >= 4]
    cited += [(f"reading {r.reading_id}", r.datasets) for r in ReadingLedger(LEDGER).records]
    assert cited, "no record or reading cites a set, so the walk read nothing"
    unreached = sorted({f"{label} / {dataset}" for label, datasets in cited for dataset in datasets if dataset not in channels})
    assert not unreached, (
        f"a cited set is in neither {CONFIG_FILENAME}'s authored_sets nor {ROLLING_SET}, so `data push` never sends it:\n  "
        + "\n  ".join(unreached)
    )
