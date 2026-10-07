from pathlib import Path

import pytest

FILES = Path(__file__).resolve().parents[1] / "infra/ansible/files"
CHANNELS = "sync_*_ed25519"
VAULT_PREFIX = "$ANSIBLE_VAULT;"

PUBLIC = sorted(FILES.glob(f"{CHANNELS}.pub"))
PRIVATE = sorted(FILES.glob(CHANNELS))


def _channel(path):
    return path.name.removesuffix(".pub").removesuffix("_ed25519")


def _remedy(channel):
    return (
        f'from infra/ansible/, run: ssh nas "sudo cat /volume1/docker/zcrypto-archive/keys/{channel}" | '
        f"uv run ansible-vault encrypt --vault-password-file scripts/vault-pass.sh --output files/{channel}_ed25519 -"
    )


# Only the first line is read, inside this helper, so a failing assertion's introspection shows a bool, never key bytes.
def _vault_shaped(path):
    with path.open() as f:
        return f.readline().startswith(VAULT_PREFIX)


def test_the_glob_finds_channels():
    assert PUBLIC, f"no {CHANNELS}.pub under {FILES}: the public-half cases are an empty parameter set, which pytest skips"
    assert PRIVATE, f"no {CHANNELS} under {FILES}: the private-half cases are an empty parameter set, which pytest skips"


@pytest.mark.parametrize("pub", PUBLIC, ids=_channel)
def test_public_half_has_a_vaulted_private_sibling(pub):
    channel = _channel(pub)
    private = pub.with_suffix("")
    assert private.is_file(), f"{channel}: {pub.name} has no private sibling {private.name} here; {_remedy(channel)}"
    assert _vault_shaped(private), (
        f"{channel}: {private.name} does not begin {VAULT_PREFIX}; replace it with the vaulted form, {_remedy(channel)}"
    )


@pytest.mark.parametrize("private", PRIVATE, ids=_channel)
def test_private_half_is_vaulted(private):
    channel = _channel(private)
    assert _vault_shaped(private), (
        f"{channel}: {private.name} is in clear text (it does not begin {VAULT_PREFIX}); "
        f"replace it with the vaulted form, {_remedy(channel)}"
    )
