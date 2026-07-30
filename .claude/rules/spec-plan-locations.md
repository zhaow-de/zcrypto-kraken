# Specs & plans

## When a committed spec/plan is required

Scale the ceremony to the change size:

- **Substantive iteration** (a feature, a non-trivial fix, anything multi-file or with design choices): run the full flow — `superpowers:brainstorming` → committed spec, `superpowers:writing-plans` → committed plan, cold spec+plan review, subagent-driven execution, and closeout through the `iteration-closeout` skill.
- **Trivial change** (one-file / obvious — e.g. a log-format tweak, a rename/relocation, a doc or rule edit): do **not** commit a spec or plan, and skip the iterations-history entry (see `iterations-history.md`). Brainstorm a short design, get approval, then implement directly. If a written design is genuinely useful, keep it as a **transient scratch file deleted after implementation + testing** — never committed.

**Cold spec+plan review (substantive flow only).** After the plan is committed and before execution starts: dispatch a fresh-context subagent to review the spec+plan **pair** — coverage (every spec requirement has a plan task), internal consistency, whether the planned verification pins the spec's load-bearing properties, and that every deferral sentence in the pair names a registered `T<NNNN>` or an explicit drop. Model floor Opus; **Fable** when the change touches the unbackfillable capture path, the live trade path, or canonical data. Fix findings before Task 1; material ones are folded into the plan, not just noted.

Trivial still keeps the non-negotiables: a feature branch off `develop`, TDD where there's code, **mandatory subagent review before push** (`commit-messages.md`), a `README.md` update if user-facing (`readme-usage.md`), and a PR into `develop`. Only the committed spec/plan/iterations-history ceremony is dropped.

**A spec or decisions-log entry that rules on how operations must be performed lands the imperative on the operating surface — the owning rule, runbook, or skill — in the same change**: a ruling recorded only in a spec is invisible at execution time.

## Locations

Superpowers skills default to `docs/superpowers/<kind>/`; in this repo use `docs/<kind>/` instead (flat tree):

- Spec (brainstorming): `docs/specs/<serial_no>-<topic>-design.md`
- Plan (writing-plans): `docs/plans/<serial_no>-<feature>.md`

`<serial_no>` is a 5-digit zero-padded counter (`00000`, `00001`, …); the next is one above the highest in `docs/specs/`. A plan reuses its spec's serial.
