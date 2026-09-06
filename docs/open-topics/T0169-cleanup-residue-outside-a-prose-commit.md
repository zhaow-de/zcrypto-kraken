---
status: partial
---

# Cleanup residue outside a prose commit

## Context — what

The prose cleanup (T0164) edits comments and docstrings only. Its batches surface what a prose commit cannot carry: test names that state the opposite of their assertions, a source module whose own comments disagree with each other, a template comment describing live host state, deferrals that lived only in a comment, a blind spot in the tripwire itself, and host actions no role enforces.

## Why this matters

A test name is read before its body, a live-host claim in a template is a claim no reader can verify from the repo, and a deferral with no topic dies with the comment that carried it.

## Findings so far

- `tests/test_engine_soak.py`: `test_offbyone_shifted_store_breaks_chain` asserts the chain holds; `test_instrument_expectations_reads_record_44` reads record 47.
- `cli/capture/segment_writer.py`: its comments say "12 pairs", "the other 19 streams" and "20 streams" at different lines; the numbers cannot all describe one universe.
- `infra/ansible/roles/ops/templates/alloy-compose.yaml.j2` says ops holds a live private key today; the ops task file's retired claim said the opposite, and `prose.md` forbids describing live host state in either direction.
- The ops task file said renaming the `zcrypto-archive-pull` unit and the `ops_archive_pull_*` metrics to match the overlay-writer job "is registered follow-up cleanup"; no topic registers it. The comment's own decision was that the names stay because the alert rules are provisioned against them.
- `infra/scripts/prose-tripwire.py` counts a triple-quoted string that is a child-interpreter probe's SOURCE as a docstring (eight blocks in `tests/test_engine_node.py`).
- `infra/ansible/roles/base/tasks/main.yml`: the docker json-log logrotate policy is held `state: absent` rather than deleted, because the file persists on every host that already has it and a deleted task would leave it rotating forever. Deleting the task is gated on host state, and that trigger lived only in the comment.
- `infra/ansible/roles/capture/tasks/main.yml`: the admin account's old capture key is removed by hand after the NAS repoints, never by the role. The stated precondition may already have fired — archived `T0068` records the NAS repointing capture/capture-red/journal to `zcrypto-data@` (resolved 2026-07-19) and `T0067` records `deploy`'s four hand-installed keys dropped — so this is a check before it is a removal.
- `infra/ansible/roles/nas/tasks/main.yml`: the old hot-push pubkey on the admin account is dropped by a one-time manual step once the `zcrypto-data` path is verified, and the workstation's `nas-hot` ssh alias repoints from `zcrypto-deploy` to `zcrypto-data` in the SAME change. That alias is configured only in the operator's own `~/.ssh/config` — `infra/external-systems.md` carries `Host` blocks for zcrypto, red, ops and nas and none for `nas-hot` — so nothing in this repo can check that half.

### From the `tests/` prose pass (T0164, branch `cleanup/prose-tests`)

- `tests/test_trades_command.py:16` — `NOW = H + timedelta(hours=6)` has no reader in the file. Pre-existing dead code, mentioned rather than deleted (`general.md`).
- `tests/test_trial_registry_provenance.py:159` — a trailing comment calls record 44 "the deployable" while record 47 now succeeds it. Trailing comments are out of scope on this branch, so the stale word ships; the widened-proof pass takes it.
- `tests/test_engine_probeplan.py` — a non-`ProbePlanError` raised out of `_parse_intent` escapes `_pickup`'s `except (ProbePlanError, OSError)`, leaving the plan neither journaled nor deleted and re-read every tick. Wanted: a `_pickup` test whose plan makes `parse_plan` raise a non-`ProbePlanError`, asserting both the journal row and the deletion.
- `tests/test_engine_probeplan.py` — the `EngineError` → `None` path at the live boundary journals nothing that any test reads. Wanted: a hook-level assertion that it emits its journal row, so "absence is loud" is checked rather than asserted in prose.
- `tests/test_engine_venuestate.py` — `_decimals` rests on the premise that the step is exactly `10 ** -decimals` across the whole basket. Wanted: a check over the committed refdata snapshot that `tick_size == 10 ** -pair_decimals` and `lot_step == 10 ** -lot_decimals` for all twelve legs.
- `tests/test_manifest_conformance.py` — `test_every_writer_emits_a_manifest_the_reader_accepts` drives two writers (`backfill_basket`, `ingest_basket`). `git grep -n 'build_manifest' -- cli/` gives six call sites: five producer modules (`ohlc/ingest.py:28`, `ohlc/reach.py:195`, `derivatives/oi.py:277`, `derivatives/funding.py:186`, `backfill/backfill.py:40`) plus `cli/data/manifest.py:319`'s own re-build. `read_manifest` appears in five test files, none of them a reach, funding or oi suite. Wanted: drive the three unexercised writers, or assert over the enumerated call sites so a sixth cannot appear unexercised.
- `tests/test_tick_sweep.py` — `test_an_unsettled_day_is_deferred_then_taken_once_settled` claims the watermark must not move early but reads no watermark. Wanted: `_watermark(out, "BTC/EUR") is None` after the 25h sweep.
- `tests/test_tick_sweep.py` — the corrupt-segment test claims an incomplete tape counts as `days_unhealed` rather than an error. Wanted: `res.days_unhealed == 0` asserted on that path.
- `tests/test_panel_primitives.py` — the BTC-book test claims all six columns come back null and asserts one. Wanted: all six `fill_bps_*` None on the EUR-ladder read.
- `tests/test_grafana_auth.py:38` — `monkeypatch.setattr(Path, "read_bytes", lambda self: pytest.fail(...))` with no `import pytest` in the file: if that guard ever trips it raises `NameError`, not the message it wrote. A code fix, outside this branch's prose-only boundary.
- `tests/test_registry_conformance.py` — `_ABSENT_OK`'s attribute docstring (a bare string after an assignment) is an `Expr` in the module body, not a docstring, so it is inside this branch's AST proof and was left byte-identical. T0164's widened-proof worklist on develop is entirely `cli/`-scoped, so this bullet is what owns it.
- `infra/ansible/scripts/vault-pass.sh:2` — the header says the script refuses `ansible-inventory --host/--list`; the case pattern and the refusal message both also cover `--vars`. `infra/` is outside this branch's boundary.
- `tests/test_crossfreq_system.py` — the CI-runnable `test_each_cost_term_is_read` pins only the SIGN of the implied turnover, so a half- or double-charging defect passes it. Wanted: the quotient compared elementwise against turnover recomputed from `base_build`'s own targets, which trips a half/double charge without the dataset.
- `tests/test_record43_book.py` — `test_neither_book_holds_a_durable_lead_across_the_cost_axis`'s comment claimed the smallest counted margin is orders of magnitude above float noise; the assertion reads only `params["step"] <= 0.002 and params["high"] >= 3.0`. Wanted: a minimum-margin bound over the counted sweep points.
- `tests/test_derivatives_funding.py` — off-cadence funding prints after `_CLOSED_WINDOW_END` (2026-01-01) are guarded by nothing. Wanted: the window moved forward, or a second assertion over the full series.
- `tests/test_derivatives_oi.py` — `fetch_oi_day`'s positional row contract is unpinned. Wanted: `len(rows[0]) == 1 + len(_FLOAT_COLUMNS)` plus the index-6 name, so a reorder in `cli/derivatives/oi.py:47-54` fails loud instead of moving a value silently.
- `tests/test_derivatives_oi.py` — the OI manifest's cross-build reproducibility is claimed by nothing: the test compares the on-disk manifest with the same build's returned dict. Wanted: two builds into two tmp dirs compared on `set_sha256`.
- `tests/test_tape_bars_rest_control.py:56` — `test_tape_bars_match_kraken_rest_ohlc` skips on `Kraken REST unreachable`, so on the data-bearing workstation a venue block reads as coverage. CLAUDE.md requires such a test to be gated on an explicit opt-in env var instead, so a skip is a decision. A code change, outside this branch's prose-only boundary.
- `tests/test_capture_upstream_silence.py` (head :449) — an assertion message names "T0105's rule"; T0105 is `status: resolved` in `docs/open-topics/archive/`. It is a string constant, so editing it would break this branch's non-prose-byte contract. A reviewer checked it: `alerts.yaml` carries no `gap_ratio` rule, so the text points at a design, which is what it says — a tense problem, not a false claim.
- `tests/test_reboot_check.py` and `tests/test_clock_offset.py` — a near-verbatim duplicated helper pair that has already drifted in three places. A shared helper would make the next divergence a failure instead of two prose copies.
- `tests/test_archive_scan_cache.py` (head :487) — the trailing comment still attributes the overlay case to `delete_cache`; the corrected docstring above it says the caller never writes such an entry (`cli/archive/command.py:1089-1094`, `cli/archive/scan_cache.py:31-33`). head :479's "and therefore the entry it stores" is the same wrong pair.
- `tests/test_engine_concordance.py:69` — `tol = 1e-6  # today's ratified default (concordance.py:159)` keeps the stale coordinate the docstring two lines above no longer uses; `compare_targets` is at `:133`.

### From the `tests/` remainder (T0164, branch `cleanup/prose-tests-remainder`)

- `infra/scripts/kraken-order-semantics-probe.py:2102` — "Kraken's costmin on the EUR pairs is 0.45" is a venue value in prose with no measurement named beside it, in a file an operator runs against real money. Outside a prose pass's reach; it is the one number in that file that can go stale in silence.

### From the docs remainder (T0164, branch `cleanup/prose-docs-remainder`)

- `docs/reference/kraken-snapshot-register.md`'s row `#127` stays far over the row bar because nearly every clause is a protected figure; the one cuttable piece is the Fee-tab "+$1 shortfall" reading convention, whose durable home is `.claude/skills/zcrypto-refdata-sweep/SKILL.md` step 7. That step now reads the account through the API rather than the screen, so the convention may be obsolete rather than relocatable — decide which before moving it.
- `docs/reference/multi-agent-protocol.md` stays over the section bar; the only remaining honest candidate is its preamble duplicating `.claude/rules/agent-ops.md`, which is a call for the owner rather than a prose cut.
- `docs/reference/capture-era-data-hygiene-map.md`'s 2026-09-03 row records an unexplained ~28 s remainder with no registered topic. It survives this pass verbatim; it wants an owner, not an edit.

## Done so far

On `fix/t0169-cleanup-residue`, each bullet's landing commits are that branch's and every one names its own file in its subject.

### The six in-repo next steps

- **The two soak tests** now say what their bodies assert. `test_offbyone_shifted_store_breaks_chain` asserts `chain_ok is True` and is `test_the_chain_identity_holds_on_shift_detectable_closes`; the second reads record 47, which `_instrument_expectations` selects — the asserted constants do not discriminate, since records 44 and 47 both carry 7302 and 1318.
- **The segment writer's three counts** are the property statement the file already used four other times: "every pair and both kinds". Twelve pairs across two kinds is twenty-four streams, so "the other 19" and "the 20 streams" could not both hold with the first.
- **The template's live-host sentence** is gone: config prose says what `/host/root:ro` exposes and what the `user:` override keeps out of reach, not what a host currently holds.
- **The two detect-only comments** say the role default is detect-only and the mode is whatever `ops_reconcile_mint` selects; the flip is a named `host_vars` setting, and neither comment asserts what a host runs.
- **The `T0020` pointer** is cut rather than re-tensed: the sentence above it already states what a reader acts on, and once the labelling pass landed the clause added no action.
- **The two adapter-verification records** cite `infra/runbooks/engine-procedures.md`'s `engine-probe-window` — three citations, not two: pre-probe step 3, pre-probe step 4 and the arming section. `engine.md` carries no pre-probe step at all since spec 00104 moved them.

### Four Findings bullets taken with them, on the coordinator's ruling

- **`tests/test_grafana_auth.py`** imports `pytest`. `test_the_password_helper_is_EXECUTED_never_read`'s guard against reading the vault-password file called `pytest.fail` in a file that never imported it, so tripping it raised `NameError`; where that read sits inside an `except Exception:` the guard passed silently green, because `Failed` derives from `BaseException` and `NameError` does not.
- **`tests/test_archive_scan_cache.py`**'s two trailing comments credit the caller's refusal to cache a changed hour, which is what covers the blind case; `delete_cache` owes the ledger-only mutation.
- **`tests/test_engine_concordance.py`** cites `compare_targets`' `tol` by symbol; the line it named was empty.
- **`infra/ansible/scripts/vault-pass.sh`**'s header names `--host/--list/--vars`, matching its own case pattern, its refusal message and `fleet-deploys.md`.

### Two rulings applied while the branch was open

- **`cli/engine/soak.py`** and **`cli/panel/primitives.py`**: `# D9` is `spec 00059 D9`; `# 34` and `# 17` were the `len()`s of the literals beside them and are gone; the panel constant cites `spec 00085 D1 Task 1 Step 0`, the form its own test already wrote.
- **Topic ids carry no status annotation** in the files this branch touched — five annotations across `cli/panel/primitives.py`, the ops role's defaults and its archive-pull template. The same form elsewhere in the tree is the sweep registered under `## Suggested next steps` below.

## Suggested next steps

- **A status annotation on a topic id, wherever it still stands.** The owner's rule is that a topic id is never annotated with its status — a reader looks the topic up and sees it, and the annotation goes stale on its own while the id does not. This branch applied it only where it edited; the rest is a mechanical sweep. Enumerate with `git grep -nE 'T0[0-9]{3}[^)]{0,30}(resolved|archived)' -- cli/ infra/ docs/reference README.md`, and re-tense each sentence to what is true rather than deleting the id, keeping it where a reader would look up the history. `infra/ansible/group_vars/observed/vault.yml` is never edited.

- **Owner's decision**: the archive-pull → overlay-writer rename is either owed (then its own topic, a converge and a re-provision of every alert that names the metrics) or not (then the names stay, and this line is the record of that).
- Tripwire: exclude a string literal assigned to a variable or passed as an argument from the docstring count, with a fixture that trips on a real docstring and passes on a probe source.
- **Host-state-gated**: delete the logrotate task once `/etc/logrotate.d/zcrypto-capture-docker` is absent on every capture host and on the engine host. Nothing in `tests/` reads it (`git grep -ln logrotate -- tests/` is empty).
- **Host action**: read the admin account's `~/.ssh/authorized_keys` on each capture host for the old capture key and remove it if present; `T0068`'s repoint, the precondition the comment names, is already recorded resolved.
- **Host action, one change**: remove the old hot-push pubkey from `~zcrypto-deploy/.ssh/authorized_keys` on the NAS once the `zcrypto-data` path is verified, AND repoint the workstation's `nas-hot` alias to `zcrypto-data` in the same change.
