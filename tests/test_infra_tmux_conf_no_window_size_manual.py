"""Guard: `set -g window-size manual` CRASHES the tmux 3.5a server ("server exited unexpectedly")
the next time a session or window is created. `set -g default-size` alone is harmless; the reflow
it was meant to prevent is recoverable, the crash is not."""

from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]

# Every tmux config this repo renders/ships onto a host.
TMUX_CONFIGS = [
    REPO / "infra/ansible/roles/access_ops/templates/tmux.conf.j2",
]


@pytest.mark.parametrize("cfg", TMUX_CONFIGS, ids=lambda p: p.name)
def test_tmux_config_has_no_window_size_manual(cfg):
    assert cfg.exists(), f"managed tmux config missing: {cfg}"
    for i, line in enumerate(cfg.read_text().splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue  # the cautionary comment naming the banned option is allowed
        assert "window-size manual" not in stripped, (
            f"{cfg.name}:{i} sets `window-size manual` -- it crashes tmux 3.5a on the next "
            f"new-session and killed the live zcrypto session once. Never ship it."
        )
