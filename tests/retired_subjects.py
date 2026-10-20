"""The research subjects whose trials are closed. `tests/conftest.py` marks their cases `retired`: CI deselects them
(`-m "not retired"`), and the nightly `infra/scripts/data-gated-run.py` runs them with the rest of the suite.

A subject joins when no trial still to run evaluates it; one a later trial still evaluates stays out, as the shared
machinery's cases over the kept subjects do."""

from __future__ import annotations

import pytest

RETIRED_SUBJECTS = frozenset(
    {
        # The B1 family, closed.
        "b1-conditioning",
        "b1-window-only",
        "b1-hourly-rv",
        "b1-hourly-rv-preflight",
        "b1-volume-confirmation",
        "b1-volume-confirmation-preflight",
        "b1-hourly-channel-exits",
        "b1-hourly-channel-exits-preflight",
        # B2's finished trials and the reading between them.
        "b2-funding-derisk",
        "b2-arm-a-bar",
        "b2-funding-derisk-full",
        "b2-funding-derisk-full-preflight",
    }
)
# The one file outside the data-gated family whose cases evaluate a subject; elsewhere a subject's name is a checker's
# data, as in the registry provenance cases, which CI keeps.
SUBJECT_TESTS = "test_research_command.py"


def names_a_retired_subject(item: pytest.Item) -> bool:
    """A function specific to one retired subject that no parameter names carries `@pytest.mark.retired` itself."""
    callspec = getattr(item, "callspec", None)
    if callspec is None or item.path.name != SUBJECT_TESTS:
        return False
    if any(isinstance(value, str) and value in RETIRED_SUBJECTS for value in callspec.params.values()):
        return True
    return any(callspec.id == name or callspec.id.startswith(f"{name}-") for name in RETIRED_SUBJECTS)
