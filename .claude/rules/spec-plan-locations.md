# Specs & plans

## When a committed spec/plan is required

Scale the ceremony to the change size:

- **Substantive iteration** (a feature, a non-trivial fix, anything whose **design choices are still open**): run the full flow — `superpowers:brainstorming` → committed spec, `superpowers:writing-plans` → committed plan, cold spec+plan review, subagent-driven execution, and closeout through the `iteration-closeout` skill.
- **Design-settled change** — the design question is already closed by an explicit ruling or by a topic that states the decision, **however many files it touches**; or the change is one-file/obvious: do **not** commit a spec or plan. Brainstorm a short design, get approval, then implement directly. The ruling or topic must **predate the branch**: a decision authored in the same run as the change it licenses is not a settled design, it is self-certification. **The file count is not the test** — a spec written after the ruling is transcription, and the cold spec+plan review has nothing left to catch. **Skip the iterations-history entry only when the change is trivial in substance** — a log-format tweak, a rename, a single doc edit. Anything that alters behaviour or guidance materially still gets its entry (`iterations-history.md`). If a written design is genuinely useful, keep it as a **transient scratch file deleted after implementation + testing** — never committed.

**Cold spec+plan review (substantive flow only).** After the plan is committed and before execution starts: dispatch a fresh-context subagent to review the spec+plan **pair** — coverage (every spec requirement has a plan task), internal consistency, whether the planned verification pins the spec's load-bearing properties, and that every deferral sentence in the pair names a registered `T<NNNN>` or an explicit drop. Model floor Opus; **Fable** when the change touches the unbackfillable capture path, the live trade path, or canonical data. Fix findings before Task 1; material ones are folded into the plan, not just noted. A cold-review loop that does not converge across rounds is a verdict on the design's SHAPE, not on the reviewers — stop iterating and re-derive; and never build a guard for a door with no production caller.

The design-settled path still keeps the non-negotiables: a feature branch off `develop`, TDD where there's code, **mandatory subagent review before push** (`commit-messages.md`) — **at the Fable floor when the change touches the unbackfillable capture path, the live trade path, or canonical data** — the floor transfers from the cold review it replaces — a `README.md` update if user-facing (`readme-usage.md`), and a PR into `develop`. Only the committed spec/plan ceremony is dropped — and, for a substantively trivial change, its history entry.

**A spec whose sha256 is stored as a registry record's `spec_hash` is immutable** — appending to it, even a dated addendum, breaks the pin that verifies that record and nothing in the gate catches it; a recovered convention's durable home is committed, runnable code.

**A spec or decisions-log entry that rules on how operations must be performed lands the imperative on the operating surface — the owning rule, runbook, or skill — in the same change**: a ruling recorded only in a spec is invisible at execution time.

## Locations

Superpowers skills default to `docs/superpowers/<kind>/`; in this repo use `docs/<kind>/` instead (flat tree):

- Spec (brainstorming): `docs/specs/<serial_no>-<topic>-design.md`
- Plan (writing-plans): `docs/plans/<serial_no>-<feature>.md`

`<serial_no>` is a 5-digit zero-padded counter (`00000`, `00001`, …); the next is one above the highest in `docs/specs/`. A plan reuses its spec's serial.
