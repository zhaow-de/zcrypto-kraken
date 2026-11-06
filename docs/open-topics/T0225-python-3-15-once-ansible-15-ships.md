---
status: open
ripe_when: 'an activity: a bump of `ansible` to 15, which Dependabot opens at its stable release and not at a pre-release; check: `uv.lock`''s `ansible` package reads version 15 or later, or `gh pr list --state all --search "Bump ansible from"` names a bump to 15'
---

# Python 3.15 once ansible 15 ships

## Context — what

The project runs on Python 3.14 (`.python-version`). A read of 2026-11-05 found every pinned dependency ready for 3.15 but one: `ansible-core`, through `ansible`, whose release is outside this repo.

## Why this matters

Nothing forces the move today, and a runtime change just before rung 3 adds risk with no benefit to name. The one blocker clears on an upstream release nobody here would otherwise see, so the question is parked on it rather than on memory. The owner's word of 2026-11-06: "yes, please let it triggered on ansible 15".

## Findings so far

The locked set on Python 3.15.2 in a scratch venv, 2026-11-05, since removed:

- 62 of the 65 pins have a Linux wheel at the pinned version or are pure Python.
- `ansible-core` 2.21.5 fails on 3.15, `dataclasses._is_type` being gone. 2.22.0 works, but `ansible` 14 pins `~=2.21`, and its 15.x was at alpha, `15.0.0a4`.
- `nautilus-trader`'s pin then, `2.0.0rc9.dev20261101`, had `cp313` and `cp314` wheels alone; nightlies from `dev20261102` carry `cp315`.
- `pyyaml` 6.0.3 has no `cp315` wheel and builds from source without the libyaml speedups: it works, slower.
- With the first nightly carrying a `cp315` wheel in nautilus's place, all 65 installed and all 192 `cli` modules imported. 1837 of 1843 sampled tests passed, the 6 failures that `ansible-core` error, and those passed on 2.22.0. No full suite, no data-gated test, no live engine and no order path ran on 3.15.

## Suggested next steps

- Repeat the read with `ansible` 15 locked: install the set on 3.15 in a scratch venv, import `cli`, run the sample and the suite's non-data cases, and read whether `pyyaml` has gained a `cp315` wheel.
- Put the move to the owner with that result. It changes `.python-version`, `requires-python` in `pyproject.toml`, the Dockerfile's `python:3.14-slim` and CI, and the attended order-semantics pass (`infra/runbooks/order-semantics-verification.md`) is tied to a build, so it owes a new one.
