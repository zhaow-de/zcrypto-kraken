---
status: open
ripe_when: 'an activity: a bump of `ansible` to 15; check: `uv.lock`''s `ansible` package reads version 15 or later, or `gh pr list --state all --search "in:title Bump ansible from"` names a bump to 15'
---

# Python 3.15 once ansible 15 ships

## Context — what

The project runs on Python 3.14 (`.python-version`). A read of 2026-11-05 found one blocker to 3.15: `ansible-core`, through `ansible`, whose release is outside this repo.

## Why this matters

Nothing forces the move today, and a runtime change just before rung 3 adds risk with no benefit to name. The owner's word of 2026-11-06: "yes, please let it triggered on ansible 15".

## Findings so far

The locked set on Python 3.15.2 in a scratch venv, 2026-11-05:

- The pins not named below have a Linux wheel or are pure Python.
- `ansible-core` 2.21.5 fails on 3.15, `dataclasses._is_type` being gone. 2.22.0 works, but `ansible` 14 pins `~=2.21.x`, and 15.x was in beta, `15.0.0b1`.
- `nautilus-trader`'s pin then, `2.0.0rc9.dev20261101`, had `cp313` and `cp314` wheels alone; nightlies from `dev20261102` carry `cp315`.
- `pyyaml` 6.0.3 has no `cp315` wheel and builds from source without the libyaml speedups: it works, slower.
- With the first nightly carrying a `cp315` wheel in nautilus's place, the set installed and every `cli` module imported; the sampled tests' only failures were that `ansible-core` error, gone on 2.22.0. No full suite, no data-gated test, no live engine and no order path ran on 3.15.

## Suggested next steps

- Repeat the read with `ansible` 15 locked: install the set on 3.15 in a scratch venv, import `cli`, run the suite's non-data cases, and read whether `pyyaml` has gained a `cp315` wheel.
- Put the move to the owner with that result. It changes `.python-version`, `requires-python` in `pyproject.toml`, the Dockerfile's `python:3.14-slim` and CI, and the attended order-semantics pass (`infra/runbooks/order-semantics-verification.md`) is tied to a build, so it owes a new one.
