---
name: zcrypto-bump-nautilus
description: Bump the nautilus-trader pin end to end — the candidate build, the guards, the attended order-semantics pass, its record, the PR and the engine rollout, on one branch. Human-run only.
disable-model-invocation: true
---

# zcrypto-bump-nautilus

The one owner of the bump's order. The pieces it points at stay where they are: the attended pass is `infra/runbooks/order-semantics-verification.md`, the arming step is `infra/runbooks/engine-procedures.md`, the guards are tests, the records are `docs/reference/adapter-verification/` and `cli/engine/order-semantics-verified.json`. This page says what happens in which order and hands off by pointer; it copies none of those texts, so there is one carrier of each.

**The bump, its attended pass and its registration land in one pull request**, red until the write-up lands: `infra/runbooks/order-semantics-verification.md` §1.6 says why, §7.4 (1) what alone registers a version.

## What a bump costs, so the decision is taken once

An attended session for the pass (`order-semantics-verification.md` §0: ~EUR 0.16 of fees and spread on the normal path), the pin frozen from the pass to the merge (§1.6), and an engine converge inside an inter-cycle gap for the rollout. A build is bumped for a reason the branch names: an upstream fix the engine waits on, a Dependabot reminder whose build carries one, or a premise a spec rests on that the nightly has moved.

## Step 1 — the candidate build

1. Read the index raw and grep it: `curl -fsS https://packages.nautechsystems.io/simple/nautilus-trader/index.html | grep -oE '2\.0\.0rc[0-9]+\.dev[0-9]{8}(\+[0-9]+)?' | sort -u`. A summarising fetch of the page truncates without saying so, so the raw fetch is the read.
2. Filter to `^2\.0\.0rc[0-9]+\.dev[0-9]{8}$` before taking the newest. A `+NNNNN` suffix is an ad-hoc build, deleted hours after creation; one date can carry both forms, and pinning the suffixed one breaks `uv lock` on the next resolve, far from its cause.
3. Verify the premise the bump is taken for against upstream, not against the date: the `nightly` branch's tip (`gh api repos/nautechsystems/nautilus_trader/compare/<merge-sha>...nightly --jq .status` reads `ahead` or `identical` for a merged PR), the upstream build run's sha, and the wheel's `last-modified` on the index.
4. Read the upstream items the engine waits on and what each does to this bump. Today: #5110 (merged; spot startup reconciliation reads ClosedOrders too) moves the premise `docs/specs/00120-engine-cache-engine-half-design.md` D7 rests on, so Step 3 re-measures it; #5064/#5065 (the Kraken margin entry price, on hold) lifts the engine restart rule when it ships, `infra/runbooks/engine-procedures.md#engine-restart-margin-position`; #5067 (the pair and asset spellings) awaits the maintainer's pick. Upstream's own compatibility note: a mass-status client conflicting with an execution client becomes a startup error, so the node's client wiring is read against the release notes from the pin up to the candidate.

## Step 2 — the branch

1. Cut `feat/engine-arm-<build>` from `develop` into its own worktree; move `pyproject.toml`'s `nautilus-trader===<build>` and run `uv lock` (the lock resolves through the `nautechsystems` index `pyproject.toml` names) and `uv sync`.
2. Open the draft PR through `open-pr` at the first commit so CI runs; the pin test keeps it red until Step 5, and a red for another reason is read first.
3. Close the Dependabot reminder PR for the same build as superseded, with this branch named in the comment; the `dependabot` skill leaves that PR open by design and this is where it ends.

## Step 3 — the static guards and the premises

Run on the bump branch, before any money:

- `tests/test_nautilus_adapter.py` — the installed version equals the pin.
- `tests/test_nautilus_interface_pin.py` — the symbols, shapes and values `cli/` depends on, at the paths it imports them from; this file answers "what changed under us" in one run.
- `tests/test_kraken_wheel_contract.py`, `tests/test_kraken_order_semantics_probe.py` and `tests/test_order_semantics_probe.py` — the harness and its contract against the new wheel.
- `tests/test_cache_restart.py` — the two-process restart harness against a real `valkey-server`, the library's restore and reconciliation paths on this build.

A change one of these reports is read, then either absorbed on the branch or the reason the build is held; the guard is re-pinned to the new shape, not loosened.

The wheel ships stripped: `_libnautilus.cpython-*.so` with no symbols, no sdist, no source checkout. A question about the adapter's behaviour on this build is answered by what the installed package states — PyO3 signatures and docstrings through introspection, the `.pyi` stubs, a `strings` dump whose Rust doc comments survive concatenated without separators — with a positive control beside each negative (another adapter's strings found by the same query), and by an empirical probe where those fall short. Binding a dated dev wheel to a guessed upstream commit is a version error, and a wrong commit answering a gate question is worse than no answer.

Then the premises: each spec whose decisions rest on the library's startup or reconciliation behaviour names what it measured, and Step 1's watch list says which of those a build moved. Re-measure them on this build, on the branch, and write the reading into the record page Step 5 opens.

## Step 4 — the attended pass

`infra/runbooks/order-semantics-verification.md`, in full, from the bump branch's worktree (§2), on the candidate Step 2 installed.

## Step 5 — the write-up

`order-semantics-verification.md` §7.4, whole, on the same branch, Step 3's premise readings on the record page. A version's note in `cli/engine/order-semantics-verified.json` records what that pass said, dated; a later bump leaves an earlier note as written.

## Step 6 — landing and rollout

1. The review trio, the undraft through `open-pr`, the merge through `merge-pr` on the owner's word.
2. The engine image built from the merged tree, rolled through `zcrypto-rollout-image`.
3. Arming, by `infra/runbooks/engine-procedures.md#engine-probe-window`'s pre-probe steps, the record's `## Owed checks not discharged by this pass` discharged first.

## Closeout

- The engine restart rule's lift, when this build carries #5065: `docs/open-topics/T0158-go-live-drill-program-execution.md`'s trigger names it.
- `.local/memo.md`'s upstream watch list re-trued to what the next bump waits on.
