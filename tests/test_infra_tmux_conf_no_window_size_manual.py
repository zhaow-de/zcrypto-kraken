"""Guard: `set -g window-size manual` CRASHES the tmux 3.5a server ("server exited unexpectedly")
the next time a session or window is created. On 2026-07-30 it was shipped into the managed
~/.tmux.conf as the D13 resize mitigation; when agentboard later created its own session on that
poisoned server, the whole tmux server died and took the live zcrypto session with it (spec 00075
D13/D15, ledger incident). `set -g default-size` alone is harmless; the reflow it was meant to
prevent is recoverable, the crash is not. This test fails if that line is ever reintroduced into a
tmux config this repo manages, so the landmine cannot come back."""

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
