"""The capture hosts pass neither extra-port variable, so their rendered ruleset must be
BYTE-IDENTICAL to the pre-seam output (spec 00075 D8) -- an internet-facing L2 host's firewall
must never change as a side effect of another host's feature."""

from pathlib import Path

import jinja2

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
