from __future__ import annotations

from pathlib import Path

from cli.config import CONFIG_FILENAME, load_config
from cli.data.rolling import ROLLING_SET
from cli.registry import ReadingLedger, TrialRegistry

REPO = Path(__file__).resolve().parents[1]
REGISTRY = REPO / "docs" / "reference" / "trial-registry.jsonl"
LEDGER = REPO / "docs" / "reference" / "reading-ledger.jsonl"


# The hub pass in tests/test_registry_conformance.py refuses a cited set absent from the hub's hot/, but runs only where
# the NAS is mounted; this holds the same invariant in CI: every cited set has a channel there — an authored set this
# node pushes, or the rolling set the ops outbox carries.
def test_every_set_a_record_or_reading_cites_has_a_channel_to_the_hub():
    config = REPO / CONFIG_FILENAME
    assert config.is_file(), f"{config} is absent, so no authored set would be read"
    channels = {*load_config(config).data.authored_sets, ROLLING_SET}
    cited = [(f"trial {r.trial_id}", r.datasets) for r in TrialRegistry(REGISTRY).records if r.schema_version >= 4]
    cited += [(f"reading {r.reading_id}", r.datasets) for r in ReadingLedger(LEDGER).records]
    assert cited, "no record or reading cites a set, so the walk read nothing"
    unreached = sorted({f"{label} / {dataset}" for label, datasets in cited for dataset in datasets if dataset not in channels})
    assert not unreached, (
        f"a cited set is in neither {CONFIG_FILENAME}'s authored_sets nor {ROLLING_SET}, so no push carries it to the hub:\n  "
        + "\n  ".join(unreached)
    )
