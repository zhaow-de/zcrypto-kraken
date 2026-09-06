---
status: resolved
---

# The prose cleanup's closeout residue: operator instructions stranded on the topology doc, and two phase-0 minors

## Context — what

T0164's docs batch (PR #407) rewrote `docs/reference/fleet.md` as a topology doc — paths, endpoints and access — and its closeout recorded ten operator instructions as cut from it. Measured at `ecdb8654`, nine of the ten are still in `fleet.md` in full and one is history-only; none has a home on the runbook page that owns its subsystem, and a procedure in a topology doc is a second home waiting to drift from the runbook's. T0164's closeout also carried two phase-0 minors the cleanup found and did not fix: `cli/snapshot/fetch.py`'s `fetch_public` returns `payload["result"]` and raises `KeyError` on a result-less body; and the trial registry's append after a hand-edited unterminated last line. T0164 archives on 2026-09-06 with these registered here, so no deferral lives only in its prose.

## Why this matters

An operator who reaches for one of these instructions — the engine-image ad-hoc read, the single-identity SSH agent a zaccess converge needs, the bridgehead's digest-less Alloy, the client-cert revocation, the agentboard node-upgrade recipe, the NAS transfer, the two drill recipes, the wiring-not-timing caveat — finds it on the topology doc or, for one of them, in a commit diff — never on the page that owns its subsystem, which is where an operator looks; a procedure kept on the topology doc beside its runbook is the second home that drifts. `fetch_public`'s bare key access turns a venue error body into a traceback where a refusal naming the body is what an operator can act on.

## Findings so far

- Nine of the ten instructions stand in `docs/reference/fleet.md` at `ecdb8654` (the bullets between the host table and the service table); the tenth, the one log class no pipeline sees, is only in the history of the commit `docs(reference): fleet.md carries topology, not the dates and incidents that produced it`, which was a rewrite (its diff's removed lines overcount the cuts). None has a runbook home, checked by grepping each instruction's subject over `infra/runbooks/`.
- `cli/snapshot/fetch.py:28` returns `payload["result"]` with no guard; the venue's error shape is `{"error": [...]}` with no `result` key.
- The registry append on an unterminated last line: the append-only tool writes a line after whatever the file ends with; a hand edit that leaves no trailing newline makes the next record share a line with the last. A hand edit of the append-only ledger is operator error the tool does not defend against.

## Resolution

**The ten instructions, each on the page that owns its subsystem, `fleet.md` keeping one topology pointer apiece** — `docs(runbooks): the ad-hoc trade-key read gets the page that owns the engine, and fleet.md a pointer`, `docs(runbooks): the bridgehead's three procedures get its own page, and three citations follow them`, `docs(runbooks): the last five instructions, each to the page that owns its subsystem`, and the correction `docs(runbooks): the engine window substitutes its journal arm, it does not take the earlier one`.

Three homes differ from the ones this topic registered, and each difference is the topic's own rule. The bridgehead's digest-less Alloy went to `infra/runbooks/zaccess.md`'s `zaccess-bridgehead-dark`, not to `infra/runbooks/observability.md`: that page scopes itself to the four Alloy CONTAINERS and its own text sends a bridgehead reader to the zaccess page, so the paragraph would have sat in the section that disclaims its subject. And: the agentboard node upgrade went to `infra/runbooks/ops-node.md` and the NAS file transfer to `infra/runbooks/nas.md`, not to `infra/runbooks/hosts.md`, which is where this topic registered them — `hosts.md` is written as the two capture VPSes, agentboard runs on the ops node and the transfer is the NAS, and placing them there required widening that page's own intro to stop claiming every signal below it is node-exporter's. Both drill recipes and the wiring-not-timing caveat went to `infra/runbooks/drills-telemetry.md` rather than to new sections of their own: the throwaway-subject and textfile-injection inductions as standing rules, the caveat and the log class no pipeline observes under the page's bound derivations — the two shapes that page already uses for what binds every drill below it.

Four citations moved with the facts they cite: `infra/ansible/scripts/run.sh`, `infra/ansible/files/README.md`, `docs/reference/fleet.md`'s own cross-reference to the bridgehead-Alloy bullet, and `docs/reference/fleet-pins.md`'s agentboard row.

**`fetch_public` now makes three refusals where it made none**, each with its own message and its own constructed defect: a body that is not a JSON object at all (`AttributeError` before), a body carrying no `result` (`KeyError` before), and a `result` that is not itself an object (returned a non-dict from a `-> dict` function, breaking frames away in `cli/snapshot/assetpairs.py`). Commits `fix(snapshot): a result-less body is a refusal, not a KeyError`, `fix(snapshot): a 200 whose body is not a JSON object is a refusal too`, and `` fix(snapshot): a `result` that is not an object, refused where it is read rather than where it breaks ``. No fourth hole is known in that function: the three above are every path by which a 200 response reached a caller as something other than a mapping. The chain stopped by exhausting them, not by running out of appetite — a hole found in it later opens its own topic rather than riding a closeout.

**The registry append is a conscious drop.** The ledger is append-only through its own tool; a hand edit that leaves the last line unterminated is operator error outside that contract, and `tests/test_trial_registry_provenance.py` refuses a malformed line on the next read, so the failure is loud rather than silent. No guard ships. If the owner wants one later it is one assertion that the file ends in a newline before every append.
