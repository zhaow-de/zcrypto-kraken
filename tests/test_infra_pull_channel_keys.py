from pathlib import Path

import pytest

FILES = Path(__file__).resolve().parents[1] / "infra/ansible/files"
VAULT_PREFIX = "$ANSIBLE_VAULT;"
# A sync channel's NAS file is named as infra/nas/compose.yaml mounts it: its key's name, the engine journal's apart.
NAS_NAMES = {"sync": "sync_journal"}
VAULTED = "$ANSIBLE_VAULT;1.1;AES256\n6162636465666768\n"

PUBLIC = sorted(FILES.glob("*_ed25519.pub"))
PRIVATE = sorted(FILES.glob("*_ed25519"))


def _channel(path):
    return path.name.removesuffix(".pub").removesuffix("_ed25519")


def _remedy(channel):
    encrypt = f"uv run ansible-vault encrypt --vault-password-file scripts/vault-pass.sh --output files/{channel}_ed25519 -"
    if channel == "sync" or channel.startswith("sync_"):
        nas = NAS_NAMES.get(channel, channel)
        return f'from infra/ansible/, run: ssh nas "sudo cat /volume1/docker/zcrypto-archive/keys/{nas}" | {encrypt}'
    return f"from infra/ansible/, pipe the private half into: {encrypt}"


# Only the first line is read, inside this helper, so a failing assertion's introspection shows a bool, never key bytes.
def _vault_shaped(path):
    with path.open() as f:
        return f.readline().startswith(VAULT_PREFIX)


def _clear_text(private):
    channel = _channel(private)
    return (
        f"{channel}: {private.name} is in clear text (it does not begin {VAULT_PREFIX}); "
        f"replace it with the vaulted form, {_remedy(channel)}"
    )


def _defects(files_dir: Path) -> list[str]:
    defects = []
    for pub in sorted(files_dir.glob("*_ed25519.pub")):
        channel = _channel(pub)
        private = pub.with_suffix("")
        if not private.is_file():
            defects.append(f"{channel}: {pub.name} has no private sibling {private.name} here; {_remedy(channel)}")
    for private in sorted(files_dir.glob("*_ed25519")):
        if not _vault_shaped(private):
            defects.append(_clear_text(private))
    return defects


def _plant_vaulted_pair(files_dir, channel):
    (files_dir / f"{channel}_ed25519.pub").write_text(f"ssh-ed25519 AAAA {channel}\n")
    (files_dir / f"{channel}_ed25519").write_text(VAULTED)


def test_a_vault_shaped_pair_is_no_defect(tmp_path):
    _plant_vaulted_pair(tmp_path, "sync_good")
    assert _defects(tmp_path) == []


def test_an_orphan_public_half_is_a_defect(tmp_path):
    _plant_vaulted_pair(tmp_path, "sync_good")
    (tmp_path / "sync_orphan_ed25519.pub").write_text("ssh-ed25519 AAAA sync_orphan\n")
    defects = _defects(tmp_path)
    assert len(defects) == 1 and defects[0].startswith("sync_orphan: "), defects
    assert "no private sibling" in defects[0], defects


def test_a_clear_text_private_half_is_a_defect(tmp_path):
    _plant_vaulted_pair(tmp_path, "sync_good")
    (tmp_path / "sync_planted_ed25519.pub").write_text("ssh-ed25519 AAAA sync_planted\n")
    (tmp_path / "sync_planted_ed25519").write_text("-----BEGIN OPENSSH PRIVATE KEY-----\nnot-a-key\n")
    defects = _defects(tmp_path)
    assert len(defects) == 1 and defects[0].startswith("sync_planted: "), defects
    assert "in clear text" in defects[0], defects


def test_the_glob_finds_channels():
    assert PUBLIC, f"no *_ed25519.pub under {FILES}: the public-half cases are an empty parameter set, which pytest skips"
    assert PRIVATE, f"no *_ed25519 under {FILES}: the private-half cases are an empty parameter set, which pytest skips"


@pytest.mark.parametrize("pub", PUBLIC, ids=_channel)
def test_public_half_has_a_private_sibling(pub):
    channel = _channel(pub)
    private = pub.with_suffix("")
    assert private.is_file(), f"{channel}: {pub.name} has no private sibling {private.name} here; {_remedy(channel)}"


@pytest.mark.parametrize("private", PRIVATE, ids=_channel)
def test_private_half_is_vaulted(private):
    assert _vault_shaped(private), _clear_text(private)
