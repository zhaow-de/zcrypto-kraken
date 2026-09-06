"""The capture hosts pass neither extra-port variable, so their rendered ruleset must be
BYTE-IDENTICAL to the pre-seam output (spec 00075 D8) -- an internet-facing L2 host's firewall
must never change as a side effect of another host's feature."""

import shutil
from pathlib import Path

import jinja2
import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
TEMPLATE = REPO / "infra/ansible/roles/firewall/templates/nftables.conf.j2"

GOLDEN_PRE_SEAM = "#!/usr/sbin/nft -f\n#\n# Managed by Ansible (roles/firewall) — do not edit by hand.\n#\n# Manages ONLY `table inet filter` (the host's own inbound policy). It deliberately does\n# NOT `flush ruleset`, because Docker installs its own nftables tables (`ip/ip6 nat`, the\n# `docker` tables) for container NAT + forwarding — a global flush wipes those and breaks\n# container networking (DNS/egress from containers). The add/delete/add idiom below\n# atomically replaces only our table, leaving Docker's tables untouched. We also omit a\n# `forward` chain so Docker's forwarding/masquerade rules govern container egress; only the\n# host's own INPUT is filtered. `nft -f` still applies this whole file as one atomic\n# transaction, so policy-drop + the 10022 accept always land together (no lockout window).\n\nadd table inet filter\ndelete table inet filter\ntable inet filter {\n  chain input {\n    type filter hook input priority 0; policy drop;\n\n    # loopback\n    iif lo accept\n\n    # established/related — keeps in-flight connections (including this SSH session) alive\n    ct state established,related accept\n\n    # SSH\n    tcp dport 10022 accept\n\n    # ICMPv4 ping\n    icmp type echo-request accept\n\n    # ICMPv6 ping + the neighbor-discovery / router-advertisement types IPv6 needs to function\n    icmpv6 type { echo-request, nd-neighbor-solicit, nd-neighbor-advert, nd-router-solicit, nd-router-advert } accept\n  }\n}\n"

BASE = {"firewall_ssh_port": "10022", "firewall_extra_tcp_ports": [], "firewall_extra_udp_ports": []}


def _render(ctx):
    env = jinja2.Environment(undefined=jinja2.StrictUndefined, trim_blocks=True, keep_trailing_newline=True)
    return env.from_string(TEMPLATE.read_text()).render(ctx)


def test_capture_render_is_byte_identical_to_pre_seam():
    assert _render(BASE) == GOLDEN_PRE_SEAM


def test_extra_ports_render_accept_rules():
    out = _render({**BASE, "firewall_extra_tcp_ports": [80, 443, 20022], "firewall_extra_udp_ports": [51820]})
    assert "tcp dport { 80, 443, 20022 } accept" in out
    assert "udp dport { 51820 } accept" in out


# --- what makes BASE the capture context rather than a literal: the role's own defaults, and the
# bridgehead's group being the only var file that overrides either of them.
ANSIBLE = REPO / "infra/ansible"
FIREWALL_DEFAULTS = ANSIBLE / "roles/firewall/defaults/main.yml"
VAR_ROOTS = (ANSIBLE / "group_vars", ANSIBLE / "host_vars")
EXTRA_PORT_VARS = ("firewall_extra_tcp_ports", "firewall_extra_udp_ports")
OPENER = "group_vars/access_host/vars.yml"


class _KeysOnlyLoader(yaml.SafeLoader):
    """Every var file here is plaintext YAML whose secrets are inline `!vault` VALUES, so the key
    names are readable -- the tag is kept as its ciphertext rather than decrypted."""


_KeysOnlyLoader.add_constructor("!vault", lambda loader, node: node.value)


def _extra_port_declarations(roots: tuple[Path, ...]) -> dict[str, list[str]]:
    """Which var file declares which extra-port list, keyed by its path under group_vars/ or host_vars/."""
    found: dict[str, list[str]] = {}
    for root in roots:
        entries = sorted(root.rglob("*"))
        assert entries, f"{root.name}/ walked empty, so this selection read no var file of it"
        # rglob does not descend a symlinked directory, so one would hide every var file beneath it
        linked = [str(p.relative_to(root)) for p in entries if p.is_symlink() and p.is_dir()]
        assert not linked, f"{root.name}/ carries a linked directory this walk does not descend: {linked}"
        for path in entries:
            if path.is_dir():
                continue
            key = f"{root.name}/{path.relative_to(root)}"
            assert path.is_file(), f"{key} is not a regular file this selection can read"
            data = yaml.load(path.read_text(), Loader=_KeysOnlyLoader)
            assert isinstance(data, dict), f"{key} does not parse as a mapping, so this selection cannot read its keys"
            declared = [v for v in EXTRA_PORT_VARS if v in data]
            if declared:
                found[key] = declared
    return found


def test_only_the_bridgehead_group_opens_extra_ports():
    """BASE's empty lists are the firewall role's own defaults, and the bridgehead's group is the only
    var file overriding either -- so the render above is what a capture host's own inventory produces."""
    defaults = yaml.safe_load(FIREWALL_DEFAULTS.read_text())
    for var in EXTRA_PORT_VARS:
        assert defaults[var] == BASE[var] == [], f"{var} defaults to {defaults[var]!r}, not the empty list BASE renders with"
    found = _extra_port_declarations(VAR_ROOTS)
    print(f"var files declaring an extra-port list: {found}")
    assert found == {OPENER: list(EXTRA_PORT_VARS)}, (
        f"only {OPENER} may declare an extra-port list, and it must declare both — found: {found}"
    )


def _var_roots_copy(tmp_path: Path) -> tuple[Path, ...]:
    # the scan reads VAR_ROOTS at call time, so a copy plus a rebound global runs its real assertions
    return tuple(shutil.copytree(root, tmp_path / root.name, symlinks=True) for root in VAR_ROOTS)


def test_a_capture_group_opening_an_inbound_port_reds_the_scan(tmp_path, monkeypatch):
    """The defect the scan exists to catch: a var file other than the bridgehead's opening a port."""
    roots = _var_roots_copy(tmp_path)
    victim = tmp_path / "group_vars" / "capture_host" / "vars.yml"
    victim.write_text(victim.read_text() + "firewall_extra_tcp_ports: [9999]\n")
    monkeypatch.setitem(globals(), "VAR_ROOTS", roots)
    with pytest.raises(AssertionError, match=r"may declare an extra-port list"):
        test_only_the_bridgehead_group_opens_extra_ports()


def test_the_copied_var_files_alone_red_nothing(tmp_path, monkeypatch):
    """The true positive beside it: the copy passes until the case above plants something."""
    monkeypatch.setitem(globals(), "VAR_ROOTS", _var_roots_copy(tmp_path))
    test_only_the_bridgehead_group_opens_extra_ports()
