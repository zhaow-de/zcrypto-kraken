---
status: partial
ripe_when: 'refine-rules round 8 is on develop: `git log origin/develop --grep="^Refine-Round-Closed: 2026-09-04T23:52:07Z" --format=%h` is non-empty'
---

# The global prose cleanup under `prose.md`

## Context — what

Round 8 landed one prose rule (`.claude/rules/prose.md`: a durable file holds state and decisions, an event goes to git) and the tripwire that holds its thresholds (`infra/scripts/prose-tripwire.py`, PR #397). The rule stops new prose over the bar from entering; nothing yet removes what exists. The owner's word (2026-09-04): right after the round, a global scan of every existing comment, docstring and living doc under that rule — the third such cleanup, the first with a written bar.

## Why this matters

The retro study of 2026-09-04 measured the prose layer as the day's cost: 26 of 30 Critical or Important review findings were prose stronger than the mechanism beside it, and half of every component's wall-clock went into the review loop that found them. Comments and docstrings are a second, untyped layer only a second reader checks; the docs half (the phase changelogs, `fleet-pins.md`, `fleet.md`) had become a commit log and a story board respectively, reviewed like code.

## Findings so far

- Baseline on develop `f5400d19`, `.local/retro/2026-09-04/study/prose-ratio.py` (tokenizer count of comment + docstring lines): `cli/` 29%, `tests/` 21%, `infra/scripts/` 24%, total 27,479 prose lines of 112,950 (24%). Re-run the script for the after-number; never carry the figure.
- Tripwire census at `b655d00e`, `uv run python infra/scripts/prose-tripwire.py`: comment-block 1909, file-prose 183, table-row 98, section 352 (in 51 files), changelog-entry 135 — 2,677 offenders, exit 1. `--since origin/develop` reports 0, so the tool gates new prose while this topic is open.
- The docs half, measured 2026-09-04 on develop: `docs/iterations-history-phase6.md` 1,232 lines / 620 KB with entries of 1.9–7.5 KB; `docs/reference/fleet-pins.md` 45 lines / 14.5 KB with rows of 1,400–1,500 characters rewritten 38 times; `docs/reference/fleet.md` 80 lines / 20 KB.

## Done so far

The first `tests/` + `infra/` batch (PR by `zcrypto-bravo`, 2026-09-05): `tests/test_engine_executor.py`, `tests/test_infra_alert_rules.py`, `tests/test_engine_flatten.py` and `infra/grafana/alerts.yaml` under the bar — every block dispositioned against its code, the Python files AST-identical with docstrings stripped, the YAML's non-comment lines and parsed content byte-identical, one whole-branch and three scoped Fable reviews. Twelve sentences that claimed what nothing asserts became T0165, T0166 and T0167. Consciously left: the six sops `vault.yml` files (encrypted; a prose pass never edits them) and the two vaulted-key wrappers whose bodies `tests/test_kraken_fixture_mint.py` pins by sha256. Measured at the batch's tip: the tripwire over `tests infra` 1,501 → 1,413 offenders; `tests/` 16,235 → 15,688 prose lines.

The second `tests/` + `infra/` batch (2026-09-05, `zcrypto-bravo`): eight more files — the continuity, converge-guard, soak, node, capture-writer and daily-pass tests, the daily pass itself and the ops role's task file — under the bar, each proven prose-only (Python AST-identical with docstrings stripped; the YAML's non-comment lines and parsed content byte-identical); one whole-branch and one scoped Fable review. The tripwire over `tests infra` 1,412 → 1,272 offenders; `tests/` 15,739 → 15,076 prose lines. What that batch found asserted only in prose went to T0168, what it could not carry to T0169; both infra halves add to both.

The docs batch (branch `cleanup/prose-docs`, 2026-09-05, `zcrypto-bravo`): `fleet-pins.md`, `fleet.md` and the seven phase changelogs under the bar, every heading, divider, rule, cell, digest and hash proven identical (`parse_pins_table` equal); tripwire on the nine files 335 → 17 at merge-base and tip — the remainder is fleet.md's twelve enumeration rows and two sections, fleet-pins' agentboard row and Standing constraints, whose operator instructions await homes, and the appended 2026-09-05 T0170 entry; a whole-branch Fable review and its fix's re-review.

### The `cli/` batch

Branch `cleanup/prose-cli`, 2026-09-05, `zcrypto-alex`: 83 of `cli/`'s 167 files brought under the bar or found already under it — 77 changed, six needing no edit — across 63 commits, one per package. Every file is proven prose-only against the commit it lands on: the AST with every docstring stripped identical, `ruff check` and `ruff format --check` unchanged, and the inventory of trailing comments on code lines byte-identical by `tokenize`, so no same-line comment moved anywhere on the branch. Eight drafter and verifier waves returned 116 file verdicts, 83 accepted and 33 left REVISE. One whole-branch Opus read, three scoped Opus reads and a per-hunk read of the corrections commit — the whole-branch read's own suggested wordings were applied unverified and two were false of the code they sat on, which is why the last read asks one question per hunk and names the code line each clause cites.

Measured over `cli/` at the merge-base and the tip, both re-run at the rebased tip (`uv run python infra/scripts/prose-tripwire.py cli`, and `.local/retro/2026-09-04/study/prose-ratio.py <rev>` for the ratio): the tripwire 773 → 418 offenders, prose 9,787 → 7,505 lines of 32,720 → 30,438, 29% → 24%, and code lines 19,433 at both ends — the prose-only property visible in the measurement. Of the 43 file-prose offenders left, 32 are exactly the REVISE files; the other 11 are modules of one to nine lines where the ratio bar is unreachable by construction (`cli/alpha/errors.py` is two lines, a class statement and its one-sentence docstring), so they need a floor in the script rather than an edit. Eleven comment-block offenders also survive in landed files — nine in `cli/engine/soak.py` and two in `cli/universe/rules.py` — each a logged keep with its own over-threshold justification recorded per block, and each owed `prose.md`'s necessity gate at review rather than a further cut.

### The `infra/` batch — code and config

Branch `cleanup/prose-infra`, 2026-09-05/06, `zcrypto-bravo`: 59 files under the bar across 30 commits, in five batches ordered by ascending offender count, each taking one Opus round over its own commits, then one whole-branch Opus read and two scoped re-reads. Every file is proven prose-only against the commit it lands on, by kind: YAML by `yaml.safe_load` equality AND a sha256 over the non-comment lines; shell by byte-identical non-comment lines, where `#!` wherever it appears — a heredoc that writes a script carries a second one — and every `# shellcheck` directive count as CODE; Python by an AST with every docstring stripped plus the inventory of same-line trailing comments byte-identical; Markdown by every heading byte-identical, which is what `tests/test_infra_alert_rules.py` and `tests/test_ops_daily.py` resolve their `Runbook:` anchors against.

Measured over `infra` at the merge-base and the rebased tip (`uv run python infra/scripts/prose-tripwire.py infra`): 529 → 448 offenders, of which 163 are the fifteen docs pages the split below defers — identical at both ends — so the code-and-config half moved 366 → 285. One block crossed the bar rather than falling under it, `infra/ansible/scripts/converge.sh`'s recorded-pass header, which carries the pins re-truing decision, the invariant that no `-e` operand is ever a secret, and the orphaned-child footgun with its recovery.

Both runbook sentences this topic registered as stale were FALSE rather than stale, and are corrected as state: `drills-order-path.md`'s "neither of the two is deployed" — the engine row pins revision `4925e060`, which declares `MODES = frozenset({"execute", "rest-cancel", "rest-hold"})` and carries `cli/engine/flatten.py` — and `engine-procedures.md`'s NAV-disarm step, whose owed fix had landed as `cli/engine/tracking.py`'s `cycle_nav = nav if s.nav is None else s.nav`. T0168 takes the batch's four test candidates and three blind spots; T0169 takes three items a prose commit cannot carry, one coupling the NAS admin-key removal to the workstation's `nas-hot` alias repoint, which is configured outside this repo.

Residuals kept, with their reasons: both credentialed wrappers stay over the four-line bar because `tests/test_kraken_fixture_mint.py` pins the probe's body by sha256 from the first line that is exactly `set -euo pipefail`, so no comment may relocate below that anchor and condensing in place is the only disposition available; `zcrypto-clock-offset.sh`'s header stays at seven because both surviving items are about the whole script rather than any line in it; `ops-postverify.sh`'s tape-bars block stays at five carrying three decisions; `infra/external-systems.md`'s `### Initial setup` section stays over the section-byte bar.

### The `tests/` batch

Branch `cleanup/prose-tests`, 2026-09-06, `zcrypto-bravo`: the whole `tests/` worklist bar the files held for `feat/t0168-unasserted-claims`, in batch commits ordered by ascending offender count, then fix commits answering the reviews. Every file is proven prose-only against the commit it lands on — the AST with every docstring stripped identical, every same-line trailing comment byte-identical, `ruff check` and `ruff format --check` verdicts unchanged, and no test renamed. Read-only drafters proposed the edits as data and never wrote the worktree; read-only reviewers read a detached worktree at each batch's commit, in disjoint file groups, while the next batch's drafters ran.

Measured over `tests/` at the merge-base and the rebased tip (`uv run python infra/scripts/prose-tripwire.py tests`): 743 → 452 offenders. `.local/retro/2026-09-04/study/prose-ratio.py` at both revisions reports the same 205 files and the same 44,136 code lines — a whole-tree corroboration of the prose-only proof from a tool built for another purpose. Its prose-line figure is not quoted here: every later prose fix moves it, so the number would be one commit stale the moment it was written.

What the pass was actually for, beyond the byte count: **the sentences the code contradicted and the citations that resolve to nothing**. A default given as 5h where the option declares `21600.0`; capture described as `restart: always` where the compose template is `unless-stopped`; a replay closure called 54 and 61 modules where `len(_replay_code_paths())` measures 81; `Executor._read_plan`, `SS12` and `H1.`, none of which exist anywhere; a scan-cache "residue `delete_cache` still covers" that the caller refuses to create; a consumer list already stale at the moment it was written.

**The proof's own weak parts, found by the reviewers and worth carrying into any future pass**: `ruff format --check` compares each side to its OWN formatted form, so a format-stable reflow — a magic-trailing-comma explosion, built as a control — passes on both sides; and `ruff check` is near-vacuous under `select = ["I"]`. What actually pins "prose only" is the docstring-stripped AST, the trailing-comment inventory, and a line-level check that every changed line on both sides falls inside a docstring span, a standalone comment, or a blank.

Residuals kept, with their reasons: `tests/conftest.py` stays over the file-prose bar because it is mostly two isolation refusals every test in the suite depends on — a leaked metrics sink means live venue calls out of the unit suite, and `_update_metrics` logs what it raises instead of propagating, so the leak is silent. `tests/test_vendored_rrsync_integrity.py` stays over it because its docstring is the decision its byte-exact pin rests on. Some of the offenders left in the last batch's files are string literals the tripwire counts as prose while the AST calls them code — a tool defect owed by `zcrypto-main`'s hook PR, not padding to be cut; the split is in that commit's message, where a count belongs.

**Still excluded, taken last after `feat/t0168-unasserted-claims` merges**: `tests/test_infra_converge_guards.py`, `tests/test_engine_node.py`, `tests/test_ops_daily.py`, `tests/test_capture_segment_writer.py`, `tests/test_infra_continuity.py`, `tests/test_mutate_probe.py`, `tests/test_infra_compose_templates.py`, `tests/test_ops_postverify.py`, `tests/test_infra_alert_rules.py`. `tests/test_infra_firewall_template.py` was released to this branch mid-pass and is done.

**One adjudication closed rather than registered**: the firewall golden pin's fidelity rests on `_render`'s Jinja settings matching ansible's template module, and they match in effect — ansible 2.21.3 defaults `trim_blocks=True`, `lstrip_blocks=False`, `newline_sequence="\n"`, and `_engine.py` appends the input/output newline difference for parity instead of setting `keep_trailing_newline`. The condition that would break that equivalence is registered in T0168 rather than left in this paragraph.


## Suggested next steps

- **The remaining scope, one PR per batch, dispatched by `zcrypto-main`** — the 33 `cli/` files left REVISE (rostered below), the nine `tests/` files held for `feat/t0168-unasserted-claims` (the tripwire's report is the worklist; a dozen sub-threshold soak blocks still carry event residue the tripwire cannot see), the three docs. Worklist per assignment: the tripwire's report for that scope, the files that can complete first (fewest offenders, one review round) under a hard clock, otherwise the churn order (`.local/retro/2026-09-04/study/churn.md`, most-changed first) with `.claude/*`, `docs/specs/*` and `docs/plans/*` excluded — the refine-rules round owns the first, and a spec/plan pair is a different kind of document with its own treatment.
- **Per file, `prose.md`'s four dispositions** (cut, condense, keep, relocate), findings agreed before editing, false-or-stale first; a config file's non-comment lines extracted before and after and byte-identical; a test docstring re-read against its assertions.
- **The `infra/` docs and runbook pages are DONE**, on branch `cleanup/prose-infra-docs`: the fifteen pages, 23 commits, five per-page Opus rounds and one whole-branch Opus read. Measured over the fifteen at the merge-base and the tip (`uv run python infra/scripts/prose-tripwire.py <the fifteen>`): 163 → 101 offenders, and 559,268 → 515,023 bytes (−7.9 %). Table rows over the 200-char bar 72 → 21 and sections over the 2,048-byte bar 91 → 80, with no file regressed; the 101 offenders at the tip are the per-page REGISTERED RESIDUALS blocks in the branch's commit messages. What remains at the tip is registered, not missed: every one of the 101 is named in a page's REGISTERED RESIDUALS block with its reason and, where a row cannot reach 200 characters, a computed floor — the whole-branch read spot-checked twelve of those floors arithmetically and found all twelve arithmetic.

  The finding, and it is why this pass exists rather than the byte count: **a pointer that resolves but whose target does not carry the claim is invisible to every guard in the tree.** `tests/test_infra_alert_rules.py` asserts that every `<file>.md#<anchor>` cross-reference resolves and that every anchor has an index row — both held green throughout — while five separate pages sent an operator to a section recording something else. The same class, differently dressed: a runbook quoting a log line the code does not emit; a page denying a field the daily pass reads every morning; an index carrying a claim its destination had explicitly retracted, dated; a page branching on a converge that had already landed on both the pin and its rollback operand; and a page calling a re-run costless where `host_vars` had set the mint flag true nine weeks earlier. Each is a citation in form and a falsehood in content, and no test in this repo can see the difference.
- **Measured before and after**: the tripwire's summary line on the merge-base and on the tip of each PR, quoted in the PR body.

### Registered from the batches, for the coordinator

- **The owner's closeout decisions the batches collected, one clause each**: fleet.md's ten operator instructions — the engine-image ad-hoc read, the single-identity SSH agent a zaccess converge needs, the bridgehead's digest-less Alloy, the client-cert revocation procedure, the agentboard node-upgrade recipe, the NAS transfer instructions, the two drill recipes and the wiring-not-timing caveat — to runbook homes; phase 2 iter-013's CPCV purge/embargo windows proven sufficient but not tight, to a topic or a two-sided-bound assertion in the CPCV property tests; iter-168's unmeasured in-flight REST query on an affected leg, to a T0160 sub-item; `notification_settings.repeat_interval` surviving a `grafana-push.sh` upsert, to a guard in `tests/test_infra_alert_rules.py` or a read-back in the script; phase 3's regime-gate EMA variant (spec 00019's out-of-scope list only) and the §12 hand-back confirming B4 as the fallback deployable (closeout report and master plan only), to a topic or decisions-log line each; phase 0's two known minors — the registry append after a hand-edited unterminated last line, and `fetch_public`'s KeyError on a result-less body (`cli/snapshot/fetch.py` still returns `payload["result"]`) — to a fix or recorded drop each. Batch 2's check-mode coarseness and converge-guard claims are already T0168's ops-role bullet.
- **Owed by `zcrypto-main`**: the rollout skill's NAS section takes the two clauses cut from the pins row (every rollout pins a `develop` build; `-e nas_capture_image_digest=` is silently accepted as an unused extra var); archived T0162 re-tensed now that the `alerts.yaml` comment is a pointer; one closeout entry in `docs/iterations-history-phase6.md` for the whole cleanup; the tripwire pre-commit hook with the last PR, once `--since` is no longer needed — its residuals to clear first: the 2026-09-05 T0170 entry, fleet.md's twelve rows and two sections, the agentboard pins row and Standing constraints, and the five section offenders this file, T0168 and T0169 now carry — a topic's registry sections grow with every registration, so the bar either exempts open-topics or these five are adjudicated as permanent keeps.

### From the `cli/` batch — the 407 candidates

The raw list, with every item's file and its live-or-dormant state, is `.local/dispatch/2026-09-05-t0164-cli-candidates.md`. Nine classes: `draft-disposition` 99, `test-or-guard-owed` 86, `test-already-asserts` 71, `home-verified` 31, `registration-owed` 31, `sibling-file-prose` 24, `tree-defect` 22, `ruling-owed` 22, `pass-level-finding` 21.

- **130 of the 407 need no main-tree action** — the `draft-disposition` and `home-verified` classes, a drafter's own choice and an audit record that a cut lost nothing.
- Of the 53 `tree-defect` and `registration-owed` items, **17 are live in landed files** and **36 are owed by whoever finishes one of the 33 REVISE files**.
- The 22 `ruling-owed` items are `zcrypto-main`'s, under their own heading in that file with the ruling each needs on one line.
- The 21 `pass-level-finding` items amend the pass brief or `prose.md` rather than any file under `cli/`, and went to `.local/agent-lessons/zcrypto-alex.jsonl` as rule feedback for the round-9 harvest.

### From the `cli/` batch — the follow-up pass this pass's rule froze

`zcrypto-main`'s ruling (2026-09-05): the proof for that pass widens to AST-with-docstrings-stripped identical plus `ruff` unchanged, trailing comments free, since the AST proof already guarantees the code and a same-line comment is prose. Its worklist:

- `cli/capture/ws_client.py`'s `(T0035)`, re-tensed now that the topic is archived `resolved`.
- `cli/derivatives/oi.py`'s `# 4xx (incl 404) is definitive`, which does not match its own branch `exc.code is None or exc.code < 500`.
- `cli/engine/probeplan.py`'s `# Sec 10's 250% floor`, to the `Master-plan §10` spelling its two siblings in `cli/risk/` use.
- `cli/engine/soak.py`'s two bare-number citations, `# D9` and `# 34`/`# 17`.
- `cli/panel/primitives.py`'s `# the Step 0 measurement, verbatim`, a plan-local step with no serial that `tests/test_code_prose_citations.py` cannot see.
- **The three `cold-review` citations that resolve from nothing in the repo** — `cli/engine/command.py`'s `# lazy -- see seed_cycle_success (cold-review I4)` (also one of the above), `cli/data/manifest.py` and `cli/liquidations/coinalyze.py`. The token names a review round, not a repo artefact, against `prose.md`'s rule that every citation resolves from the repo alone.

### The 33 `cli/` files left REVISE

Untouched in the tree, and each owed by whoever finishes that file. Every one carries at least one Critical or Important against its draft — 5 Critical and 44 Important in all — with the count and the leading finding below.

#### `cli/alpha` through `cli/data`

- **`cli/alpha`** — `b1.py` (1I, the completion-time cut lost its binding to the decision boundary); `killbar.py` (1C/1I, `full window` dropped, an invariant the types do not hold now stated nowhere).
- **`cli/archive`** — `command.py` (3I, a purpose clause scoped to `pull` rewritten as a claim about all four commands); `pull.py` (1I, `verified`'s membership restated without the and-ok half); `reader.py` (1I, the doubled-stream consequence re-attached to the wrong arm); `reconcile.py` (1I, the dedup described as global where the code drops equal neighbours); `scan_cache.py` (1I, `deeply` dropped, leaving a claim false of the line above it); `settle.py` (1C/2I, the inclusive-bounds why now stated nowhere in the file).
- **`cli/capture`** — `book.py` (1I, a `_to_decimal` precondition written wider than the code); `desync_recovery.py` (1I, an undisclosed cut took the grace's lower bound); `segment_writer.py` (5I, a stream clause false of the reference the code computes); `ws_client.py` (1I, `uncorrelated` invented for a path that still mints and tracks `sub_id`).
- **`cli/costs`** — `calibrate.py` (1I, names a refusal `calibrate()` cannot produce).
- **`cli/data`** — `manifest.py` (1I, the invariant binding `relpath` to the frame it was read from, dropped); `sync.py` (1I, half the why for the file's existence over-cut).

#### `cli/engine` through `cli/portfolio`

- **`cli/engine`** — `cycle.py` (1I, the defect the placement exists to prevent, mis-stated); `execgate.py` (2I, a contract left wider than the code); `executor.py` (4I, `_publish_fill`'s reach stated wider than its three call sites); `flatten.py` (2I, a consequence the code beside it cannot produce); `gate_cache.py` (1I, the draft trips the tripwire on both the block and the file); `instruments.py` (1C, an undeclared cut took the base-10 clause); `node.py` (1I, over-cut on a verification that tested the wrong surface); `venuestate.py` (1I, detectability replaced by a weaker claim).
- **`cli/features`** — `derivatives.py` (1C, the constancy qualifier, spec 00110 D7's load-bearing word, dropped); `volatility.py` (1I, the output-length invariant cut).
- **`cli/liquidations`** — `coinalyze.py` (1I, the same-tree condition that makes the reuse claim true, dropped).
- **`cli/panel`** — `materialize.py` (2I, names a float hazard this module's Float64 inputs cannot carry).
- **`cli/portfolio`** — `crossfreq.py` (1I, the fence-post end never bound to an index); `crossfreq_system.py` (2I, an identity pin attributed to a test that does not assert it); `record43_book.py` (1I, `recomputed` attached to fields returned straight from the builder).

#### `cli/snapshot` through `cli/xcheck`

- **`cli/snapshot`** — `register.py` (1C, a relocated sentence states a contract wider than T0025's resolution).
- **`cli/trades`** — `backfill.py` (1I, cites a `--mint` flag this command does not define).
- **`cli/xcheck`** — `binance.py` (1I, drops the `<=` and asserts the fetch returns `limit` candles).
