"""Guard: `tape-bars.sh.j2` renders to the ops materializer's shell script, and the two properties
it can silently get wrong are pinned by execution rather than by reading the template.

1. **Argument order.** `zcrypto tick materialize` takes `(primary, OUT) --reconciled-root`, while
   the panel runner this template was modelled on takes `(primary, reconciled) --panel-root`. A
   transposition renders, runs, exits 0 and publishes the UN-HEALED stream — permanently, since the
   dataset has no rewrite path. The rendered argv is therefore parsed and matched against the real
   Typer command's own parameter order.
2. **The gauge block.** The timer's failure mode is a green silence: the not-yet-healed path exits
   0 by design, so a stalled healer freezes the dataset while every other surface reports success.
   The block is executed against a seeded .prom, because every text assertion over it survives the
   mutations that matter (a carried-forward read moved below the rename, a publish stamp advanced
   on a run that published nothing).

`trim_blocks=True, lstrip_blocks=False` mirrors Ansible's own Jinja defaults, matching
`test_infra_archive_pull_template.py`."""

import re
import shlex
import shutil
import subprocess
from pathlib import Path

import jinja2
import pytest
from typer.main import get_command

from cli.__main__ import app

REPO = Path(__file__).resolve().parents[1]
TEMPLATE = REPO / "infra/ansible/roles/ops/templates/tape-bars.sh.j2"

_ENV = jinja2.Environment(trim_blocks=True, lstrip_blocks=False, undefined=jinja2.StrictUndefined)

CONTEXT = {
    # Real values; uid/gid arrive as STRINGS (set_fact from getent_passwd), not the ints a guess
    # supplies.
    "ops_textfile_dir": "/var/lib/zcrypto-ops/textfile",
    "ops_nas_mount": "/mnt/zhao-crypto",
    "ops_data_dir": "/var/lib/zcrypto-ops",
    "ops_capture_subdir": "capture-segments",
    "ops_reconciled_subdir": "capture-reconciled",
    "ops_tape_bars_subdir": "tape-bars",
    "ops_image": "ghcr.io/zhaow-de/zcrypto-capture",
    "ops_image_digest": "sha256:" + "c" * 64,
    "ops_uid": "998",
    "ops_gid": "998",
}

PROM_BLOCK_END = 'mv "$tmp" "$PROM"'


def _rendered() -> str:
    return _ENV.from_string(TEMPLATE.read_text()).render(**CONTEXT)


def _bash() -> str:
    found = shutil.which("bash")
    if found is None:  # pragma: no cover - bash is present on every dev and CI image we run
        pytest.skip("bash not available")
    return found


def _rendered_argv() -> list[str]:
    """The `docker run` invocation, tokenised — the redirection tail dropped."""
    r = _rendered()
    start = r.index("docker run --rm --pull never")
    command = r[start : r.index('> "$log" 2>&1', start)]
    # shlex renders each `\<newline>` continuation as a bare newline token; drop those, they are
    # not arguments.
    return [t for t in shlex.split(command) if t.strip()]


def _value(text: str, series: str) -> str:
    return next(line for line in text.splitlines() if line.startswith(f"{series} ")).split()[1]


def test_the_runner_calls_the_cli_with_the_arguments_in_the_cli_s_own_order():
    """The transposition this whole test file exists for: swapping the second positional with the
    overlay publishes the un-healed stream, silently and permanently."""
    materialize = get_command(app).commands["tick"].commands["materialize"]
    # `param_type_name`, not isinstance: Typer's TyperArgument does not answer to `click.Argument`
    # here, and an isinstance filter silently yields an EMPTY list — which `zip(strict=True)` would
    # then reject, but only by accident.
    positional_names = [p.name for p in materialize.params if p.param_type_name == "argument"]
    # Pin the CLI side too: if the command's own order ever changes, mapping the rendered tokens
    # onto it would swap in lockstep and this file would keep passing while the runner was wrong.
    assert positional_names == ["primary_root", "out_root"], f"the CLI's positional order changed: {positional_names}"

    argv = _rendered_argv()
    assert argv[argv.index("--entrypoint") + 1] == "zcrypto"
    tail = argv[argv.index("materialize") + 1 :]
    positionals = [t for i, t in enumerate(tail) if not t.startswith("--") and not (i and tail[i - 1].startswith("--"))]
    supplied = dict(zip(positional_names, positionals, strict=True))
    assert supplied["primary_root"] == "/nas/capture-segments", "the primary must be the NAS canonical trade tree"
    assert supplied["out_root"] == "/data/tape-bars", "the second positional is the OUTPUT root, not the overlay"
    assert "--reconciled-root" in tail, "the healed overlay must be passed, or the un-healed stream is published"
    assert tail[tail.index("--reconciled-root") + 1] == "/data/capture-reconciled"
    assert "--panel-root" not in tail, "the panel's flag was copied along with its shape"


def test_the_output_root_is_the_only_writable_mount():
    """The overlay and the output share the rw /data mount; the canonical tree must stay :ro, or a
    bug in the sweep could write into the unbackfillable archive."""
    argv = _rendered_argv()
    mounts = [argv[i + 1] for i, t in enumerate(argv) if t == "-v"]
    assert "/mnt/zhao-crypto:/nas:ro" in mounts
    assert "/var/lib/zcrypto-ops:/data" in mounts


def test_the_gauge_parse_matches_what_the_cli_actually_prints():
    """The gauges are parsed out of the CLI's summary line, so a wording drift on either side breaks
    them silently. Rather than re-implement the sed in Python, run the real one over the CLI's own
    format string — a change on either side then fails here."""
    sed = shutil.which("sed")
    if sed is None:  # pragma: no cover - sed is present on every image we run
        pytest.skip("sed not available")
    emitter = (REPO / "cli/tick/command.py").read_text()
    for field in ("days_written", "days_unhealed", "days_gap", "errors"):
        assert f"{field}=" in emitter, f"the CLI no longer prints {field}"
    match = re.search(r'sed -n "s/\.\*\$1=(.+?)/p"', _rendered())
    assert match, "the summary parse is missing from the rendered script"

    # Distinct values per field: an all-zero sample cannot tell a right capture from a wrong one.
    sample = "days_written=2 days_skipped=5 days_unsettled=1 days_unhealed=3 days_gap=4 rows=192 errors=6"
    for field, expected in (("days_written", "2"), ("days_unhealed", "3"), ("days_gap", "4"), ("errors", "6")):
        script = f"s/.*{field}={match.group(1)}/p"
        out = subprocess.run([sed, "-n", script], input=sample, text=True, capture_output=True)
        assert out.stdout.strip() == expected, f"{field} parsed as {out.stdout.strip()!r}, expected {expected}"

    # The grep anchors the summary to its own first field so a per-day ERROR line on stderr — which
    # carries an arbitrary exception message — can never be parsed as counters.
    assert "grep -E '^days_written='" in _rendered()


def _run_block(tmp_path, *, rc: int, summary: str, now: int, seed: str) -> str:
    """Execute the rendered gauge/export block against a seeded .prom and return the result."""
    r = _rendered()
    block = r[r.index("gauge() {") : r.index(PROM_BLOCK_END) + len(PROM_BLOCK_END)]
    # The slice runs in isolation, so a conditional wrapping the WHOLE block would be invisible to
    # it — a wrapper that skipped the export on a failed run would leave every gauge stale at its
    # last clean value while exit_code stayed 0. Balance the slice structurally instead.
    before = r[: r.index("gauge() {")]
    opens = len([ln for ln in before.splitlines() if re.match(r"\s*if\s", ln)])
    closes = len([ln for ln in before.splitlines() if re.match(r"\s*fi\s*$", ln)])
    assert opens == closes, f"the export block sits at conditional depth {opens - closes}, not the top level"

    prom = tmp_path / "tape-bars.prom"
    prom.write_text(seed)
    harness = f"set -u\nrc={rc}\nnow={now}\nsummary={shlex.quote(summary)}\nPROM={shlex.quote(str(prom))}\n{block}"
    proc = subprocess.run([_bash(), "-c", harness], capture_output=True, text=True)
    assert proc.returncode == 0, f"the export block aborted: {proc.stderr}"
    return prom.read_text()


SEED = (
    "zcrypto_tapebars_days_written 7\n"
    "zcrypto_tapebars_days_unhealed 1\n"
    "zcrypto_tapebars_days_gap 4\n"
    "zcrypto_tapebars_errors 0\n"
    "zcrypto_tapebars_last_success_timestamp_seconds 1753700000\n"
    "zcrypto_tapebars_last_publish_timestamp_seconds 1753600000\n"
)

SERIES = (
    "zcrypto_tapebars_exit_code",
    "zcrypto_tapebars_days_written",
    "zcrypto_tapebars_days_unhealed",
    "zcrypto_tapebars_days_gap",
    "zcrypto_tapebars_errors",
    "zcrypto_tapebars_last_run_timestamp_seconds",
    "zcrypto_tapebars_last_success_timestamp_seconds",
    "zcrypto_tapebars_last_publish_timestamp_seconds",
)


def test_a_run_that_reported_nothing_carries_every_gauge_forward(tmp_path):
    """A run that died before the CLI reported (leftover container, missing image, EIO on the NFS
    mount) MEASURED nothing. Publishing a 0 there would retract the permanent-gap alert — the one
    signal nothing else in the fleet will ever raise again — and the file is rewritten whole each
    run, so omitting a line deletes the series outright."""
    written = _run_block(tmp_path, rc=125, summary="", now=1753800000, seed=SEED)
    for series in SERIES:
        assert f"{series} " in written, f"{series} is missing after a failed run — the series is deleted"
    assert _value(written, "zcrypto_tapebars_exit_code") == "125"
    assert _value(written, "zcrypto_tapebars_days_gap") == "4", "an unmeasured run published a 0 gap"
    assert _value(written, "zcrypto_tapebars_last_success_timestamp_seconds") == "1753700000", (
        "last_success was not carried forward — a 0 makes time() - last_success enormous and pages forever"
    )
    assert _value(written, "zcrypto_tapebars_last_publish_timestamp_seconds") == "1753600000"
    assert _value(written, "zcrypto_tapebars_last_run_timestamp_seconds") == "1753800000"


def test_a_clean_run_that_published_nothing_does_not_advance_the_publish_stamp(tmp_path):
    """The green silence itself. A stalled healer leaves every day unhealed, which exits 0 by
    design — so last_success advances every hour while the dataset stops growing. Only the publish
    stamp can see that, and only if it refuses to advance on a clean run that wrote no day."""
    summary = "days_written=0 days_skipped=5 days_unsettled=1 days_unhealed=3 days_gap=0 rows=0 errors=0"
    written = _run_block(tmp_path, rc=0, summary=summary, now=1753800000, seed=SEED)
    assert _value(written, "zcrypto_tapebars_last_success_timestamp_seconds") == "1753800000"
    assert _value(written, "zcrypto_tapebars_last_publish_timestamp_seconds") == "1753600000", (
        "the publish stamp advanced on a run that published nothing — the watermark-freeze signal is blind"
    )
    # A MEASURED zero must overwrite the seeded 4: the carry-forward is for unmeasured runs only,
    # or a gap that was later healed would be reported forever.
    assert _value(written, "zcrypto_tapebars_days_gap") == "0"
    assert _value(written, "zcrypto_tapebars_days_unhealed") == "3"


def test_a_run_that_published_advances_the_publish_stamp(tmp_path):
    summary = "days_written=2 days_skipped=5 days_unsettled=1 days_unhealed=0 days_gap=0 rows=192 errors=0"
    written = _run_block(tmp_path, rc=0, summary=summary, now=1753800000, seed=SEED)
    assert _value(written, "zcrypto_tapebars_last_publish_timestamp_seconds") == "1753800000"
    assert _value(written, "zcrypto_tapebars_days_written") == "2"
