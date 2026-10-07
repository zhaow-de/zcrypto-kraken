from pathlib import Path

FILES = Path(__file__).resolve().parents[1] / "infra/ansible/files"
VAULT_PREFIX = "$ANSIBLE_VAULT;"
# An ed25519 private half vaults to about 1900 bytes; an empty payload, what a failed read piped into encrypt writes, to 355.
VAULT_FLOOR = 1000
# A sync channel's NAS file is keys/<its key's name>, unless infra/nas/compose.yaml mounts it under another.
NAS_NAMES = {"sync": "sync_journal"}
VAULTED = "$ANSIBLE_VAULT;1.1;AES256\n" + ("61" * 40 + "\n") * 24
EMPTY_PAYLOAD = "$ANSIBLE_VAULT;1.1;AES256\n" + ("61" * 40 + "\n") * 4 + "6162\n"
CLEAR = "-----BEGIN OPENSSH PRIVATE KEY-----\nnot-a-key\n"


def _channel(path):
    return path.name.removesuffix(".pub").removesuffix("_ed25519")


def _nas(channel):
    if channel == "sync" or channel.startswith("sync_"):
        return NAS_NAMES.get(channel, channel)
    return None


# ansible.cfg supplies the vault password file; passing it again makes encrypt refuse two default vault ids.
def _encrypt(channel):
    return f"uv run ansible-vault encrypt --output files/{channel}_ed25519 -"


def _remedy(channel):
    if nas := _nas(channel):
        return (
            f'from infra/ansible/, run: k=$(ssh nas "sudo cat /volume1/docker/zcrypto-archive/keys/{nas}") '
            f"&& printf '%s\\n' \"$k\" | {_encrypt(channel)}"
        )
    return f"from infra/ansible/, pipe the private half into: {_encrypt(channel)}"


def _rotation(channel):
    nas = _nas(channel)
    drop = f", drop the new private half on the NAS at keys/{nas}" if nas else ""
    return (
        "a key committed and pushed in clear is compromised, so rotate it, never re-vault it: generate a new pair, "
        "commit its public half, re-converge the hosts that authorize it, remove the old line wherever an "
        f"authorized_keys still carries it (an exclusive: false install never removes one){drop}, then from "
        f"infra/ansible/ pipe the new private half into: {_encrypt(channel)}"
    )


# Only the first line is read, inside this helper, so no defect line or failure output carries key bytes.
def _vault_shaped(path):
    with path.open() as f:
        return f.readline().startswith(VAULT_PREFIX)


def _defects(files_dir: Path) -> list[str]:
    publics = sorted(files_dir.glob("*_ed25519.pub"))
    defects = [] if publics else [f"no *_ed25519.pub under {files_dir}"]
    for pub in publics:
        channel = _channel(pub)
        private = pub.with_suffix("")
        if not private.is_file():
            defects.append(f"{channel}: {pub.name} has no private sibling {private.name} here; {_remedy(channel)}")
    # zaccess_ca.key.vault, the one vaulted key here that is no *_ed25519 pair, is outside these globs.
    for private in sorted(files_dir.glob("*_ed25519")):
        channel = _channel(private)
        if not _vault_shaped(private):
            defects.append(f"{channel}: {private.name} is in clear text (it does not begin {VAULT_PREFIX}); {_rotation(channel)}")
        elif (size := private.stat().st_size) < VAULT_FLOOR:
            defects.append(f"{channel}: {private.name} is vault-shaped but {size} bytes, too small to be a key; {_remedy(channel)}")
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


def test_an_orphan_deploy_public_half_is_a_defect(tmp_path):
    _plant(tmp_path, "sync")
    (tmp_path / "deploy_y_ed25519.pub").write_text("ssh-ed25519 AAAA deploy_y\n")
    _the_one_defect(tmp_path, "deploy_y", "no private sibling")


def test_a_clear_text_private_half_is_a_defect(tmp_path):
    _plant(tmp_path, "deploy_x")
    _plant(tmp_path, "sync", private=CLEAR)
    _the_one_defect(tmp_path, "sync", "in clear text")


def test_a_deploy_key_in_clear_is_a_defect(tmp_path):
    _plant(tmp_path, "sync")
    _plant(tmp_path, "deploy_x", private=CLEAR)
    _the_one_defect(tmp_path, "deploy_x", "in clear text")


def test_an_empty_payload_vault_is_a_defect(tmp_path):
    _plant(tmp_path, "deploy_x")
    _plant(tmp_path, "sync_panel", private=EMPTY_PAYLOAD)
    _the_one_defect(tmp_path, "sync_panel", "too small to be a key")


def test_a_directory_without_public_halves_is_a_defect(tmp_path):
    (tmp_path / "sync_hc_backup_ed25519").write_text(VAULTED)
    defects = _defects(tmp_path)
    assert len(defects) == 1 and defects[0].startswith("no *_ed25519.pub under "), defects


def test_the_tree_has_no_defects():
    defects = _defects(FILES)
    assert defects == [], "\n".join(defects)
