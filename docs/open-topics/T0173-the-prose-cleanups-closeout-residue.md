---
status: open
---

# The prose cleanup's closeout residue: operator instructions cut from the topology doc, and two phase-0 minors

## Context — what

T0164's docs batch (PR #407) rewrote `docs/reference/fleet.md` as a topology doc — paths, endpoints and access — and its closeout recorded ten operator instructions as cut from it. Measured at `ecdb8654`, nine of the ten are still in `fleet.md` in full and one is history-only; none has a home on the runbook page that owns its subsystem, and a procedure in a topology doc is a second home waiting to drift from the runbook's. T0164's closeout also carried two phase-0 minors the cleanup found and did not fix: `cli/snapshot/fetch.py`'s `fetch_public` returns `payload["result"]` and raises `KeyError` on a result-less body; and the trial registry's append after a hand-edited unterminated last line. T0164 archives on 2026-09-06 with these registered here, so no deferral lives only in its prose.

## Why this matters

An operator who reaches for one of the cut instructions — the engine-image ad-hoc read, the single-identity SSH agent a zaccess converge needs, the bridgehead's digest-less Alloy, the client-cert revocation, the agentboard node-upgrade recipe, the NAS transfer, the two drill recipes, the wiring-not-timing caveat — finds it in git history only, and a git-history-only procedure is the class `agent-ops.md` calls a stranded context. `fetch_public`'s bare key access turns a venue error body into a traceback where a refusal naming the body is what an operator can act on.

## Findings so far

- Nine of the ten instructions stand in `docs/reference/fleet.md` at `ecdb8654` (the bullets between the host table and the service table); the tenth, the one log class no pipeline sees, is only in the history of the commit `docs(reference): fleet.md carries topology, not the dates and incidents that produced it`, which was a rewrite (its diff's removed lines overcount the cuts). None has a runbook home, checked by grepping each instruction's subject over `infra/runbooks/`.
- `cli/snapshot/fetch.py:28` returns `payload["result"]` with no guard; the venue's error shape is `{"error": [...]}` with no `result` key.
- The registry append on an unterminated last line: the append-only tool writes a line after whatever the file ends with; a hand edit that leaves no trailing newline makes the next record share a line with the last. A hand edit of the append-only ledger is operator error the tool does not defend against.

## Suggested next steps

- Move each of the ten instructions to its runbook home in one docs PR, `fleet.md` keeping one pointer sentence per instruction (where the thing is and which page owns the procedure) so no procedure has two homes: the engine-image ad-hoc read → `infra/runbooks/engine-procedures.md`; the single-identity SSH agent and the client-cert revocation → the zaccess page under `infra/runbooks/`; the bridgehead's digest-less Alloy → `infra/runbooks/observability.md` beside the Alloy pins; the agentboard node-upgrade recipe and the NAS transfer → `infra/runbooks/hosts.md`; the two drill recipes → `infra/runbooks/drills-telemetry.md`; the wiring-not-timing caveat → the page whose drill it qualifies. Re-read each against the tree before placing it (a sentence may already be stale), and name the page in T0164's archived Done so far only by pointer.
- `fetch_public`: return the venue's `error` list as a refusal when `result` is absent, with a test that feeds a result-less body (the constructed defect) beside a healthy body (the true positive); a `fix(snapshot)` commit riding the same PR.
- The registry append: record the drop here — the ledger is append-only through its tool, a hand edit is outside the contract, and `tests/test_trial_registry_provenance.py` would refuse a malformed line on the next read — or, if the owner prefers a guard, one assertion that the file ends in a newline before every append.
