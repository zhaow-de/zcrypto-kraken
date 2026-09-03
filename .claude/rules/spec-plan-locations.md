# Specs & plans

## When a committed spec/plan is required

Scale the ceremony to the change size:

- **Substantive iteration** (a feature, a non-trivial fix, anything whose **design choices are still open**): run the full flow — `superpowers:brainstorming` → committed spec, `superpowers:writing-plans` → committed plan, `zcrypto-plan-review`, subagent-driven execution, and closeout through the `iteration-closeout` skill. **The spec carries a `## The measured basis` section**: every premise about the tree, a library, a runtime, or a venue is verified by a command at write time and says so — the review's contract pin then confirms rather than discovers.
- **Design-settled change** — the design question is already closed by an explicit ruling or by a topic that states the decision, **however many files it touches**; or the change is one-file/obvious: do **not** commit a spec or plan. Brainstorm a short design, get approval, then implement directly. The ruling or topic must **predate the branch** — a decision authored in the same run as the change it licenses is self-certification, not a settled design. **Skip the iterations-history entry only when the change is trivial in substance** — a log-format tweak, a rename, a single doc edit; anything that materially alters behaviour or guidance still gets its entry (`iterations-history.md`). Keep a genuinely useful written design as a **transient scratch file, deleted after implementation + testing** — never committed.

**The spec+plan review (substantive flow only) is the `zcrypto-plan-review` skill** — invoke it after the plan is committed and before Task 1; its exit (no Critical or Important standing, every foldable Minor folded, the consequence statement written) is the licence to execute. The reviewers' lenses, the model floor, the fixer's contract and the stopping rule are decided inside it, nowhere else.

**Rank every pre-push review dispatch by blast radius** (the plan review does this inside its skill). Name the two or three things whose being wrong would cost something — what ships to production, what a paged operator acts on, what a number would change — and tell the reviewer everything else is Minor by construction. Never dispatch an open-ended sweep ("find every stale claim"). **Two rounds on one subject is the ceiling once nothing above Minor remains**: when round two returns only Minor or only prose, the subject is done — record what was consciously left rather than opening round three. A Critical or Important finding is never capped: fix it, and the fix is a new commit taking its own mandatory pre-push review (`commit-messages.md`) — a first review of new work, never round three.

The design-settled path still keeps the non-negotiables: a feature branch off `develop`, TDD where there's code, **mandatory subagent review before push** (`commit-messages.md`) — **at the Fable floor when the change touches the unbackfillable capture path, the live trade path, or canonical data**, the floor transferring from the plan review it replaces — a `README.md` update if user-facing (`readme-usage.md`), and a PR into `develop`. Only the committed spec/plan ceremony is dropped — and, for a substantively trivial change, its history entry.

**A spec whose sha256 is stored as a registry record's `spec_hash` is immutable** — appending to it, even a dated addendum, breaks the pin that verifies that record and nothing in the gate catches it. A recovered convention's durable home is committed, runnable code.

**A spec or decisions-log entry that rules on how operations must be performed lands the imperative on the operating surface** — the owning rule, runbook, or skill — **in the same change**: a ruling recorded only in a spec is invisible at execution time.

## Locations

Superpowers skills default to `docs/superpowers/<kind>/`; in this repo use `docs/<kind>/` instead (flat tree):

- Spec (brainstorming): `docs/specs/<serial_no>-<topic>-design.md`
- Plan (writing-plans): `docs/plans/<serial_no>-<feature>.md`

`<serial_no>` is a 5-digit zero-padded counter (`00000`, `00001`, …); the next is one above the highest in `docs/specs/`. A plan reuses its spec's serial.
