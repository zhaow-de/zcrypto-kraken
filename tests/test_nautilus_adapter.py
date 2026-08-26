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

    A mechanical consistency check, deliberately not a hardcoded string. The pin tracks a nightly
    channel and moves often; an assertion that had to be hand-edited at every move would be edited
    without being read, which is how a guard stops guarding.

    What it catches: an environment left behind by a pin change, a resolver that served something
    other than what was written down, and the local-segment trap `_NAUTILUS_PIN`'s comment names.
    It is also what keeps the two arming guards reading the SAME operand -- the converge assert
    compares the PIN against `cli/engine/order-semantics-verified.json`, the runtime execution gate
    compares the RUNNING interpreter's version against it, and those are one string only while this
    holds.

    It says nothing about whether the installed version may be TRADED on. That is the record's
    business and it is enforced where it can bite: the converge refuses to render an armed config on
    an unrecorded version, and the execution gate refuses to arm on one.
    """
    assert nautilus_trader.__version__ == _pinned_nautilus_version()


def test_the_arming_gate_consults_this_interpreter_and_the_committed_record(tmp_path):
    """The gate's version input on the production path, with nothing injected.

    Every gate test in `tests/test_engine_execgate.py` supplies its own version reader, so all of
    them would still pass if `evaluate` stopped consulting the running interpreter altogether. This
    one builds a fully permissive gate -- config armed, arm file present, venue online, no kill, no
    restart hold -- and leaves the version reader at its default, so the only thing that can refuse
    it is the real path: read this interpreter's version, look it up in the committed record.

    Stated as an equivalence rather than a fixed verdict on purpose. Both operands are live: a
    version is refused exactly while the record does not list it, and cleared the moment an attended
    order-semantics pass adds it. A fixed verdict would have to be hand-edited at precisely the
    moment the money guard changes state, which is when nobody should be editing tests.
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

    # The DEFAULT reader is the one `evaluate` really used -- not a stub, not a constant.
    assert verdict.inputs["nautilus_version"] == installed
    assert verdict.inputs["nautilus_verified"] is (installed in recorded)
    if installed in recorded:
        assert "nautilus_unverified" not in verdict.reasons
        assert verdict.level == GateLevel.FULL
    else:
        assert "nautilus_unverified" in verdict.reasons
        assert verdict.level == GateLevel.NONE


def test_the_gates_version_reader_reports_the_really_installed_version():
    """The production reader's only direct true-positive. Every gate test injects a reader or
    patches this function, so an always-'' implementation -- a renamed attribute, a swallowed
    import error -- would ship green while making the arming gate refuse unconditionally. Asserted
    here because this module already imports nautilus_trader and pays the cost anyway."""
    from cli.engine.execgate import _installed_nautilus_version

    assert _installed_nautilus_version() == nautilus_trader.__version__
    assert _installed_nautilus_version() != ""


def test_kraken_adapter_config_and_factories_import():
    assert KrakenDataClientConfig is not None
    assert KrakenExecutionClientConfig is not None
    assert KrakenDataClientFactory is not None
    assert KrakenExecutionClientFactory is not None
