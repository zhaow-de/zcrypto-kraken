---
status: resolved
---

# Tests and infra claims the second cleanup batch left unasserted

## Context — what

The `tests/` + `infra/` prose-cleanup batches (T0164) condensed comments across both trees. Some sentences describe a blind spot nothing else carries and stay in their files on `prose.md`'s clause that a blind spot that matters gets a test or a topic; other claims the comments made about the tree, which no test asserts, left the prose. Each item below is a test to write, or a recorded drop.

## Why this matters

The claims sit on the ops role, the daily pass, the engine node wrapper and the capture writer. A sentence that says what a guard covers, with nothing asserting it, is the class that produced most of the review findings of 2026-09-04.

## Findings so far

Kept in the files until this topic closes them:

- `infra/ansible/roles/ops/tasks/main.yml`: `ops_unit_install`'s loop aggregates eight items, so under `--check` any changed unit template suppresses the timer preview for all four timers.
- `tests/test_engine_node.py`: the venue-sourced join (an external order reaching the observer through live reconciliation) is beyond the suite, proven by hand in archived T0152; an opt-in live test would need the IP-bound engine-host key. Same file: the stub-cache tests never run reconciliation, so the `filter_unclaimed_external_orders is False` pin is the only guard against an upstream default flip.
- `infra/scripts/ops_daily.py`: no fixture exercises the read side of `_UNREACHABLE` (a 200 whose body read raises).
- `tests/test_ops_daily.py`: `Report.reminders` gaining a default is watched by nothing; a reader added to `ops_daily.py` without an endpoint pin is caught by nothing; the grep operand-0 skip is sound only while no flag consumes the pattern.

Dropped from the prose, unasserted:

- Every probe in the ops role carries `failed_when: false`; the `daemon.json` task notifies `restart docker` (the docker-role ordering test stays green if the notify is dropped); every image-consuming ops guard carries `when: ops_image_digest is defined`; `env.j2` renders the empty hash scope as an empty assignment that compose and the entrypoint substitute `full` for; the echo's negated clause equals the assert's first disjunct verbatim.
- `zcrypto-capture.service` has `Restart=always` and no `After=time-sync.target`, the premise of the leading-clock scenario; `_recover`'s `.tmp` unlink is `__init__`'s one unguarded operation.
- Each `VERDICT_CHECKS` bound equals its owning rule's evaluator; the healthchecks fixture's keys are a subset of `{name, tags, desc}`; `test_legitimate_heavy_tails_stay_measured` claimed a 200-seed sweep over a loop of ten.
- `infra/ansible/roles/base/defaults/main.yml`: a FAILED unattended upgrade pages nobody. `node_reboot_required` (spec 00071) covers only the opposite case, a SUCCESSFUL upgrade awaiting reboot, so the gap is patches that never install. T0027 and T0100 cover the reboot side alone, and no rule in `infra/grafana/alerts.yaml` reads an upgrade failure.
- `infra/ansible/roles/access/tasks/main.yml`: the bridgehead relay's socket half is applied by neither its restart handler nor its end-of-role drift assert, so a changed `ListenStream` is written and never applied. The fact itself is stated in archived T0156; what had no live home is its TRIGGER — widen the gate if that value ever changes — and an archived topic is never re-read. `git grep -n ListenStream -- tests/` is empty.
- `infra/ansible/roles/access/tasks/main.yml`: no alert fires on a caddy-only outage. The cert-expiry rule that probes the edge carries `noDataState: OK` because it treats `zcrypto-alloy-dark-zaccess` as owning "the host is dark", and that rule stays green while Alloy is healthy; spec 00075 D11's rule list — bridgehead dark, WG stale, cert expiry, disk — has no member covering it.

## Done so far

### Wave 1 — the topic's own list

On `feat/t0168-unasserted-claims`, whose merge commit names it: each bullet's landing commits are that
branch's, and every one of them names its own test file or command in its subject. Each item's claim now has an assertion, each guard's constructed defect was seen to trip it, and a production-shaped true positive stands beside it.

- **Ops role**, `tests/test_infra_converge_guards.py`: the six guards landed — a changed-but-not-new unit template under check mode, a walk asserting `failed_when: false` over the role's probes, the `daemon.json` task's notify, the digest gate over every image-consuming ops task, the `env.j2` render on the empty scope, and the echo/assert text equality. The digest gate's asset selection was rebuilt until it delegates resolution to ansible's own `DataLoader().path_dwim_relative` rather than modelling the search rules, and a dangling link anywhere in the role is refused by a presence walk rather than by any rule about how a `src:` is spelled.
- **Engine node**, `tests/test_engine_node.py`: the venue-sourced join is a recorded drop naming T0152 (the key is IP-bound, so the join cannot run from CI or a workstation); five execution knobs are asserted through a rebound stand-in, with `use_ws_trade` named as the contrast because it belongs to a different config class. The cache-entry case is dropped: no in-process node runs reconciliation, so the stand-in pins the config the builder receives instead.
- **Daily pass**, `tests/test_ops_daily.py`: the six claims landed, and two defects surfaced while landing them — a content-head veto that ran one branch too late, and a grep read by the spelling of its operand. The recursion grammar the guard could not own is gone: a first-stage `cat` or `grep` that names no file is refused, whatever its flags say, and the grep shapes' admitted surface is pinned by content so a further spelling cannot be added silently.

### Wave 1, continued

- **Capture writer**, `tests/test_capture_segment_writer.py`: the `zcrypto-capture.service` unit read beside the other unit-file guards, and the `.tmp` unlink asserted as the one unguarded operation. The unit parser refuses a backslash-continued line rather than reading past it, because systemd joins such a pair, fails to parse the joined value and discards the assignment.
- **Continuity**, `tests/test_infra_continuity.py`: `test_legitimate_heavy_tails_stay_measured` runs the range its docstring named.
- **Unattended upgrades**: decided — not a page. A failed security patch surfaces as a daily-pass check with no metric, no rule and no converge, and the reboot-packages line rides with it.

### Found on the way, off the topic's own list

- `cli/capture/segment_writer.py`'s `_hour_of` raised `OverflowError` past an `except ValueError` that promised to skip a foreign directory. Widened; it ships with the next capture rollout and is not live until then. The same defect at seven other sites is T0171.
- The classifier's read-safe-root model is lexical and a symlink defeats it for `cat`, `grep` and `grep -r` alike — T0172. Dropping `-R` narrowed what a safe root reaches during traversal; it did not close the class.

### Wave 2 — the remainder, resolved

The owner pruned the remainder on 2026-09-06: 24 bullets kept and asserted, 28 dropped consciously, with `notification_settings.repeat_interval` added as a 25th keep from T0164's closeout paragraph on the owner's word. Every keep below names the commit that landed it by subject, on `feat/t0168-wave2-remaining-claims`; each was proven by constructing the defect and watching the named assertion fire, with a production-shaped true positive beside it.

#### The paged surfaces

- **A deleted `.prom` took its own alarm with it.** `zcrypto_engine_journal_prune_*` had no rule, so a vanished series was silence on the host carrying both the live trade engine and the unbackfillable capture spool. `feat(obs): the deleted .prom that took its own alarm with it` adds `zcrypto-engine-journal-prune-dead` with `noDataState: Alerting`, so the absence is itself the alarm, plus its runbook section and index row.
- **A summary promised a host the expression never reads.** `zcrypto-fleet-alloy-memory-headroom` said "512 MiB elsewhere" while reading four hosts. The topic's recommended fix — adding zaccess to the selector — is unbuildable: the rule is a percentage of a memory cap and zaccess's apt Alloy has none, so there is no denominator. `fix(obs): the paged summary that promised a host the expression never reads` names the four hosts the expression reads; capping zaccess so it could join is separate, converge-bearing work.
- **An all-clear a counter of admitted silence cannot give.** `zcrypto-reconcile-healable-gap-rate` said "Every gap was covered"; the counter measures the silence a gap was ADMITTED on, not what a splice inserted. `fix(obs): the all-clear a counter of ADMITTED silence cannot give` says what the counter measures and points at the ledger's `residual_seconds`.
#### The operating surfaces

- **The post-verify read every signal except the dead-man's own.** `test(ops): the post-verify's tenth check reads the dead-man's own operand` adds the tenth check on `ops_archive_pull_last_success_timestamp`. One `printf` block writes the exit code and both timestamps together, so a stopped timer freezes all three and the report read ALL PASS about a writer that had not run.
- **One `repeat_interval` a dropped payload field would cost silently.** `test(obs): the one repeat_interval a dropped payload field would cost silently` runs the push script's own jq program over every rule and compares the `notification_settings` block whole, refusing to pass vacuously.

#### The tests

- `test(capture): the clock-offset unit readers refuse the line systemd would join` and `test(engine): a wrapped unit directive read as its first half` — both unit readers now refuse a backslash-continued line, below the comment skip. The engine half is the one that decides the item, and its blind spot was measured on the parent commit: with `ReadWritePaths=` wrapped, the ProtectSystem test passed on the half-line while the textfile grant had silently gone.
- `test(capture): the last_seen seed is asserted by its VALUES, not by its literal` · `test(capture): the desync-recovery task is pinned in both shutdown tuples` · `test(infra): the zaccess tunnel's port, declared in three files and reconciled in none` · `test(infra): the empty-list BASE, read back from the inventory that makes it the capture context` · `test(config): a prefix anchor whose content exempts nothing` · `test(alpha): the a2 ensemble index where min, max and sum each answer differently` · `test(research): the module default that a forgotten _anchor appends to the committed ledger` · `test(snapshot): the fee and borrow cells the sweep's UNCHANGED verdict is read off` · `test(data): the universe median moved off the window its own params declare`.

#### The tests, continued

- `test(infra): the weld a rendered template can hide from bash -n` · `test(infra): the capture group's "and only them" half, asserted` · `test(infra): the reconcile mode flag, in its position and through its cast` · `test(engine): the gate's universe read off _evaluate_journal, not passed to it by hand` · `test(engine): the engine subcommand set compared, not a six-name list restated` · `test(infra): a print that reaches the trade key, which the accessor-name scan cannot see` · `test(obs): the logship gauge an alert reads, named where a count let it slip` · `test(trades): the echoed summary's arity, so a fourteenth counter cannot be the last one` · `test(ops): the panel regeneration's could-not-read arm, which the NAS deletion branches on` · `test(obs): the ingest regex pinned to both alloy pipelines it is a copy of`.

#### Two bullets the prune did not reach, asserted rather than deliberated

The 2026-09-06 prune enumerated 52 of this section's 63 bullets. Two were in neither list — outside the owner's drops and outside the keeps — so on the coordinator's ruling they were asserted rather than carried:

- `test(continuity): a tolerance wide enough to hide the crossing and tail its docstring excludes` — `approx(400.0, rel=0.05)` spanned 380-420, so a booked 2.6 s crossing or 1.2 s tail passed unseen while the sibling `trunc` assertion stayed green too. `abs=0.5` bites: both defects measured SURVIVED before and KILLED after.
- `test(tick): the division days_gap makes, which nothing asserted` — a settled, permanently holed day counts as `days_unhealed` while the re-scan window reaches it and as `days_gap` once past it, never as both. Both arms sit in one test, straddling the boundary by a day each way; widening the D4 floor by one day inverts the gap arm while the in-window arm holds.

#### Coordinates corrected against the tree

Six citations in the readings did not resolve as written; the claims held and the coordinates are corrected here so the archived record is followable.

- The e1b probe's no-echo claim lives in the module docstring, not at `:36` (`:36` is `API_KEY_VAR`).
- The reconcile mode flag is at `archive-pull.sh.j2:131`, not `:130`.
- The ops ingest regex is at `roles/ops/files/config.alloy:322`, not `:323`.
- The rendered engine-prune `ExecStart=` is 157 characters, not about 170; its `ReadWritePaths=` renders to 77.
- The engine-prune reader's refusal cannot use `{unit.name}` — `_rendered_unit()` returns substituted text, not a path — so the message carries the line number alone; a rendered line number is the template's, since substitution inserts no newlines.
- `assert rc == 9` is at `tests/test_mutate_probe.py:398`, not `:431`.

#### Dropped consciously, with the reason

The owner dropped 28 of the 52 remaining bullets on 2026-09-06, each read at source first. They are recorded here rather than deleted, so a later reader does not re-open one as an oversight.

**Already asserted somewhere else.** `tests/test_infra_compose_templates.py` — the template's `9101` is pinned at `:98`, and the two files are deliberately not in lock-step. `tests/test_mutate_probe.py` — `assert rc == 9` at `:398`, and rc 3's two refusals are discriminated by their message substrings; nothing branches on a numeric code. `tests/test_engine_gate_cache.py` — the `>= 40` replay-path guard is the assertion, its looseness recorded. `tests/test_engine_feeders.py` — `limit_bound` is computed, published and already asserted. `tests/test_engine_journal_prune.py` — both halves are asserted elsewhere in the same file. `tests/test_features_derivatives.py` — the sentence is already gone and four tests call `ratio_features`. `tests/test_dashboards_cover_metrics.py` (two bullets) — the keep-regex claim is asserted in `tests/test_infra_alloy_series.py`, and `test_every_alerted_family_is_charted` already computes the alerted-minus-charted difference. `tests/test_engine_concordance.py` — `compare_targets` returns structurally before the per-asset indexing, so the `KeyError` is unreachable. `tests/test_archive_reconcile_command.py` — the `> 0.0` assertion is satisfied by one half alone. `tests/test_trades_backfill.py` — the one field a machine reads is asserted from both sides.

#### Dropped: the claim describes something production never reaches

**Not reached.** `tests/test_alpha_a1_directions.py` — the banded-short branch is research-only; production A1 runs `short="off"`. `tests/test_capture_book.py` — the property is measured continuously on live traffic by an exported per-pair gauge. `tests/test_capture_command.py` — production pairs come from the compose template's explicit list, never this path. `tests/test_tick_materialize.py` — a flattened-tree fixture would pin today's coincidence rather than a contract.

**The opposite is the asserted design.** `tests/test_universe_rules.py` — an uncaptured pair is recorded as unevaluated and NOT rejected, which a test already names. `tests/test_code_prose_citations.py` — the claim holds; the predicate is inline and the file's only assertion is the one that reads it. `tests/test_engine_cycle.py` — the docstring's aside cannot license removing the guard the same test pins with `pytest.raises`.

#### Dropped: nothing to pin, and the rest

**Nothing tree-derivable to pin.** `tests/test_dashboards_cover_metrics.py` (two bullets) — no rule or panel writes the `__name__=` form today, and no recording rule exists in the repo. `tests/test_nautilus_interface_pin.py` — the asymmetry is real but there is no tree-derivable source for the hand-listed half. `tests/test_costs_spread.py` — there is no max constant to pin. `tests/test_continuity_overlay.py` — the unexercised claim is a test-local helper's docstring.

**Ruled by the owner.** `roles/access/templates/zaccess-ssh-proxy.socket.j2` — the socket-ports drift. `tests/fixtures/healthchecks_descriptions.json` — the dead-man pings on gate-skips deliberately, so the fixture's wording is not the defect.

**Two claims in one bullet, and the arm that would page loses.** `zaccess-probe.sh.j2` — a failed `openssl s_client` makes `zaccess_tls_not_after_seconds` vanish rather than go stale and the cert rule's `noDataState: OK` swallows it; the page arm is what the owner declined.

**Barred by a rule.** `tests/test_capture_upstream_silence.py` — the cut sentence was a claim about the suite, which `prose.md` bans outright.

**Moves nothing deployed.** `tests/test_infra_firewall_template.py` — ansible renders the deployed ruleset from the same template either way, so an include-family divergence moves only the harness's byte-fidelity.

## Suggested next steps

_(none — every bullet of this topic is above, asserted or consciously dropped.)_
