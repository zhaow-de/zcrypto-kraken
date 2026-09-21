---
status: open
ripe_when: '`infra/ansible/scripts/converge.sh` or `infra/scripts/deploy-log-audit.py` is next changed — a session already at the writer or the reader this topic would change, and the arm the daily pass decides; OR `infra/scripts/count-list.sh engine-rows-on-the-completion-floor` reads 3 or more, the band having grown past the single row that made deferring it right.'
---

# The engine-gap counter infers the floor it cannot read

## Context — what

`infra/scripts/deploy-log-audit.py` meters the rule that an engine converge happens only inside the 4-hourly inter-cycle gap.

Since spec 00083 D6 the playbook's own floor is the boundary cycle's journalled `completed_at` plus 300 s, read from `/var/lib/zcrypto-engine/journal/<UTC day>/cycle-<HH>.json` on the engine host, with the fixed B+1800 as the arm it takes when that journal is unreadable.

The deploy log is a file in this repo and cannot read that journal. So PR #570 taught the counter to exempt a row in the band below the fixed floor when it succeeded and carried no `engine_window_override`, on the reasoning that the playbook's assert precedes the run: a row that landed there and succeeded is one the assert admitted. That is an inference from the outcome, never a measurement of the floor the row was admitted on.

PR #586 gave the band its own count, `infra/scripts/count-list.sh engine-rows-on-the-completion-floor`, so the inferred rows are visible rather than folded into a line nothing read.

The strict form, which PR #570 named and did not build: the deploy-log row carries the floor it was admitted on, written by `infra/ansible/scripts/converge.sh` at the moment the assert passes, and the counter reads that field instead of inferring.

## Why this matters

The counter is the only instrument over a rule whose subject is the live trade engine, and the band it cannot verify is exactly where a violation would hide. A converge admitted on a floor nobody recorded is indistinguishable from one the assert would have refused, so the count that reads 0 outside the window is 0 only under the inference.

It matters less than it sounds today, which is why it is deferred rather than queued. The band holds one row. The assert itself is not in doubt: it runs in the engine play's pre_tasks on every converge, `tests/test_infra_converge_guards.py` drives both its arms, and nothing about this topic weakens it. What is missing is the counter's ability to prove after the fact what the assert decided at the time.

The cost of building it is why the owner deferred it: `converge.sh` is the wrapper every fleet deploy runs through, including the capture pair, so a change there is paid by every host and wants its own careful read for a counter's benefit.

## Findings so far

The inference is stated in the script itself, at `infra/scripts/deploy-log-audit.py`'s `on_the_completion_floor`: "Success is sufficient evidence of that, since the window assert precedes it." It admits any successful un-overridden row in `[B+300, B+1800)` without checking that a completion was journalled at or before `since - 300`.

One case the counter cannot see at all, and which this topic's strict form would not fix either: the assert's floor follows the journal in both directions, so a cycle that ran to B+1700 keeps the window shut until B+2000 and refuses a converge at B+1900. The audit's fixed-offset `inside_gap` calls that row inside the window, so a raised floor never reaches the outside count; it surfaces only as a failed row.

The owner's ruling of 2026-09-21 is to leave the strict form unbuilt and let the count say whether it is worth building. A count that stays at one or two rows is the answer that the wrapper change buys nothing.

## Suggested next steps

Read the count first: `infra/scripts/count-list.sh engine-rows-on-the-completion-floor`. If it still reads one or two, record that reading here and defer again; the topic's own criterion is that a band which does not grow is not worth a wrapper change.

If it has grown, the build is a field on the deploy-log row. `infra/ansible/scripts/converge.sh` writes the record after the play returns, so the floor the assert used has to reach it: the assert's own arms already compute it, and the value to carry is the epoch it compared against plus which arm produced it, the journalled completion or the fixed fallback.

Then `on_the_completion_floor` reads that field rather than inferring, and a row that carries no field is one written before the change, which the counter reports apart rather than exempting.

A converge is attended and the engine's runs inside the gap, so the first row carrying the field arrives at whatever engine converge comes next; the reader change and the writer change can land together because the reader tolerates a row without the field.
