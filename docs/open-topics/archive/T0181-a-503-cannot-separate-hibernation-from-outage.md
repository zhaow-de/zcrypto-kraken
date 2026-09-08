---
status: resolved
---

# A 503 cannot separate a hibernation from a Grafana Cloud outage, and the keep-alive has no second signal

## Context — what

The keep-alive records the HTTP status of one authenticated call an hour. A hibernating Grafana Cloud instance returns 503; so does a Grafana Cloud outage. Nothing the call observes distinguishes them, and nothing else in the tree does either. A vendor status page was considered as an arbiter and removed from the surfaces during this branch; whether it can serve as one is undecided and stands open. The instrument therefore produces a signal whose meaning is undecidable at the moment it is read, and the question is whether that is accepted or whether a second signal is added that can separate the two.

## Why this matters

Review rounds on `feat/grafana-keepalive` each corrected prose asserting one cause or the other, and each round a reader found the next assertion standing. The pattern is not carelessness: every surface that tries to say what a 503 means is writing around a measurement that does not decide, so each sentence is either false or hedged into saying nothing an operator can act on. Three concrete gaps remain open in the tree because no sentence closes them honestly, and they are one question wearing three hats.

The stakes are not only editorial. `infra/runbooks/observability.md`'s `grafana-cloud-dark` section covers a state in which the live trade path runs unwatched and `zcrypto-engine-dark-with-exposure` cannot fire. An operator who reads a 503 as "just a nap" stops investigating while an armed engine may hold a position with nothing watching it — the branch carried exactly that sentence for a time, and the step carrying it was deleted before merge.

## Findings so far

The surfaces that stand incomplete, each needing a claim nobody can currently author:

- **`infra/runbooks/observability.md`'s step 1 as it then stood** routed a 503 and a `0` onward but said nothing about a `200`, and never warned that the reading can be roughly an hour stale — the keep-alive timer runs `*:37` while the watchdog probe runs `*:0/5:41`, so the two disagree about how fresh "now" is.
- **`infra/grafana/fleet-health-dashboard.json` panel 801** carries a clause importing the metric's own 503 reading, which crosses the rule stated in `infra/ansible/roles/ops/templates/grafana-keepalive.sh.j2`'s own comment: the HELP lines are the one home for what values mean, and other surfaces report and point rather than restate.
- **No surface anywhere states the experiment's decision rule** — what observation would end it, in which direction. The changelog said a recurrence refutes; that clause is deleted, because a recurrence does not say which event produced it either.

**The dashboard-probe answer is unfalsifiable from here and should not be adopted on its appeal.** It is tempting to say a hibernation ends when someone opens a dashboard and an outage does not. It has no recorded support at all: the only measured hibernation in this repo, recorded in `docs/reference/ops-journal/2026-09.md`'s 2026-09-07 entry for the event of 2026-09-06, states that the stack woke on an API probe, not on a dashboard. And it cannot be tested, because testing it needs an outage nobody can arrange. A claim that cannot be falsified is not a disambiguator.

## Resolution

**The owner ruled the accept arm on 2026-09-08: no second signal.** In their words — *"no need to separate, 503 is 503. And in theory, if our hourly keep-alive ping does its job, we should be able to eliminate the hibernation. let's keep it simple."*

That answers the question this topic was opened to preserve. The undecidability is accepted rather than engineered around, and the decision rule the topic reported no surface stated is the owner's own sentence: if the keep-alive works, hibernations stop happening. It is a rule the metric can carry, because it turns on whether 503s recur at all rather than on telling two causes apart.

The remaining surfaces are left as they stand, deliberately. Two mention a 503 -- the metric's `# HELP` line and panel 801 -- and both say it does not distinguish the two events, which is "503 is 503" in the only form left once the step that routed on one is gone. Neither routes an operator anywhere, and `grafana-cloud-dark` now mentions the keep-alive nowhere. The accept arm's proposal to author one sentence and point at it from three places was not taken, because the ruling's other half was to keep it simple and ship.

**The item the ruling did not reach was removed rather than answered**: the step that said nothing about a `200`, and never warned its reading could be an hour old, no longer exists. Asked why the section needed it, the owner had it deleted — every state it could observe routed onward, so it ended nothing and changed no action, and the four rounds spent making it correctly say nothing were the evidence. No sentence about a `200` is owed anywhere, because there is no step to owe it.

## Suggested next steps

_Superseded by the Resolution above._ The decision this section asked for was made; the two arms it laid out are spent, and the surfaces it proposed editing were left alone — one of them deleted outright. Nothing here is owed.
