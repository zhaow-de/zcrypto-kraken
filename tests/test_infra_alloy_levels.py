"""Each host's level stages after its parse, driven over the line shapes its sources print. The model reads the
configs' own selectors; where an `alloy` binary is on PATH the same blocks also run through Alloy itself."""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import NamedTuple

import pytest

from tests.alloy_text import live_alloy_text
from tests.skip_gates import no_binary
from tests.test_infra_alloy_stages import ALLOY_CONFIGS, _assigned, _blocks, _parse_body, _run_alloy, _stage_blocks

REPO = Path(__file__).resolve().parents[1]
CONFIGS = {host: REPO / f"infra/ansible/roles/{host}/files/config.alloy" for host in ("mon", "hc", "ops", "capture", "cache")} | {
    "nas": REPO / "infra/nas/config.alloy"
}
# A dropped line: DROP where the drop admits a line with no level, the unlevelled copy of a record its source ships
# levelled; DROP_NO_FAULT where it admits only a level the parse set, a line that reports no fault.
DROP = "DROP"
DROP_NO_FAULT = "DROP_NO_FAULT"


class Fixture(NamedTuple):
    id: str
    host: str
    labels: dict[str, str]
    line: str
    expected: str | None


# The labels are the ones the level stages see, a level among them where the host's parse set one; numbers are filled
# in, and an address or a user name is a documentation one.
FIXTURES: list[Fixture] = [
    Fixture(
        "mon_selfcheck_ok",
        "mon",
        {"container": "zcrypto-mon-selfcheck"},
        "selfcheck: rules=ok (114 rules scheduled, last tick 4 s ago) fleet=ok (8 fleet hosts shipping) loki=ok (ready) -> pinged",
        "INFO",
    ),
    Fixture(
        "mon_selfcheck_fail",
        "mon",
        {"container": "zcrypto-mon-selfcheck"},
        "selfcheck: rules=FAIL (unreadable: URLError) fleet=FAIL (unreadable: URLError) loki=FAIL (unreadable: URLError) -> not pinging",
        "WARNING",
    ),
    Fixture(
        "mon_selfcheck_ping_failed",
        "mon",
        {"container": "zcrypto-mon-selfcheck"},
        "selfcheck: rules=ok (114 rules scheduled, last tick 4 s ago) fleet=ok (8 fleet hosts shipping) loki=ok (ready) -> ping failed: URLError",
        "WARNING",
    ),
    Fixture(
        "mon_selfcheck_no_ping_url",
        "mon",
        {"container": "zcrypto-mon-selfcheck"},
        "selfcheck: rules=ok (114 rules scheduled, last tick 4 s ago) fleet=ok (8 fleet hosts shipping) loki=ok (ready) -> healthy, and no ping URL is set",
        "WARNING",
    ),
    Fixture(
        "mon_selfcheck_unnamed_shape",
        "mon",
        {"container": "zcrypto-mon-selfcheck"},
        "an unclassified line from zcrypto-mon-selfcheck",
        None,
    ),
    Fixture(
        "mon_grafana_panel_cancelled",
        "mon",
        {"container": "grafana-server", "level": "ERROR"},
        r'logger=plugin.loki t=2026-11-03T16:37:12.345678901Z level=error msg="Partial data response error" dsName=Loki dsUid=grafanacloud-logs error="Get \"http://127.0.0.1:3100/loki/api/v1/query_range?direction=backward&end=1762187832000000000&query=sum%28rate%28%7Bhost%3D~%22zcrypto%22%7D%5B5m%5D%29%29&start=1762184232000000000&step=60000ms\": context canceled"',
        DROP_NO_FAULT,
    ),
    Fixture(
        "mon_grafana_panel_failed",
        "mon",
        {"container": "grafana-server", "level": "ERROR"},
        r'logger=plugin.loki t=2026-11-03T16:37:12.345678901Z level=error msg="Partial data response error" dsName=Loki dsUid=grafanacloud-logs error="Get \"http://127.0.0.1:3100/loki/api/v1/query_range?direction=backward&end=1762187832000000000&query=sum%28rate%28%7Bhost%3D~%22zcrypto%22%7D%5B5m%5D%29%29&start=1762184232000000000&step=60000ms\": dial tcp 127.0.0.1:3100: connect: connection refused"',
        "ERROR",
    ),
    Fixture(
        "mon_grafana_loki_connection_closed",
        "mon",
        {"container": "grafana-server", "level": "ERROR"},
        'logger=plugin.loki t=2026-11-04T13:56:53.50144968Z level=error msg="Partial data response error" error="read tcp 127.0.0.1:45606->127.0.0.1:3100: use of closed network connection" pluginId=loki refID=A pluginVersion=13.2.2 status=500 statusSource=plugin uname=example-admin dsName=Loki dsUid=grafanacloud-logs endpoint=queryData',
        DROP_NO_FAULT,
    ),
    Fixture(
        "mon_grafana_loki_connection_reset",
        "mon",
        {"container": "grafana-server", "level": "ERROR"},
        'logger=plugin.loki t=2026-11-04T13:56:53.50144968Z level=error msg="Partial data response error" error="read tcp 127.0.0.1:45606->127.0.0.1:3100: read: connection reset by peer" pluginId=loki refID=A pluginVersion=13.2.2 status=500 statusSource=plugin uname=example-admin dsName=Loki dsUid=grafanacloud-logs endpoint=queryData',
        "ERROR",
    ),
    Fixture(
        "mon_grafana_loki_request_summary",
        "mon",
        {"container": "grafana-server", "level": "ERROR"},
        'logger=plugin.loki t=2026-11-04T13:56:53.502074533Z level=error msg="Plugin Request Completed" dsUid=grafanacloud-logs pluginId=loki status=error statusSource=plugin dsName=Loki duration=113.707769ms endpoint=queryData pluginVersion=13.2.2 uname=example-admin',
        DROP_NO_FAULT,
    ),
    Fixture(
        "mon_grafana_loki_request_failed",
        "mon",
        {"container": "grafana-server", "level": "ERROR"},
        'logger=plugin.loki t=2026-11-04T13:56:53.502074533Z level=error msg="Plugin Request Completed" dsUid=grafanacloud-logs pluginId=loki status=error statusSource=plugin dsName=Loki duration=113.707769ms endpoint=queryData pluginVersion=13.2.2 error="failed to query data: rpc error: code = Unavailable desc = connection error" uname=example-admin',
        "ERROR",
    ),
    Fixture(
        "mon_grafana_prometheus_request_summary",
        "mon",
        {"container": "grafana-server", "level": "ERROR"},
        'logger=plugin.prometheus t=2026-11-04T13:56:53.502074533Z level=error msg="Plugin Request Completed" dsUid=grafanacloud-prom pluginId=prometheus status=error statusSource=downstream dsName=Prometheus duration=113.707769ms endpoint=queryData pluginVersion=13.2.4 uname=example-admin',
        "ERROR",
    ),
    Fixture(
        "mon_loki_mapping_cancelled",
        "mon",
        {"container": "loki", "level": "WARNING"},
        r'ts=2026-11-03T16:37:30.123456789Z caller=spanlogger.go:111 middleware=QueryShard.astMapperware org_id=fake user=fake level=warn msg="failed mapping AST" err="context canceled" query="sum(rate({host=~\"zcrypto|zcrypto-red|ops\"} [5m]))"',
        DROP_NO_FAULT,
    ),
    Fixture(
        "mon_loki_mapping_failed",
        "mon",
        {"container": "loki", "level": "WARNING"},
        r'ts=2026-11-03T16:37:30.123456789Z caller=spanlogger.go:111 middleware=QueryShard.astMapperware org_id=fake user=fake level=warn msg="failed mapping AST" err="rpc error: code = DeadlineExceeded desc = context deadline exceeded" query="sum(rate({host=~\"zcrypto|zcrypto-red|ops\"} [5m]))"',
        "WARNING",
    ),
    Fixture(
        "mon_loki_scheduler_cancelled",
        "mon",
        {"container": "loki", "level": "ERROR"},
        'level=error ts=2026-11-03T16:33:01.123456789Z caller=scheduler_processor.go:111 component=querier msg="error processing requests from scheduler" err="rpc error: code = Canceled desc = context canceled" addr=127.0.0.1:9095',
        DROP_NO_FAULT,
    ),
    Fixture(
        "mon_loki_scheduler_eof",
        "mon",
        {"container": "loki", "level": "ERROR"},
        'level=error ts=2026-11-03T16:33:02.123456789Z caller=scheduler_processor.go:175 component=querier org_id=fake msg="error notifying scheduler about finished query" err=EOF addr=127.0.0.1:9095',
        DROP_NO_FAULT,
    ),
    Fixture(
        "mon_loki_scheduler_unavailable",
        "mon",
        {"container": "loki", "level": "ERROR"},
        r'level=error ts=2026-11-03T16:33:01.123456789Z caller=scheduler_processor.go:111 component=querier msg="error processing requests from scheduler" err="rpc error: code = Unavailable desc = connection error: desc = \"transport: Error while dialing: dial tcp 127.0.0.1:9095: connect: connection refused\"" addr=127.0.0.1:9095',
        "ERROR",
    ),
    Fixture(
        "mon_loki_scheduler_notify_failed",
        "mon",
        {"container": "loki", "level": "ERROR"},
        r'level=error ts=2026-11-03T16:33:02.123456789Z caller=scheduler_processor.go:175 component=querier org_id=fake msg="error notifying scheduler about finished query" err="rpc error: code = Unavailable desc = connection error: desc = \"transport: Error while dialing: dial tcp 127.0.0.1:9095: connect: connection refused\"" addr=127.0.0.1:9095',
        "ERROR",
    ),
    Fixture(
        "mon_loki_health_check_closing",
        "mon",
        {"container": "loki", "level": "ERROR"},
        'level=error ts=2026-11-04T09:31:55.314893014Z caller=scheduler_processor.go:304 component=querier org_id=fake frontend=127.0.0.1:9096 msg="error health checking" err="rpc error: code = Canceled desc = grpc: the client connection is closing"',
        DROP_NO_FAULT,
    ),
    Fixture(
        "mon_loki_health_check_failed",
        "mon",
        {"container": "loki", "level": "ERROR"},
        'level=error ts=2026-11-04T09:31:55.314893014Z caller=scheduler_processor.go:304 component=querier org_id=fake frontend=127.0.0.1:9096 msg="error health checking" err="rpc error: code = DeadlineExceeded desc = context deadline exceeded"',
        "ERROR",
    ),
    Fixture(
        "mon_loki_schema_overlap_sliver",
        "mon",
        {"container": "loki", "level": "WARNING"},
        'level=warn ts=2026-11-04T15:00:00.975465676Z caller=limits.go:723 org_id=fake msg="could not determine query overlaps on tsdb vs non-tsdb schemas, likely due to query not overlapping any of the schema configs,letting downstream code handle it gracefully" start=1793804400 end=1793804400.772',
        DROP_NO_FAULT,
    ),
    Fixture(
        "mon_loki_series_limit",
        "mon",
        {"container": "loki", "level": "WARNING"},
        'level=warn ts=2026-11-04T15:00:00.975465676Z caller=limits.go:410 org_id=fake msg="maximum number of series (500) reached for a single query; consider reducing query cardinality by adding more filters"',
        "WARNING",
    ),
    Fixture(
        "mon_grafana_quotas_501",
        "mon",
        {"container": "grafana-server", "level": "ERROR"},
        'logger=context userId=2 orgId=1 uname=example-admin t=2026-11-03T16:32:41.123456789Z level=error msg="Request Completed" method=GET path=/apis/quotas.grafana.app/v0alpha1/namespaces/default/usage status=501 remote_addr=192.0.2.20 time_ms=1 duration=1.234567ms size=81',
        DROP_NO_FAULT,
    ),
    Fixture(
        "mon_grafana_quotas_500",
        "mon",
        {"container": "grafana-server", "level": "ERROR"},
        'logger=context userId=2 orgId=1 uname=example-admin t=2026-11-03T16:32:41.123456789Z level=error msg="Request Completed" method=GET path=/apis/quotas.grafana.app/v0alpha1/namespaces/default/usage status=500 remote_addr=192.0.2.20 time_ms=1 duration=1.234567ms size=81',
        "ERROR",
    ),
    Fixture(
        "mon_grafana_contact_point_test",
        "mon",
        {"container": "grafana-server", "level": "ERROR"},
        'logger=ngalert.notifier t=2026-11-03T10:00:00.123456789Z level=error component=alertmanager orgID=1 receiver= integration=slack[0] version=v1 aggrGroup=slack-0a1b2c3d4e5f-6a7b8c9d0e1f msg="Missing notification reason"',
        DROP_NO_FAULT,
    ),
    Fixture(
        "mon_grafana_notifier_failure",
        "mon",
        {"container": "grafana-server", "level": "ERROR"},
        'logger=ngalert.notifier t=2026-11-03T10:00:00.123456789Z level=error component=alertmanager orgID=1 receiver=logs integration=slack[0] version=v1 aggrGroup=slack-0a1b2c3d4e5f-6a7b8c9d0e1f msg="Missing notification reason"',
        "ERROR",
    ),
    Fixture(
        "mon_grafana_plugin_stop",
        "mon",
        {"container": "grafana-server", "level": "ERROR"},
        'logger=plugin.grafana-pyroscope-datasource t=2026-11-02T21:14:10.123456789Z level=error msg="plugin process exited" path=/usr/share/grafana/plugins-bundled/grafana-pyroscope-datasource/gpx_grafana-pyroscope-datasource_linux_amd64 pid=1234 error="signal: terminated"',
        DROP_NO_FAULT,
    ),
    Fixture(
        "mon_grafana_plugin_killed",
        "mon",
        {"container": "grafana-server", "level": "ERROR"},
        'logger=plugin.grafana-pyroscope-datasource t=2026-11-02T21:14:10.123456789Z level=error msg="plugin process exited" path=/usr/share/grafana/plugins-bundled/grafana-pyroscope-datasource/gpx_grafana-pyroscope-datasource_linux_amd64 pid=1234 error="signal: killed"',
        "ERROR",
    ),
    Fixture(
        "mon_grafana_stale_session",
        "mon",
        {"container": "grafana-server", "level": "WARNING"},
        'logger=authn.service t=2026-11-03T09:55:01.123456789Z level=warn msg="Failed to authenticate request" client=auth.client.session error="user token not found"',
        "WARNING",
    ),
    Fixture("mon_alloy_start", "mon", {"container": "alloy"}, "Alloy starting in Default Engine mode", "INFO"),
    Fixture("mon_alloy_unnamed_shape", "mon", {"container": "alloy"}, "an unclassified line from alloy", None),
    Fixture(
        "mon_alloy_node_evaluation",
        "mon",
        {"container": "alloy", "level": "INFO"},
        'ts=2026-11-04T09:22:01.123456789Z level=info msg="finished node evaluation" controller_path=/ controller_id="" trace_id=0a1b2c3d4e5f60718293a4b5c6d7e8f9 node_id=loki.process.parse duration=1.234567ms',
        DROP_NO_FAULT,
    ),
    Fixture(
        "mon_alloy_graph_evaluation",
        "mon",
        {"container": "alloy", "level": "INFO"},
        'ts=2026-11-04T09:22:01.234567891Z level=info msg="finished complete graph evaluation" controller_path=/ controller_id="" trace_id=0a1b2c3d4e5f60718293a4b5c6d7e8f9 duration=12.345678ms',
        "INFO",
    ),
    Fixture("mon_caddy_env_home", "mon", {"container": "caddy"}, "HOME=/var/lib/caddy", "INFO"),
    Fixture(
        "mon_caddy_env_version",
        "mon",
        {"container": "caddy"},
        "caddy.Version=v2.11.7 h1:yj3Y5fYZGPkSvibBJ1sTWE4xC2fxztVyXEW8iIdUT0=",
        "INFO",
    ),
    Fixture(
        "mon_caddy_json_line",
        "mon",
        {"container": "caddy", "level": "INFO"},
        '{"level":"info","ts":1762187832.1234567,"logger":"http.log","msg":"server running","name":"srv0","protocols":["h1","h2","h3"]}',
        "INFO",
    ),
    Fixture("mon_caddy_unnamed_shape", "mon", {"container": "caddy"}, "an unclassified line from caddy", None),
    Fixture(
        "mon_grafana_store_not_ready",
        "mon",
        {"container": "grafana-server"},
        "curl: (22) The requested URL returned error: 503",
        "WARNING",
    ),
    Fixture(
        "mon_grafana_store_unreachable",
        "mon",
        {"container": "grafana-server"},
        "curl: (7) Failed to connect to 127.0.0.1 port 9090 after 0 ms: Could not connect to server",
        "WARNING",
    ),
    Fixture("mon_grafana_unnamed_shape", "mon", {"container": "grafana-server"}, "an unclassified line from grafana-server", None),
    Fixture("hc_selfcheck_ok", "hc", {"container": "zcrypto-hc-selfcheck"}, "selfcheck: web=ok (answered OK) -> pinged", "INFO"),
    Fixture(
        "hc_selfcheck_fail",
        "hc",
        {"container": "zcrypto-hc-selfcheck"},
        "selfcheck: web=FAIL (answered 500) -> not pinging",
        "WARNING",
    ),
    Fixture(
        "hc_selfcheck_ping_failed",
        "hc",
        {"container": "zcrypto-hc-selfcheck"},
        "selfcheck: web=ok (answered OK) -> ping failed: HTTPError",
        "WARNING",
    ),
    Fixture(
        "hc_selfcheck_no_ping_url",
        "hc",
        {"container": "zcrypto-hc-selfcheck"},
        "selfcheck: web=ok (answered OK) -> healthy, and no ping URL is set",
        "WARNING",
    ),
    Fixture(
        "hc_selfcheck_unnamed_shape",
        "hc",
        {"container": "zcrypto-hc-selfcheck"},
        "an unclassified line from zcrypto-hc-selfcheck",
        None,
    ),
    Fixture(
        "hc_sqlite_backup_done",
        "hc",
        {"container": "zcrypto-sqlite-backup"},
        "2026-11-03 02:47:01,234 INFO zcrypto.sqlite-backup [zcrypto-sqlite-backup.sh] - backed up /data/hc.sqlite to /data/backups/hc-2026-11-03T024701Z.sqlite and copied it into /var/backups/zcrypto-hc",
        "INFO",
    ),
    Fixture(
        "hc_sqlite_backup_failed",
        "hc",
        {"container": "zcrypto-sqlite-backup"},
        "2026-11-03 02:47:01,234 ERROR zcrypto.sqlite-backup [zcrypto-sqlite-backup.sh] - VACUUM INTO /data/backups/hc-2026-11-03T024701Z.sqlite from /data/hc.sqlite failed",
        "ERROR",
    ),
    Fixture(
        "hc_uwsgi_cron_start",
        "hc",
        {"container": "hc"},
        'Tue Nov  3 03:17:01 2026 - [uwsgi-cron] running "./manage.py prune --skip-checks" (pid 4321)',
        "INFO",
    ),
    Fixture(
        "hc_uwsgi_cron_exit",
        "hc",
        {"container": "hc"},
        '[uwsgi-cron] command "./manage.py prune --skip-checks" running with pid 4321 exited after 3 second(s)',
        "INFO",
    ),
    Fixture(
        "hc_prune_summary",
        "hc",
        {"container": "hc"},
        "Deleted api_ping 1440, api_notification 0, api_flip 2, api_tokenbucket 0, django_session 3, django_admin_log 0; freed 12 SQLite pages, 0 left free; checkpointed 12 of 12 WAL frames",
        "INFO",
    ),
    Fixture(
        "hc_django_text_line",
        "hc",
        {"container": "hc"},
        "2026-10-05 18:01:02,345 ERROR django.request Internal Server Error: /ping/REDACTED/zcrypto-capture",
        None,
    ),
    Fixture(
        "hc_sqlite_backup_copying",
        "hc",
        {"container": "zcrypto-sqlite-backup"},
        " zcrypto-hc Copying zcrypto-hc:/data/backups/hc-2026-11-03T024701Z.sqlite to /var/backups/zcrypto-hc.incoming/",
        "INFO",
    ),
    Fixture(
        "hc_sqlite_backup_copied",
        "hc",
        {"container": "zcrypto-sqlite-backup"},
        " zcrypto-hc Copied zcrypto-hc:/data/backups/hc-2026-11-03T024701Z.sqlite to /var/backups/zcrypto-hc.incoming/",
        "INFO",
    ),
    Fixture(
        "hc_sqlite_backup_unnamed_shape",
        "hc",
        {"container": "zcrypto-sqlite-backup"},
        "an unclassified line from zcrypto-sqlite-backup",
        None,
    ),
    Fixture(
        "hc_alloy_series_gc",
        "hc",
        {"container": "alloy", "level": "INFO"},
        'ts=2026-11-03T15:08:01.234567891Z level=info msg="series GC completed" component_path=/ component_id=prometheus.remote_write.mon subcomponent=wal duration=1.234ms',
        "INFO",
    ),
    Fixture(
        "hc_alloy_usage_report",
        "hc",
        {"container": "alloy", "level": "INFO"},
        'ts=2026-11-03T15:57:01.234567891Z level=info msg="usage report sent with success"',
        "INFO",
    ),
    Fixture("hc_alloy_start", "hc", {"container": "alloy"}, "Alloy starting in Default Engine mode", "INFO"),
    Fixture("hc_alloy_unnamed_shape", "hc", {"container": "alloy"}, "an unclassified line from alloy", None),
    Fixture(
        "hc_alloy_node_evaluation",
        "hc",
        {"container": "alloy", "level": "INFO"},
        'ts=2026-11-04T09:22:01.123456789Z level=info msg="finished node evaluation" controller_path=/ controller_id="" trace_id=0a1b2c3d4e5f60718293a4b5c6d7e8f9 node_id=prometheus.scrape.host duration=1.234567ms',
        DROP_NO_FAULT,
    ),
    Fixture(
        "hc_alloy_graph_evaluation",
        "hc",
        {"container": "alloy", "level": "INFO"},
        'ts=2026-11-04T09:22:01.234567891Z level=info msg="finished complete graph evaluation" controller_path=/ controller_id="" trace_id=0a1b2c3d4e5f60718293a4b5c6d7e8f9 duration=12.345678ms',
        "INFO",
    ),
    Fixture(
        "hc_uwsgi_body_read",
        "hc",
        {"container": "hc"},
        "[uwsgi-body-read] Error reading 65536 bytes. Content-Length: 1048576 consumed: 0 left: 1048576 message: Client closed connection",
        "WARNING",
    ),
    Fixture(
        "hc_uwsgi_starting",
        "hc",
        {"container": "hc"},
        "*** Starting uWSGI 2.0.31 (64bit) on [Mon Nov  3 17:22:01 2026] ***",
        "INFO",
    ),
    Fixture("hc_uwsgi_mode", "hc", {"container": "hc"}, "*** Operational MODE: preforking ***", "INFO"),
    Fixture("hc_uwsgi_interpreters", "hc", {"container": "hc"}, "*** uWSGI is running in multiple interpreter mode ***", "INFO"),
    Fixture(
        "hc_uwsgi_no_routing", "hc", {"container": "hc"}, "!!! no internal routing support, rebuild with pcre support !!!", "INFO"
    ),
    Fixture(
        "hc_uwsgi_ini",
        "hc",
        {"container": "hc"},
        "[uWSGI] getting INI configuration from /opt/healthchecks/docker/uwsgi.ini",
        "INFO",
    ),
    Fixture(
        "hc_uwsgi_daemon_spawning",
        "hc",
        {"container": "hc"},
        '[uwsgi-daemons] spawning "./manage.py sendalerts --skip-checks" (uid: 999 gid: 999)',
        "INFO",
    ),
    Fixture(
        "hc_uwsgi_daemon_stopping",
        "hc",
        {"container": "hc"},
        "[uwsgi-daemons] stopping daemon (pid: 42): ./manage.py sendreports --loop --skip-checks",
        "INFO",
    ),
    Fixture("hc_uwsgi_master", "hc", {"container": "hc"}, "spawned uWSGI master process (pid: 1)", "INFO"),
    Fixture("hc_uwsgi_worker_spawned", "hc", {"container": "hc"}, "spawned uWSGI worker 1 (pid: 43, cores: 1)", "INFO"),
    Fixture("hc_uwsgi_socket", "hc", {"container": "hc"}, "uwsgi socket 0 bound to TCP address :8000 fd 3", "INFO"),
    Fixture(
        "hc_uwsgi_app_ready",
        "hc",
        {"container": "hc"},
        "WSGI app 0 (mountpoint='') ready in 2 seconds on interpreter 0x7f3a12fad40e60 pid: 1 (default app)",
        "INFO",
    ),
    Fixture("hc_uwsgi_worker_buried", "hc", {"container": "hc"}, "worker 1 buried after 1 seconds", "INFO"),
    Fixture("hc_uwsgi_goodbye", "hc", {"container": "hc"}, "goodbye to uWSGI.", "INFO"),
    Fixture("hc_uwsgi_sigterm", "hc", {"container": "hc"}, "SIGINT/SIGTERM received...killing workers...", "INFO"),
    Fixture(
        "hc_uwsgi_python_version",
        "hc",
        {"container": "hc"},
        "Python version: 3.12.8 (main, Oct 15 2025, 21:12:34) [GCC 12.2.0]",
        "INFO",
    ),
    Fixture(
        "hc_uwsgi_python_interpreter", "hc", {"container": "hc"}, "Python main interpreter initialized at 0x7f3a12fad40e60", "INFO"
    ),
    Fixture("hc_uwsgi_python_threads", "hc", {"container": "hc"}, "python threads support enabled", "INFO"),
    Fixture("hc_uwsgi_chdir", "hc", {"container": "hc"}, "chdir() to /opt/healthchecks", "INFO"),
    Fixture("hc_uwsgi_clock_source", "hc", {"container": "hc"}, "clock source: unix", "INFO"),
    Fixture("hc_uwsgi_compiled", "hc", {"container": "hc"}, "compiled with version: 12.2.0 on 15 October 2025 20:41:07", "INFO"),
    Fixture("hc_uwsgi_cwd", "hc", {"container": "hc"}, "current working directory: /opt/healthchecks", "INFO"),
    Fixture("hc_uwsgi_binary_path", "hc", {"container": "hc"}, "detected binary path: /opt/venv/bin/uwsgi", "INFO"),
    Fixture("hc_uwsgi_max_fd", "hc", {"container": "hc"}, "detected max file descriptor number: 65536", "INFO"),
    Fixture("hc_uwsgi_cpu_cores", "hc", {"container": "hc"}, "detected number of CPU cores: 2", "INFO"),
    Fixture("hc_uwsgi_lock_engine", "hc", {"container": "hc"}, "lock engine: pthread robust mutexes", "INFO"),
    Fixture("hc_uwsgi_machine", "hc", {"container": "hc"}, "machine: x86_64", "INFO"),
    Fixture("hc_uwsgi_nodename", "hc", {"container": "hc"}, "nodename: 4f2a9c1e7b3d", "INFO"),
    Fixture(
        "hc_uwsgi_os",
        "hc",
        {"container": "hc"},
        "os: Linux-6.12.148+deb13-amd64 #1 SMP PREEMPT_DYNAMIC Debian 6.12.148-1 (2026-10-20)",
        "INFO",
    ),
    Fixture("hc_uwsgi_thunder_lock", "hc", {"container": "hc"}, "thunder lock: enabled", "INFO"),
    Fixture("hc_uwsgi_mapped", "hc", {"container": "hc"}, "mapped 416880 bytes (407 KB) for 4 cores", "INFO"),
    Fixture("hc_uwsgi_body_buffering", "hc", {"container": "hc"}, "setting request body buffering size to 65536 bytes", "INFO"),
    Fixture("hc_uwsgi_page_size", "hc", {"container": "hc"}, "your memory page size is 4096 bytes", "INFO"),
    Fixture("hc_uwsgi_mercy", "hc", {"container": "hc"}, "your mercy for graceful operations on workers is 60 seconds", "INFO"),
    Fixture(
        "hc_uwsgi_listen_backlog",
        "hc",
        {"container": "hc"},
        "your server socket listen backlog is limited to 100 connections",
        "INFO",
    ),
    Fixture("hc_uwsgi_exec_migrate", "hc", {"container": "hc"}, 'running "exec:./manage.py migrate" (asap)...', "INFO"),
    Fixture("hc_migrate_operations", "hc", {"container": "hc"}, "Operations to perform:", "INFO"),
    Fixture(
        "hc_migrate_apply_all",
        "hc",
        {"container": "hc"},
        "  Apply all migrations: accounts, admin, api, auth, contenttypes, sessions",
        "INFO",
    ),
    Fixture("hc_migrate_running", "hc", {"container": "hc"}, "Running migrations:", "INFO"),
    Fixture("hc_migrate_applying", "hc", {"container": "hc"}, "  Applying api.0001_initial... OK", "INFO"),
    Fixture("hc_migrate_none", "hc", {"container": "hc"}, "  No migrations to apply.", "INFO"),
    Fixture(
        "ops_tape_bars_summary",
        "ops",
        {"container": "zcrypto-tape-bars"},
        "days_written=1 days_skipped=0 days_unsettled=0 days_unhealed=0 days_gap=0 rows=4320 errors=0",
        "INFO",
    ),
    Fixture("ops_tape_bars_head", "ops", {"container": "zcrypto-tape-bars"}, "head=2026-11-02 days_written=1 holes=0", "INFO"),
    Fixture(
        "ops_tape_bars_day_error",
        "ops",
        {"container": "zcrypto-tape-bars"},
        "  ERROR BTC/EUR 2026-11-02: no settled trades file for the day",
        "ERROR",
    ),
    Fixture(
        "ops_tape_bars_docker_refusal",
        "ops",
        {"container": "zcrypto-tape-bars"},
        'docker: Error response from daemon: Conflict. The container name "/zcrypto-tape-bars" is already in use by container "0123abcd".',
        None,
    ),
    Fixture(
        "ops_verified_replay_ok",
        "ops",
        {"container": "zcrypto-verified-replay"},
        "2026-11-02T00:00:00+00:00  ok (worst |diff| 0.00e+00)",
        "INFO",
    ),
    Fixture(
        "ops_verified_replay_mismatch",
        "ops",
        {"container": "zcrypto-verified-replay"},
        "2026-11-02T04:00:00+00:00  MISMATCH: worst BTC |diff| 1.20e-03",
        "WARNING",
    ),
    Fixture(
        "ops_verified_replay_invalid",
        "ops",
        {"container": "zcrypto-verified-replay"},
        "2026-11-02T08:00:00+00:00  VALIDATION-FAILED: cycle record carries no final targets",
        "WARNING",
    ),
    Fixture(
        "ops_verified_replay_failed_cycle",
        "ops",
        {"container": "zcrypto-verified-replay"},
        "2026-11-02T12:00:00+00:00  failed cycle (venue read failed)",
        "INFO",
    ),
    Fixture(
        "ops_verified_replay_summary",
        "ops",
        {"container": "zcrypto-verified-replay"},
        "replayed 6 success record(s) via the verified path: 6 ok, 0 mismatch(es), 0 validation failure(s); 0 failed cycle(s) (sidecars)",
        "INFO",
    ),
    Fixture("ops_verified_replay_none_found", "ops", {"container": "zcrypto-verified-replay"}, "no journaled cycles found", "INFO"),
    Fixture(
        "ops_verified_replay_capped",
        "ops",
        {"container": "zcrypto-verified-replay"},
        "verified-replay: capped at 30 day(s) this run; 4 day(s) still unverified, resuming tomorrow",
        "INFO",
    ),
    Fixture(
        "ops_verified_replay_journal_behind",
        "ops",
        {"container": "zcrypto-verified-replay"},
        "verified-replay: journal has not caught up: /mnt/zhao-crypto/engine-journal/2026-11-02 holds no cycle artifacts; stopping without advancing the watermark (day 2026-11-02 retries next run)",
        "WARNING",
    ),
    Fixture(
        "ops_verified_replay_freshness_unproven",
        "ops",
        {"container": "zcrypto-verified-replay"},
        "verified-replay: journal freshness unproven: no 2026-11-03 artifacts yet, so 2026-11-02 may be partially pulled; stopping without advancing the watermark (day 2026-11-02 retries next run)",
        "WARNING",
    ),
    Fixture(
        "ops_verified_replay_corrupt_evidence",
        "ops",
        {"container": "zcrypto-verified-replay"},
        "2026-11-02T16:00:00+00:00  MISMATCH (corrupt evidence): content hash mismatch for pair='BTC/EUR' grid='240' -- corrupt evidence",
        "WARNING",
    ),
    Fixture(
        "ops_verified_replay_structural",
        "ops",
        {"container": "zcrypto-verified-replay"},
        "2026-11-02T20:00:00+00:00  MISMATCH: structural (asset sets differ)",
        "WARNING",
    ),
    Fixture(
        "ops_verified_replay_unnamed_shape",
        "ops",
        {"container": "zcrypto-verified-replay"},
        "an unclassified line from zcrypto-verified-replay",
        None,
    ),
    Fixture(
        "ops_verify_replay_census",
        "ops",
        {"container": "zcrypto-verify-replay"},
        "verify-replay census replayed=12 reused=8748 audited=24 mismatches=0 pending=0 evicted=0 duration_s=312",
        DROP,
    ),
    Fixture(
        "ops_verify_replay_summary", "ops", {"container": "zcrypto-verify-replay"}, "replayed 8772 hour(s): 8772 ok, 0 failed", DROP
    ),
    Fixture(
        "ops_verify_replay_audit_mismatch",
        "ops",
        {"container": "zcrypto-verify-replay"},
        "AUDIT MISMATCH  BTC/EUR 2026-11-02T13  -- the re-replayed hour disagrees with the verdict served from cache",
        "WARNING",
    ),
    Fixture(
        "ops_verify_replay_unnamed_shape",
        "ops",
        {"container": "zcrypto-verify-replay"},
        "an unclassified line from zcrypto-verify-replay",
        None,
    ),
    Fixture(
        "ops_archive_pull_backfill_echo",
        "ops",
        {"container": "zcrypto-archive-pull"},
        "trade backfill complete pairs=10 gaps=0 trades_missing=0 duplicate_rows_found=0 recovered=0 unrecoverable=0 deferred=0 fetch_failed=0 mint_failed=0 duplicates_collapsed=0 duplicates_cross_hour=0 hours_minted=0 hours_repaired_after_loss=0 errors=0",
        DROP,
    ),
    Fixture("ops_archive_pull_traceback", "ops", {"container": "zcrypto-archive-pull"}, "Traceback (most recent call last):", None),
    Fixture(
        "ops_alloy_node_evaluation",
        "ops",
        {"container": "alloy", "level": "INFO"},
        'ts=2026-11-04T09:22:01.123456789Z level=info msg="finished node evaluation" controller_path=/ controller_id="" trace_id=0a1b2c3d4e5f60718293a4b5c6d7e8f9 node_id=loki.source.journal.zcrypto_units duration=1.234567ms',
        DROP_NO_FAULT,
    ),
    Fixture(
        "ops_alloy_graph_evaluation",
        "ops",
        {"container": "alloy", "level": "INFO"},
        'ts=2026-11-04T09:22:01.234567891Z level=info msg="finished complete graph evaluation" controller_path=/ controller_id="" trace_id=0a1b2c3d4e5f60718293a4b5c6d7e8f9 duration=12.345678ms',
        "INFO",
    ),
    Fixture(
        "capture_prune_done",
        "capture",
        {"container": "zcrypto-capture-prune"},
        'zcrypto-capture-prune: deleted=24 retention_days=14 cutoff="2026-10-20 03:17:01 UTC" dir=/var/lib/zcrypto-capture',
        "INFO",
    ),
    Fixture(
        "capture_prune_refused",
        "capture",
        {"container": "zcrypto-capture-prune"},
        "capture data dir not found: /var/lib/zcrypto-capture",
        "ERROR",
    ),
    Fixture(
        "engine_journal_prune_done",
        "capture",
        {"container": "zcrypto-engine-journal-prune"},
        'zcrypto-engine-journal-prune: deleted=1 kept=30 retention_days=30 cutoff="2026-10-04 UTC" dir=/var/lib/zcrypto-engine/journal',
        "INFO",
    ),
    Fixture(
        "engine_journal_prune_refused",
        "capture",
        {"container": "zcrypto-engine-journal-prune"},
        "engine journal dir not found: /var/lib/zcrypto-engine/journal",
        "ERROR",
    ),
    Fixture(
        "cache_proxy_server_up",
        "capture",
        {"container": "cache-proxy"},
        'Server votes-node2/via-node3 is UP, reason: Layer7 check passed, code: 0, info: "(tcp-check)", check duration: 2ms. 3 active and 0 backup servers online. 0 sessions requeued, 0 total in queue.',
        DROP,
    ),
    Fixture(
        "cache_proxy_server_down",
        "capture",
        {"container": "cache-proxy"},
        'Server votes-node2/via-node3 is DOWN, reason: Layer4 timeout, info: " at step 1 of tcp-check (connect)", check duration: 2001ms. 2 active and 0 backup servers left. 0 sessions active, 0 requeued, 0 remaining in queue.',
        DROP,
    ),
    Fixture(
        "cache_proxy_route_down",
        "capture",
        {"container": "cache-proxy"},
        'Server node2/valkey is DOWN, reason: Layer7 wrong status, code: 503, info: "Service Unavailable", check duration: 0ms. 0 active and 0 backup servers left. 2 sessions active, 0 requeued, 0 remaining in queue.',
        DROP,
    ),
    Fixture(
        "cache_proxy_proxy_stopped",
        "capture",
        {"container": "cache-proxy"},
        "Proxy node1 stopped (cumulated conns: FE: 0, BE: 12).",
        DROP,
    ),
    Fixture("cache_proxy_no_server", "capture", {"container": "cache-proxy"}, "backend node1 has no server available!", DROP),
    Fixture(
        "cache_proxy_session",
        "capture",
        {"container": "cache-proxy"},
        "192.0.2.10:51234 [03/Nov/2026:14:14:05.123] cache node2/valkey 1/0/3601234 1234 -- 1/1/0/0/0 0/0",
        "INFO",
    ),
    Fixture(
        "cache_proxy_session_cut",
        "capture",
        {"container": "cache-proxy"},
        "192.0.2.10:51236 [03/Nov/2026:14:19:02.456] cache node2/valkey 1/0/1201 87 DC 2/2/1/1/0 0/0",
        "INFO",
    ),
    Fixture("cache_proxy_unnamed_shape", "capture", {"container": "cache-proxy"}, "an unclassified line from cache-proxy", None),
    Fixture(
        "capture_alloy_node_evaluation",
        "capture",
        {"container": "alloy", "level": "INFO"},
        'ts=2026-11-04T09:22:01.123456789Z level=info msg="finished node evaluation" controller_path=/ controller_id="" trace_id=0a1b2c3d4e5f60718293a4b5c6d7e8f9 node_id=loki.source.journal.capture_units duration=1.234567ms',
        DROP_NO_FAULT,
    ),
    Fixture(
        "capture_alloy_graph_evaluation",
        "capture",
        {"container": "alloy", "level": "INFO"},
        'ts=2026-11-04T09:22:01.234567891Z level=info msg="finished complete graph evaluation" controller_path=/ controller_id="" trace_id=0a1b2c3d4e5f60718293a4b5c6d7e8f9 duration=12.345678ms',
        "INFO",
    ),
    Fixture(
        "cache_valkey_sigterm",
        "cache",
        {"container": "valkey"},
        "1:signal-handler (1762161901) Received SIGTERM scheduling shutdown...",
        "WARNING",
    ),
    Fixture(
        "cache_sentinel_sigterm",
        "cache",
        {"container": "sentinel"},
        "1:signal-handler (1762161901) Received SIGTERM scheduling shutdown...",
        "WARNING",
    ),
    Fixture(
        "cache_valkey_monotonic", "cache", {"container": "valkey"}, "monotonic: x86 linux, 'constant_tsc' flag not present", "INFO"
    ),
    Fixture(
        "cache_sentinel_monotonic",
        "cache",
        {"container": "sentinel"},
        "monotonic: x86 linux, 'constant_tsc' flag not present",
        "INFO",
    ),
    Fixture("cache_valkey_crash_report", "cache", {"container": "valkey"}, "------ STACK TRACE ------", None),
    Fixture("cache_sentinel_crash_report", "cache", {"container": "sentinel"}, "------ STACK TRACE ------", None),
    Fixture(
        "cache_alloy_node_evaluation",
        "cache",
        {"container": "alloy", "level": "INFO"},
        'ts=2026-11-04T09:22:01.123456789Z level=info msg="finished node evaluation" controller_path=/ controller_id="" trace_id=0a1b2c3d4e5f60718293a4b5c6d7e8f9 node_id=loki.source.journal.cache_units duration=1.234567ms',
        DROP_NO_FAULT,
    ),
    Fixture(
        "cache_alloy_graph_evaluation",
        "cache",
        {"container": "alloy", "level": "INFO"},
        'ts=2026-11-04T09:22:01.234567891Z level=info msg="finished complete graph evaluation" controller_path=/ controller_id="" trace_id=0a1b2c3d4e5f60718293a4b5c6d7e8f9 duration=12.345678ms',
        "INFO",
    ),
    Fixture(
        "nas_archive_pull_file_vanished",
        "nas",
        {"container": "archive-pull"},
        'file has vanished: "/var/lib/zcrypto-capture/BTC/EUR/book/2026/10/23/14.part3.parquet"',
        "WARNING",
    ),
    Fixture(
        "nas_archive_pull_rsync_warning",
        "nas",
        {"container": "archive-pull"},
        "rsync warning: some files vanished before they could be transferred (code 24) at main.c(1338) [generator=3.4.1]",
        "WARNING",
    ),
    Fixture(
        "nas_archive_pull_rsync_error",
        "nas",
        {"container": "archive-pull"},
        "rsync error: unexplained error (code 255) at io.c(232) [Receiver=3.4.1]",
        "WARNING",
    ),
    Fixture(
        "nas_archive_pull_connection_closed",
        "nas",
        {"container": "archive-pull"},
        "rsync: connection unexpectedly closed (0 bytes received so far) [Receiver]",
        "WARNING",
    ),
    Fixture(
        "nas_archive_pull_ssh_resolve",
        "nas",
        {"container": "archive-pull"},
        "ssh: Could not resolve hostname zcrypto-red.zhaow.me: Temporary failure in name resolution",
        "WARNING",
    ),
    Fixture(
        "nas_archive_pull_ssh_connect",
        "nas",
        {"container": "archive-pull"},
        "ssh: connect to host zcrypto-red.zhaow.me port 22: Cannot assign requested address",
        "WARNING",
    ),
    Fixture("nas_archive_pull_host_key", "nas", {"container": "archive-pull"}, "Host key verification failed.", None),
    Fixture("nas_archive_pull_traceback", "nas", {"container": "archive-pull"}, "Traceback (most recent call last):", None),
    Fixture(
        "nas_alloy_node_evaluation",
        "nas",
        {"container": "alloy", "level": "INFO"},
        'ts=2026-11-04T09:22:01.123456789Z level=info msg="finished node evaluation" controller_path=/ controller_id="" trace_id=0a1b2c3d4e5f60718293a4b5c6d7e8f9 node_id=loki.source.journal.containers duration=1.234567ms',
        DROP_NO_FAULT,
    ),
    Fixture(
        "nas_alloy_graph_evaluation",
        "nas",
        {"container": "alloy", "level": "INFO"},
        'ts=2026-11-04T09:22:01.234567891Z level=info msg="finished complete graph evaluation" controller_path=/ controller_id="" trace_id=0a1b2c3d4e5f60718293a4b5c6d7e8f9 duration=12.345678ms',
        "INFO",
    ),
]

_STRING = r'"((?:[^"\\]|\\.)*)"'
_LABEL_OPS = {
    "=": lambda value, want: value == want,
    "!=": lambda value, want: value != want,
    "=~": lambda value, want: re.fullmatch(want, value) is not None,
    "!~": lambda value, want: re.fullmatch(want, value) is None,
}
_LINE_OPS = {
    "|=": lambda line, want: want in line,
    "!=": lambda line, want: want not in line,
    "|~": lambda line, want: re.search(want, line) is not None,
    "!~": lambda line, want: re.search(want, line) is None,
}


def _unquote(literal: str) -> str:
    """A LogQL string literal's value; the model reads the configs' two escapes and refuses any other."""
    assert re.fullmatch(r'(?:[^\\]|\\[\\"])*', literal), f"an unmodelled escape: {literal!r}"
    return re.sub(r"\\(.)", r"\1", literal)


def selector(text: str) -> tuple[list[tuple[str, str, str]], list[tuple[str, str]]]:
    """A stream selector's label matchers and the line filters after it, each value unquoted."""
    m = re.fullmatch(r"\{([^}]*)\}((?:\s*(?:\|=|\|~|!=|!~)\s*" + _STRING + r")*)\s*", text)
    assert m, f"a selector the model does not read whole: {text!r}"
    matchers = re.findall(r"(\w+)\s*(=~|!~|!=|=)\s*" + _STRING, m.group(1))
    assert ", ".join(f'{k}{op}"{v}"' for k, op, v in matchers) == m.group(1).strip(), m.group(1)
    filters = re.findall(r"(\|=|\|~|!=|!~)\s*" + _STRING, m.group(2))
    return [(k, op, _unquote(v)) for k, op, v in matchers], [(op, _unquote(v)) for op, v in filters]


def _admits(text: str, labels: dict[str, str], line: str) -> bool:
    matchers, filters = selector(text)
    return all(_LABEL_OPS[op](labels.get(k, ""), v) for k, op, v in matchers) and all(_LINE_OPS[op](line, v) for op, v in filters)


def _top_blocks(host: str) -> list[str]:
    return _blocks(_parse_body(live_alloy_text(CONFIGS[host])), "stage.match")


def _keys_on_level(block: str) -> bool:
    return any(k == "level" for k, _, _ in selector(_assigned(block, "selector"))[0])


def _static_level(block: str) -> str | None:
    m = re.search(r'stage\.static_labels \{\s*values = \{ level = "([A-Z]+)" \}', block)
    return m and m.group(1)


def _drop(block: str) -> str:
    level_matchers = [(op, v) for k, op, v in selector(_assigned(block, "selector"))[0] if k == "level"]
    return DROP if all(_LABEL_OPS[op]("", v) for op, v in level_matchers) else DROP_NO_FAULT


def level_blocks(host: str) -> list[tuple[str, str]]:
    """The host's top-level blocks that key on `level`, in pipeline order: each selector with its level, or the drop it
    makes."""
    out = []
    for block in _top_blocks(host):
        if not _keys_on_level(block):
            continue
        if _assigned(block, "action") == "drop":
            out.append((_assigned(block, "selector"), _drop(block)))
            continue
        assert len(_stage_blocks(block)) == 1 and _static_level(block), f"a level-keyed block the model does not read:\n{block}"
        out.append((_assigned(block, "selector"), _static_level(block)))
    return out


def model(host: str, labels: dict[str, str], line: str) -> str | None:
    """The level the host's level-keyed blocks leave on a line, None for none, DROP or DROP_NO_FAULT for a dropped line."""
    labels = dict(labels)
    for text, action in level_blocks(host):
        if _admits(text, labels, line):
            if action in (DROP, DROP_NO_FAULT):
                return action
            labels["level"] = action
    return labels.get("level")


def _level_name(value: str | None) -> str | None:
    """The `level` label the fleet's template stage renders from a parsed value."""
    return value and {"warn": "WARNING", "fatal": "CRITICAL"}.get(value, value.upper())


def _logfmt_level(line: str) -> str | None:
    m = re.search(r"(?:^| )level=(\w+)(?: |$)", line)
    return _level_name(m and m.group(1))


def _parser(host: str, labels: dict[str, str], line: str) -> str | None:
    """The block of the host's that parsed the line: for a `cache-proxy` line the one named `cache_proxy`, whose own
    stages set that container label; else the first that keys on no level and admits it."""
    if labels.get("container") == "cache-proxy":
        return next(b for b in _top_blocks(host) if _assigned(b, "pipeline_name") == "cache_proxy")
    blocks = [b for b in _top_blocks(host) if not _keys_on_level(b)]
    return next((b for b in blocks if _admits(_assigned(b, "selector"), labels, line)), None)


def _parsed_level(host: str, labels: dict[str, str], line: str) -> str | None:
    """The level the host's parse leaves on a line, read through the expressions its config carries."""
    block = _parser(host, labels, line)
    if block is None:
        return None
    if "stage.logfmt" in block:
        return _logfmt_level(line)
    if "stage.json" in block:
        (key,) = re.findall(r'expressions = \{ level = "(\w+)" \}', block)
        try:
            record = json.loads(line)
        except ValueError:
            return None
        value = record.get(key) if isinstance(record, dict) else None
        return _level_name(value) if "stage.template" in block else value
    if _assigned(block, "pipeline_name") == "cache_proxy":
        (expression,) = [e for e in re.findall(r'expression = "((?:[^"\\]|\\.)*)"', block) if "?P<level>" in e]
        m = re.search(_unquote(expression), line)
        return m and {"ALERT": "CRITICAL", "NOTICE": "INFO"}.get(m.group("level"), m.group("level"))
    (expression,) = re.findall(r'expression = "((?:[^"\\]|\\.)*)"', block)
    m = re.search(_unquote(expression), line)
    if m is None:
        return None
    if "level" in m.groupdict():
        return m.group("level").upper()
    return {"#": "WARNING", ".": "DEBUG"}.get(m.group("mark"), "INFO")


@pytest.mark.parametrize("fixture", [pytest.param(f, id=f.id) for f in FIXTURES])
def test_each_line_takes_the_level_its_source_reports(fixture):
    assert model(fixture.host, fixture.labels, fixture.line) == fixture.expected


@pytest.mark.parametrize("fixture", [pytest.param(f, id=f.id) for f in FIXTURES])
def test_each_line_reaches_the_level_stages_as_its_hosts_parse_leaves_it(fixture):
    assert _parsed_level(fixture.host, fixture.labels, fixture.line) == fixture.labels.get("level")


def test_a_level_is_set_after_every_parse():
    for host in CONFIGS:
        keyed = [_keys_on_level(b) for b in _top_blocks(host)]
        parses = [i for i, k in enumerate(keyed) if not k]
        levels = [i for i, k in enumerate(keyed) if k]
        assert not levels or max(parses) < min(levels), f"{host}: a parse runs after a level stage, blocks {parses} and {levels}"


def test_a_trailing_stage_sets_a_level_only_where_none_is_set():
    for host in CONFIGS:
        for block in _top_blocks(host):
            if _static_level(block):
                on_level = {m for m in selector(_assigned(block, "selector"))[0] if m[0] == "level"}
                assert on_level == {("level", "=", "")}, (host, block)


def test_no_alloy_config_reads_the_journal_priority():
    readers = [c.relative_to(REPO).as_posix() for c in ALLOY_CONFIGS if "__journal_priority" in live_alloy_text(c)]
    assert not readers, f"the journal's priority is no line's level: {readers}"


def _alloy_match(host: str) -> str:
    (match,) = [b for b in _top_blocks(host) if _assigned(b, "selector") == '{container="alloy"}']
    return match


def test_the_dead_man_nodes_alloy_parses_its_logfmt_as_the_fleets_do():
    hc, fleet = ([" ".join(stage.split()) for stage in _stage_blocks(_alloy_match(host))] for host in ("hc", "cache"))
    assert hc == fleet


# --- the same blocks, through Alloy itself ---------------------------------------------------------------------------
@pytest.mark.parametrize("host", sorted({f.host for f in FIXTURES}))
def test_alloy_itself_agrees_with_the_level_model(host, tmp_path):
    if no_binary("alloy"):
        pytest.skip("no alloy binary on PATH; the model above is the guard, this is its check against the real stage engine")
    fixtures = [f for f in FIXTURES if f.host == host]
    keys = list(dict.fromkeys(json.dumps(f.labels, sort_keys=True) for f in fixtures))
    groups = [
        (json.loads(k) | {"host": host}, [f.line for f in fixtures if json.dumps(f.labels, sort_keys=True) == k]) for k in keys
    ]
    blocks = [b for b in _top_blocks(host) if _keys_on_level(b)]
    expected = [
        [
            (f.expected, f.line)
            for f in fixtures
            if json.dumps(f.labels, sort_keys=True) == k and f.expected not in (DROP, DROP_NO_FAULT)
        ]
        for k in keys
    ]
    survivors = _run_alloy(shutil.which("alloy"), tmp_path, groups, blocks)
    assert [[(echoed.get("level"), entry) for echoed, entry in group] for group in survivors] == expected


# Each dropped copy beside the line its source ships levelled: the logged record on ops, HAProxy's stderr copy on the
# engine host.
TWINS = {
    "ops_verify_replay_census": "2026-11-03 02:31:07,123 INFO zcrypto.archive.command [command.py:1305] - verify-replay census replayed=12 reused=8748 audited=24 mismatches=0 pending=0 evicted=0 duration_s=312",
    "ops_verify_replay_summary": "2026-11-03 02:31:07,124 INFO zcrypto.archive.command [command.py:1331] - verify-replay complete hours=8772 ok=8772 failed=0",
    "ops_archive_pull_backfill_echo": "2026-11-03 00:14:05,123 INFO zcrypto.trades.backfill [backfill.py:300] - trade backfill complete pairs=10 gaps=0 trades_missing=0 duplicate_rows_found=0 recovered=0 unrecoverable=0 deferred=0 fetch_failed=0 mint_failed=0 duplicates_collapsed=0 duplicates_cross_hour=0 hours_minted=0 hours_repaired_after_loss=0 errors=0",
    "cache_proxy_server_up": '[WARNING]  (8) : Server votes-node2/via-node3 is UP, reason: Layer7 check passed, code: 0, info: "(tcp-check)", check duration: 2ms. 3 active and 0 backup servers online. 0 sessions requeued, 0 total in queue.',
    "cache_proxy_server_down": '[WARNING]  (8) : Server votes-node2/via-node3 is DOWN, reason: Layer4 timeout, info: " at step 1 of tcp-check (connect)", check duration: 2001ms. 2 active and 0 backup servers left. 0 sessions active, 0 requeued, 0 remaining in queue.',
    "cache_proxy_route_down": '[WARNING]  (3609811) : Server node2/valkey is DOWN, reason: Layer7 wrong status, code: 503, info: "Service Unavailable", check duration: 0ms. 0 active and 0 backup servers left. 2 sessions active, 0 requeued, 0 remaining in queue.',
    "cache_proxy_proxy_stopped": "[WARNING]  (8) : Proxy node1 stopped (cumulated conns: FE: 0, BE: 12).",
    "cache_proxy_no_server": "[ALERT]    (8) : backend 'node1' has no server available!",
}


@pytest.mark.parametrize("fixture", [pytest.param(f, id=f.id) for f in FIXTURES if f.expected == DROP])
def test_a_dropped_line_is_a_copy_its_source_ships_with_a_level(fixture):
    assert set(TWINS) == {f.id for f in FIXTURES if f.expected == DROP}
    assert _parsed_level(fixture.host, fixture.labels, TWINS[fixture.id]) in {"INFO", "WARNING", "CRITICAL"}


NEAR_MISSES = {
    "mon_grafana_panel_cancelled": "mon_grafana_panel_failed",
    "mon_grafana_loki_connection_closed": "mon_grafana_loki_connection_reset",
    "mon_grafana_loki_request_summary": "mon_grafana_prometheus_request_summary",
    "mon_loki_mapping_cancelled": "mon_loki_mapping_failed",
    "mon_loki_scheduler_cancelled": "mon_loki_scheduler_unavailable",
    "mon_loki_scheduler_eof": "mon_loki_scheduler_notify_failed",
    "mon_loki_health_check_closing": "mon_loki_health_check_failed",
    "mon_loki_schema_overlap_sliver": "mon_loki_series_limit",
    "mon_grafana_quotas_501": "mon_grafana_quotas_500",
    "mon_grafana_contact_point_test": "mon_grafana_notifier_failure",
    "mon_grafana_plugin_stop": "mon_grafana_plugin_killed",
    "mon_alloy_node_evaluation": "mon_alloy_graph_evaluation",
    "hc_alloy_node_evaluation": "hc_alloy_graph_evaluation",
    "ops_alloy_node_evaluation": "ops_alloy_graph_evaluation",
    "capture_alloy_node_evaluation": "capture_alloy_graph_evaluation",
    "cache_alloy_node_evaluation": "cache_alloy_graph_evaluation",
    "nas_alloy_node_evaluation": "nas_alloy_graph_evaluation",
}


@pytest.mark.parametrize("fixture", [pytest.param(f, id=f.id) for f in FIXTURES if f.expected == DROP_NO_FAULT])
def test_a_no_fault_drop_leaves_a_near_miss_of_its_source_at_its_level(fixture):
    assert set(NEAR_MISSES) == {f.id for f in FIXTURES if f.expected == DROP_NO_FAULT}
    (near,) = [f for f in FIXTURES if f.id == NEAR_MISSES[fixture.id]]
    assert (near.host, near.labels) == (fixture.host, fixture.labels)
    assert model(near.host, near.labels, near.line) == near.labels["level"]


def test_the_node_counts_each_grafana_or_loki_drop_under_a_reason_its_runbook_names():
    runbook = (REPO / "infra/runbooks/mon.md").read_text()
    reasons = [
        _assigned(b, "drop_counter_reason")
        for b in _top_blocks("mon")
        if _assigned(b, "action") == "drop"
        and any(
            k == "container" and set(v.split("|")) & {"grafana-server", "loki"} for k, _, v in selector(_assigned(b, "selector"))[0]
        )
    ]
    assert len(reasons) == len(set(reasons)) == 9, reasons
    assert all(r and re.search(rf'reason="{r}"|`{r}`', runbook) for r in reasons), reasons


def test_every_no_fault_drop_admits_a_fixture_with_a_near_miss():
    for host in CONFIGS:
        for text, action in level_blocks(host):
            if action == DROP_NO_FAULT:
                assert any(f.host == host and f.id in NEAR_MISSES and _admits(text, f.labels, f.line) for f in FIXTURES), (
                    host,
                    text,
                )


MEASURED = {
    ("mon", "zcrypto-mon-selfcheck"),
    ("mon", "alloy"),
    ("mon", "caddy"),
    ("mon", "grafana-server"),
    ("hc", "zcrypto-hc-selfcheck"),
    ("hc", "zcrypto-sqlite-backup"),
    ("hc", "hc"),
    ("hc", "alloy"),
    ("ops", "zcrypto-tape-bars"),
    ("ops", "zcrypto-verified-replay"),
    ("ops", "zcrypto-verify-replay"),
    ("ops", "zcrypto-archive-pull"),
    ("capture", "zcrypto-capture-prune"),
    ("capture", "zcrypto-engine-journal-prune"),
    ("capture", "cache-proxy"),
    ("cache", "valkey"),
    ("cache", "sentinel"),
    ("nas", "archive-pull"),
}


def test_the_fixtures_hold_every_source_the_30_day_read_found_without_a_level():
    covered = {(f.host, f.labels["container"]) for f in FIXTURES if "level" not in f.labels and f.expected is not None}
    assert sorted(MEASURED - covered) == []
