from pathlib import Path

FILES = Path(__file__).resolve().parents[1] / "infra/ansible/files"
VAULT_PREFIX = "$ANSIBLE_VAULT;"
# A sync channel's NAS file is keys/<its key's name>, unless infra/nas/compose.yaml mounts it under another.
NAS_NAMES = {"sync": "sync_journal"}
VAULTED = "$ANSIBLE_VAULT;1.1;AES256\n6162636465666768\n"
CLEAR = "-----BEGIN OPENSSH PRIVATE KEY-----\nnot-a-key\n"


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


def _defects(files_dir: Path) -> list[str]:
    publics = sorted(files_dir.glob("*_ed25519.pub"))
    defects = [] if publics else [f"no *_ed25519.pub under {files_dir}: nothing was checked"]
    for pub in publics:
        channel = _channel(pub)
        private = pub.with_suffix("")
        if not private.is_file():
            defects.append(f"{channel}: {pub.name} has no private sibling {private.name} here; {_remedy(channel)}")
    for private in sorted(files_dir.glob("*_ed25519")):
        channel = _channel(private)
        if not _vault_shaped(private):
            defects.append(
                f"{channel}: {private.name} is in clear text (it does not begin {VAULT_PREFIX}); "
                f"replace it with the vaulted form, {_remedy(channel)}"
            )
    return defects


def _plant(files_dir, channel, private=VAULTED):
    (files_dir / f"{channel}_ed25519.pub").write_text(f"ssh-ed25519 AAAA {channel}\n")
    (files_dir / f"{channel}_ed25519").write_text(private)


def _the_one_defect(files_dir, channel, phrase):
    defects = _defects(files_dir)
    assert len(defects) == 1 and defects[0].startswith(f"{channel}: "), defects
    assert phrase in defects[0], defects


def test_vault_shaped_pairs_are_no_defect(tmp_path):
    for channel in ("sync", "sync_capture", "deploy_x"):
        _plant(tmp_path, channel)
    assert _defects(tmp_path) == []


def test_an_orphan_public_half_is_a_defect(tmp_path):
    _plant(tmp_path, "deploy_x")
    (tmp_path / "sync_ed25519.pub").write_text("ssh-ed25519 AAAA sync\n")
    _the_one_defect(tmp_path, "sync", "no private sibling")


def test_a_clear_text_private_half_is_a_defect(tmp_path):
    _plant(tmp_path, "deploy_x")
    _plant(tmp_path, "sync", private=CLEAR)
    _the_one_defect(tmp_path, "sync", "in clear text")


def test_a_deploy_key_in_clear_is_a_defect(tmp_path):
    _plant(tmp_path, "sync")
    _plant(tmp_path, "deploy_x", private=CLEAR)
    _the_one_defect(tmp_path, "deploy_x", "in clear text")


def test_a_directory_without_public_halves_is_a_defect(tmp_path):
    (tmp_path / "sync_hc_backup_ed25519").write_text(VAULTED)
    defects = _defects(tmp_path)
    assert len(defects) == 1 and defects[0].startswith("no *_ed25519.pub under "), defects


def test_the_tree_has_no_defects():
    defects = _defects(FILES)
    assert defects == [], "\n".join(defects)
