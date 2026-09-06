import re
import tomllib
from datetime import datetime, timezone
from pathlib import Path

import nautilus_trader
from nautilus_trader.adapters.kraken import (
    KrakenDataClientConfig,
    KrakenDataClientFactory,
    KrakenExecutionClientConfig,
    KrakenExecutionClientFactory,
)

_REPO = Path(__file__).resolve().parents[1]

# `===` is PEP 440 arbitrary equality, and the pin must keep using it. The index publishes both
# `<version>` and `<version>+<build>` for the same wheel; `==<version>` matches the local-segment
# form as well and ORDERS IT ABOVE, so `==` silently resolves to a different artifact than the one
# written down. Anything but `===` is a finding here, not a spelling to tolerate.
_NAUTILUS_PIN = re.compile(r"^nautilus-trader\s*===\s*(?P<version>\S+)$")


def _pinned_nautilus_version() -> str:
    """The version `pyproject.toml` pins -- read from the file, never duplicated into this test."""
    deps = tomllib.loads((_REPO / "pyproject.toml").read_text())["project"]["dependencies"]
    entries = [d.strip() for d in deps if re.match(r"^nautilus-trader\b", d.strip())]
    assert len(entries) == 1, f"expected exactly one nautilus-trader dependency, found {entries}"
    matched = _NAUTILUS_PIN.match(entries[0])
    assert matched, f"the nautilus-trader dependency must pin with `===`: {entries[0]!r}"
    return matched.group("version")


def test_pinned_version():
    """The interpreter under test runs exactly the wheel `pyproject.toml` names.

    Deliberately not a hardcoded version: the pin tracks a nightly channel and moves often, and an
    assertion hand-edited at every move gets edited without being read. The equality is also what
    keeps the two arming guards on one operand -- the converge looks up the pyproject PIN and the
    execution gate the RUNNING interpreter's version, both in `cli/engine/order-semantics-verified.json`.
    """
    assert nautilus_trader.__version__ == _pinned_nautilus_version()


def test_the_arming_gate_consults_this_interpreter_and_the_committed_record(tmp_path):
    """The gate's version input on the production path, with nothing injected.

    Every gate test in `tests/test_engine_execgate.py` injects or patches the version reader, so all
    of them would still pass if `evaluate` stopped consulting the running interpreter. Here the
    reader is left at its default, and the verdict is asserted as an equivalence rather than a fixed
    value: both operands are live, and a fixed verdict would need hand-editing at exactly the moment
    the money guard changes state.
    """
    from cli.engine.execgate import ARM_FILE, ExecutionGate, GateLevel, _verified_nautilus_versions, exec_dir
    from cli.engine.venue import VenueStatus

    recorded = _verified_nautilus_versions()
    # A record that vouched for nothing would satisfy the refusing branch below for the wrong
    # reason: an unreadable record refuses everything, which is correct but proves nothing here.
    assert recorded, "the committed record must be readable and vouch for at least one version"

    d = exec_dir(tmp_path)
    d.mkdir(parents=True, exist_ok=True)
    (d / ARM_FILE).touch()
    gate = ExecutionGate(
        armed_in_config=True,
        state_dir=tmp_path,
        venue_reader=lambda *, now, opener=None: VenueStatus(status="online", ok=True, observed_at=now),
    )

    verdict = gate.evaluate(datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc))
    installed = nautilus_trader.__version__

    assert verdict.inputs["nautilus_version"] == installed
    assert verdict.inputs["nautilus_verified"] is (installed in recorded)
    if installed in recorded:
        assert "nautilus_unverified" not in verdict.reasons
        assert verdict.level == GateLevel.FULL
    else:
        assert "nautilus_unverified" in verdict.reasons
        assert verdict.level == GateLevel.NONE


def test_the_gates_version_reader_reports_the_really_installed_version():
    """The production reader against the running interpreter, unpatched. No test that patches or
    injects this reader can see an always-'' implementation -- a renamed attribute, a swallowed
    import error -- which would make the arming gate refuse unconditionally. Asserted here because
    this module already imports nautilus_trader and pays the cost anyway."""
    from cli.engine.execgate import _installed_nautilus_version

    assert _installed_nautilus_version() == nautilus_trader.__version__
    assert _installed_nautilus_version() != ""


def test_kraken_adapter_config_and_factories_import():
    assert KrakenDataClientConfig is not None
    assert KrakenExecutionClientConfig is not None
    assert KrakenDataClientFactory is not None
    assert KrakenExecutionClientFactory is not None
