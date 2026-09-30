---
name: zcrypto-bump-nautilus
description: Bump the nautilus-trader pin end to end — the candidate build, the guards, the attended order-semantics pass, its record, the PR and the engine rollout, on one branch. Human-run only.
disable-model-invocation: true
---

# zcrypto-bump-nautilus

The one owner of the bump's order. The pieces it points at stay where they are: the attended pass is `infra/runbooks/order-semantics-verification.md`, the arming step is `infra/runbooks/engine-procedures.md`, the guards are tests, the records are `docs/reference/adapter-verification/` and `cli/engine/order-semantics-verified.json`. This page says what happens in which order and hands off by pointer; it copies none of those texts, so there is one carrier of each.

**The bump, its attended pass and its registration land in one pull request** (the owner's ruling of 2026-09-30). `tests/test_nautilus_pin_verified.py` fails the required `Full test suite` check on a tree whose installed build the record does not verify, so the bump's PR is red from the pin until §7.4's write-up lands on the same branch, and develop carries no unverified build. A version is added to the record by that write-up alone, after a PASS, and the runbook's §7.4 (1) says why the shortcut is forbidden.

## What a bump costs, so the decision is taken once

An attended session for the pass (~EUR 0.20 of fees and spread at rung-1 money, `order-semantics-verification.md` §0), the pin frozen from the pass to the merge (§1.6), an engine converge inside an inter-cycle gap for the rollout, and the two live-only readings the cache spec sends to the first boot on a new build. A build is bumped for a reason the branch names: an upstream fix the engine waits on, a Dependabot reminder whose build carries one, or a premise a spec rests on that the nightly has moved.

## Step 1 — the candidate build

1. Read the index raw and grep it: `curl -fsS https://packages.nautechsystems.io/simple/nautilus-trader/index.html | grep -oE '2\.0\.0rc[0-9]+\.dev[0-9]{8}(\+[0-9]+)?' | sort -u`. The page is ~200 KB and ~1850 links; a summarising fetch of it once returned a slice two months older than the pin with no sign it had truncated, so the raw fetch is the read.
2. Filter to `^2\.0\.0rc[0-9]+\.dev[0-9]{8}$` before taking the newest. A `+NNNNN` suffix is an ad-hoc build, deleted hours after creation; one date can carry both forms, and pinning the suffixed one breaks `uv lock` on the next resolve, far from its cause.
3. Verify the premise the bump is taken for against upstream, not against the date: the `nightly` branch's tip (`gh api repos/nautechsystems/nautilus_trader/compare/<merge-sha>...nightly --jq .status` reads `ahead` or `identical` for a merged PR), the upstream build run's sha, and the wheel's `last-modified` on the index.
4. Read the upstream items the engine waits on and what each does to this bump. Today: #5110 (merged 2026-09-27, spot startup reconciliation reads ClosedOrders too) changes the startup read `docs/specs/00119-exec-findings-design.md`'s premises rest on, so Step 3 re-measures them; #5064/#5065 (the Kraken margin entry price, on hold) lifts the engine restart rule when it ships, `infra/runbooks/engine-procedures.md#engine-restart-margin-position`; #5067 (the pair and asset spellings) awaits the maintainer's pick. Upstream's own compatibility note: a mass-status client conflicting with an execution client becomes a startup error, so the node's client wiring is read against the release notes from the pin up to the candidate.

## Step 2 — the branch

1. Cut `feat/engine-arm-<build>` from `develop` into its own worktree; move `pyproject.toml`'s `nautilus-trader===<build>` and run `uv lock` (the lock resolves through the `nautechsystems` index `pyproject.toml` names) and `uv sync`.
2. Open the draft PR at the first commit so CI runs, and expect it red: the pin test refuses the unverified build until Step 5. A red for another reason is read before anything else.
3. Close the Dependabot reminder PR for the same build as superseded, with this branch named in the comment; the `dependabot` skill leaves that PR open by design and this is where it ends.

The pin stays where Step 2 put it until the merge: a re-pin or re-lock after the pass makes the record name a build the branch no longer installs (§1.6).

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

`infra/runbooks/order-semantics-verification.md`, in full, from the bump branch's worktree (§2), the pin frozen (§1.6), the harness proven before it is pointed at money (§3). It runs in the main loop by hand. What this page adds: the pass runs on the candidate installed by Step 2, so `$PY -c 'import nautilus_trader; print(nautilus_trader.__version__)'` equals the pin before §5, and the engine on the host stays on its current build throughout.

## Step 5 — the write-up

§7.4's list, on the same branch: the record page `docs/reference/adapter-verification/<build>.md` from the harness's table, the version added to `cli/engine/order-semantics-verified.json` with its note (the note records what that pass said, dated; a later bump leaves the earlier note as written), `tests/test_engine_execgate.py` re-pinned to the new set by hand, the arming step's baselines in `engine-procedures.md`, and the previous page cross-linked. Step 3's premise readings go on the record page. With the write-up committed, the pin test turns green and CI with it.

## Step 6 — landing and rollout

1. The PR through `open-pr` and the review trio, merged through `merge-pr` on the owner's word.
2. The engine image built from the merged tree, rolled through `zcrypto-rollout-image`: the capture secondary's re-pin and bake as for each app image, then the primary `--tags capture,engine` inside the journal-computed gap while flat, the record it needs in `docs/reference/fleet-pins.md`. The two readings the cache spec sends to the first boot on a new build are taken at that boot.
3. Arming, by `infra/runbooks/engine-procedures.md#engine-probe-window`'s pre-probe steps, the record's `## Owed checks not discharged by this pass` discharged first.

## Closeout

- The engine restart rule's lift, when this build carries #5065: `docs/open-topics/T0158-go-live-drill-program-execution.md`'s trigger names it.
- `.local/memo.md`'s upstream watch list re-trued to what the next bump waits on.
