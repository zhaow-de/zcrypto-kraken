"""Guard: what each host's Alloy config ships to the observability node, and the names its secrets template renders."""

import re
from pathlib import Path

import pytest
import yaml

from tests.alloy_text import live_alloy_text as _live_alloy_text
from tests.alloy_text import live_j2_text as _live_j2_text

REPO = Path(__file__).resolve().parents[1]
NAS_ALLOY = REPO / "infra/nas/config.alloy"
# NOTE: files/, not templates/ — this config is installed with `ansible.builtin.copy`, which
# only ever searches a role's files/ dir.
OPS_ALLOY = REPO / "infra/ansible/roles/ops/files/config.alloy"
CAPTURE_ALLOY = REPO / "infra/ansible/roles/capture/files/config.alloy"
ACCESS_ALLOY = REPO / "infra/ansible/roles/access/files/config.alloy"
CACHE_ALLOY = REPO / "infra/ansible/roles/cache/files/config.alloy"
HC_ALLOY = REPO / "infra/ansible/roles/hc/files/config.alloy"
CACHE_SECRETS = REPO / "infra/ansible/roles/cache/templates/alloy-secrets.env.j2"
OPS_SECRETS = REPO / "infra/ansible/roles/ops/templates/alloy-secrets.env.j2"
ACCESS_SECRETS = REPO / "infra/ansible/roles/access/templates/alloy-env.j2"
HC_ENV = REPO / "infra/ansible/roles/hc/templates/alloy-env.j2"
NAS_SECRETS = REPO / "infra/ansible/roles/nas/templates/alloy-secrets.env.j2"
CAPTURE_SECRETS = REPO / "infra/ansible/roles/capture/templates/alloy-secrets.env.j2"

_LIVE_REGEX_LINE = re.compile(r'^\s*regex\s*=\s*"(.*)"\s*$', re.M)
_LIVE_SEPARATOR_LINE = re.compile(r'^\s*separator\s*=\s*";"\s*$', re.M)
_LIVE_JOURNAL_SOURCE_LABELS_LINE = re.compile(
    r'^\s*source_labels\s*=\s*\["__journal__systemd_unit", "__journal_container_name"\]\s*$', re.M
)


def _live_regex(block: str, where: str) -> str:
    """The block's first `regex = "..."` line matched whole, so a `//` copy of a broader one above it is not read."""
    m = _LIVE_REGEX_LINE.search(block)
    assert m, f"{where}: no live regex line"
    return m.group(1)


# --- the ops journal keep-regex is a census too (T0178) -------------------------------------------
_OPS_ROLE = REPO / "infra/ansible/roles/ops"
# Deliberately unshipped: the parse stage below the keep rule reads the Python logging shape.
_JOURNAL_NOT_SHIPPED = {
    "zcrypto-grafana-watchdog": "a shell probe; a dark Grafana pages through the /fail it pings, and a refused post is curl's one line, read on the host",
    "zcrypto-clock-offset": "a shell probe; its output is the .prom it writes, and a chronyc failure is the unknown offset it publishes",
    "zcrypto-reboot-check": "a shell probe; its output is the .prom it writes, and a failed write is the absence the publisher count pages on",
}


def _journal_keep_block(config: Path) -> str:
    for block in re.findall(r"^\s*rule \{(.*?)\n  \}", config.read_text(), re.M | re.S):
        if re.search(r'^\s*source_labels\s*=.*"__journal__systemd_unit"', block, re.M) and re.search(
            r'^\s*action\s*=\s*"keep"\s*$', block, re.M
        ):
            return block
    raise AssertionError(f"no journal keep rule found in {config}")


def _ops_journal_keep_block() -> str:
    return _journal_keep_block(OPS_ALLOY)


def _ops_journal_keep_regex() -> str:
    """The journal `keep` rule's regex, as written in the file."""
    return _live_regex(_ops_journal_keep_block(), f"{OPS_ALLOY}: journal keep rule")


def _journal_units_kept() -> set[str]:
    """The units the keep rule admits. Read out of the alternation: the regex is written
    `zcrypto-(archive-pull|verify-replay|...)`, so no full unit name appears in it to match on."""
    inner = re.search(r"zcrypto-\((.*?)\)", _ops_journal_keep_regex())
    assert inner, "the journal keep-regex no longer spells its units as one `zcrypto-(a|b|c)` alternation"
    return {f"zcrypto-{m}" for m in inner.group(1).split("|")}


def _installed_units() -> set[str]:
    """Both install idioms: `templates/*.timer.j2` rendered, and `files/*.timer` copied, which is how the capture
    and engine roles install theirs. A timer added the other way was invisible to this guard. Every rendered service
    too: a oneshot with no timer of its own, pulled in by another unit, is installed and logs as well."""
    # The two idioms name their files differently: a template is `archive-pull.timer.j2` and takes the prefix,
    # a copied file is already `zcrypto-capture-prune.timer` and must not. Prefixing both produced
    # `zcrypto-zcrypto-…`, which matched no regex entry, so the guard went green with a phantom unit kept and the
    # real unit's journal dropped.
    units = {f"zcrypto-{p.name.removesuffix('.timer.j2')}" for p in (_OPS_ROLE / "templates").glob("*.timer.j2")}
    units |= {p.name.removesuffix(".timer") for p in (_OPS_ROLE / "files").glob("*.timer")}
    services = (p.name.removesuffix(".service.j2") for p in (_OPS_ROLE / "templates").glob("*.service.j2"))
    units |= {n if n.startswith("zcrypto-") else f"zcrypto-{n}" for n in services}
    assert all(not u.startswith("zcrypto-zcrypto-") for u in units), f"double-prefixed unit name: {sorted(units)}"
    return units


def test_the_ops_journal_keep_regex_accounts_for_every_unit_the_role_installs():
    """Adding a timer fails here until it is named in the regex or excluded with a reason."""
    kept = _journal_units_kept()
    units = sorted(_installed_units())
    assert units, "no timer templates found -- the glob is broken, not the role empty"
    unaccounted = [u for u in units if u not in kept and u not in _JOURNAL_NOT_SHIPPED]
    assert not unaccounted, (
        f"{unaccounted} are installed by the ops role and neither named in the journal keep-regex nor listed as "
        f"deliberately unshipped: their journal lines reach no Loki, and nothing else would say so"
    )


def test_a_unit_listed_as_unshipped_is_not_in_the_keep_regex():
    """The two categories are alternatives, not a free choice: shipping a unit this file calls deliberately
    unshipped passed green, because nothing said the regex may not name it."""
    both = sorted(_journal_units_kept() & set(_JOURNAL_NOT_SHIPPED))
    assert not both, (
        f"{both} are named in the keep-regex AND listed here as deliberately unshipped -- one of the two is a "
        f"lie; if their journal should ship now, delete the row and its reason"
    )


@pytest.mark.parametrize("config", [OPS_ALLOY, CAPTURE_ALLOY], ids=["ops", "capture"])
def test_the_keep_rule_admits_alloys_own_stream_and_joins_on_unit_and_container(config):
    """Both hosts: the capture pair's rule is the ops rule's twin field for field."""
    rule = _journal_keep_block(config)
    regex = _live_regex(rule, f"{config}: journal keep rule")
    assert _LIVE_SEPARATOR_LINE.search(rule), (
        f"the keep rule's separator is no longer `;`, so the `unit;container` values it matches are not the ones "
        f"the regex is written for and the rule matches nothing: {rule!r}"
    )
    assert _LIVE_JOURNAL_SOURCE_LABELS_LINE.search(rule), (
        f"the keep rule's source_labels changed, so the two halves of the joined value swap and the regex's unit "
        f"arm no longer lines up with the unit: {rule!r}"
    )
    assert regex.endswith(";.*|.*;grafana-alloy"), (
        f"the keep rule no longer ends with the unit-arm separator and Alloy's own stream: {regex!r}"
    )
    assert "\\.service;" in regex, (
        f"the unit arm no longer anchors on `.service;`, so the `unit;container` join is not what it was: {regex!r}"
    )


def test_the_unshipped_list_holds_no_unit_that_no_longer_exists():
    """The other direction: an excuse for a deleted unit is a stale reason a reader would trust."""
    stale = sorted(u for u in _JOURNAL_NOT_SHIPPED if u not in _installed_units())
    assert not stale, f"{stale} carry a not-shipped reason but the role installs no such timer"


def test_the_journal_keep_regex_names_no_unit_the_role_does_not_install():
    """A name kept in the regex after its unit goes reads as coverage of something that cannot log."""
    extra = sorted(_journal_units_kept() - _installed_units())
    assert not extra, f"the keep-regex names {extra}, which the role does not install"


# --- the cache nodes' config ---------------------------------------------------------------------
def test_the_capture_config_scrapes_the_cache_proxy_and_labels_its_journal_lines_before_the_engines_block():
    text = _live_alloy_text(CAPTURE_ALLOY)
    scrape = re.search(r'^prometheus\.scrape "cache_proxy" \{(.*?)\n\}', text, re.M | re.DOTALL)
    assert scrape, "no cache_proxy scrape block"
    assert re.search(r'^\s*targets\s*=\s*\[\{"__address__"\s*=\s*"127\.0\.0\.1:9104"\}\]\s*$', scrape.group(1), re.M), (
        f"no live targets line on 127.0.0.1:9104 in the cache_proxy scrape block: {scrape.group(1)!r}"
    )
    assert re.search(r'^\s*job_name\s*=\s*"cache_proxy"\s*$', scrape.group(1), re.M), (
        f'no live `job_name = "cache_proxy"` line in the cache_proxy scrape block: {scrape.group(1)!r}'
    )
    proxy = re.search(r'^\s*pipeline_name\s*=\s*"cache_proxy"\s*$', text, re.M)
    engine = re.search(r'^\s*pipeline_name\s*=\s*"engine_nautilus"\s*$', text, re.M)
    assert proxy and engine, f"a live pipeline_name line is missing: proxy={proxy}, engine={engine}"
    assert proxy.start() < engine.start(), "the proxy's match must run before the engine's, which relabels the whole unit"
    block = text[proxy.start() : engine.start()]
    assert re.search(r'^\s*values\s*=\s*\{\s*container\s*=\s*"cache-proxy"\s*\}\s*$', block, re.M), block
    assert re.search(r'^\s*expression\s*=\s*".*zcrypto-cache-proxy.*"\s*$', block, re.M), block
    for key in ("selector", "expression"):
        assert re.search(rf'^\s*{key}\s*=\s*".*NOTICE\|WARNING\|ALERT\|INFO.*"\s*$', block, re.M), (key, block)


def _env_names_read(config: Path) -> set[str]:
    return set(re.findall(r'sys\.env\("([A-Z_]+)"\)', _live_alloy_text(config)))


def _env_names_rendered(template: Path) -> set[str]:
    return set(re.findall(r"^([A-Z_]+)=", _live_j2_text(template), re.M))


def test_the_cache_secrets_template_renders_every_name_the_config_reads():
    """A name the config reads that the env file lacks is an empty string at runtime: remote_write or the
    exporter's AUTH fails with nothing in the tree to say why."""
    read, rendered = _env_names_read(CACHE_ALLOY), _env_names_rendered(CACHE_SECRETS)
    assert {"CACHE_EXPORTER_PASSWORD", "CACHE_SENTINEL_REQUIREPASS"} <= read, f"the config reads {sorted(read)}"
    assert read == rendered, f"config reads {sorted(read - rendered)} unrendered; template renders {sorted(rendered - read)} unread"


def test_the_redis_exporters_ship_under_the_jobs_the_rules_select():
    """Both exporters' targets carry the same built-in `job`, which wins over a scrape's `job_name`; the
    relabel is what makes `job="valkey"` and `job="sentinel"` exist at all."""
    text = _live_alloy_text(CACHE_ALLOY)
    targets = re.findall(r"^\s*targets\s*=\s*(\S.*?)\s*$", text, re.M)
    for job in ("valkey", "sentinel"):
        relabel = re.search(rf'^discovery\.relabel "{job}" \{{(.*?)\n\}}', text, re.M | re.S)
        assert relabel, f"no live discovery.relabel for {job}"
        rules = relabel.group(1)
        assert re.search(rf"^\s*targets\s*=\s*prometheus\.exporter\.redis\.{job}\.targets\s*$", rules, re.M), rules
        assert re.search(r'^\s*target_label\s*=\s*"job"\s*$', rules, re.M), rules
        assert re.search(rf'^\s*replacement\s*=\s*"{job}"\s*$', rules, re.M), f"no live replacement line for {job}: {rules!r}"
        assert f"discovery.relabel.{job}.output" in targets, f"the {job} scrape does not read its relabelled targets"


def test_the_cache_journal_keep_rule_keys_the_containers_by_name():
    """Keyed by container name: the journald-driver streams carry `docker.service` as their unit, so a unit
    arm cannot select them, and keying the unit that runs the compose project too would ship each line
    twice."""
    rule = _journal_keep_block(CACHE_ALLOY)
    regex = _live_regex(rule, f"{CACHE_ALLOY}: journal keep rule")
    assert _LIVE_SEPARATOR_LINE.search(rule) and _LIVE_JOURNAL_SOURCE_LABELS_LINE.search(rule)
    assert regex == "zcache-probe\\\\.service;.*|.*;(zcrypto-valkey|zcrypto-sentinel|grafana-alloy)", regex


def test_the_cache_textfile_collector_reads_where_the_mesh_probe_writes():
    """The mesh probe of `roles/cache_link` writes zcache.prom into `cache_link_textfile_dir` and the cache role's
    reboot check writes reboot.prom into `cache_textfile_dir`; the node's Alloy reads that one directory through its
    `/:/host/root:ro` mount, so each path differs from the collector's by that prefix alone."""
    directory = re.search(r'textfile \{\s*directory = "([^"]+)"', _live_alloy_text(CACHE_ALLOY))
    assert directory, "no textfile directory in the cache config"
    for role, var in (("cache_link", "cache_link_textfile_dir"), ("cache", "cache_textfile_dir")):
        written = re.search(rf"^{var}: (\S+)$", (REPO / f"infra/ansible/roles/{role}/defaults/main.yml").read_text(), re.M)
        assert written and directory.group(1) == "/host/root" + written.group(1), (role, written, directory.group(1))


_CACHE_DROPS = [
    '{container=\\"alloy\\"} |= \\"ERR unknown command \'LATENCY\'\\"',
    '{container=\\"alloy\\", level=\\"INFO\\"} |= \\"msg=\\\\\\"finished node evaluation\\\\\\"\\"',
]


def test_the_cache_log_pipeline_drops_the_sentinel_exporters_latency_error_and_alloys_node_evaluations_and_nothing_else():
    pipeline = re.search(r'^loki\.process "parse" \{\n(.*?)\n\}', CACHE_ALLOY.read_text(), re.M | re.S)
    assert pipeline, 'no loki.process "parse" in the cache config'
    drops = [
        block
        for block in re.findall(r"^  stage\.match \{\n(.*?)\n  \}", pipeline.group(1), re.M | re.S)
        if re.search(r'^\s*action\s*=\s*"drop"$', block, re.M)
    ]
    selectors = []
    for drop in drops:
        selector = re.search(r'^\s*selector\s*=\s*"(.*)"$', drop, re.M)
        assert selector, drop
        selectors.append(selector.group(1))
        assert re.search(r'^\s*drop_counter_reason\s*=\s*"\w+"$', drop, re.M), drop
        assert not re.search(r"^\s*stage\.", drop, re.M), drop
    assert sorted(selectors) == sorted(_CACHE_DROPS), drops


# --- the node's leg: each host's one endpoint, and the names it reads ---------------------------------
def _endpoint_blocks(path: Path) -> list[str]:
    component = re.search(r'\nprometheus\.remote_write "grafana" \{(.*?)\n\}\n', _live_alloy_text(path), re.S).group(1)
    return re.findall(r"\n  endpoint \{(.*?)\n  \}", component, re.S)


@pytest.mark.parametrize(
    "path", [ACCESS_ALLOY, OPS_ALLOY, CACHE_ALLOY, NAS_ALLOY, CAPTURE_ALLOY], ids=["access", "ops", "cache", "nas", "capture"]
)
def test_the_one_endpoint_is_the_nodes_and_carries_no_relabel_block(path):
    (mon,) = _endpoint_blocks(path)
    assert "write_relabel_config" not in mon and "GRAFANA_" not in mon
    assert re.search(r'^\s*name\s*=\s*"mon"\s*$', mon, re.M)
    assert all(
        re.search(rf'^\s*{n.lower()}\s*=\s*sys\.env\("MON_PROM_{n}"\)\s*$', mon, re.M) for n in ("URL", "USERNAME", "PASSWORD")
    )


@pytest.mark.parametrize(
    "path", [NAS_ALLOY, OPS_ALLOY, CAPTURE_ALLOY, ACCESS_ALLOY, CACHE_ALLOY], ids=["nas", "ops", "capture", "access", "cache"]
)
def test_alloys_own_targets_are_concatenated_into_the_scrape_that_feeds_the_remote_write(path):
    text = path.read_text()
    assert re.search(r'^prometheus\.exporter\.self "alloy" \{\}$', text, re.M), f"{path}: no prometheus.exporter.self component"
    scrapes = re.findall(r'\nprometheus\.scrape "[a-z_]+" \{(.*?)\n\}', text, re.S)
    concat = (
        r"^\s*targets\s*=\s*array\.concat\(prometheus\.exporter\.unix\.host\.targets, prometheus\.exporter\.self\.alloy\.targets\)$"
    )
    carrying = [s for s in scrapes if re.search(concat, s, re.M)]
    assert len(carrying) == 1, f"{path}: {len(carrying)} scrapes concatenate the self targets onto the host's"
    assert re.search(r"^\s*forward_to\s*=\s*\[prometheus\.remote_write\.grafana\.receiver\]$", carrying[0], re.M), carrying[0]


# Held by literal, so a node name bound to another group var fails here before it is a converge.
_MON_PROM_LINES = [
    "MON_PROM_URL={{ mon_ingest_prom_url }}",
    "MON_PROM_USERNAME={{ mon_ingest_fleet_user }}",
    "MON_PROM_PASSWORD={{ mon_ingest_fleet_password }}",
]
_MON_LOKI_LINES = [
    "MON_LOKI_URL={{ mon_ingest_loki_url }}",
    "MON_LOKI_USERNAME={{ mon_ingest_fleet_user }}",
    "MON_LOKI_PASSWORD={{ mon_ingest_fleet_password }}",
]


_HC_LINES = [
    "HC_METRICS_PATH={{ hc_metrics_path }}",
    "HC_READONLY_KEY={{ hc_readonly_api_key }}",
]


@pytest.mark.parametrize(
    ("template", "mon_lines", "hc_lines"),
    [
        (ACCESS_SECRETS, _MON_PROM_LINES, []),
        (OPS_SECRETS, _MON_PROM_LINES + _MON_LOKI_LINES, _HC_LINES),
        (CACHE_SECRETS, _MON_PROM_LINES + _MON_LOKI_LINES, []),
        (HC_ENV, _MON_PROM_LINES + _MON_LOKI_LINES, []),
        (NAS_SECRETS, _MON_PROM_LINES + _MON_LOKI_LINES, []),
        (CAPTURE_SECRETS, _MON_PROM_LINES + _MON_LOKI_LINES, []),
    ],
    ids=["access", "ops", "cache", "hc", "nas", "capture"],
)
def test_the_secrets_lines_are_held_by_literal(template, mon_lines, hc_lines):
    lines = _live_j2_text(template).splitlines()
    assert [line for line in lines if line.startswith("GRAFANA_")] == []
    assert [line for line in lines if line.startswith("MON_")] == mon_lines
    assert [line for line in lines if line.startswith("HC_")] == hc_lines


HC_DEFAULTS = REPO / "infra/ansible/roles/hc/defaults/main.yml"
OBSERVED_VARS = REPO / "infra/ansible/group_vars/observed/vars.yml"


def test_the_ops_scrape_reads_the_dead_man_service_with_the_read_only_key_as_its_bearer_token():
    block = re.search(r'^prometheus\.scrape "healthchecks" \{\n(.*?)\n\}', _live_alloy_text(OPS_ALLOY), re.M | re.S)
    assert block, f'{OPS_ALLOY}: no prometheus.scrape "healthchecks"'
    body = block.group(1)
    hostname = yaml.safe_load(HC_DEFAULTS.read_text())["hc_hostname"]
    assert re.findall(r'"__address__"\s*=\s*"([^"]*)"', body) == [hostname], body
    assert re.search(r'^\s*scheme\s*=\s*"https"\s*$', body, re.M), body
    assert re.search(r'^\s*metrics_path\s*=\s*sys\.env\("HC_METRICS_PATH"\)\s*$', body, re.M), body
    assert re.search(r'^\s*bearer_token\s*=\s*sys\.env\("HC_READONLY_KEY"\)\s*$', body, re.M), body
    assert yaml.safe_load(OBSERVED_VARS.read_text())["hc_metrics_path"] == "/projects/{{ hc_project_uuid }}/metrics/"


# A name the config reads that the template lacks is an empty string at runtime: the endpoint fails with
# nothing in the tree to say why.
@pytest.mark.parametrize(
    ("config", "template", "unread"),
    [
        (ACCESS_ALLOY, ACCESS_SECRETS, {"CONFIG_FILE", "CUSTOM_ARGS"}),
        (OPS_ALLOY, OPS_SECRETS, set()),
        (HC_ALLOY, HC_ENV, {"CONFIG_FILE", "CUSTOM_ARGS"}),
        (NAS_ALLOY, NAS_SECRETS, set()),
        (CAPTURE_ALLOY, CAPTURE_SECRETS, set()),
    ],
    ids=["access", "ops", "hc", "nas", "capture"],
)
def test_each_secrets_template_renders_the_names_its_config_reads(config, template, unread):
    read, rendered = _env_names_read(config), _env_names_rendered(template)
    assert read <= rendered, f"{config.name} reads {sorted(read - rendered)}, which {template.name} does not render"
    assert rendered - read == unread, f"{template.name} renders {sorted(rendered - read)} that {config.name} does not read"


# --- the node's log leg: the one loki.write the parse stage feeds --------------------------------------
def _loki_write_block(path: Path, name: str) -> str:
    block = re.search(rf'\nloki\.write "{name}" \{{(.*?)\n\}}\n', _live_alloy_text(path) + "\n", re.S)
    assert block, f'{path}: no loki.write "{name}" component'
    return block.group(1)


def _one_endpoint_reading(block: str, names: tuple[str, str, str]) -> None:
    assert len(re.findall(r"^\s*endpoint\s*\{\s*$", block, re.M)) == 1, block
    for key, name in zip(("url", "username", "password"), names, strict=True):
        assert re.search(rf'^\s*{key}\s*=\s*sys\.env\("{name}"\)\s*$', block, re.M), (name, block)


@pytest.mark.parametrize("path", [OPS_ALLOY, CACHE_ALLOY, NAS_ALLOY, CAPTURE_ALLOY], ids=["ops", "cache", "nas", "capture"])
def test_the_parse_stage_feeds_the_nodes_loki_write_alone(path):
    parse = re.search(r'^loki\.process "parse" \{\n(.*?)\n\}', _live_alloy_text(path), re.M | re.S)
    assert parse, f'{path}: no loki.process "parse"'
    forward = re.search(r"^  forward_to\s*=\s*\[(.*?)\]\s*$", parse.group(1), re.M)
    assert forward and forward.group(1) == "loki.write.mon.receiver", parse.group(1)
    assert re.findall(r'^loki\.write "(\w+)" \{$', _live_alloy_text(path), re.M) == ["mon"]
    mon = _loki_write_block(path, "mon")
    _one_endpoint_reading(mon, ("MON_LOKI_URL", "MON_LOKI_USERNAME", "MON_LOKI_PASSWORD"))
    assert "GRAFANA_" not in mon


# --- the unix exporter's netdev exclusion: the container and bridge devices stay at the source ----------
def _unix_exporter_block(path: Path) -> str:
    block = re.search(r'\nprometheus\.exporter\.unix "host" \{(.*?)\n\}\n', _live_alloy_text(path), re.S)
    assert block, f'{path}: no prometheus.exporter.unix "host" component'
    return block.group(1)


_NETDEV_EXCLUSION = r'^\s*device_exclude\s*=\s*"\^\(veth\|br-\)"\s*$'


@pytest.mark.parametrize("path", [OPS_ALLOY, NAS_ALLOY, CAPTURE_ALLOY], ids=["ops", "nas", "capture"])
def test_the_unix_exporter_excludes_the_container_and_bridge_devices(path):
    netdev = re.search(r"^\s*netdev\s*\{\s*$(.*?)^\s*\}\s*$", _unix_exporter_block(path), re.M | re.S)
    assert netdev, f"{path}: the unix exporter has no netdev block"
    assert re.search(_NETDEV_EXCLUSION, netdev.group(1), re.M), netdev.group(1)


@pytest.mark.parametrize("path", [ACCESS_ALLOY, CACHE_ALLOY], ids=["access", "cache"])
def test_the_unix_exporter_has_no_netdev_block_where_none_is_prescribed(path):
    assert not re.search(r"^\s*netdev\s*\{", _unix_exporter_block(path), re.M), (
        f"{path}: the unix exporter gained a netdev block; a config that takes the exclusion moves to the "
        f"excluding side of these two tests"
    )
