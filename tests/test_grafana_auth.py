"""TDD for `infra/scripts/grafana_auth.py` — the vaulted-credential resolver both Grafana scripts share.

`continuity.py`'s test file sets the precedent: these are standalone scripts, not package modules,
so they load via `importlib.util.spec_from_file_location`.

Every test here pins something that actually went wrong during the 2026-07-28 capture rollout, when
the decrypt was improvised from prose and took two failed attempts before it worked.
"""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[1] / "infra" / "scripts" / "grafana_auth.py"
_spec = importlib.util.spec_from_file_location("grafana_auth", _SCRIPT)
ga = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ga)

TOKEN = "glsa_TOTALLY_NOT_A_REAL_TOKEN_0123456789"


def test_the_vault_password_file_comes_from_ansible_cfg_not_a_hardcoded_path():
    """Hardcoding it would rot silently the day the config moves, and the resulting error reads as
    a wrong key rather than a wrong path."""
    path = ga.vault_password_file()

    assert path.name == "vault-pass.sh"
    assert path.exists(), path
    assert path.is_relative_to(ga.ANSIBLE_DIR)


def test_the_password_helper_is_EXECUTED_never_read(monkeypatch):
    """THE footgun. `vault_password_file` names a GPG helper script, not a file containing a
    password. Reading its bytes yields shell source, and ansible then fails with "no vault secrets
    were found that could decrypt" -- which reads as a wrong key, sending the next person hunting
    the wrong thing entirely."""
    calls = []

    def fake_run(argv, **kw):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout=b"  s3cret\n", stderr=b"")

    monkeypatch.setattr(ga.subprocess, "run", fake_run)
    # Reading the path instead of running it must not be how the password is obtained.
    monkeypatch.setattr(Path, "read_bytes", lambda self: pytest.fail(f"read {self} instead of executing it"))

    assert ga.vault_password() == b"s3cret", "stdout, stripped"
    assert calls and calls[0] == [str(ga.vault_password_file())]


def test_the_vault_context_is_initialized_before_a_scalar_is_read(monkeypatch):
    """THE OTHER footgun, and the one review found unpinned: `VaultSecretsContext.initialize` looks
    like dead setup -- it returns nothing, and `secrets` is handed to `set_vault_secrets` two lines
    later anyway -- so a cleanup pass deletes it and the suite stays green. Without it, `str()` on a
    `!vault` scalar raises `ReferenceError: A required VaultSecretsContext context is not active`,
    which reads as an API-version problem rather than a missing step, and the next operator
    improvises the decrypt all over again."""
    import ansible.parsing.dataloader as dl
    import ansible.parsing.vault as v

    seen = {}
    monkeypatch.setattr(ga, "vault_password", lambda: b"pw")
    monkeypatch.setattr(ga, "_CONTEXT_READY", False)
    monkeypatch.setattr(v.VaultSecretsContext, "initialize", classmethod(lambda cls, ctx: seen.setdefault("init", ctx)))

    class FakeLoader:
        def set_vault_secrets(self, secrets):
            seen["secrets"] = secrets

        def load_from_file(self, path):
            assert "init" in seen, "the scalar was read before the context was initialized"
            return {"grafana_sa_token": TOKEN}

    monkeypatch.setattr(dl, "DataLoader", FakeLoader)

    assert ga.vault_var("grafana_sa_token") == TOKEN
    assert seen.get("init") is not None and seen.get("secrets")


def test_reading_a_second_credential_does_not_crash_on_the_once_only_initialize(monkeypatch):
    """`initialize` raises RuntimeError on a second call. The gate reads one credential today, but
    the signature is parameterized and the superseded recipe says "swap for any other key" -- so a
    second read must be a no-op, not a crash mid-gate."""
    import ansible.parsing.dataloader as dl
    import ansible.parsing.vault as v

    calls = []
    monkeypatch.setattr(ga, "vault_password", lambda: b"pw")
    monkeypatch.setattr(ga, "_CONTEXT_READY", False)

    def once(cls, ctx):
        calls.append(ctx)
        if len(calls) > 1:
            raise RuntimeError("The VaultSecretsContext context is already initialized.")

    monkeypatch.setattr(v.VaultSecretsContext, "initialize", classmethod(once))

    class FakeLoader:
        def set_vault_secrets(self, secrets): ...
        def load_from_file(self, path):
            return {"grafana_sa_token": TOKEN, "slack_webhook_url": "https://hooks.example/x"}

    monkeypatch.setattr(dl, "DataLoader", FakeLoader)

    assert ga.vault_var("grafana_sa_token") == TOKEN
    assert ga.vault_var("slack_webhook_url").startswith("https://")  # would RuntimeError unguarded
    assert len(calls) == 1


def test_vault_var_reads_the_file_it_is_given(monkeypatch):
    """The engine's healthcheck URL and the healthchecks admin key live in per-group vault files,
    not `all/`; a resolver fixed to one file cannot reach them."""
    seen = {}

    class FakeLoader:
        def set_vault_secrets(self, secrets): ...

        def load_from_file(self, path):
            seen["path"] = path
            return {"engine_healthcheck_url": "https://example.invalid/abc"}

    monkeypatch.setattr(ga, "_load_ansible_vault", lambda: (FakeLoader(), object()))

    got = ga.vault_var("engine_healthcheck_url", vault_file="group_vars/engine_host/vault.yml")
    assert got == "https://example.invalid/abc"
    assert seen["path"].endswith("group_vars/engine_host/vault.yml")
