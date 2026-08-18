---
status: open
ripe_when: the next change that adds a section to `infra/runbooks/README.md` — count `grep -c '^## ' infra/runbooks/README.md` and subtract 1 for the Scope section; it reads 19 against the file's own ~12 threshold today, so any addition makes the split overdue rather than due
---

# The runbook file exceeds its own stated split threshold

## Context — what

`infra/runbooks/README.md` states its own split rule in its Scope section: *"**Split when** this file exceeds ~12 sections, or gains a second subsystem's worth of material: move to `infra/runbooks/<subsystem>.md` and keep the explicit `<a name=…>` anchors byte-identical, because alert summaries and code comments cite them."* Measured 2026-08-18: **19 procedure sections** (20 `##` headings less the Scope section itself) across 743 lines, spanning at least four subsystems — capture, zaccess, ops/reconcile, and the engine's execution path. The threshold is exceeded by more than half again, and iter-140 added the largest single section in the file (`engine-probe-window`, a five-phase attended procedure).

The split was **not** done in iter-140, deliberately. Two reasons, both recorded here rather than left as a sentence in a task report:

- **It is a separate nameable component.** `branch-workflow.md`'s one-PR-one-component rule cuts both ways — a restructure of every runbook section is not "the rung-1 order path", and folding it into that branch would have made a safety-critical checklist commit also a file-move commit.
- **The anchors must stay byte-identical, and the checklist commit is the wrong place to risk them.** They are explicit `<a name=…>` tags precisely because the `— ALERT` / `— KNOWN LIMITATION` markers would otherwise become part of a heading-derived slug. Moving sections while an operator-facing probe checklist is the diff's subject mixes a reviewable procedure with a mechanical migration, and the procedure is the half a reviewer must actually read.

## Why this matters

The file's opening line is *"You are here because an alert fired in Slack"* — it is read at 03:00, on a phone, by a responder with nothing else open. Its own split rule exists because a runbook nobody can finish scanning is a runbook nobody reads, and that cost lands exactly when the responder is least able to absorb it.

The migration is also not free, which is why it needs its own change rather than a drive-by:

- **21 anchors, 17 of them cited from `infra/grafana/alerts.yaml`** alert summaries as `infra/runbooks/README.md#<anchor>` — a live page's only next step. Also cited from `cli/archive/settle.py`, `tests/test_dashboards_cover_metrics.py` and `.pre-commit-config.yaml`.
- **`tests/test_infra_alert_rules.py` hardcodes the single-file assumption**: `RUNBOOK = REPO / "infra/runbooks/README.md"` and `_RUNBOOK_LINK = re.compile(r"infra/runbooks/README\.md#([A-Za-z0-9._-]+)")`, with `test_every_runbook_link_in_an_alert_summary_resolves` asserting every cited anchor exists. That test is the split's safety net **and** its blocker — it must learn about multiple files in the same change, or it goes green by resolving against a file the sections have left.
- A link that 404s is worse than a long file: the responder gets a fragment and no next step, which is the exact failure the test above was written to prevent.

## Findings so far

- Measured 2026-08-18 on the `feat/00090-rung-1-order-path` branch: 19 procedure sections, 21 `<a name=…>` anchors, 743 lines. Section families by prefix: `zcrypto-capture-*` (2), `cross-hour-straddle`, `zaccess-*` (4), `zcrypto-ops-*` (4), `zcrypto-engine-*` (4), `zcrypto-venue-*` (2), `refdata-sweep-due`, `engine-probe-window`.
- The split rule's second clause ("a second subsystem's worth of material") fired long before the count did — `zaccess` and `zcrypto-ops` are already distinct subsystems from capture, and the engine execution sections are a third.
- Two sections are not alert-triggered and split along a different seam than the rest: `refdata-sweep-due` (a scheduled reminder) and `engine-probe-window` (an attended procedure with human gates G1–G6). A subsystem-shaped split would separate them from the alert sections whether or not that is the intent.

## Suggested next steps

- **Decide the seam before moving anything, and record it**: by subsystem (`capture.md`, `zaccess.md`, `ops.md`, `engine.md`) as the file's own rule suggests, or by kind (alerts vs procedures). The two disagree on where `engine-probe-window` and `refdata-sweep-due` land, so the choice is a real one and not a formatting preference.
- **Widen `tests/test_infra_alert_rules.py` first, in the same change**: make `RUNBOOK` a set of files under `infra/runbooks/` and the link regex path-agnostic, then confirm the widened test still fails on a planted broken anchor before moving a single section — a migration guarded by a test that stopped looking is unguarded.
- **Verify anchors byte-identically after the move**, not by eye: extract the `<a name=…>` set from the pre-split file and from the post-split tree and assert equality, then re-run the alert-link test. Every cited anchor must resolve to exactly one file.
- **Update the citing sites in the same change**: the 17 `alerts.yaml` summaries plus `cli/archive/settle.py`, `tests/test_dashboards_cover_metrics.py` and `.pre-commit-config.yaml`. A summary pointing at a moved section is a page with no next step.
- Keep the Scope section (and its split rule) in `infra/runbooks/README.md` as the index, so the entry point an operator was taught still exists and routes.
