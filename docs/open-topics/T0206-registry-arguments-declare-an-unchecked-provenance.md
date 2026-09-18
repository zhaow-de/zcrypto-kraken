---
status: open
ripe_when: 'the next branch that adds a `nothing_found(...)` gate — the guard''s own walk counts 13 of them at this registration, and the branch writing the fourteenth is already holding the claim this topic would have the helper check'
---

# The registry's arguments declare an unchecked provenance

## Context — what

`tests/skip_gates.py` is where a skip gate declares what it reads when its guard does not say so on its face, and a call into that module is one of the six forms `tests/test_live_venue_opt_in.py` matches (spec 00114 D3).

Two of its three functions read a place: `develop_resolves()` runs a local `git rev-parse` and `no_binary(name)` reads PATH.
The third, `nothing_found(rows)`, is handed a VALUE rather than a place — it answers whether a collection is empty, and the claim that the collection came from a scan of local data is the call site's, checked by nothing.
Spec 00114 D5 names this as the one reading a form leaves unjudged: `nothing_found(rows)` over a collection a venue answer filtered would decide a skip through a declaration that says the scan was local.

A scan helper that took the PATH and did the glob itself — `nothing_found_under(root, pattern)` — would move the provenance from the caller into the registry, and the matcher's literal-rooted predicate would then judge `root` exactly as it judges a path receiver.

## Why this matters

This is the hole the matcher exists to close, moved one level in: the gate is matched, so the tree assertion is green, and what it is matched to is a sentence nobody can check.

`tests/test_tape_bars_rest_control.py` is the worked example the matcher's own spec cites: its `day` gate was filtered by `stamps`, Kraken's REST answer, so `nothing_found(day)` would have been a false claim.
Spec 00114 D8 split that gate into a local half and a `pytest.fail` rather than declaring it — and the split is correct only because a person read the data flow and saw where the value came from.

Nothing in the tree caught that, and nothing will catch the next one: 13 gates declare through `nothing_found(...)` today, and each is one reviewer's reading of where its rows came from.

## Findings so far

- 13 gates call `nothing_found(...)` at this registration, across `tests/test_costmin_drift.py`, `tests/test_derivatives_funding.py`, `tests/test_derivatives_oi.py`, `tests/test_engine_venuestate.py`, `tests/test_manifest_conformance.py`, `tests/test_registry_conformance.py`, `tests/test_registry_observed.py`, `tests/test_tape_bars_rest_control.py` and `tests/test_universe_provenance.py`; their arguments are globs, index reads, a filtered registry read and presence lists, each read at its call site on the branch that migrated them (`9f210e8ca`).
- The registry is held closed by `test_the_registry_reads_nothing_a_form_could_not` (spec 00114 D4) — imports within an allowlist, one `git` launch whose every argv word is an allowlisted literal, every function a single `return`. A scan helper fits that shape, `pathlib` being already on the allowlist, so the closure test is not what blocks this.
- What blocks it is the migration: most of the 13 sites compute their collection for the test BODY as well as for the gate, so moving the glob into the registry means either scanning twice or handing the rows back, which is a larger change than the matcher itself needed.
- Five of the 13 are rooted in a path the local config names — `_substrate_root(...)` in the two derivatives files and `load_config().nfs_mount_dir` in `tests/test_tape_bars_rest_control.py` — and a root the matcher cannot read stays a claim whichever argument carries it, so a scan helper closes eight of the 13 and not all of them.

## Suggested next steps

- Add `nothing_found_under(root: Path, pattern: str) -> bool` to `tests/skip_gates.py` and teach the registry form to judge that first argument with `_rooted`, the predicate the matcher already applies to a path receiver — a root the gate's own scope supplies is then refused at the gate with the remedy, rather than accepted as a claim.
- Where the test body needs the rows, give the registry a `scan(root, pattern) -> list` beside it and gate on its result, so the scan happens once; migrate the eight literal-rooted sites one file at a time and confirm each gate's decision is unchanged by running the file with and without its dataset present.
- Decide the five config-rooted gates separately — a form that reads the config, a literal mount the config no longer owns, or a recorded acceptance that they stay declarations — and record the decision where the next reader of `nothing_found`'s docstring will meet it.
- Keep `nothing_found(rows)` only as long as a site still needs it: while both exist, a gate can pick the unchecked one, so the docstring has to say which is which.
