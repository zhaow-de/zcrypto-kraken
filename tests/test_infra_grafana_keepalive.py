"""The keep-alive runner's output, rendered through Ansible's own `Templar` and run against a stub `curl`."""

import pathlib
import re
import subprocess

import pytest
import yaml

from tests.test_infra_shell_templates_render import ansible_render, role_variables

TEMPLATE = pathlib.Path(__file__).resolve().parent.parent / "infra/ansible/roles/ops/templates/grafana-keepalive.sh.j2"


def _run(tmp_path, curl_body, *, token="tok", prom_seed=None, want_stdout=False):
    """Render the script with `ops_textfile_dir` pointed at `tmp_path`, run it against a stub curl,
    and return the metrics it wrote (empty for no file), and its stdout and stderr if asked."""
    variables = role_variables(TEMPLATE)
    variables["ops_textfile_dir"] = str(tmp_path)
    script = tmp_path / "keepalive.sh"
    script.write_text(ansible_render(TEMPLATE.read_text(), variables))
    script.chmod(0o755)

    stub_dir = tmp_path / "bin"
    stub_dir.mkdir()
    curl = stub_dir / "curl"
    curl.write_text(curl_body)
    curl.chmod(0o755)

    prom = tmp_path / "grafana-keepalive.prom"
    if prom_seed is not None:
        prom.write_text(prom_seed)

    env = {
        "PATH": f"{stub_dir}:/usr/bin:/bin",
        "ZCRYPTO_GRAFANA_KEEPALIVE_TOKEN": token,
    }
    result = subprocess.run([str(script)], env=env, capture_output=True, text=True)
    assert result.returncode == 0, f"the runner must not fail the unit: {result.stderr}"
    metrics = (
        {line.split()[0]: line.split()[1] for line in prom.read_text().splitlines() if line and not line.startswith("#")}
        if prom.exists()
        else {}
    )
    return (metrics, result.stdout, result.stderr) if want_stdout else metrics


def test_a_success_is_recorded_with_its_duration_and_both_stamps(tmp_path):
    metrics = _run(tmp_path, '#!/bin/sh\nprintf "200 0.412"\n')

    assert metrics["zcrypto_grafana_keepalive_status"] == "200"
    assert metrics["zcrypto_grafana_keepalive_duration_seconds"] == "0.412"
    run = int(metrics["zcrypto_grafana_keepalive_last_run_timestamp_seconds"])
    assert run > 1_700_000_000, "a real unix stamp, not a placeholder"
    assert metrics["zcrypto_grafana_keepalive_last_success_timestamp_seconds"] == str(run)


def test_the_token_is_delivered_on_stdin_and_never_in_argv(tmp_path):
    """The runner engages curl's stdin config, puts the token in it, and passes no token in argv --
    /proc/<pid>/cmdline is world-readable where /proc/<pid>/environ, which carries the value, is not."""
    metrics = _run(
        tmp_path,
        "#!/bin/sh\n"
        'd="$(dirname "$0")"\n'
        "tr '\\0' '\\n' < /proc/self/cmdline > \"$d/argv.txt\"\n"
        'cat > "$d/stdin.txt"\n'
        "printf '200 0.412\\n'\n",
        token="glsa_NotARealToken_aB3-xY9",
    )
    argv = (tmp_path / "bin" / "argv.txt").read_text()
    stdin = (tmp_path / "bin" / "stdin.txt").read_text()

    # The true positive first: a runner that simply stopped sending the header would pass the
    # absence assertion below while authenticating nothing.
    assert 'header = "Authorization: Bearer glsa_NotARealToken_aB3-xY9"' in stdin
    # Without `--config -` curl never reads that stdin, and both assertions below still pass while
    # every call goes out unauthenticated.
    args = argv.split("\n")
    assert "--config" in args, f"curl was not told to read a config at all: {argv}"
    assert args[args.index("--config") + 1] == "-", f"curl reads its config from elsewhere: {argv}"
    assert "glsa_NotARealToken_aB3-xY9" not in argv, f"the token reached argv: {argv}"
    assert metrics["zcrypto_grafana_keepalive_status"] == "200"


def test_a_curl_that_ends_its_write_out_with_a_newline_is_read_the_same(tmp_path):
    """Real curl ends its write-out with a newline."""
    metrics = _run(tmp_path, '#!/bin/sh\nprintf "200 0.412\\n"\n')

    assert metrics["zcrypto_grafana_keepalive_status"] == "200"
    assert metrics["zcrypto_grafana_keepalive_duration_seconds"] == "0.412"


def test_a_503_is_recorded_rather_than_swallowed(tmp_path):
    """`curl -f` would have made a 503 an error exit with no data instead."""
    metrics = _run(tmp_path, '#!/bin/sh\nprintf "503 12.8"\n')

    assert metrics["zcrypto_grafana_keepalive_status"] == "503"
    assert metrics["zcrypto_grafana_keepalive_duration_seconds"] == "12.8"
    assert metrics["zcrypto_grafana_keepalive_last_success_timestamp_seconds"] == "0", "no 200 yet"


@pytest.mark.parametrize(
    ("curl_body", "line"),
    [('#!/bin/sh\nprintf "503 0.419"\n', "status=503 duration=0.419s"), ("#!/bin/sh\nexit 7\n", "status=0 duration=0s")],
)
def test_each_run_logs_its_result_to_the_journal(tmp_path, curl_body, line):
    _, stdout, _ = _run(tmp_path, curl_body, want_stdout=True)
    assert stdout.splitlines() == [line], stdout


def test_an_unreachable_host_writes_the_failure_rather_than_nothing(tmp_path):
    """A missing file is `(no series)`, which reads as an absent exporter rather than a failed call --
    so a curl that never got a status must still leave a sample saying so."""
    metrics = _run(tmp_path, '#!/bin/sh\nprintf "000 0.000"\nexit 6\n')

    assert metrics["zcrypto_grafana_keepalive_status"] == "0"
    assert int(metrics["zcrypto_grafana_keepalive_last_run_timestamp_seconds"]) > 1_700_000_000


def test_a_curl_that_writes_nothing_at_all_still_leaves_a_sample(tmp_path):
    """`-w` writes nothing if curl dies before the write-out; the parse publishes 0 rather than an
    empty value, which would leave this file unscrapeable."""
    metrics = _run(tmp_path, "#!/bin/sh\nexit 7\n")

    assert metrics["zcrypto_grafana_keepalive_status"] == "0"
    assert metrics["zcrypto_grafana_keepalive_duration_seconds"] == "0"


def test_a_failed_run_carries_the_previous_success_stamp_forward(tmp_path):
    """Resetting it to 0 on every failure would make `time() - last_success` measure the run, not the
    gap -- and the gap is the whole question a hibernation asks."""
    seed = "zcrypto_grafana_keepalive_last_success_timestamp_seconds 1757000000\n"
    metrics = _run(tmp_path, '#!/bin/sh\nprintf "503 1.0"\n', prom_seed=seed)

    assert metrics["zcrypto_grafana_keepalive_last_success_timestamp_seconds"] == "1757000000"


def test_no_token_writes_no_file_at_all(tmp_path):
    """Before the owner mints it there is nothing to say, and `(no series)` says that honestly where a
    zero status would read as a call that happened and failed."""
    metrics, stdout, stderr = _run(tmp_path, '#!/bin/sh\nprintf "200 0.1"\n', token="", want_stdout=True)
    assert metrics == {} and stdout == "" and stderr == "", (
        "no file and no journal line: the runbook reads a start without one as no token"
    )
    assert not (tmp_path / "grafana-keepalive.prom").exists(), "no file at all, not an empty one"


@pytest.mark.parametrize(
    "family",
    [
        "zcrypto_grafana_keepalive_status",
        "zcrypto_grafana_keepalive_duration_seconds",
        "zcrypto_grafana_keepalive_last_run_timestamp_seconds",
        "zcrypto_grafana_keepalive_last_success_timestamp_seconds",
    ],
)
def test_every_family_carries_its_help_and_type(tmp_path, family):
    """A textfile without HELP/TYPE scrapes as an untyped series, and the exporter's own families are
    read by people who never open this repo."""
    variables = role_variables(TEMPLATE)
    variables["ops_textfile_dir"] = str(tmp_path)
    script = tmp_path / "keepalive.sh"
    script.write_text(ansible_render(TEMPLATE.read_text(), variables))
    stub = tmp_path / "bin"
    stub.mkdir()
    (stub / "curl").write_text('#!/bin/sh\nprintf "200 0.1"\n')
    (stub / "curl").chmod(0o755)
    script.chmod(0o755)
    subprocess.run(
        [str(script)],
        env={"PATH": f"{stub}:/usr/bin:/bin", "ZCRYPTO_GRAFANA_KEEPALIVE_TOKEN": "tok"},
        check=True,
    )

    written = (tmp_path / "grafana-keepalive.prom").read_text()
    assert f"# HELP {family} " in written
    assert f"# TYPE {family} gauge" in written


def test_the_stale_rule_tolerates_one_skipped_slot_of_the_timer_it_watches():
    """One skipped slot peaks near two periods and must stay quiet; two peak near three, and page only if the threshold plus `for` is below that."""
    root = pathlib.Path(__file__).resolve().parent.parent
    timer = (TEMPLATE.parent / "grafana-keepalive.timer.j2").read_text()
    step = re.search(r"^OnCalendar=\*:\d+/(\d+):00$", timer, re.M)
    assert step, "the timer is no longer `*:MM/N:00`; read its period some other way"
    period = int(step.group(1)) * 60
    rule = next(
        r
        for r in yaml.safe_load((root / "infra/grafana/alerts.yaml").read_text())["rules"]
        if r["uid"] == "zcrypto-ops-grafana-keepalive-stale"
    )
    (threshold,) = next(d for d in rule["data"] if d["refId"] == "C")["model"]["conditions"][0]["evaluator"]["params"]
    held = re.fullmatch(r"(\d+)([smh])", rule["for"])
    assert held, f"`for: {rule['for']}` is not a single-unit duration; read it some other way"
    for_s = int(held.group(1)) * {"s": 1, "m": 60, "h": 3600}[held.group(2)]
    assert 2 * period < threshold, f"threshold {threshold} s pages on one skipped slot of a {period} s timer"
    assert threshold + for_s < 3 * period, f"threshold {threshold} s plus `for` {for_s} s never pages on two skipped slots"
