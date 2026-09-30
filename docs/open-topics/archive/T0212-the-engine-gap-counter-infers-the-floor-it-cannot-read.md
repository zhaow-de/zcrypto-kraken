---
status: resolved
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

**The reading of 2026-09-27: the file arm fired and the band still holds one row, so the topic is deferred again under that ruling.** The watched files changed four times since registration, none of them at the floor or its inference: 11cf4e531 added a sentence to the window comment in `infra/scripts/deploy-log-audit.py` and 2caf33cee removed it, leaving the file as it was (#608, 2026-09-24); 1605abe64 added the three cache nodes to that script's `NO_VENUE_EXPOSURE` and to `infra/ansible/scripts/converge.sh`'s hosts, tags and keys, and 519600589 trimmed the wrapper's comment on them (#607, 2026-09-25). `infra/scripts/count-list.sh engine-rows-on-the-completion-floor` reads 1, and the row is the one the band has held since before registration: 2026-09-19T08:12:24Z, `--limit zcrypto`, tags `capture,engine`, rc 0.

## Resolution

Built as the strict form on the owner's approval of 2026-09-30, the design settled by that ruling, on the branch `fix/daily-pass-handoffs-t0212`:

- 8a27b407a: once the engine play's window assert passes, `infra/ansible/site.yml` writes `{"at", "floor", "arm", "override"}` into the file `infra/ansible/scripts/converge.sh` names with `zcrypto_window_record`, and the wrapper copies it into the deploy-log row as `window`. The floor and its journal test mirror the assert's own expression, and `tests/test_infra_converge_guards.py` holds them equal to it; `override` is whether the override echo fired. The wrapper refuses an operator's `zcrypto_window_record` and removes the file on every exit.
- 92a532fc7: `infra/scripts/deploy-log-audit.py` judges a row carrying `window` on the floor it records, with the close anchored to the boundary after the recorded clock, and an override row as admitted. It reports the rows without the field apart as `inferred`, and a recorded override row as `overridden`. `infra/scripts/count-list.sh engine-rows-on-the-completion-floor` counts only the inferred rows in the band.
- 94420d8b4: `infra/runbooks/engine.md` says what that count now holds.

At resolution the count reads 1, the 2026-09-19T08:12:24Z row, which carries no record and stays in the band. A row whose run reached the engine play's assert and whose record the wrapper read now carries one; an `engine`-tagged run whose `--limit` reaches no engine host, a record the wrapper could not read, or a row appended by hand still carries none, so the band can still gain a row. The file arm of the trigger retires with the topic. A converge the assert refuses writes no record and is still judged by inference: the raised-floor case under *Findings so far* still surfaces only as a failed row.
