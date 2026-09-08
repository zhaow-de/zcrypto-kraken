"""The push stage is the ratchet alone, resolved through pre-commit rather than read off the YAML.

An upstream manifest can widen a hook's stages without this repo's config changing a byte, which is
how five hooks — two of them rewriters — reached the push stage in the first place."""

import pathlib

_ROOT = pathlib.Path(__file__).resolve().parents[1]


def _pre_push_hook_ids() -> list[str]:
    from pre_commit.clientlib import load_config
    from pre_commit.repository import all_hooks
    from pre_commit.store import Store

    config = load_config(str(_ROOT / ".pre-commit-config.yaml"))
    return sorted(hook.id for hook in all_hooks(config, Store()) if "pre-push" in hook.stages)


def test_the_push_stage_is_the_ratchet_alone() -> None:
    assert _pre_push_hook_ids() == ["prose-tripwire"]
