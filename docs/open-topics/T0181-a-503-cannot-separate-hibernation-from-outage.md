---
status: open
---

# A 503 cannot separate a hibernation from a Grafana Cloud outage, and the keep-alive has no second signal

## Context — what

The keep-alive records the HTTP status of one authenticated call an hour. A hibernating Grafana Cloud instance returns 503; so does a Grafana Cloud outage. Nothing the call observes distinguishes them, and nothing else in the tree does either — the vendor status page was considered and rejected as an arbiter, because the hibernation this fleet measured on 2026-09-06 appeared on no such page. The instrument therefore produces a signal whose meaning is undecidable at the moment it is read, and the question is whether that is accepted or whether a second signal is added that can separate the two.

## Why this matters

Four review rounds on `feat/grafana-keepalive` each corrected prose asserting one cause or the other, and each round a reader found the next assertion standing. The pattern is not carelessness: every surface that tries to say what a 503 means is writing around a measurement that does not decide, so each sentence is either false or hedged into saying nothing an operator can act on. Three concrete gaps remain open in the tree because no sentence closes them honestly, and they are one question wearing three hats.

The stakes are not only editorial. `infra/runbooks/observability.md`'s `grafana-cloud-dark` section covers a state in which the live trade path runs unwatched and `zcrypto-engine-dark-with-exposure` cannot fire. An operator who reads a 503 as "just a nap" stops investigating while an armed engine may hold a position with nothing watching it — the branch shipped and then removed exactly that sentence.

## Findings so far

The three surfaces that stand incomplete, each needing a claim nobody can currently author:

- **`infra/runbooks/observability.md` step 1** routes a 503 and a `0` onward but says nothing about a `200`, and does not warn that the reading can be roughly an hour stale — the keep-alive timer runs `*:37` while the watchdog probe runs `*:0/5:41`, so the two disagree about how fresh "now" is.
- **`infra/grafana/fleet-health-dashboard.json` panel 801** carries a clause importing the metric's own 503 reading, which crosses the rule stated in `infra/ansible/roles/ops/templates/grafana-keepalive.sh.j2`'s own comment: the HELP lines are the one home for what values mean, and other surfaces report and point rather than restate.
- **No surface anywhere states the experiment's decision rule** — what observation would end it, in which direction. The changelog said a recurrence refutes; that clause is deleted, because a recurrence does not say which event produced it either.

**The dashboard-probe answer is unfalsifiable from here and should not be adopted on its appeal.** It is tempting to say a hibernation ends when someone opens a dashboard and an outage does not. It rests on a single observation — `docs/reference/ops-journal/2026-09.md`'s 2026-09-07 entry, the only measured hibernation in this repo — and it cannot be tested, because testing it needs an outage nobody can arrange. A claim that cannot be falsified is not a disambiguator.

## Suggested next steps

- **The decision is the owner's**: accept that the signal is undecidable and say so plainly on every surface, or add a second signal that separates the two cases. There is no third option that a sentence can deliver, which is what four rounds of rewriting established.
- If a second signal is wanted, the shape to price first is a probe whose response differs between the two states rather than another reading of the same 503 — and it must be answerable without the repo, since the surface that matters is read on the host while Grafana is unreadable.
- If undecidability is accepted, the three surfaces above take the same sentence, authored once and pointed at from the others, and the runbook step gains the staleness bound its two timers imply.
- Until then, treat every sentence about what a 503 means as owed to this topic. The branch stopped authoring them deliberately.
