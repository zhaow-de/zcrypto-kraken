# The Blockpit fallback: Kraken's ledger and trades exports become Blockpit manual-import rows, archived monthly — implementation plan

> Every value a rollout reading decides is a marked slot, `ROLLOUT:` inside double square brackets, listed at the end.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `zcrypto tax blockpit` maps one window of Kraken's ledger and trades CSV exports onto the rows of Blockpit's manual-import template — a `collateralconversion` pair as one Trade EUR → EURC, a margin close's fee in a Margin Fee row of its own beside its Margin Profit or Loss, every other row type the export holds as spec 00126 D3's table labels it — and writes a provenance file beside the output; it refuses, writing nothing, on a row it cannot map, a balance that does not chain, a movement the output does not carry, a repeated Trx. ID, or a window that does not follow the one before. The monthly procedure archives the exports and the file on the NAS, the daily pass reminds it, and the tracking report reads the export's spelling of a reward. The owner then imports the whole history into a fresh manual integration and re-reads Step 7's five criteria.

**Architecture:** Nine tasks on `docs/t0215-blockpit-fallback`, the branch that holds spec 00126 and this plan, merged as one pull request. The module grows task by task in `cli/tax/`: the template's header and labels and the two readers over the invented windows first; then the mapping and window one's golden rows; the join's cross-check; the run with its checks and its provenance; the `--after` chain and window two; the command and its README section. Then the tracking report's `earn`, the bookkeeping page with the NAS tree's mentions and the daily pass's reminder, and the topic, flipped to `partial` once the pull request is open. The Rollout opens the pull request as a draft before Task 9 and undrafts it after, and after the merge runs the first whole-history window into Blockpit, the five criteria's re-read and, once it passes, the owner's decision on the connector's integration.

**Tech Stack:** Python 3.14 through `uv run` (`csv`, `decimal`, `hashlib`, `json`, `zipfile` from the standard library, no new dependency); Typer (`cli/__main__.py`'s app) and `typer.testing.CliRunner`; pytest; `infra/scripts/mutate-probe.sh` for guard verdicts; the daily pass `infra/scripts/ops_daily.py`; the workstation's `kraken` CLI and Blockpit's web UI in the Rollout alone.

**Spec:** `docs/specs/00126-blockpit-fallback-transform-design.md` as the branch's last commit to it leaves it (`git log -1 --format=%h -- docs/specs/00126-blockpit-fallback-transform-design.md`): D1 to D10 as the owner's rulings of 2026-10-09 settle them, "What changes in the repo", the invariants and the measured basis. Every label, column, refusal and file name below is the spec's; where this plan pins a literal the spec leaves open — a refusal's wording, the provenance's keys, the integration name, the fixture — the plan's text is the one written.

## Global Constraints

- No executor step reaches Kraken, Blockpit, the NAS, a fleet host, Grafana or Slack, and none runs the `kraken` CLI: each such step is an operator step of the Rollout. `ansible-playbook` and `infra/ansible/scripts/converge.sh` are not run at all — nothing here converges, and the workstation is the fleet host `zcrypto-ops`.
- The owner's real exports lie under `/home/zhaow/Projects/zcrypto-kraken/.claude/worktrees/t0215-blockpit/.tmp/spec-00126/` (gitignored). An executor reads that directory at four steps: Before Task 1's hash read of the template's two files and Task 1's copy of them — Blockpit's own files, none of the owner's — Task 1's check that the invented windows share no value with the owner's exports, which prints one count, and Task 6's smoke run, whose output stays under `.tmp/` and is deleted at its step. No value of the owner's exports — a `txid`, `refid`, time, amount or balance — enters a commit, a fixture, a test, a message or a pull request body; a file's sha256, which names the file and carries none of its values, is not one. The fixtures are the invented windows this plan gives byte for byte, their ids `LFX…`, `TFX…`, `OFX…`, `EFX…`, `FFX…`, their months March and April 2031 and their crypto assets ATOM, ALGO, XTZ and NEAR.
- A guard is proven by `infra/scripts/mutate-probe.sh`, one probe at a time, in-repo on the committed tree, never beside a pytest run in the same checkout. The task commits with the line `PROBE_VERDICT` in its message; its probes run on the committed tree, each with `--control '1,$d'` — every probed file here is a module, a test-read fixture, a test-read README or a runbook page whose emptied text fails the selected tests, or the test file, whose emptied text leaves the selection nothing to collect, pytest's exit 5 — and each must end `mutate-probe: KILLED (control proven, tree restored byte-identically)`; then a message-only amend, the tree clean, replaces `PROBE_VERDICT` with each probe's command and its verdict, naming `infra/scripts/mutate-probe.sh`. The branch is unpushed while the tasks run, so the amend rewrites nothing a reader holds. Every probe below was run against a draft of the code this plan gives and was killed; a probe that does not run as printed — a `sed` the committed text does not match is refused as a no-op, rc 6 — is re-anchored on the committed line, never dropped.
- Line numbers of existing files are readings at `f70be7dae`, the branch's base, which the branch's spec commits did not move: each edit is anchored on the quoted text, the number only where to look.
- `tests/test_internal_terms_not_operator_visible.py` scans every string literal under `cli/` and `infra/scripts/` and the README and runbook text: none carries `Phase <N>`, `T<NNNN>`, `iter-<N>`, `spec <NNNNN>`, `D<N>` or `WP<N>`; a provenance token goes in a comment. No non-Markdown file under `cli/` or `infra/` carries the string `kraken-cli` (`infra/scripts/count-list.sh kraken-cli-on-infra-surfaces`).
- The commit gate before every commit: the commit's files staged by path, its new files among them, then `uv run pre-commit run -a` until clean, its rewrites staged (ruff's `--fix` orders imports). Conventional Commits; no `.claude/` file and no rule is touched by this plan. Every commit is green over its consumers, never the full suite locally: `infra/scripts/consumers.sh` governs each task's consumers run, in the implementer contract's form — every test it lists for each path the task's commit stages — and the tests a consumers step names are a floor beneath that list, never the whole run.
- A step of Tasks 1 to 6 that names no command runs this one: *Run the tests* or *Run them* — `uv run pytest tests/test_tax_blockpit.py -q -p no:cacheprovider`; *The consumers* of Tasks 1 to 5 — the tax consumers command, `uv run pytest tests/test_tax_blockpit.py tests/test_internal_terms_not_operator_visible.py tests/test_code_prose_citations.py tests/test_live_venue_opt_in.py tests/test_guidance_refs_resolve.py -q -p no:cacheprovider`, then the consumers' run, Expected: no failure. *The consumers' run*, in every task after the tests its consumers step names: `uv run pytest $(infra/scripts/consumers.sh <each path the task's commit stages> | grep -E '^tests/test_[^/]*\.py$' | sort -u) -q -p no:cacheprovider`, Expected: no failure; the script's `git grep` reads tracked files alone, so a test the task creates is among the step's named tests, not in its list. *The tree is clean*, in every task, is `git status --porcelain`, Expected: empty.
- A new Markdown paragraph or list item is one line; an existing file keeps its form. Every page under `infra/runbooks/` and `docs/reference/fleet.md` is a contract page of the commit-msg guidance guard: a list item carrying `every`, `never`, `always`, `only`, `any` or `cannot` names its count or declares `(no count command: …)`, so the texts below are worded without them, and `uv run python infra/scripts/guidance-guard.py --uncounted <page>` prints nothing before the commit. `zcrypto-refine-rules` is loaded before Task 8 writes `infra/runbooks/bookkeeping.md`, a new top-level page under `infra/runbooks/`.
- Every reviewer — each task's and the branch's — runs on Opus, the model passed explicitly.
- A commit message ends with this trailer, the placeholder replaced by the executing model's own name, followed by the executing session's `Claude-Session:` line where its harness supplies one:

```
Co-Authored-By: Claude <actual executing model> <noreply@anthropic.com>
```

## File structure

- `cli/tax/__init__.py` (new, empty), `cli/tax/errors.py` (new: `Refusal`, `TaxExportError`, `Refused`), `cli/tax/kraken_export.py` (new: `LedgerRow`, `TradeRow`, `read_ledger`, `read_trades`), and `.pre-commit-config.yaml` (the template's CSV kept as fetched) — Task 1.
- `cli/tax/blockpit.py` (new): `HEADER` and `TEMPLATE_LABELS` (Task 1); the mapping, `map_rows` and `render_csv` (Task 2); `check_cross` (Task 3); `check_chain`, `check_conservation`, `check_order`, `check_unique`, the provenance and `transform` (Task 4); `check_continuity`, `_previous` and `transform`'s `after` (Task 5).
- `cli/tax/command.py` (new) and `cli/__main__.py` (the app's registration); `README.md`'s `### zcrypto tax` section — Task 6.
- `tests/test_tax_blockpit.py` (new, Tasks 1 to 6); `tests/fixtures/tax_blockpit/` (new): the template's `blockpit-template.xlsx` and `blockpit-template-gid0.csv` and the two windows' four exports (Task 1), window one's golden `window-1-blockpit.csv` (Task 2) and `window-1-blockpit.csv.provenance.json` (Task 4), window two's golden pair (Task 5).
- `cli/engine/tracking.py`, `tests/test_engine_tracking.py`, `README.md`'s `tracking-report` row, `infra/runbooks/engine-procedures.md` — Task 7.
- `infra/runbooks/bookkeeping.md` (new), `infra/runbooks/nas.md`, `docs/reference/fleet.md`, `infra/scripts/ops_daily.py`, `tests/test_ops_daily.py` — Task 8.
- `docs/open-topics/T0215-blockpit-fallback-pre-transform.md` and `docs/open-topics/README.md` — Task 9.

## Review Focus

- The mapping is spec D3's table and nothing else: window one's golden rows (Task 2), read row by row against the table, reproduce the connector's labels and change exactly its two shapes; every label written is one of the template's 33 (Tasks 1, 2).
- No row is dropped unrecorded: every shape maps or refuses, a run that refuses writes nothing, and the run's conservation check holds every asset's movement equal to the ledger's (Tasks 2, 4).
- Exactness: amounts are the export's own strings with the sign dropped, arithmetic is `Decimal`, and the one computed value, the small-balance allocation, sums to the receive (Task 2).
- The join's two exemptions — a `rollover` whose opening trade is in an earlier export, a close whose `posttxid` names one — are no refusals, while a `trade`, `margin`, `settled` or `collateralconversion` row whose trade is missing is (Tasks 2, 3).
- Determinism and provenance: no clock, environment or network reaches the output; two runs are byte-equal, and the trades export's row order does not reach the import file; the provenance's hashes are the files' (Task 4); `cli/tax/` imports nothing outside its allowlist (Task 6).
- The order inside one second is the ledger export's own, in which each asset's balance chain holds, never the `txid`s' (Task 2), and a written order that runs an asset below zero refuses (Task 4).
- The chain: a window opens where the one before closed and starts after it, the first opens at zero (Task 5).
- The reminder reads the NAS mount through `STATEMENTS`, which no test reads (Task 8).

---

### Before Task 1: the branch is at develop's tip and the plan's premises hold

- [ ] **Step 1: Develop's tip** — `git fetch origin develop`, then `git merge-base --is-ancestor origin/develop HEAD; echo "rc $?"`. Expected: `rc 0`; on `rc 1`, `git merge origin/develop` into the branch — a merge, never a rebase, the spec commits having been read — and the premises below read again.
- [ ] **Step 2: The premises**

```bash
grep -n 'from cli.snapshot.command import snapshot_app' cli/__main__.py
grep -n 'app.add_typer(snapshot_app, name="snapshot")' cli/__main__.py
grep -n '^_NO_FILL_LEDGER_TYPES' cli/engine/tracking.py
grep -n '^HEALABLE_RUNBOOK\|^    deploy_log: Path = DEPLOY_LOG,\|^    hours = max(1' infra/scripts/ops_daily.py
grep -n '^def live_soak_run' tests/test_ops_daily.py
sha256sum /home/zhaow/Projects/zcrypto-kraken/.claude/worktrees/t0215-blockpit/.tmp/spec-00126/blockpit-template.xlsx /home/zhaow/Projects/zcrypto-kraken/.claude/worktrees/t0215-blockpit/.tmp/spec-00126/blockpit-template-gid0.csv
ls cli/tax 2>&1
```

Expected: `17:` and `32:` for the two `cli/__main__.py` lines; `437:` for the allowlist; `345:` (`HEALABLE_RUNBOOK`), `389:` (the `deploy_log` parameter) and `433:` and `559:` for `hours = max(1` — the first inside `read_reminders`, the one Task 8 anchors on; `127:` for the fixture; the two hashes `fa48315e27f1b6413418d6964793e4b5841e4a336fcf9064ae921eedd3f61acf` and `914ab78ebd09b88ad899f75429e6ed107b2ceb79ab61ebf74c06d3ec304e078a`; and `ls: cannot access 'cli/tax'`. A different line number is re-read at the quoted text before its task; a different hash stops the plan, the template not being the one spec 00126 pins.

- [ ] **Step 3: The tree is clean** — `git status --porcelain`; Expected: empty.

---

### Task 1: The template's header and labels, the two readers, and the invented windows

**Files:**
- Create: `cli/tax/__init__.py` (empty), `cli/tax/errors.py`, `cli/tax/kraken_export.py`, `cli/tax/blockpit.py` (its docstring, imports, `HEADER` and `TEMPLATE_LABELS`)
- Create: `tests/fixtures/tax_blockpit/blockpit-template.xlsx`, `blockpit-template-gid0.csv`, `window-1-ledgers.csv`, `window-1-trades.csv`, `window-2-ledgers.csv`, `window-2-trades.csv`
- Modify: `.pre-commit-config.yaml` (`:42`, the comment above `end-of-file-fixer`; `:45`, its `&recorded-index` exclude)
- Test: `tests/test_tax_blockpit.py` (new)

**Interfaces:**
- Consumes: the template as fetched 2026-10-09 (spec D3, D8; its two sha256s, which Step 3's `TEMPLATE_SHA256` holds); spec D1's column names.
- Produces, for Tasks 2 to 6: `read_ledger(path, data=None) -> list[LedgerRow]` and `read_trades(path, data=None) -> dict[str, TradeRow]`, each value the export's own string, `data` the file's bytes where a caller has read them; `LedgerRow.dec(column) -> Decimal`; `TradeRow.closing`; `Refusal(txids, kind, reason)` with `.line()`; `TaxExportError`; `Refused(refusals)`; `HEADER` (11 names) and `TEMPLATE_LABELS` (33); the two windows' exports; the test file's helpers `_edited` and `_without`.

**What this task decides, where the spec leaves it open:** the readers keep each value as the export writes it and validate `time` and the three amounts a run reads on every row (`amount`, `fee`, `balance`) — an amount that does not parse and one that parses to no finite number each a case of its own, and each member of the caught errors (`ValueError` for a time, `InvalidOperation` for an amount) a probe dropping it — leaving `amountusd` to the one mapping that reads it — the owner's export writes it `"-"` on 3 of its 113 rows, so a reader that parsed it would refuse a sound export. The fixture's windows are invented in the sample's shapes: window one opens from zero and holds one of every row spec D3 maps; window two follows it with a rollover and a close of a position window one opened and a spot sale whose `amountusd` is `"-"`. Their numbers are round, and each window's balances chain. Their crypto assets are ATOM, ALGO, XTZ and NEAR, none of the 13 spec 00126's measured basis lists for the owner's export, and Step 2's check reads every non-zero number and every id of the four files against every cell of the owner's two exports, its reading a count, never a value; zero stays outside it, D3's shapes being written in it (a margin open's `amount`, an unfee'd row's `fee`). Window one's first EURC-fee'd open lists its conversion pair before its `margin` row, as the export books them, while the `margin` row's `txid` sorts first — a shape the owner's export holds — so an order by `txid` and the export's own order write different files. The template's CSV, as fetched, has CRLF line endings and no final newline, which the commit gate's `end-of-file-fixer`, `mixed-line-ending` and `trailing-whitespace` would rewrite; the gate's exclude for a recorded file takes it, as it takes the recorded registry index, and a test holds both template files to their sha256s, so an exclude that stops matching the CSV fails a test. A reader parses the bytes its caller passes as `data`, where it passes them, so Task 4's run hashes and parses one read of each file.

- [ ] **Step 1: The template's two files**

```bash
mkdir -p tests/fixtures/tax_blockpit
cp /home/zhaow/Projects/zcrypto-kraken/.claude/worktrees/t0215-blockpit/.tmp/spec-00126/blockpit-template.xlsx tests/fixtures/tax_blockpit/
cp /home/zhaow/Projects/zcrypto-kraken/.claude/worktrees/t0215-blockpit/.tmp/spec-00126/blockpit-template-gid0.csv tests/fixtures/tax_blockpit/
sha256sum tests/fixtures/tax_blockpit/blockpit-template.xlsx tests/fixtures/tax_blockpit/blockpit-template-gid0.csv
```

Expected: the two sha256s Step 3's `TEMPLATE_SHA256` holds. Then in `.pre-commit-config.yaml`, the comment `# A recorded registry index keeps the registry's bytes: its sha256 is the digest file beside it.` and the `exclude: &recorded-index` line below it become the first and last lines here, the two between them unchanged:

```yaml
      # A recorded file keeps its source's bytes: a registry index, its sha256 the digest file beside it, and the tax template's CSV as fetched.
      - id: end-of-file-fixer
        stages: [pre-commit]
        exclude: &recorded-index '^tests/fixtures/(alloy_version/index-[^/]*\.json|tax_blockpit/blockpit-template-gid0\.csv)$'
```

- [ ] **Step 2: The two windows' exports** — each file written byte for byte from its block, one trailing newline, no other byte; the ledger's 16 columns and the trades' 24 are the export's, strings quoted and numbers bare as the export writes them.

`tests/fixtures/tax_blockpit/window-1-ledgers.csv`:

```csv
"txid","refid","time","type","subtype","aclass","subclass","asset","wallet","amount","fee","balance","amountusd","feeusd","balanceusd","feecurrency"
"LFX001-SYNTH-LEDGER","FFX0001-SYNTH-DEPOSIT-00000001","2031-03-03 09:00:00","deposit","","currency","fiat","EUR","spot / main",1250.0,0.0,1250.0,1562.5,0.0,1562.5,""
"LFX002-SYNTH-LEDGER","FFX0002-SYNTH-DEPOSIT-00000002","2031-03-03 09:10:00","deposit","","currency","crypto","ATOM","spot / main",8.5,0.0,8.5,10.625,0.0,10.625,""
"LFX003-SYNTH-LEDGER","TFX001-SYNTH-TRADES","2031-03-03 10:00:00","trade","tradespot","currency","fiat","EUR","spot / main",-120.0,0.48,1129.52,-150.0,0.6,1411.9,"EUR"
"LFX004-SYNTH-LEDGER","TFX001-SYNTH-TRADES","2031-03-03 10:00:00","trade","tradespot","currency","crypto","ALGO","spot / main",320.0,0.0,320.0,400.0,0.0,400.0,""
"LFX005-SYNTH-LEDGER","TFX002-SYNTH-TRADES","2031-03-03 11:00:00","trade","tradespot","currency","crypto","ALGO","spot / main",-160.0,0.0,160.0,-200.0,0.0,200.0,""
"LFX006-SYNTH-LEDGER","TFX002-SYNTH-TRADES","2031-03-03 11:00:00","trade","tradespot","currency","fiat","EUR","spot / main",60.0,0.24,1189.28,75.0,0.3,1486.6,"EUR"
"LFX007-SYNTH-LEDGER","TFX003-SYNTH-TRADES","2031-03-03 11:30:00","trade","tradespot","currency","crypto","XTZ","spot / main",0.00004,0.0,0.00004,0.00004375,0.0,0.00005,""
"LFX009-SYNTH-LEDGER","TFX004-SYNTH-TRADES","2031-03-03 12:00:00","collateralconversion","","currency","fiat","EUR","spot / main",-0.075,0.0,1189.205,-0.09375,0.0,1486.50625,""
"LFX010-SYNTH-LEDGER","TFX004-SYNTH-TRADES","2031-03-03 12:00:00","collateralconversion","","currency","stable_coin","EURC","spot / main",0.075,0.0,0.075,0.09375,0.0,0.09375,""
"LFX008-SYNTH-LEDGER","TFX004-SYNTH-TRADES","2031-03-03 12:00:00","margin","","currency","stable_coin","EURC","spot / main",0.0,0.075,0.0,0.0,0.09375,0.0,"EURC"
"LFX011-SYNTH-LEDGER","TFX005-SYNTH-TRADES","2031-03-03 12:05:00","margin","","currency","fiat","EUR","spot / main",0.0,0.065,1189.14,0.0,0.08125,1486.425,"EUR"
"LFX012-SYNTH-LEDGER","TFX006-SYNTH-TRADES","2031-03-03 13:00:00","margin","","currency","fiat","EUR","spot / main",0.0,0.075,1189.065,0.0,0.09375,1486.33125,"EUR"
"LFX013-SYNTH-LEDGER","TFX005-SYNTH-TRADES","2031-03-03 16:05:00","rollover","","currency","fiat","EUR","spot / main",0.0,0.0035,1189.0615,0.0,0.004375,1486.326875,"EUR"
"LFX014-SYNTH-LEDGER","TFX005-SYNTH-TRADES","2031-03-03 20:05:00","rollover","","currency","fiat","EUR","spot / main",0.0,0.0035,1189.058,0.0,0.004375,1486.3225,"EUR"
"LFX015-SYNTH-LEDGER","TFX007-SYNTH-TRADES","2031-03-04 09:00:00","margin","","currency","fiat","EUR","spot / main",1.75,0.065,1190.743,2.1875,0.08125,1488.42875,"EUR"
"LFX016-SYNTH-LEDGER","TFX008-SYNTH-TRADES","2031-03-05 10:00:00","collateralconversion","","currency","fiat","EUR","spot / main",-0.075,0.0,1190.668,-0.09375,0.0,1488.335,""
"LFX017-SYNTH-LEDGER","TFX008-SYNTH-TRADES","2031-03-05 10:00:00","collateralconversion","","currency","stable_coin","EURC","spot / main",0.075,0.0,0.075,0.09375,0.0,0.09375,""
"LFX018-SYNTH-LEDGER","TFX008-SYNTH-TRADES","2031-03-05 10:00:00","margin","","currency","stable_coin","EURC","spot / main",0.0,0.075,0.0,0.0,0.09375,0.0,"EURC"
"LFX019-SYNTH-LEDGER","TFX009-SYNTH-TRADES","2031-03-05 14:00:00","collateralconversion","","currency","fiat","EUR","spot / main",-0.825,0.0,1189.843,-1.03125,0.0,1487.30375,""
"LFX020-SYNTH-LEDGER","TFX009-SYNTH-TRADES","2031-03-05 14:00:00","collateralconversion","","currency","stable_coin","EURC","spot / main",0.825,0.0,0.825,1.03125,0.0,1.03125,""
"LFX021-SYNTH-LEDGER","TFX009-SYNTH-TRADES","2031-03-05 14:00:00","margin","","currency","stable_coin","EURC","spot / main",-0.75,0.075,0.0,-0.9375,0.09375,0.0,"EURC"
"LFX022-SYNTH-LEDGER","TFX010-SYNTH-TRADES","2031-03-06 10:00:00","margin","","currency","fiat","EUR","spot / main",0.0,0.065,1189.778,0.0,0.08125,1487.2225,"EUR"
"LFX023-SYNTH-LEDGER","TFX011-SYNTH-TRADES","2031-03-06 15:00:00","settled","","currency","fiat","EUR","spot / main",-15.6,0.0,1174.178,-19.5,0.0,1467.7225,""
"LFX024-SYNTH-LEDGER","TFX011-SYNTH-TRADES","2031-03-06 15:00:00","settled","","currency","crypto","ATOM","spot / main",2.6,0.0,11.1,3.25,0.0,13.875,""
"LFX025-SYNTH-LEDGER","TFX012-SYNTH-TRADES","2031-03-20 10:00:00","margin","","currency","fiat","EUR","spot / main",0.0,0.065,1174.113,0.0,0.08125,1467.64125,"EUR"
"LFX026-SYNTH-LEDGER","EFX0001-SYNTH-REWARD","2031-03-25 14:00:00","earn","reward","currency","crypto","ALGO","spot / main",0.35,0.105,160.245,0.4375,0.13125,200.30625,"ALGO"
"LFX027-SYNTH-LEDGER","EFX0002-SYNTH-REWARD","2031-03-25 14:00:00","earn","reward","currency","crypto","ATOM","spot / main",0.0025,0.0,11.1025,0.003125,0.0,13.878125,""
"LFX028-SYNTH-LEDGER","EFX0003-SYNTH-REWARD","2031-03-25 14:00:00","earn","reward","currency","crypto","NEAR","spot / main",0.0000035,0.00000105,0.00000245,0.000004375,0.0000013125,0.0000030625,"NEAR"
"LFX029-SYNTH-LEDGER","TFXD001-SYNTH-SWEEPS","2031-03-28 22:00:00","spend","dustsweeping","currency","crypto","XTZ","spot / main",-0.00004,0.0,0.0,-0.000035,0.0,0.0,""
"LFX030-SYNTH-LEDGER","TFXD001-SYNTH-SWEEPS","2031-03-28 22:00:00","spend","dustsweeping","currency","crypto","NEAR","spot / main",-0.0000024,0.00000005,0.0,-0.000017,0.0000000625,0.0,"NEAR"
"LFX031-SYNTH-LEDGER","TFXD001-SYNTH-SWEEPS","2031-03-28 22:00:00","receive","dustsweeping","currency","fiat","EUR","spot / main",0.0003,0.0,1174.1133,0.000375,0.0,1467.641625,""
```

`tests/fixtures/tax_blockpit/window-1-trades.csv`:

```csv
"txid","ordertxid","pair","aclass","subclass","time","type","ordertype","price","cost","fee","vol","margin","misc","ledgers","posttxid","posstatuscode","cprice","ccost","cfee","cvol","cmargin","net","trades"
"TFX001-SYNTH-TRADES","OFX001-SYNTH-ORDERS","ALGO/EUR","forex","crypto","2031-03-03 10:00:00.1000","buy","limit",0.375,120.0,0.48,320.0,0.0,"","LFX004-SYNTH-LEDGER,LFX003-SYNTH-LEDGER","TFX000-SYNTH-NOPOSN","","","","","","","",""
"TFX002-SYNTH-TRADES","OFX002-SYNTH-ORDERS","ALGO/EUR","forex","crypto","2031-03-03 11:00:00.1000","sell","limit",0.375,60.0,0.24,160.0,0.0,"","LFX006-SYNTH-LEDGER,LFX005-SYNTH-LEDGER","TFX000-SYNTH-NOPOSN","","","","","","","",""
"TFX003-SYNTH-TRADES","OFX003-SYNTH-ORDERS","XTZ/EUR","forex","crypto","2031-03-03 11:30:00.1000","buy","limit",0.875,0.000035,0.0,0.00004,0.0,"","LFX007-SYNTH-LEDGER","TFX000-SYNTH-NOPOSN","","","","","","","",""
"TFX004-SYNTH-TRADES","OFX004-SYNTH-ORDERS","ATOM/EUR","forex","crypto","2031-03-03 12:00:00.1000","buy","market",6.25,18.75,0.075,3.0,9.375,"initiated","LFX010-SYNTH-LEDGER,LFX009-SYNTH-LEDGER,LFX008-SYNTH-LEDGER","TFX000-SYNTH-NOPOSN","closed","","","","","","","TFX006-SYNTH-TRADES"
"TFX005-SYNTH-TRADES","OFX005-SYNTH-ORDERS","ALGO/EUR","forex","crypto","2031-03-03 12:05:00.1000","sell","limit",0.375,26.25,0.065,70.0,13.125,"","LFX011-SYNTH-LEDGER,LFX013-SYNTH-LEDGER,LFX014-SYNTH-LEDGER","TFX000-SYNTH-NOPOSN","closed","","","","","","","TFX007-SYNTH-TRADES"
"TFX006-SYNTH-TRADES","OFX006-SYNTH-ORDERS","ATOM/EUR","forex","crypto","2031-03-03 13:00:00.1000","sell","market",6.25,18.75,0.075,3.0,9.375,"initiated,closing","LFX012-SYNTH-LEDGER","TFX004-SYNTH-TRADES","","","","","","","",""
"TFX007-SYNTH-TRADES","OFX007-SYNTH-ORDERS","ALGO/EUR","forex","crypto","2031-03-04 09:00:00.1000","buy","limit",0.35,24.5,0.065,70.0,12.25,"closing","LFX015-SYNTH-LEDGER","TFX005-SYNTH-TRADES","","","","","","","",""
"TFX008-SYNTH-TRADES","OFX008-SYNTH-ORDERS","ATOM/EUR","forex","crypto","2031-03-05 10:00:00.1000","buy","limit",6.25,18.75,0.075,3.0,9.375,"","LFX018-SYNTH-LEDGER,LFX017-SYNTH-LEDGER,LFX016-SYNTH-LEDGER","TFX000-SYNTH-NOPOSN","closed","","","","","","","TFX009-SYNTH-TRADES"
"TFX009-SYNTH-TRADES","OFX009-SYNTH-ORDERS","ATOM/EUR","forex","crypto","2031-03-05 14:00:00.1000","sell","limit",6.0,18.0,0.075,3.0,9.0,"closing","LFX021-SYNTH-LEDGER,LFX020-SYNTH-LEDGER,LFX019-SYNTH-LEDGER","TFX008-SYNTH-TRADES","","","","","","","",""
"TFX010-SYNTH-TRADES","OFX010-SYNTH-ORDERS","ATOM/EUR","forex","crypto","2031-03-06 10:00:00.1000","buy","limit",6.0,15.6,0.065,2.6,7.8,"","LFX022-SYNTH-LEDGER","TFX000-SYNTH-NOPOSN","closed","","","","","","","TFX011-SYNTH-TRADES"
"TFX011-SYNTH-TRADES","OFX011-SYNTH-ORDERS","ATOM/EUR","forex","crypto","2031-03-06 15:00:00.1000","buy","limit",6.0,15.6,0.0,2.6,7.8,"initiated,closing","LFX024-SYNTH-LEDGER,LFX023-SYNTH-LEDGER","TFX010-SYNTH-TRADES","","","","","","","",""
"TFX012-SYNTH-TRADES","OFX012-SYNTH-ORDERS","ALGO/EUR","forex","crypto","2031-03-20 10:00:00.1000","sell","limit",0.375,33.75,0.065,90.0,16.875,"","LFX025-SYNTH-LEDGER,LFX101-SYNTH-LEDGER","TFX000-SYNTH-NOPOSN","","","","","","","",""
```

`tests/fixtures/tax_blockpit/window-2-ledgers.csv`:

```csv
"txid","refid","time","type","subtype","aclass","subclass","asset","wallet","amount","fee","balance","amountusd","feeusd","balanceusd","feecurrency"
"LFX101-SYNTH-LEDGER","TFX012-SYNTH-TRADES","2031-04-01 10:00:00","rollover","","currency","fiat","EUR","spot / main",0.0,0.0035,1174.1098,0.0,0.004375,1467.63725,"EUR"
"LFX102-SYNTH-LEDGER","TFX013-SYNTH-TRADES","2031-04-02 09:00:00","margin","","currency","fiat","EUR","spot / main",2.25,0.065,1176.2948,2.8125,0.08125,1470.3685,"EUR"
"LFX103-SYNTH-LEDGER","TFX014-SYNTH-TRADES","2031-04-03 12:00:00","trade","tradespot","currency","crypto","ATOM","spot / main",-8.5,0.0,2.6025,"-",0.0,3.253125,""
"LFX104-SYNTH-LEDGER","TFX014-SYNTH-TRADES","2031-04-03 12:00:00","trade","tradespot","currency","fiat","EUR","spot / main",54.4,0.2176,1230.4772,68.0,0.272,1538.0965,"EUR"
```

`tests/fixtures/tax_blockpit/window-2-trades.csv`:

```csv
"txid","ordertxid","pair","aclass","subclass","time","type","ordertype","price","cost","fee","vol","margin","misc","ledgers","posttxid","posstatuscode","cprice","ccost","cfee","cvol","cmargin","net","trades"
"TFX013-SYNTH-TRADES","OFX013-SYNTH-ORDERS","ALGO/EUR","forex","crypto","2031-04-02 09:00:00.1000","buy","limit",0.35,31.5,0.065,90.0,15.75,"closing","LFX102-SYNTH-LEDGER","TFX012-SYNTH-TRADES","","","","","","","",""
"TFX014-SYNTH-TRADES","OFX014-SYNTH-ORDERS","ATOM/EUR","forex","crypto","2031-04-03 12:00:00.1000","sell","limit",6.4,54.4,0.2176,8.5,0.0,"","LFX104-SYNTH-LEDGER,LFX103-SYNTH-LEDGER","TFX000-SYNTH-NOPOSN","","","","","","","",""
```

```bash
sha256sum tests/fixtures/tax_blockpit/window-*-ledgers.csv tests/fixtures/tax_blockpit/window-*-trades.csv
```

Expected: `window-1-ledgers.csv` 5c61ac12ded70979c2a637822e5b61913f8e8654e3f6a104847aa55ef0a22fab; `window-1-trades.csv` baf679ca665a1dde690a382a9297f8b55f874f0411dded64c2cbf74fc057569a; `window-2-ledgers.csv` ccc8609590662862c89896842e1aaba32f42fd956aa4a3b72e030c734e2a0b6d; `window-2-trades.csv` b663b23967bb5b005fe9517742bddd23382fe5a0532553820a8244a0a0ab0500. The golden provenance files of Tasks 4 and 5 carry these hashes, so a byte off here fails them there.

Then, once, before the commit, the check that the four files share no value with the owner's exports: it reads the sample under `.tmp/spec-00126/` and prints one count, never a value.

```bash
uv run python -I - /home/zhaow/Projects/zcrypto-kraken/.claude/worktrees/t0215-blockpit/.tmp/spec-00126 tests/fixtures/tax_blockpit/window-*-ledgers.csv tests/fixtures/tax_blockpit/window-*-trades.csv <<'PY'
import csv
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

IDS = {"txid", "refid", "time", "ordertxid", "posttxid", "ledgers", "trades"}


def cells(paths):
    numbers, ids = set(), set()
    for path in paths:
        with open(path, newline="", encoding="utf-8-sig") as handle:
            header, *rows = csv.reader(handle)
        for row in rows:
            for at, cell in enumerate(row):
                for part in cell.split(","):
                    try:
                        number = Decimal(part)
                    except InvalidOperation:
                        number = None
                    if number is not None and number.is_finite() and number != 0:
                        numbers.add(abs(number).normalize())
                    elif at < len(header) and header[at] in IDS and part:
                        ids.add(part)
    return numbers, ids


paths = sorted(Path(sys.argv[1]).glob("*-full/*.csv"))
sample = cells(paths)
assert len(paths) == 2 and all(sample), f"the sample is not read: {len(paths)} files"
fixture = cells(sys.argv[2:])
print(f"intersection {len(sample[0] & fixture[0]) + len(sample[1] & fixture[1])}")
PY
```

Expected: `intersection 0`. An `AssertionError` is a check that read no sample — the path wrong or its two CSVs gone — and stops the plan until the check reads them. Another count stops the plan: an invented value equals a cell of the owner's records, and the fixture is invented again before anything is committed.

- [ ] **Step 3: Write the failing tests** — `tests/test_tax_blockpit.py` with the imports it keeps to the end (the module is referenced as `blockpit.<name>`, so no import names a function a later task adds), the fixture paths, two helpers and the readers' cases:

```python
import ast
import csv
import hashlib
import io
import json
import re
import zipfile
from decimal import Decimal
from importlib.metadata import version
from pathlib import Path

import pytest
from typer.testing import CliRunner

from cli.__main__ import app
from cli.tax import blockpit
from cli.tax.errors import Refused, TaxExportError
from cli.tax.kraken_export import read_ledger, read_trades

FIXTURES = Path(__file__).parent / "fixtures" / "tax_blockpit"
LEDGER_1 = FIXTURES / "window-1-ledgers.csv"
TRADES_1 = FIXTURES / "window-1-trades.csv"
LEDGER_2 = FIXTURES / "window-2-ledgers.csv"
TRADES_2 = FIXTURES / "window-2-trades.csv"
# The template's two files as fetched 2026-10-09 (spec 00126 D8), held byte for byte.
TEMPLATE_SHA256 = {
    "blockpit-template.xlsx": "fa48315e27f1b6413418d6964793e4b5841e4a336fcf9064ae921eedd3f61acf",
    "blockpit-template-gid0.csv": "914ab78ebd09b88ad899f75429e6ed107b2ceb79ab61ebf74c06d3ec304e078a",
}


def _template_labels() -> list[str]:
    sheet = zipfile.ZipFile(FIXTURES / "blockpit-template.xlsx").read("xl/worksheets/sheet1.xml").decode()
    (formula,) = re.findall(r'<dataValidation type="list"[^>]*sqref="C2:C986"><formula1>(.*?)</formula1>', sheet)
    return "".join(re.findall(r"&quot;(.*?)&quot;", formula)).split(",")


def _edited(tmp_path: Path, source: Path, edits: list[tuple[str, str | None, str | None]]) -> Path:
    """`source` with each (txid, column, value) applied; a None column drops the row."""
    with source.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    for txid, column, value in edits:
        (row,) = [row for row in rows if row["txid"] == txid]
        if column is None:
            rows.remove(row)
        else:
            row[column] = value
    target = tmp_path / source.name
    with target.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, list(rows[0]) if rows else [], lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return target


def _without(tmp_path: Path, source: Path, column: str) -> Path:
    rows = [line.split(",") for line in source.read_text().splitlines()]
    at = rows[0].index(f'"{column}"')
    target = tmp_path / source.name
    target.write_text("\n".join(",".join(row[:at] + row[at + 1 :]) for row in rows) + "\n")
    return target


@pytest.mark.parametrize("name", sorted(TEMPLATE_SHA256))
def test_the_templates_files_are_as_fetched(name):
    assert hashlib.sha256((FIXTURES / name).read_bytes()).hexdigest() == TEMPLATE_SHA256[name]


def test_the_header_is_the_templates_first_row():
    with (FIXTURES / "blockpit-template-gid0.csv").open(newline="", encoding="utf-8") as handle:
        assert tuple(next(csv.reader(handle))) == blockpit.HEADER


def test_the_labels_are_the_templates_dropdown():
    assert list(blockpit.TEMPLATE_LABELS) == _template_labels()
    assert len(blockpit.TEMPLATE_LABELS) == 33


def test_the_ledger_reader_keeps_the_exports_own_strings():
    rows = read_ledger(LEDGER_1)
    assert len(rows) == 31
    first = rows[0]
    assert (first.txid, first.type, first.asset, first.amount, first.wallet) == (
        "LFX001-SYNTH-LEDGER",
        "deposit",
        "EUR",
        "1250.0",
        "spot / main",
    )
    assert read_ledger(LEDGER_2)[2].amountusd == "-"


def test_the_trades_reader_reads_the_closing_flag_the_position_and_the_ledger_ids():
    trades = read_trades(TRADES_1)
    assert len(trades) == 12
    close = trades["TFX006-SYNTH-TRADES"]
    assert close.closing and close.posttxid == "TFX004-SYNTH-TRADES" and close.ledgers == ("LFX012-SYNTH-LEDGER",)
    opening = trades["TFX004-SYNTH-TRADES"]
    assert not opening.closing
    assert opening.ledgers == ("LFX010-SYNTH-LEDGER", "LFX009-SYNTH-LEDGER", "LFX008-SYNTH-LEDGER")


def test_a_missing_column_is_refused_by_name(tmp_path):
    with pytest.raises(TaxExportError, match="wallet"):
        read_ledger(_without(tmp_path, LEDGER_1, "wallet"))


@pytest.mark.parametrize(
    "column,value",
    [("time", "2031-03-03T09:00:00Z"), ("amount", "abc"), ("balance", "NaN")],
    ids=["time_the_export_does_not_write", "amount_the_export_does_not_write", "balance_not_finite"],
)
def test_a_value_the_export_does_not_write_is_refused(tmp_path, column, value):
    with pytest.raises(TaxExportError, match="LFX001-SYNTH-LEDGER"):
        read_ledger(_edited(tmp_path, LEDGER_1, [("LFX001-SYNTH-LEDGER", column, value)]))
```

- [ ] **Step 4: Run them and read the failure**

```bash
uv run pytest tests/test_tax_blockpit.py -q -p no:cacheprovider
```

Expected: a collection error, `ModuleNotFoundError: No module named 'cli.tax'`.

- [ ] **Step 5: The three modules** — `cli/tax/__init__.py` empty; `cli/tax/errors.py`:

```python
"""The refusals of `zcrypto tax blockpit`: a row it cannot map, a check that fails, or an input it cannot read."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Refusal:
    txids: tuple[str, ...]
    kind: str
    reason: str

    def line(self) -> str:
        return f"refused {','.join(self.txids) or '-'} [{self.kind}]: {self.reason}"


class TaxExportError(Exception):
    pass


class Refused(Exception):
    def __init__(self, refusals: list[Refusal]):
        super().__init__(f"{len(refusals)} refusal(s)")
        self.refusals = refusals
```

`cli/tax/kraken_export.py`:

```python
"""Kraken's ledger and trades CSV exports, read by header name into the export's own decimal strings."""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from cli.tax.errors import TaxExportError

LEDGER_COLUMNS = (
    "txid",
    "refid",
    "time",
    "type",
    "subtype",
    "wallet",
    "asset",
    "amount",
    "fee",
    "balance",
    "amountusd",
    "feecurrency",
)
TRADES_COLUMNS = ("txid", "pair", "misc", "ledgers", "posttxid")
LEDGER_TIME = "%Y-%m-%d %H:%M:%S"


@dataclass(frozen=True)
class LedgerRow:
    txid: str
    refid: str
    time: str
    type: str
    subtype: str
    wallet: str
    asset: str
    amount: str
    fee: str
    balance: str
    amountusd: str
    feecurrency: str

    def dec(self, column: str) -> Decimal:
        return Decimal(getattr(self, column))


@dataclass(frozen=True)
class TradeRow:
    txid: str
    pair: str
    misc: tuple[str, ...]
    ledgers: tuple[str, ...]
    posttxid: str

    @property
    def closing(self) -> bool:
        return "closing" in self.misc


def _rows(path: Path, columns: tuple[str, ...], data: bytes | None) -> list[dict[str, str]]:
    # `utf-8-sig`: a file opened and saved in a spreadsheet gains a byte-order mark glued to its first column name.
    # `data` is the file's bytes where the caller has read them to hash, so the rows parse the bytes it hashed.
    text = (path.read_bytes() if data is None else data).decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text, newline=""))
    missing = [column for column in columns if column not in (reader.fieldnames or [])]
    if missing:
        raise TaxExportError(f"{path} has no {', '.join(missing)} column")
    return list(reader)


def read_ledger(path: Path, data: bytes | None = None) -> list[LedgerRow]:
    rows = []
    for number, raw in enumerate(_rows(path, LEDGER_COLUMNS, data), start=1):
        row = LedgerRow(*(raw[column] for column in LEDGER_COLUMNS))
        try:
            datetime.strptime(row.time, LEDGER_TIME)
            if not all(row.dec(column).is_finite() for column in ("amount", "fee", "balance")):
                raise InvalidOperation
        except (ValueError, InvalidOperation) as exc:
            raise TaxExportError(f"{path} data row {number} ({row.txid}): a time or an amount the export does not write") from exc
        rows.append(row)
    return rows


def read_trades(path: Path, data: bytes | None = None) -> dict[str, TradeRow]:
    trades = {}
    for raw in _rows(path, TRADES_COLUMNS, data):
        misc = tuple(word for word in raw["misc"].split(",") if word)
        ledgers = tuple(txid for txid in raw["ledgers"].split(",") if txid)
        trades[raw["txid"]] = TradeRow(raw["txid"], raw["pair"], misc, ledgers, raw["posttxid"])
    return trades
```

`cli/tax/blockpit.py`, its docstring, its imports — the whole module's, written now so no later task edits them — and the template's two constants:

```python
"""Kraken's ledger and trades exports mapped onto Blockpit's manual-import rows, the provenance written beside them."""

from __future__ import annotations

import csv
import hashlib
import io
import json
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from decimal import ROUND_DOWN, Decimal, InvalidOperation
from importlib.metadata import version
from pathlib import Path

from cli.tax.errors import Refusal, Refused, TaxExportError
from cli.tax.kraken_export import LEDGER_TIME, LedgerRow, TradeRow, read_ledger, read_trades

# The template's first row and its Label dropdown, the data validation on C2:C986.
HEADER = (
    "Date (UTC)",
    "Integration Name",
    "Label",
    "Outgoing Asset",
    "Outgoing Amount",
    "Incoming Asset",
    "Incoming Amount",
    "Fee Asset (optional)",
    "Fee Amount (optional)",
    "Comment (optional)",
    "Trx. ID (optional)",
)
TEMPLATE_LABELS = (
    "Trade",
    "Deposit",
    "Airdrop",
    "Bounty",
    "Gift Received",
    "Hard Fork",
    "Masternode",
    "Mining",
    "Staking",
    "Interest",
    "Derivative Profit",
    "Withdrawal",
    "Payment",
    "Gift Sent",
    "Derivative Fee",
    "Derivative Loss",
    "Non-Taxable In",
    "Non-Taxable Out",
    "Lost",
    "Income",
    "Cashback",
    "Fee",
    "Repay Loan",
    "Receive Loan",
    "Margin Profit",
    "Margin Loss",
    "Margin Fee",
    "Stock Purchase",
    "Stock Sale",
    "Prediction Profit",
    "Prediction Loss",
    "Open Perp",
    "Close Perp",
)
```

- [ ] **Step 6: Run the tests** — Step 4's command; Expected: `10 passed`.
- [ ] **Step 7: The consumers** — the tax consumers command (Global Constraints), and the tests naming `.pre-commit-config.yaml`: `uv run pytest tests/test_pre_push_stage.py tests/test_message_citations.py tests/test_vendored_rrsync_integrity.py -q -p no:cacheprovider`; then the consumers' run; Expected: no failure.

- [ ] **Step 8: The commit gate**
- [ ] **Step 9: Commit**

```bash
git add .pre-commit-config.yaml cli/tax/__init__.py cli/tax/errors.py cli/tax/kraken_export.py cli/tax/blockpit.py tests/test_tax_blockpit.py tests/fixtures/tax_blockpit/blockpit-template.xlsx tests/fixtures/tax_blockpit/blockpit-template-gid0.csv tests/fixtures/tax_blockpit/window-1-ledgers.csv tests/fixtures/tax_blockpit/window-1-trades.csv tests/fixtures/tax_blockpit/window-2-ledgers.csv tests/fixtures/tax_blockpit/window-2-trades.csv
git commit -F- <<'MSG'
feat(tax): Kraken's two CSV exports read by header name, and Blockpit's template header and labels pinned

The ledger and trades exports are read into the export's own decimal strings, refusing a
missing column by name and a time or an amount the export does not write; amountusd is left to the
one mapping that reads it, since the export writes it "-" where it has no USD value. The template's
first row and the 33 values of its Label dropdown are constants a test holds equal to the template
file as fetched 2026-10-09, which the fixture keeps beside two invented windows of exports; the
commit gate's line-ending and whitespace fixers pass over the template's CSV, as over the recorded
registry index, so it stays as fetched, and a test holds both template files to their sha256s.

PROBE_VERDICT

Co-Authored-By: Claude <actual executing model> <noreply@anthropic.com>
MSG
```

- [ ] **Step 10: The tree is clean** — `git status --porcelain`; Expected: empty. Then `uv run pytest tests/test_tax_blockpit.py -k templates_files_are_as_fetched -q -p no:cacheprovider`; Expected: `2 passed`, the gate having left both template files as fetched.
- [ ] **Step 11: Prove the guards, then record their verdicts** — eleven probes; Expected: each ends `mutate-probe: KILLED (control proven, tree restored byte-identically)`; then the message-only amend.

```bash
infra/scripts/mutate-probe.sh --file cli/tax/kraken_export.py --control '1,$d' \
  --mutation 's/^    if missing:$/    if False:/' \
  -- uv run pytest tests/test_tax_blockpit.py -k missing_column -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file cli/tax/kraken_export.py --control '1,$d' \
  --mutation 's/^            datetime.strptime(row.time, LEDGER_TIME)$/            pass/' \
  -- uv run pytest tests/test_tax_blockpit.py -k time_the_export_does_not_write -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file cli/tax/kraken_export.py --control '1,$d' \
  --mutation 's/^            if not all(row.dec(column).is_finite() for column in ("amount", "fee", "balance")):$/            if False:/' \
  -- uv run pytest tests/test_tax_blockpit.py -k amount_the_export_does_not_write -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file cli/tax/kraken_export.py --control '1,$d' \
  --mutation 's/row.dec(column).is_finite() for column in/row.dec(column) is not None for column in/' \
  -- uv run pytest tests/test_tax_blockpit.py -k balance_not_finite -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file cli/tax/kraken_export.py --control '1,$d' \
  --mutation 's/^        except (ValueError, InvalidOperation) as exc:$/        except InvalidOperation as exc:/' \
  -- uv run pytest tests/test_tax_blockpit.py -k time_the_export_does_not_write -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file cli/tax/kraken_export.py --control '1,$d' \
  --mutation 's/^        except (ValueError, InvalidOperation) as exc:$/        except ValueError as exc:/' \
  -- uv run pytest tests/test_tax_blockpit.py -k 'amount_the_export_does_not_write or balance_not_finite' -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file cli/tax/kraken_export.py --control '1,$d' \
  --mutation 's/^        return "closing" in self.misc$/        return False/' \
  -- uv run pytest tests/test_tax_blockpit.py -k closing_flag -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file cli/tax/kraken_export.py --control '1,$d' \
  --mutation 's/^        ledgers = tuple(txid for txid in raw\["ledgers"\].split(",") if txid)$/        ledgers = (raw["ledgers"],)/' \
  -- uv run pytest tests/test_tax_blockpit.py -k closing_flag -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file cli/tax/blockpit.py --control '1,$d' \
  --mutation 's/^    "Trx. ID (optional)",$/    "Trx. ID",/' \
  -- uv run pytest tests/test_tax_blockpit.py -k header_is_the_templates -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file cli/tax/blockpit.py --control '1,$d' \
  --mutation '/^    "Close Perp",$/d' \
  -- uv run pytest tests/test_tax_blockpit.py -k labels_are_the_templates -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file tests/fixtures/tax_blockpit/blockpit-template-gid0.csv --control '1,$d' \
  --mutation 's/\r$//' \
  -- uv run pytest tests/test_tax_blockpit.py -k templates_files_are_as_fetched -q -p no:cacheprovider
```

---

### Task 2: The row mapping — every shape the export holds mapped or refused — and window one's golden rows

**Files:**
- Modify: `cli/tax/blockpit.py` (appended after `TEMPLATE_LABELS`)
- Create: `tests/fixtures/tax_blockpit/window-1-blockpit.csv`
- Test: `tests/test_tax_blockpit.py`

**Interfaces:**
- Consumes: Task 1's readers, `HEADER`, `TEMPLATE_LABELS`, `Refusal`, `TaxExportError`.
- Produces: `map_rows(ledger, trades) -> Mapped` — its `rows` (`OutRow`), `refusals`, `positions` (opening trade id → ledger txids) and `no_movement`; `render_csv(rows) -> bytes`, the import file's bytes, raising `TaxExportError` on a label outside `TEMPLATE_LABELS`; `_moves(row)`, an output row's signed movement per asset, which the tests and Task 4's checks read; `SINGLE` and `GROUPED`, the dispatch Task 4's conservation test patches.

**What this task decides, where the spec leaves it open:** the refusal wording; the `Comment`'s form for spec D3's content — `kraken <type>`, or `kraken <type>/<subtype>` where the row has a subtype, then the `pair` of the trades row its `refid` names where the export holds that row, then `position <id>` on a margin-family row; a one-leg trade's ends `one leg booked` and a sweep's names its `refid` — with no comma, so no field is quoted; the integration name `Kraken manual import` (column B, which an upload into an existing integration ignores); and the row order inside a group — an amount row before its fee row, a sweep's spends by `txid`. A sweep's rows each carry their spend's ledger `txid` as the `Trx. ID` and the group's `refid` in the `Comment`, as spec D3's line of 2026-10-09 rules: a sweep writes one Trade per spent coin, so the group's one `refid` on each row would repeat a `Trx. ID`, which `check_unique` refuses; every other row built from a group carries its group's `refid`. A row's group is its type's and its `refid`, so a margin open's `collateralconversion` pair, `margin` row and the `rollover` rows sharing its `refid` stay apart; a `spend` and a `receive` of one sweep share one group. A group's place among one second's rows is its first row's position in the ledger export (spec D5): `Mapped.index` holds each ledger `txid`'s position, and `Mapped.at` turns a group's rows and an ordinal into a row's `order`; `_written` sorts the rows by `time` and `order`, the one written order `render_csv` and Task 4's order check read. `render_csv` checks each row's label against `TEMPLATE_LABELS` as it writes the row, a label outside it a `TaxExportError` naming the label, so the constant is read at run time, and a test hands `render_csv` a row the mapping never writes. `_moves`, an output row's signed movement per asset, is written here once, over `OutRow`, for the tests and Task 4's checks; `_pair_trade` builds the one Trade row of a two-leg group for `_trade` and `_settled`. A row moving nothing is counted only once its type and subtype have a mapping, so an unknown type at zero refuses. Each member of a compound refusal condition has a `REFUSALS` case it alone decides and a probe dropping that member: `_legs`'s out count and in count; `_conversion`'s row count, EUR debit, EURC credit and fee; `_sweep`'s receive count, spend presence and receive fee, then its receive credit and spend debits, then its finite values and non-zero total. The receive count's case, `sweep_with_two_receives`, turns the fee-less spend into a second receive, so the receive fee does not decide it; the non-zero total's probe selects `sweep_of_one_spend_amountusd_zero`, whose one spend reaches no division; and each of the sweep's probes, and the conversion's whole-condition probe, selects cases whose mutant runs on to the test's assertion rather than raising. Every `OutRow` takes its `order` from `Mapped.at`: the deposit, reward, rollover and margin rows from their own ledger row, the trade, settle, conversion and sweep rows from their group's. A sweep's shares are rounded down at ten places and the last spend, by `txid`, takes the remainder.

- [ ] **Step 1: The golden rows** — `tests/fixtures/tax_blockpit/window-1-blockpit.csv`, byte for byte, written before the code: each row is spec D3's table read off window one by hand — the EUR deposit as Non-Taxable In and the ATOM deposit as Deposit; the two spot trades and the one-leg trade, its EUR leg at `0`; the two opens fee'd in EURC each a Trade EUR → EURC and a Margin Fee in EURC; the three opens fee'd in EUR — one closed in the window, one settled, one held into window two — and the zero-PnL close each a Margin Fee; the two rollovers; the profit close a Margin Profit and a Margin Fee `…-fee`; the loss close's own conversion pair, its Margin Loss in EURC and its Margin Fee; the settle a Trade EUR → ATOM; the three rewards as Staking; the sweep as two Trades into EUR at `0.000201923` and `0.000098077`, which sum to the receive.

```csv
Date (UTC),Integration Name,Label,Outgoing Asset,Outgoing Amount,Incoming Asset,Incoming Amount,Fee Asset (optional),Fee Amount (optional),Comment (optional),Trx. ID (optional)
03.03.2031 09:00:00,Kraken manual import,Non-Taxable In,,,EUR,1250.0,,,kraken deposit,LFX001-SYNTH-LEDGER
03.03.2031 09:10:00,Kraken manual import,Deposit,,,ATOM,8.5,,,kraken deposit,LFX002-SYNTH-LEDGER
03.03.2031 10:00:00,Kraken manual import,Trade,EUR,120.0,ALGO,320.0,EUR,0.48,kraken trade/tradespot ALGO/EUR,TFX001-SYNTH-TRADES
03.03.2031 11:00:00,Kraken manual import,Trade,ALGO,160.0,EUR,60.0,EUR,0.24,kraken trade/tradespot ALGO/EUR,TFX002-SYNTH-TRADES
03.03.2031 11:30:00,Kraken manual import,Trade,EUR,0,XTZ,0.00004,,,kraken trade/tradespot XTZ/EUR one leg booked,TFX003-SYNTH-TRADES
03.03.2031 12:00:00,Kraken manual import,Trade,EUR,0.075,EURC,0.075,,,kraken collateralconversion ATOM/EUR position TFX004-SYNTH-TRADES,TFX004-SYNTH-TRADES
03.03.2031 12:00:00,Kraken manual import,Margin Fee,EURC,0.075,,,,,kraken margin ATOM/EUR position TFX004-SYNTH-TRADES,LFX008-SYNTH-LEDGER
03.03.2031 12:05:00,Kraken manual import,Margin Fee,EUR,0.065,,,,,kraken margin ALGO/EUR position TFX005-SYNTH-TRADES,LFX011-SYNTH-LEDGER
03.03.2031 13:00:00,Kraken manual import,Margin Fee,EUR,0.075,,,,,kraken margin ATOM/EUR position TFX004-SYNTH-TRADES,LFX012-SYNTH-LEDGER
03.03.2031 16:05:00,Kraken manual import,Margin Fee,EUR,0.0035,,,,,kraken rollover ALGO/EUR position TFX005-SYNTH-TRADES,LFX013-SYNTH-LEDGER
03.03.2031 20:05:00,Kraken manual import,Margin Fee,EUR,0.0035,,,,,kraken rollover ALGO/EUR position TFX005-SYNTH-TRADES,LFX014-SYNTH-LEDGER
04.03.2031 09:00:00,Kraken manual import,Margin Profit,,,EUR,1.75,,,kraken margin ALGO/EUR position TFX005-SYNTH-TRADES,LFX015-SYNTH-LEDGER
04.03.2031 09:00:00,Kraken manual import,Margin Fee,EUR,0.065,,,,,kraken margin ALGO/EUR position TFX005-SYNTH-TRADES,LFX015-SYNTH-LEDGER-fee
05.03.2031 10:00:00,Kraken manual import,Trade,EUR,0.075,EURC,0.075,,,kraken collateralconversion ATOM/EUR position TFX008-SYNTH-TRADES,TFX008-SYNTH-TRADES
05.03.2031 10:00:00,Kraken manual import,Margin Fee,EURC,0.075,,,,,kraken margin ATOM/EUR position TFX008-SYNTH-TRADES,LFX018-SYNTH-LEDGER
05.03.2031 14:00:00,Kraken manual import,Trade,EUR,0.825,EURC,0.825,,,kraken collateralconversion ATOM/EUR position TFX008-SYNTH-TRADES,TFX009-SYNTH-TRADES
05.03.2031 14:00:00,Kraken manual import,Margin Loss,EURC,0.75,,,,,kraken margin ATOM/EUR position TFX008-SYNTH-TRADES,LFX021-SYNTH-LEDGER
05.03.2031 14:00:00,Kraken manual import,Margin Fee,EURC,0.075,,,,,kraken margin ATOM/EUR position TFX008-SYNTH-TRADES,LFX021-SYNTH-LEDGER-fee
06.03.2031 10:00:00,Kraken manual import,Margin Fee,EUR,0.065,,,,,kraken margin ATOM/EUR position TFX010-SYNTH-TRADES,LFX022-SYNTH-LEDGER
06.03.2031 15:00:00,Kraken manual import,Trade,EUR,15.6,ATOM,2.6,,,kraken settled ATOM/EUR position TFX010-SYNTH-TRADES,TFX011-SYNTH-TRADES
20.03.2031 10:00:00,Kraken manual import,Margin Fee,EUR,0.065,,,,,kraken margin ALGO/EUR position TFX012-SYNTH-TRADES,LFX025-SYNTH-LEDGER
25.03.2031 14:00:00,Kraken manual import,Staking,,,ALGO,0.35,ALGO,0.105,kraken earn/reward,LFX026-SYNTH-LEDGER
25.03.2031 14:00:00,Kraken manual import,Staking,,,ATOM,0.0025,,,kraken earn/reward,LFX027-SYNTH-LEDGER
25.03.2031 14:00:00,Kraken manual import,Staking,,,NEAR,0.0000035,NEAR,0.00000105,kraken earn/reward,LFX028-SYNTH-LEDGER
28.03.2031 22:00:00,Kraken manual import,Trade,XTZ,0.00004,EUR,0.000201923,,,kraken spend/dustsweeping TFXD001-SYNTH-SWEEPS,LFX029-SYNTH-LEDGER
28.03.2031 22:00:00,Kraken manual import,Trade,NEAR,0.0000024,EUR,0.000098077,NEAR,0.00000005,kraken spend/dustsweeping TFXD001-SYNTH-SWEEPS,LFX030-SYNTH-LEDGER
```

- [ ] **Step 2: Write the failing tests** — appended to `tests/test_tax_blockpit.py`. `REFUSALS` holds one case per shape the mapping refuses, each a one-line edit of window one; a case's id is the name its probe selects:

```python
def test_window_one_maps_to_its_golden_rows():
    mapped = blockpit.map_rows(read_ledger(LEDGER_1), read_trades(TRADES_1))
    assert mapped.refusals == []
    assert blockpit.render_csv(mapped.rows) == (FIXTURES / "window-1-blockpit.csv").read_bytes()


def _mapped_rows() -> list[dict[str, str]]:
    body = blockpit.render_csv(blockpit.map_rows(read_ledger(LEDGER_1), read_trades(TRADES_1)).rows).decode()
    return list(csv.DictReader(io.StringIO(body)))


def test_every_label_the_mapping_writes_is_a_template_label():
    mapped = blockpit.map_rows(read_ledger(LEDGER_1), read_trades(TRADES_1))
    assert {row.label for row in mapped.rows} <= set(_template_labels())
    assert {row.label for row in mapped.rows} == {
        "Trade",
        "Deposit",
        "Non-Taxable In",
        "Staking",
        "Margin Profit",
        "Margin Loss",
        "Margin Fee",
    }


def test_a_label_outside_the_template_is_refused_as_the_file_is_written():
    stray = blockpit.OutRow(
        "2031-03-03 09:00:00", "Unlabeled", "", "", "EUR", "1250.0", "", "", "kraken deposit", "LFX001-SYNTH-LEDGER", (0, 0)
    )
    with pytest.raises(TaxExportError, match="'Unlabeled' is not one of the template's labels"):
        blockpit.render_csv([stray])


def test_every_asset_moves_in_the_mapped_rows_as_in_the_ledger():
    want, got = {}, {}
    for row in read_ledger(LEDGER_1):
        want[row.asset] = want.get(row.asset, Decimal(0)) + Decimal(row.amount) - Decimal(row.fee)
    for row in blockpit.map_rows(read_ledger(LEDGER_1), read_trades(TRADES_1)).rows:
        for asset, moved in blockpit._moves(row):
            got[asset] = got.get(asset, Decimal(0)) + moved
    assert got == want


def test_no_assets_balance_runs_below_zero_in_the_written_order():
    held = {}
    for row in blockpit._written(blockpit.map_rows(read_ledger(LEDGER_1), read_trades(TRADES_1)).rows):
        for asset, moved in blockpit._moves(row):
            held[asset] = held.get(asset, Decimal(0)) + moved
            assert held[asset] >= 0, (asset, row.trx_id)


def test_a_margin_close_with_pnl_splits_its_fee_into_its_own_row():
    rows = [row for row in _mapped_rows() if row["Trx. ID (optional)"].startswith("LFX015-")]
    assert [
        (r["Label"], r["Incoming Amount"], r["Outgoing Amount"], r["Fee Amount (optional)"], r["Trx. ID (optional)"]) for r in rows
    ] == [
        ("Margin Profit", "1.75", "", "", "LFX015-SYNTH-LEDGER"),
        ("Margin Fee", "", "0.065", "", "LFX015-SYNTH-LEDGER-fee"),
    ]


def test_a_conversion_pair_is_one_trade_from_eur_to_eurc():
    (row,) = [row for row in _mapped_rows() if row["Trx. ID (optional)"] == "TFX009-SYNTH-TRADES"]
    assert (row["Label"], row["Outgoing Asset"], row["Outgoing Amount"], row["Incoming Asset"], row["Incoming Amount"]) == (
        "Trade",
        "EUR",
        "0.825",
        "EURC",
        "0.825",
    )
    assert row["Comment (optional)"].endswith("position TFX008-SYNTH-TRADES")


def test_a_small_balance_conversion_shares_the_receive_by_amountusd():
    rows = [row for row in _mapped_rows() if "dustsweeping" in row["Comment (optional)"]]
    assert [(r["Outgoing Asset"], r["Incoming Amount"]) for r in rows] == [("XTZ", "0.000201923"), ("NEAR", "0.000098077")]


def test_a_one_leg_trade_writes_the_absent_leg_at_zero():
    (row,) = [row for row in _mapped_rows() if row["Trx. ID (optional)"] == "TFX003-SYNTH-TRADES"]
    assert (row["Outgoing Asset"], row["Outgoing Amount"], row["Incoming Asset"], row["Incoming Amount"]) == (
        "EUR",
        "0",
        "XTZ",
        "0.00004",
    )


def test_a_one_leg_debit_writes_the_absent_leg_incoming_at_zero(tmp_path):
    ledger = _edited(tmp_path, LEDGER_1, [("LFX007-SYNTH-LEDGER", "amount", "-0.00004")])
    rows = blockpit.map_rows(read_ledger(ledger), read_trades(TRADES_1)).rows
    (row,) = [row for row in rows if row.trx_id == "TFX003-SYNTH-TRADES"]
    assert (row.out_asset, row.out_amount, row.in_asset, row.in_amount) == ("XTZ", "0.00004", "EUR", "0")


REFUSALS = [
    (
        "unknown_type",
        LEDGER_1,
        [("LFX027-SYNTH-LEDGER", "type", "adjustment"), ("LFX027-SYNTH-LEDGER", "subtype", "")],
        "no mapping is written",
    ),
    ("unknown_subtype", LEDGER_1, [("LFX027-SYNTH-LEDGER", "subtype", "allocation")], "no mapping is written"),
    (
        "unknown_type_at_zero",
        LEDGER_1,
        [("LFX013-SYNTH-LEDGER", "type", "adjustment"), ("LFX013-SYNTH-LEDGER", "fee", "0.0")],
        "no mapping is written",
    ),
    ("wallet", LEDGER_1, [("LFX027-SYNTH-LEDGER", "wallet", "earn / flexible")], "is not 'spot / main'"),
    ("fee_currency", LEDGER_1, [("LFX003-SYNTH-LEDGER", "feecurrency", "ALGO")], "a fee of 0.48 ALGO on a row in EUR"),
    ("negative_fee", LEDGER_1, [("LFX003-SYNTH-LEDGER", "fee", "-0.48")], "a fee of -0.48 EUR on a row in EUR"),
    ("split_times", LEDGER_1, [("LFX004-SYNTH-LEDGER", "time", "2031-03-03 10:00:01")], "carry different times"),
    (
        "three_rows",
        LEDGER_1,
        [("LFX007-SYNTH-LEDGER", "refid", "TFX001-SYNTH-TRADES"), ("LFX007-SYNTH-LEDGER", "time", "2031-03-03 10:00:00")],
        "3 ledger rows where a pair is two",
    ),
    ("trade_one_sign", LEDGER_1, [("LFX003-SYNTH-LEDGER", "amount", "120.0")], "not one out and one in"),
    ("settled_one_sign", LEDGER_1, [("LFX024-SYNTH-LEDGER", "amount", "-2.6")], "not one out and one in"),
    ("trade_zero_leg", LEDGER_1, [("LFX003-SYNTH-LEDGER", "amount", "0.0")], "not one out and one in"),
    ("trade_zero_credit", LEDGER_1, [("LFX006-SYNTH-LEDGER", "amount", "0.0")], "not one out and one in"),
    ("one_asset", LEDGER_1, [("LFX004-SYNTH-LEDGER", "asset", "EUR")], "the two rows are one asset"),
    (
        "fee_on_both_legs",
        LEDGER_1,
        [("LFX004-SYNTH-LEDGER", "fee", "0.105"), ("LFX004-SYNTH-LEDGER", "feecurrency", "ALGO")],
        "a fee on both rows",
    ),
    ("one_leg_off_its_pair", TRADES_1, [("TFX003-SYNTH-TRADES", "pair", "NEAR/EUR")], "XTZ is neither side of NEAR/EUR"),
    ("conversion_not_eur_to_eurc", LEDGER_1, [("LFX010-SYNTH-LEDGER", "asset", "USDC")], "not one EUR row out and one EURC row in"),
    ("conversion_not_from_eur", LEDGER_1, [("LFX009-SYNTH-LEDGER", "asset", "USDC")], "not one EUR row out and one EURC row in"),
    (
        "conversion_with_a_fee",
        LEDGER_1,
        [("LFX016-SYNTH-LEDGER", "fee", "0.0035"), ("LFX016-SYNTH-LEDGER", "feecurrency", "EUR")],
        "not one EUR row out and one EURC row in, without a fee",
    ),
    (
        "conversion_with_a_third_row",
        LEDGER_1,
        [
            ("LFX018-SYNTH-LEDGER", "type", "collateralconversion"),
            ("LFX018-SYNTH-LEDGER", "amount", "-0.075"),
            ("LFX018-SYNTH-LEDGER", "fee", "0.0"),
            ("LFX018-SYNTH-LEDGER", "feecurrency", ""),
        ],
        "not one EUR row out and one EURC row in, without a fee",
    ),
    (
        "margin_without_its_trade",
        LEDGER_1,
        [("LFX011-SYNTH-LEDGER", "refid", "TFX099-SYNTH-TRADES")],
        "no row of the trades export is TFX099-SYNTH-TRADES",
    ),
    ("closing_without_a_position", TRADES_1, [("TFX006-SYNTH-TRADES", "posttxid", "")], "names no position"),
    ("deposit_credits_nothing", LEDGER_1, [("LFX001-SYNTH-LEDGER", "amount", "-1250.0")], "a deposit that credits nothing"),
    ("reward_credits_nothing", LEDGER_1, [("LFX026-SYNTH-LEDGER", "amount", "-0.35")], "a reward that credits nothing"),
    ("rollover_moves_an_amount", LEDGER_1, [("LFX013-SYNTH-LEDGER", "amount", "0.0035")], "a rollover that moves an amount"),
    ("sweep_without_a_receive", LEDGER_1, [("LFX031-SYNTH-LEDGER", None, None)], "not one receive without a fee"),
    ("sweep_with_two_receives", LEDGER_1, [("LFX029-SYNTH-LEDGER", "type", "receive")], "not one receive without a fee"),
    (
        "sweep_without_a_spend",
        LEDGER_1,
        [("LFX029-SYNTH-LEDGER", None, None), ("LFX030-SYNTH-LEDGER", None, None)],
        "at least one spend",
    ),
    (
        "sweep_receive_with_a_fee",
        LEDGER_1,
        [("LFX031-SYNTH-LEDGER", "fee", "0.0003"), ("LFX031-SYNTH-LEDGER", "feecurrency", "EUR")],
        "not one receive without a fee",
    ),
    ("sweep_receive_credits_nothing", LEDGER_1, [("LFX031-SYNTH-LEDGER", "amount", "-0.0003")], "a receive that credits nothing"),
    ("sweep_spend_debits_nothing", LEDGER_1, [("LFX029-SYNTH-LEDGER", "amount", "0.00004")], "a spend that debits nothing"),
    ("sweep_amountusd_missing", LEDGER_1, [("LFX029-SYNTH-LEDGER", "amountusd", "-")], "cannot be shared"),
    ("sweep_amountusd_not_finite", LEDGER_1, [("LFX029-SYNTH-LEDGER", "amountusd", "NaN")], "cannot be shared"),
    (
        "sweep_amountusd_zero",
        LEDGER_1,
        [("LFX029-SYNTH-LEDGER", "amountusd", "0.0"), ("LFX030-SYNTH-LEDGER", "amountusd", "0.0")],
        "cannot be shared",
    ),
    (
        "sweep_of_one_spend_amountusd_zero",
        LEDGER_1,
        [("LFX030-SYNTH-LEDGER", None, None), ("LFX029-SYNTH-LEDGER", "amountusd", "0.0")],
        "cannot be shared",
    ),
]


def _refusal_inputs(tmp_path: Path, source: Path, edits: list[tuple[str, str | None, str | None]]) -> tuple[Path, Path]:
    return (
        _edited(tmp_path, LEDGER_1, edits) if source == LEDGER_1 else LEDGER_1,
        _edited(tmp_path, TRADES_1, edits) if source == TRADES_1 else TRADES_1,
    )


@pytest.mark.parametrize("source,edits,reason", [case[1:] for case in REFUSALS], ids=[case[0] for case in REFUSALS])
def test_each_unmappable_shape_is_refused_by_the_mapping(tmp_path, source, edits, reason):
    ledger, trades = _refusal_inputs(tmp_path, source, edits)
    mapped = blockpit.map_rows(read_ledger(ledger), read_trades(trades))
    assert any(reason in refusal.reason for refusal in mapped.refusals), [r.line() for r in mapped.refusals]


def test_a_rollover_and_a_close_whose_open_is_an_earlier_windows_are_no_refusal():
    mapped = blockpit.map_rows(read_ledger(LEDGER_2), read_trades(TRADES_2))
    assert mapped.refusals == []
    assert mapped.positions == {"TFX012-SYNTH-TRADES": ["LFX101-SYNTH-LEDGER", "LFX102-SYNTH-LEDGER"]}
```

- [ ] **Step 3: Run them and read the failure** — `uv run pytest tests/test_tax_blockpit.py -q -p no:cacheprovider`; Expected: the 45 new cases fail with `AttributeError: module 'cli.tax.blockpit' has no attribute` — `'map_rows'`, `'render_csv'`, `'_written'` or `'OutRow'` — Task 1's 10 pass.
- [ ] **Step 4: The mapping** — appended to `cli/tax/blockpit.py`:

```python
OUTPUT_DATE = "%d.%m.%Y %H:%M:%S"
INTEGRATION = "Kraken manual import"
SPOT_WALLET = "spot / main"
EURO = "EUR"
EURC = "EURC"
ALLOCATION_QUANTUM = Decimal("1e-10")


@dataclass(frozen=True)
class OutRow:
    time: str
    label: str
    out_asset: str
    out_amount: str
    in_asset: str
    in_amount: str
    fee_asset: str
    fee_amount: str
    comment: str
    trx_id: str
    order: tuple[int, int]


@dataclass
class Mapped:
    index: dict[str, int] = field(default_factory=dict)
    rows: list[OutRow] = field(default_factory=list)
    refusals: list[Refusal] = field(default_factory=list)
    positions: dict[str, list[str]] = field(default_factory=dict)
    no_movement: int = 0

    def refuse(self, rows: list[LedgerRow], kind: str, reason: str) -> None:
        self.refusals.append(Refusal(tuple(sorted(row.txid for row in rows)), kind, reason))

    def at(self, rows: list[LedgerRow], ordinal: int = 0) -> tuple[int, int]:
        return (min(self.index[row.txid] for row in rows), ordinal)


def _unsigned(text: str) -> str:
    return text[1:] if text.startswith("-") else text


def _plain(value: Decimal) -> str:
    return format(value.normalize(), "f") if value else "0"


def _fee(row: LedgerRow) -> tuple[str, str]:
    return (row.asset, row.fee) if row.dec("fee") != 0 else ("", "")


def _position(trade: TradeRow, rows: list[LedgerRow], kind: str, mapped: Mapped) -> str | None:
    if not trade.closing:
        return trade.txid
    if not trade.posttxid:
        mapped.refuse(rows, kind, f"closing trade {trade.txid} names no position")
        return None
    return trade.posttxid


def _trade_of(refid: str, rows: list[LedgerRow], kind: str, trades: dict[str, TradeRow], mapped: Mapped) -> TradeRow | None:
    trade = trades.get(refid)
    if trade is None:
        mapped.refuse(rows, kind, f"no row of the trades export is {refid}")
    return trade


def _deposit(row: LedgerRow, trades: dict[str, TradeRow], mapped: Mapped) -> None:
    if row.dec("amount") <= 0:
        mapped.refuse([row], "deposit", "a deposit that credits nothing")
        return
    label = "Non-Taxable In" if row.asset == EURO else "Deposit"
    mapped.rows.append(
        OutRow(row.time, label, "", "", row.asset, row.amount, *_fee(row), "kraken deposit", row.txid, mapped.at([row]))
    )


def _reward(row: LedgerRow, trades: dict[str, TradeRow], mapped: Mapped) -> None:
    if row.dec("amount") <= 0:
        mapped.refuse([row], "earn/reward", "a reward that credits nothing")
        return
    mapped.rows.append(
        OutRow(row.time, "Staking", "", "", row.asset, row.amount, *_fee(row), "kraken earn/reward", row.txid, mapped.at([row]))
    )


def _rollover(row: LedgerRow, trades: dict[str, TradeRow], mapped: Mapped) -> None:
    if row.dec("amount") != 0:
        mapped.refuse([row], "rollover", "a rollover that moves an amount")
        return
    mapped.positions.setdefault(row.refid, []).append(row.txid)
    trade = trades.get(row.refid)
    pair = f" {trade.pair}" if trade else ""
    comment = f"kraken rollover{pair} position {row.refid}"
    mapped.rows.append(OutRow(row.time, "Margin Fee", row.asset, row.fee, "", "", "", "", comment, row.txid, mapped.at([row])))


def _margin(row: LedgerRow, trades: dict[str, TradeRow], mapped: Mapped) -> None:
    trade = _trade_of(row.refid, [row], "margin", trades, mapped)
    position = _position(trade, [row], "margin", mapped) if trade else None
    if position is None:
        return
    mapped.positions.setdefault(position, []).append(row.txid)
    comment = f"kraken margin {trade.pair} position {position}"
    amount = row.dec("amount")
    if amount > 0:
        mapped.rows.append(
            OutRow(row.time, "Margin Profit", "", "", row.asset, row.amount, "", "", comment, row.txid, mapped.at([row]))
        )
    if amount < 0:
        out = _unsigned(row.amount)
        mapped.rows.append(OutRow(row.time, "Margin Loss", row.asset, out, "", "", "", "", comment, row.txid, mapped.at([row])))
    if row.dec("fee") != 0:
        trx_id = f"{row.txid}-fee" if amount != 0 else row.txid
        mapped.rows.append(OutRow(row.time, "Margin Fee", row.asset, row.fee, "", "", "", "", comment, trx_id, mapped.at([row], 1)))


def _legs(rows: list[LedgerRow], kind: str, mapped: Mapped) -> tuple[LedgerRow, LedgerRow, tuple[str, str]] | None:
    if len(rows) != 2:
        mapped.refuse(rows, kind, f"{len(rows)} ledger rows where a pair is two")
        return None
    outs = [row for row in rows if row.dec("amount") < 0]
    ins = [row for row in rows if row.dec("amount") > 0]
    if len(outs) != 1 or len(ins) != 1:
        mapped.refuse(rows, kind, "the two rows are not one out and one in")
        return None
    if outs[0].asset == ins[0].asset:
        mapped.refuse(rows, kind, "the two rows are one asset")
        return None
    fees = [row for row in rows if row.dec("fee") != 0]
    if len(fees) > 1:
        mapped.refuse(rows, kind, "a fee on both rows")
        return None
    return outs[0], ins[0], _fee(fees[0]) if fees else ("", "")


def _pair_trade(legs: tuple[LedgerRow, LedgerRow, tuple[str, str]], comment: str, refid: str, order: tuple[int, int]) -> OutRow:
    out, into, fee = legs
    return OutRow(out.time, "Trade", out.asset, _unsigned(out.amount), into.asset, into.amount, *fee, comment, refid, order)


def _trade(refid: str, rows: list[LedgerRow], trades: dict[str, TradeRow], mapped: Mapped) -> None:
    trade = _trade_of(refid, rows, "trade/tradespot", trades, mapped)
    if trade is None:
        return
    order = mapped.at(rows)
    if len(rows) == 1:
        (leg,) = rows
        base, _, quote = trade.pair.partition("/")
        if leg.asset not in (base, quote):
            mapped.refuse(rows, "trade/tradespot", f"{leg.asset} is neither side of {trade.pair}")
            return
        other = quote if leg.asset == base else base
        comment = f"kraken trade/tradespot {trade.pair} one leg booked"
        if leg.dec("amount") > 0:
            row = OutRow(leg.time, "Trade", other, "0", leg.asset, leg.amount, *_fee(leg), comment, refid, order)
        else:
            row = OutRow(leg.time, "Trade", leg.asset, _unsigned(leg.amount), other, "0", *_fee(leg), comment, refid, order)
        mapped.rows.append(row)
        return
    legs = _legs(rows, "trade/tradespot", mapped)
    if legs is not None:
        comment = f"kraken trade/tradespot {trade.pair}"
        mapped.rows.append(_pair_trade(legs, comment, refid, order))


def _settled(refid: str, rows: list[LedgerRow], trades: dict[str, TradeRow], mapped: Mapped) -> None:
    trade = _trade_of(refid, rows, "settled", trades, mapped)
    legs = _legs(rows, "settled", mapped) if trade else None
    position = _position(trade, rows, "settled", mapped) if legs else None
    if position is None:
        return
    mapped.positions.setdefault(position, []).extend(row.txid for row in rows)
    comment = f"kraken settled {trade.pair} position {position}"
    mapped.rows.append(_pair_trade(legs, comment, refid, mapped.at(rows)))


def _conversion(refid: str, rows: list[LedgerRow], trades: dict[str, TradeRow], mapped: Mapped) -> None:
    trade = _trade_of(refid, rows, "collateralconversion", trades, mapped)
    if trade is None:
        return
    outs = [row for row in rows if row.asset == EURO and row.dec("amount") < 0]
    ins = [row for row in rows if row.asset == EURC and row.dec("amount") > 0]
    if len(rows) != 2 or len(outs) != 1 or len(ins) != 1 or any(row.dec("fee") != 0 for row in rows):
        mapped.refuse(rows, "collateralconversion", "not one EUR row out and one EURC row in, without a fee")
        return
    position = _position(trade, rows, "collateralconversion", mapped)
    if position is None:
        return
    mapped.positions.setdefault(position, []).extend(row.txid for row in rows)
    comment = f"kraken collateralconversion {trade.pair} position {position}"
    order = mapped.at(rows)
    mapped.rows.append(
        OutRow(outs[0].time, "Trade", EURO, _unsigned(outs[0].amount), EURC, ins[0].amount, "", "", comment, refid, order)
    )


def _sweep(refid: str, rows: list[LedgerRow], trades: dict[str, TradeRow], mapped: Mapped) -> None:
    kind = "spend/receive dustsweeping"
    spends = sorted((row for row in rows if row.type == "spend"), key=lambda row: row.txid)
    receives = [row for row in rows if row.type == "receive"]
    if len(receives) != 1 or not spends or receives[0].dec("fee") != 0:
        mapped.refuse(rows, kind, "not one receive without a fee and at least one spend")
        return
    if receives[0].dec("amount") <= 0 or any(row.dec("amount") >= 0 for row in spends):
        mapped.refuse(rows, kind, "a receive that credits nothing, or a spend that debits nothing")
        return
    try:
        values = [abs(row.dec("amountusd")) for row in spends]
    except InvalidOperation:
        values = []
    total = sum(values, Decimal(0))
    if not all(value.is_finite() for value in values) or total == 0:
        mapped.refuse(rows, kind, "the spends' amountusd are not decimals summing above zero, so the receive cannot be shared")
        return
    received = receives[0].dec("amount")
    shares = [(received * value / total).quantize(ALLOCATION_QUANTUM, rounding=ROUND_DOWN) for value in values[:-1]]
    shares.append(received - sum(shares, Decimal(0)))
    for ordinal, (spend, share) in enumerate(zip(spends, shares)):
        comment = f"kraken spend/dustsweeping {refid}"
        out = _unsigned(spend.amount)
        row = OutRow(
            spend.time,
            "Trade",
            spend.asset,
            out,
            receives[0].asset,
            _plain(share),
            *_fee(spend),
            comment,
            spend.txid,
            mapped.at(rows, ordinal),
        )
        mapped.rows.append(row)


SINGLE = {("deposit", ""): _deposit, ("earn", "reward"): _reward, ("rollover", ""): _rollover, ("margin", ""): _margin}


GROUPED = {
    ("trade", "tradespot"): _trade,
    ("settled", ""): _settled,
    ("collateralconversion", ""): _conversion,
    ("spend", "dustsweeping"): _sweep,
    ("receive", "dustsweeping"): _sweep,
}


def map_rows(ledger: list[LedgerRow], trades: dict[str, TradeRow]) -> Mapped:
    mapped = Mapped(index={row.txid: number for number, row in enumerate(ledger)})
    groups: dict[tuple[object, str], list[LedgerRow]] = defaultdict(list)
    for row in ledger:
        kind = f"{row.type}/{row.subtype}" if row.subtype else row.type
        key = (row.type, row.subtype)
        if row.wallet != SPOT_WALLET:
            mapped.refuse([row], kind, f"wallet {row.wallet!r} is not {SPOT_WALLET!r}")
        elif row.dec("fee") < 0 or (row.dec("fee") != 0 and row.feecurrency != row.asset):
            mapped.refuse([row], kind, f"a fee of {row.fee} {row.feecurrency} on a row in {row.asset}")
        elif key not in SINGLE and key not in GROUPED:
            mapped.refuse([row], kind, "no mapping is written for this type and subtype")
        elif row.dec("amount") == 0 and row.dec("fee") == 0:
            mapped.no_movement += 1
        elif key in SINGLE:
            SINGLE[key](row, trades, mapped)
        else:
            groups[(GROUPED[key], row.refid)].append(row)
    for (mapper, refid), rows in groups.items():
        if len({row.time for row in rows}) != 1:
            mapped.refuse(rows, rows[0].type, f"the rows under {refid} carry different times")
        else:
            mapper(refid, rows, trades, mapped)
    return mapped


def _moves(row: OutRow):
    for asset, amount, sign in (
        (row.in_asset, row.in_amount, 1),
        (row.out_asset, row.out_amount, -1),
        (row.fee_asset, row.fee_amount, -1),
    ):
        if asset:
            yield asset, sign * Decimal(amount)


def _written(rows: list[OutRow]) -> list[OutRow]:
    return sorted(rows, key=lambda row: (row.time, row.order))


def render_csv(rows: list[OutRow]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(HEADER)
    for row in _written(rows):
        if row.label not in TEMPLATE_LABELS:
            raise TaxExportError(f"{row.label!r} is not one of the template's labels")
        date = datetime.strptime(row.time, LEDGER_TIME).strftime(OUTPUT_DATE)
        writer.writerow(
            (
                date,
                INTEGRATION,
                row.label,
                row.out_asset,
                row.out_amount,
                row.in_asset,
                row.in_amount,
                row.fee_asset,
                row.fee_amount,
                row.comment,
                row.trx_id,
            )
        )
    return buffer.getvalue().encode("utf-8")
```

- [ ] **Step 5: Run the tests** — Step 3's command; Expected: `55 passed`.
- [ ] **Step 6: The consumers** — the tax consumers command, then the consumers' run; Expected: no failure.
- [ ] **Step 7: The commit gate**
- [ ] **Step 8: Commit**

```bash
git add cli/tax/blockpit.py tests/test_tax_blockpit.py tests/fixtures/tax_blockpit/window-1-blockpit.csv
git commit -F- <<'MSG'
feat(tax): every Kraken ledger row type mapped onto Blockpit's template rows, the conversion pair a trade and the close's fee its own row

The mapping writes the connector's labels for every row type it measured and changes two
shapes: a collateralconversion pair is one Trade EUR to EURC at the pair's amounts, and a margin row
with a non-zero amount is a Margin Profit or Loss at the amount beside a Margin Fee row at its fee.
A crypto deposit is a Deposit, Blockpit's unlabeled incoming type; an earn reward is Staking, gross
with Kraken's commission as its fee; a small-balance conversion is one Trade per spent coin, the
receive shared by amountusd; a trade whose ledger booked one leg writes the other at zero. Every
other type or subtype, and every shape outside the measured ones, is a refusal naming its rows.
Rows of one second keep the ledger export's own order, in which each asset's balance chain holds,
since Kraken's txids carry no booking order. A label outside the template's own list stops the file
before it is written.

PROBE_VERDICT

Co-Authored-By: Claude <actual executing model> <noreply@anthropic.com>
MSG
```

- [ ] **Step 9: The tree is clean**
- [ ] **Step 10: Prove the guards, then record their verdicts** — forty-five probes, the mapping's ten shapes, its thirty-four refusal guards and the label check; Expected: each KILLED; then the message-only amend.

```bash
infra/scripts/mutate-probe.sh --file cli/tax/blockpit.py --control '1,$d' \
  --mutation 's/^    label = "Non-Taxable In" if row.asset == EURO else "Deposit"$/    label = "Non-Taxable (In)" if row.asset == EURO else "Deposit"/' \
  -- uv run pytest tests/test_tax_blockpit.py -k mapping_writes -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file cli/tax/blockpit.py --control '1,$d' \
  --mutation 's/^        if row.label not in TEMPLATE_LABELS:$/        if False:/' \
  -- uv run pytest tests/test_tax_blockpit.py -k label_outside_the_template -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file cli/tax/blockpit.py --control '1,$d' \
  --mutation '/^def _conversion/,/^def _sweep/s/^    mapped.rows.append($/    0 and mapped.rows.append(/' \
  -- uv run pytest tests/test_tax_blockpit.py -k conversion_pair_is_one_trade -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file cli/tax/blockpit.py --control '1,$d' \
  --mutation 's/^        trx_id = f"{row.txid}-fee" if amount != 0 else row.txid$/        trx_id = row.txid/' \
  -- uv run pytest tests/test_tax_blockpit.py -k splits_its_fee -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file cli/tax/blockpit.py --control '1,$d' \
  --mutation 's/^    if amount > 0:$/    if False:/' \
  -- uv run pytest tests/test_tax_blockpit.py -k splits_its_fee -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file cli/tax/blockpit.py --control '1,$d' \
  --mutation 's/^    if amount < 0:$/    if False:/' \
  -- uv run pytest tests/test_tax_blockpit.py -k golden_rows -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file cli/tax/blockpit.py --control '1,$d' \
  --mutation 's/^ALLOCATION_QUANTUM = Decimal("1e-10")$/ALLOCATION_QUANTUM = Decimal("1e-4")/' \
  -- uv run pytest tests/test_tax_blockpit.py -k shares_the_receive -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file cli/tax/blockpit.py --control '1,$d' \
  --mutation 's/^    return sorted(rows, key=lambda row: (row.time, row.order))$/    return rows/' \
  -- uv run pytest tests/test_tax_blockpit.py -k golden_rows -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file cli/tax/blockpit.py --control '1,$d' \
  --mutation 's/^    mapped = Mapped(index={row.txid: number for number, row in enumerate(ledger)})$/    mapped = Mapped(index={row.txid: number for number, row in enumerate(sorted(ledger, key=lambda row: row.txid))})/' \
  -- uv run pytest tests/test_tax_blockpit.py -k runs_below_zero -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file cli/tax/blockpit.py --control '1,$d' \
  --mutation 's/^    pair = f" {trade.pair}" if trade else ""$/    pair = ""/' \
  -- uv run pytest tests/test_tax_blockpit.py -k golden_rows -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file cli/tax/blockpit.py --control '1,$d' \
  --mutation 's/^            row = OutRow(leg.time, "Trade", leg.asset, _unsigned(leg.amount), other, "0", \*_fee(leg), comment, refid, order)$/            row = OutRow(leg.time, "Trade", other, "0", leg.asset, _unsigned(leg.amount), *_fee(leg), comment, refid, order)/' \
  -- uv run pytest tests/test_tax_blockpit.py -k one_leg_debit -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file cli/tax/blockpit.py --control '1,$d' \
  --mutation 's/^        if row.wallet != SPOT_WALLET:$/        if False:/' \
  -- uv run pytest tests/test_tax_blockpit.py -k wallet -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file cli/tax/blockpit.py --control '1,$d' \
  --mutation 's/^        elif row.dec("fee") < 0 or (row.dec("fee") != 0 and row.feecurrency != row.asset):$/        elif row.dec("fee") != 0 and row.feecurrency != row.asset:/' \
  -- uv run pytest tests/test_tax_blockpit.py -k negative_fee -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file cli/tax/blockpit.py --control '1,$d' \
  --mutation 's/^        elif row.dec("fee") < 0 or (row.dec("fee") != 0 and row.feecurrency != row.asset):$/        elif row.dec("fee") < 0:/' \
  -- uv run pytest tests/test_tax_blockpit.py -k fee_currency -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file cli/tax/blockpit.py --control '1,$d' \
  --mutation 's/^            mapped.refuse(\[row\], kind, "no mapping is written for this type and subtype")$/            pass/' \
  -- uv run pytest tests/test_tax_blockpit.py -k unknown_ -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file cli/tax/blockpit.py --control '1,$d' \
  --mutation 's/^        elif key not in SINGLE and key not in GROUPED:$/        elif key not in SINGLE and key not in GROUPED and (row.dec("amount") != 0 or row.dec("fee") != 0):/' \
  -- uv run pytest tests/test_tax_blockpit.py -k unknown_type_at_zero -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file cli/tax/blockpit.py --control '1,$d' \
  --mutation 's/^        if len({row.time for row in rows}) != 1:$/        if False:/' \
  -- uv run pytest tests/test_tax_blockpit.py -k split_times -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file cli/tax/blockpit.py --control '1,$d' \
  --mutation '/^def _deposit/,/^def _reward/s/^    if row.dec("amount") <= 0:$/    if False:/' \
  -- uv run pytest tests/test_tax_blockpit.py -k deposit_credits_nothing -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file cli/tax/blockpit.py --control '1,$d' \
  --mutation '/^def _reward/,/^def _rollover/s/^    if row.dec("amount") <= 0:$/    if False:/' \
  -- uv run pytest tests/test_tax_blockpit.py -k reward_credits_nothing -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file cli/tax/blockpit.py --control '1,$d' \
  --mutation 's/^    if row.dec("amount") != 0:$/    if False:/' \
  -- uv run pytest tests/test_tax_blockpit.py -k rollover_moves_an_amount -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file cli/tax/blockpit.py --control '1,$d' \
  --mutation 's/^        mapped.refuse(rows, kind, f"no row of the trades export is {refid}")$/        pass/' \
  -- uv run pytest tests/test_tax_blockpit.py -k margin_without_its_trade -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file cli/tax/blockpit.py --control '1,$d' \
  --mutation 's/^    if not trade.posttxid:$/    if False:/' \
  -- uv run pytest tests/test_tax_blockpit.py -k closing_without_a_position -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file cli/tax/blockpit.py --control '1,$d' \
  --mutation 's/^    if not trade.closing:$/    if trade.closing:/' \
  -- uv run pytest tests/test_tax_blockpit.py -k earlier_windows -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file cli/tax/blockpit.py --control '1,$d' \
  --mutation 's/^    if len(rows) != 2:$/    if False:/' \
  -- uv run pytest tests/test_tax_blockpit.py -k three_rows -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file cli/tax/blockpit.py --control '1,$d' \
  --mutation 's/^    if len(outs) != 1 or len(ins) != 1:$/    if False:/' \
  -- uv run pytest tests/test_tax_blockpit.py -k one_sign -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file cli/tax/blockpit.py --control '1,$d' \
  --mutation 's/^    if len(outs) != 1 or len(ins) != 1:$/    if len(outs) != 1 and len(ins) != 1:/' \
  -- uv run pytest tests/test_tax_blockpit.py -k trade_zero_leg -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file cli/tax/blockpit.py --control '1,$d' \
  --mutation 's/^    if len(outs) != 1 or len(ins) != 1:$/    if len(outs) != 1:/' \
  -- uv run pytest tests/test_tax_blockpit.py -k trade_zero_credit -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file cli/tax/blockpit.py --control '1,$d' \
  --mutation 's/^    if outs\[0\].asset == ins\[0\].asset:$/    if False:/' \
  -- uv run pytest tests/test_tax_blockpit.py -k one_asset -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file cli/tax/blockpit.py --control '1,$d' \
  --mutation 's/^    if len(fees) > 1:$/    if False:/' \
  -- uv run pytest tests/test_tax_blockpit.py -k fee_on_both_legs -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file cli/tax/blockpit.py --control '1,$d' \
  --mutation 's/^        if leg.asset not in (base, quote):$/        if False:/' \
  -- uv run pytest tests/test_tax_blockpit.py -k one_leg_off_its_pair -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file cli/tax/blockpit.py --control '1,$d' \
  --mutation 's/^    if len(rows) != 2 or len(outs) != 1 or len(ins) != 1 or any(row.dec("fee") != 0 for row in rows):$/    if False:/' \
  -- uv run pytest tests/test_tax_blockpit.py -k 'conversion_with_a_fee or conversion_with_a_third_row' -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file cli/tax/blockpit.py --control '1,$d' \
  --mutation 's/ or len(outs) != 1 or len(ins) != 1 or any/ or len(ins) != 1 or any/' \
  -- uv run pytest tests/test_tax_blockpit.py -k conversion_not_from_eur -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file cli/tax/blockpit.py --control '1,$d' \
  --mutation 's/ or len(ins) != 1 or any(row.dec("fee")/ or any(row.dec("fee")/' \
  -- uv run pytest tests/test_tax_blockpit.py -k conversion_not_eur_to_eurc -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file cli/tax/blockpit.py --control '1,$d' \
  --mutation 's/ or any(row.dec("fee") != 0 for row in rows):$/:/' \
  -- uv run pytest tests/test_tax_blockpit.py -k conversion_with_a_fee -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file cli/tax/blockpit.py --control '1,$d' \
  --mutation 's/^    if len(rows) != 2 or len(outs) != 1/    if len(outs) != 1/' \
  -- uv run pytest tests/test_tax_blockpit.py -k conversion_with_a_third_row -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file cli/tax/blockpit.py --control '1,$d' \
  --mutation 's/^    if len(receives) != 1 or not spends or receives\[0\].dec("fee") != 0:$/    if False:/' \
  -- uv run pytest tests/test_tax_blockpit.py -k sweep_with_two_receives -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file cli/tax/blockpit.py --control '1,$d' \
  --mutation 's/^    if len(receives) != 1 or not spends or /    if not spends or /' \
  -- uv run pytest tests/test_tax_blockpit.py -k sweep_with_two_receives -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file cli/tax/blockpit.py --control '1,$d' \
  --mutation 's/^    if len(receives) != 1 or not spends or /    if len(receives) != 1 or /' \
  -- uv run pytest tests/test_tax_blockpit.py -k sweep_without_a_spend -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file cli/tax/blockpit.py --control '1,$d' \
  --mutation 's/ or receives\[0\].dec("fee") != 0:$/:/' \
  -- uv run pytest tests/test_tax_blockpit.py -k sweep_receive_with_a_fee -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file cli/tax/blockpit.py --control '1,$d' \
  --mutation 's/^    if receives\[0\].dec("amount") <= 0 or any(row.dec("amount") >= 0 for row in spends):$/    if False:/' \
  -- uv run pytest tests/test_tax_blockpit.py -k sweep_receive_credits_nothing -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file cli/tax/blockpit.py --control '1,$d' \
  --mutation 's/^    if receives\[0\].dec("amount") <= 0 or /    if /' \
  -- uv run pytest tests/test_tax_blockpit.py -k sweep_receive_credits_nothing -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file cli/tax/blockpit.py --control '1,$d' \
  --mutation 's/ or any(row.dec("amount") >= 0 for row in spends):$/:/' \
  -- uv run pytest tests/test_tax_blockpit.py -k sweep_spend_debits_nothing -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file cli/tax/blockpit.py --control '1,$d' \
  --mutation 's/^    if not all(value.is_finite() for value in values) or total == 0:$/    if False:/' \
  -- uv run pytest tests/test_tax_blockpit.py -k 'sweep_amountusd_missing or sweep_amountusd_not_finite' -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file cli/tax/blockpit.py --control '1,$d' \
  --mutation 's/^    if not all(value.is_finite() for value in values) or total == 0:$/    if total == 0:/' \
  -- uv run pytest tests/test_tax_blockpit.py -k sweep_amountusd_not_finite -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file cli/tax/blockpit.py --control '1,$d' \
  --mutation 's/ or total == 0:$/:/' \
  -- uv run pytest tests/test_tax_blockpit.py -k sweep_of_one_spend_amountusd_zero -q -p no:cacheprovider
```

---

### Task 3: The join's cross-check — a trades row with none of its ledger rows

**Files:**
- Modify: `cli/tax/blockpit.py` (appended after `render_csv`)
- Test: `tests/test_tax_blockpit.py`

**Interfaces:**
- Consumes: Task 1's readers.
- Produces: `check_cross(ledger, trades) -> list[Refusal]`, which Task 4's run calls; the ledger-to-trades direction is Task 2's `_trade_of`.

**What this task decides, where the spec leaves it open:** one present ledger id is enough, since an opening trade's `ledgers` names rollover rows past the window's end — window one's `TFX012` names `LFX101`, a row of window two.

- [ ] **Step 1: Write the failing tests**

```python
def test_a_trades_row_without_its_ledger_rows_is_refused(tmp_path):
    trades = read_trades(_edited(tmp_path, TRADES_1, [("TFX003-SYNTH-TRADES", "ledgers", "LFX999-SYNTH-LEDGER")]))
    (refusal,) = blockpit.check_cross(read_ledger(LEDGER_1), trades)
    assert refusal.txids == ("TFX003-SYNTH-TRADES",) and refusal.kind == "trades"


def test_a_trades_row_naming_one_present_ledger_id_is_enough():
    assert blockpit.check_cross(read_ledger(LEDGER_1), read_trades(TRADES_1)) == []
```

- [ ] **Step 2: Run them and read the failure** — `uv run pytest tests/test_tax_blockpit.py -q -p no:cacheprovider`; Expected: the 2 new cases fail with `AttributeError: … 'check_cross'`.
- [ ] **Step 3: The check** — appended to `cli/tax/blockpit.py`:

```python
def check_cross(ledger: list[LedgerRow], trades: dict[str, TradeRow]) -> list[Refusal]:
    present = {row.txid for row in ledger}
    return [
        Refusal((trade.txid,), "trades", "none of its ledger ids is in the ledger export")
        for trade in trades.values()
        if not present.intersection(trade.ledgers)
    ]
```

- [ ] **Step 4: Run the tests** — Expected: `57 passed`.
- [ ] **Step 5: The consumers** — the tax consumers command, then the consumers' run; Expected: no failure.
- [ ] **Step 6: The commit gate**
- [ ] **Step 7: Commit**

```bash
git add cli/tax/blockpit.py tests/test_tax_blockpit.py
git commit -F- <<'MSG'
feat(tax): a trades row none of whose ledger rows is in the ledger export is refused

The two exports describe one window when each trades row names at least one ledger row the
ledger export holds; one is enough, since an opening trade names its later rollover rows.

PROBE_VERDICT

Co-Authored-By: Claude <actual executing model> <noreply@anthropic.com>
MSG
```

- [ ] **Step 8: The tree is clean**
- [ ] **Step 9: Prove the guards, then record their verdicts** — two probes; Expected: each KILLED; then the message-only amend.

```bash
infra/scripts/mutate-probe.sh --file cli/tax/blockpit.py --control '1,$d' \
  --mutation 's/^        if not present.intersection(trade.ledgers)$/        if False/' \
  -- uv run pytest tests/test_tax_blockpit.py -k trades_row_without_its_ledger_rows -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file cli/tax/blockpit.py --control '1,$d' \
  --mutation 's/^        if not present.intersection(trade.ledgers)$/        if not present.issuperset(trade.ledgers)/' \
  -- uv run pytest tests/test_tax_blockpit.py -k naming_one_present -q -p no:cacheprovider
```

---

### Task 4: The run — the balance chain, conservation, one Trx. ID a row, the provenance, and nothing written on a refusal

**Files:**
- Modify: `cli/tax/blockpit.py` (appended after `check_cross`)
- Create: `tests/fixtures/tax_blockpit/window-1-blockpit.csv.provenance.json`
- Test: `tests/test_tax_blockpit.py`

**Interfaces:**
- Consumes: Tasks 1 to 3.
- Produces: `transform(ledgers, trades, out) -> Written`, writing `out` and `<out>.provenance.json` or raising `Refused` (nothing written) or `TaxExportError` (an output that exists, an unreadable input, a label outside the template), its `label_rows` the written rows counted by label; `check_chain`, `check_conservation`, `check_order`, `check_unique`; the provenance's keys — `inputs` (`ledgers`: `file`, `sha256`, `rows`, `first_time`, `last_time`; `trades`: `file`, `sha256`, `rows`), `output` (`file`, `sha256`, `rows`), `labels` (label → asset → `rows`, `incoming`, `outgoing`, `fee`), `opening`, `closing`, `positions`, `no_movement`, `previous` (null until Task 5), `zcrypto`.

**What this task decides, where the spec leaves it open:** the provenance is `json.dumps(…, indent=2, sort_keys=True)` with a newline, its decimals normalized, and a test holds the written file to that form; the golden provenance is that record compact and without its two run-dependent keys, `previous` and `zcrypto`, which the tests read apart — spec D8's golden comparison, but for those two; the chain is read in the export's own row order; the written order is read too, each asset's balance from its opening, each row applied whole, never below zero, so an export that interleaves two groups' rows inside one second — a shape the owner's export does not hold — refuses rather than listing a debit before the credit that funds it; the run over the trades rows reordered compares the import file alone, since the provenance carries the trades file's own sha256; each input is read once, its bytes both hashed into the provenance and handed to its reader.

- [ ] **Step 1: The golden provenance** — `tests/fixtures/tax_blockpit/window-1-blockpit.csv.provenance.json`, one line:

```json
{"closing": {"ALGO": "160.245", "ATOM": "11.1025", "EUR": "1174.1133", "EURC": "0", "NEAR": "0", "XTZ": "0"}, "inputs": {"ledgers": {"file": "window-1-ledgers.csv", "first_time": "2031-03-03 09:00:00", "last_time": "2031-03-28 22:00:00", "rows": 31, "sha256": "5c61ac12ded70979c2a637822e5b61913f8e8654e3f6a104847aa55ef0a22fab"}, "trades": {"file": "window-1-trades.csv", "rows": 12, "sha256": "baf679ca665a1dde690a382a9297f8b55f874f0411dded64c2cbf74fc057569a"}}, "labels": {"Deposit": {"ATOM": {"fee": "0", "incoming": "8.5", "outgoing": "0", "rows": 1}}, "Margin Fee": {"EUR": {"fee": "0", "incoming": "0", "outgoing": "0.342", "rows": 7}, "EURC": {"fee": "0", "incoming": "0", "outgoing": "0.225", "rows": 3}}, "Margin Loss": {"EURC": {"fee": "0", "incoming": "0", "outgoing": "0.75", "rows": 1}}, "Margin Profit": {"EUR": {"fee": "0", "incoming": "1.75", "outgoing": "0", "rows": 1}}, "Non-Taxable In": {"EUR": {"fee": "0", "incoming": "1250", "outgoing": "0", "rows": 1}}, "Staking": {"ALGO": {"fee": "0.105", "incoming": "0.35", "outgoing": "0", "rows": 1}, "ATOM": {"fee": "0", "incoming": "0.0025", "outgoing": "0", "rows": 1}, "NEAR": {"fee": "0.00000105", "incoming": "0.0000035", "outgoing": "0", "rows": 1}}, "Trade": {"ALGO": {"fee": "0", "incoming": "320", "outgoing": "160", "rows": 2}, "ATOM": {"fee": "0", "incoming": "2.6", "outgoing": "0", "rows": 1}, "EUR": {"fee": "0.72", "incoming": "60.0003", "outgoing": "136.575", "rows": 9}, "EURC": {"fee": "0", "incoming": "0.975", "outgoing": "0", "rows": 3}, "NEAR": {"fee": "0.00000005", "incoming": "0", "outgoing": "0.0000024", "rows": 1}, "XTZ": {"fee": "0", "incoming": "0.00004", "outgoing": "0.00004", "rows": 2}}}, "no_movement": 0, "opening": {"ALGO": "0", "ATOM": "0", "EUR": "0", "EURC": "0", "NEAR": "0", "XTZ": "0"}, "output": {"file": "window-1-blockpit.csv", "rows": 26, "sha256": "cec7551dd902916254581c8da8e576a28159cd8fe663083326e640128348bf35"}, "positions": {"TFX004-SYNTH-TRADES": ["LFX008-SYNTH-LEDGER", "LFX009-SYNTH-LEDGER", "LFX010-SYNTH-LEDGER", "LFX012-SYNTH-LEDGER"], "TFX005-SYNTH-TRADES": ["LFX011-SYNTH-LEDGER", "LFX013-SYNTH-LEDGER", "LFX014-SYNTH-LEDGER", "LFX015-SYNTH-LEDGER"], "TFX008-SYNTH-TRADES": ["LFX016-SYNTH-LEDGER", "LFX017-SYNTH-LEDGER", "LFX018-SYNTH-LEDGER", "LFX019-SYNTH-LEDGER", "LFX020-SYNTH-LEDGER", "LFX021-SYNTH-LEDGER"], "TFX010-SYNTH-TRADES": ["LFX022-SYNTH-LEDGER", "LFX023-SYNTH-LEDGER", "LFX024-SYNTH-LEDGER"], "TFX012-SYNTH-TRADES": ["LFX025-SYNTH-LEDGER"]}}
```

- [ ] **Step 2: Write the failing tests** — the run helper and the run's cases:

```python
def _run(tmp_path: Path, ledger: Path = LEDGER_1, trades: Path = TRADES_1, name: str = "window-1-blockpit.csv"):
    return blockpit.transform(ledger, trades, tmp_path / name)


def _provenance(path: Path) -> dict:
    record = json.loads(path.read_text())
    return {key: value for key, value in record.items() if key not in ("zcrypto", "previous")}


def test_a_run_writes_window_ones_golden_rows_and_provenance(tmp_path):
    written = _run(tmp_path)
    assert written.out.read_bytes() == (FIXTURES / "window-1-blockpit.csv").read_bytes()
    assert _provenance(written.provenance) == json.loads((FIXTURES / "window-1-blockpit.csv.provenance.json").read_text())
    text = written.provenance.read_text()
    assert text == json.dumps(json.loads(text), indent=2, sort_keys=True) + "\n"
    record = json.loads(text)
    assert record["zcrypto"] == version("zcrypto") and record["previous"] is None


def test_two_runs_are_byte_equal(tmp_path):
    first, second = tmp_path / "a", tmp_path / "b"
    first.mkdir(), second.mkdir()
    one, two = _run(first), _run(second)
    assert one.out.read_bytes() == two.out.read_bytes()
    assert one.provenance.read_bytes() == two.provenance.read_bytes()


def test_a_run_over_the_trades_rows_reordered_writes_the_same_file(tmp_path):
    header, *rows = TRADES_1.read_text().splitlines()
    (tmp_path / "reordered").mkdir()
    reordered = tmp_path / "reordered" / TRADES_1.name
    reordered.write_text("\n".join([header, *reversed(rows)]) + "\n")
    plain, shuffled = _run(tmp_path), _run(tmp_path, trades=reordered, name="reordered.csv")
    assert shuffled.out.read_bytes() == plain.out.read_bytes()


def test_the_provenance_hashes_are_the_files(tmp_path):
    written = _run(tmp_path)
    record = json.loads(written.provenance.read_text())
    assert record["output"]["sha256"] == hashlib.sha256(written.out.read_bytes()).hexdigest()
    assert record["inputs"]["ledgers"]["sha256"] == hashlib.sha256(LEDGER_1.read_bytes()).hexdigest()
    assert record["inputs"]["trades"]["sha256"] == hashlib.sha256(TRADES_1.read_bytes()).hexdigest()


@pytest.mark.parametrize(
    "edits",
    [[("LFX005-SYNTH-LEDGER", "balance", "320.0")], [("LFX013-SYNTH-LEDGER", None, None)]],
    ids=["balance_edited", "row_removed"],
)
def test_a_broken_balance_chain_is_refused_and_nothing_is_written(tmp_path, edits):
    ledger = _edited(tmp_path, LEDGER_1, edits)
    with pytest.raises(Refused) as caught:
        _run(tmp_path, ledger=ledger)
    assert "balance" in {refusal.kind for refusal in caught.value.refusals}
    assert sorted(path.name for path in tmp_path.iterdir()) == ["window-1-ledgers.csv"]


@pytest.mark.parametrize("source,edits,reason", [case[1:] for case in REFUSALS], ids=[case[0] for case in REFUSALS])
def test_each_refused_shape_writes_nothing(tmp_path, source, edits, reason):
    ledger, trades = _refusal_inputs(tmp_path, source, edits)
    before = sorted(tmp_path.iterdir())
    with pytest.raises(Refused) as caught:
        _run(tmp_path, ledger=ledger, trades=trades)
    assert any(reason in refusal.reason for refusal in caught.value.refusals), [r.line() for r in caught.value.refusals]
    assert sorted(tmp_path.iterdir()) == before


def test_a_mapping_that_loses_a_movement_is_refused_by_conservation(tmp_path, monkeypatch):
    monkeypatch.setitem(blockpit.SINGLE, ("rollover", ""), lambda row, trades, mapped: None)
    with pytest.raises(Refused) as caught:
        _run(tmp_path)
    assert [refusal.line() for refusal in caught.value.refusals] == [
        "refused - [conservation]: EUR moves 1174.1203 in the output and 1174.1133 in the ledger"
    ]


def test_two_rows_with_one_trx_id_are_refused():
    row = blockpit.map_rows(read_ledger(LEDGER_1), read_trades(TRADES_1)).rows[0]
    (refusal,) = blockpit.check_unique([row, row])
    assert refusal.kind == "trx-id" and refusal.txids == (row.trx_id,)


def test_a_run_refuses_a_trades_row_without_its_ledger_rows(tmp_path):
    trades = _edited(tmp_path, TRADES_1, [("TFX003-SYNTH-TRADES", "ledgers", "LFX999-SYNTH-LEDGER")])
    with pytest.raises(Refused) as caught:
        _run(tmp_path, trades=trades)
    assert [refusal.kind for refusal in caught.value.refusals] == ["trades"]
    assert sorted(path.name for path in tmp_path.iterdir()) == ["window-1-trades.csv"]


def test_a_run_refuses_two_rows_with_one_trx_id(tmp_path, monkeypatch):
    deposit = blockpit.SINGLE[("deposit", "")]

    def twice(row, trades, mapped):
        deposit(row, trades, mapped)
        deposit(row, trades, mapped)

    monkeypatch.setitem(blockpit.SINGLE, ("deposit", ""), twice)
    with pytest.raises(Refused) as caught:
        _run(tmp_path)
    assert "trx-id" in {refusal.kind for refusal in caught.value.refusals}


@pytest.mark.parametrize(
    "existing", ["window-1-blockpit.csv", "window-1-blockpit.csv.provenance.json"], ids=["out_file", "provenance_file"]
)
def test_an_existing_output_is_never_overwritten(tmp_path, existing):
    (tmp_path / existing).write_text("{}")
    with pytest.raises(TaxExportError, match="never overwrites"):
        _run(tmp_path)
    assert sorted(path.name for path in tmp_path.iterdir()) == [existing]
    assert (tmp_path / existing).read_text() == "{}"


def test_a_row_moving_nothing_is_counted_and_written_nowhere(tmp_path):
    edits = [
        ("LFX013-SYNTH-LEDGER", "fee", "0.0"),
        ("LFX013-SYNTH-LEDGER", "balance", "1189.065"),
        ("LFX014-SYNTH-LEDGER", "fee", "0.007"),
    ]
    written = _run(tmp_path, ledger=_edited(tmp_path, LEDGER_1, edits))
    assert json.loads(written.provenance.read_text())["no_movement"] == 1
    assert "LFX013-SYNTH-LEDGER" not in written.out.read_text()


def test_a_run_over_a_ledger_without_a_column_writes_nothing(tmp_path):
    ledger = _without(tmp_path, LEDGER_1, "wallet")
    before = sorted(tmp_path.iterdir())
    with pytest.raises(TaxExportError, match="wallet"):
        _run(tmp_path, ledger=ledger)
    assert sorted(tmp_path.iterdir()) == before


def _moved(path: Path, txid: str, before: str) -> Path:
    header, *rows = path.read_text().splitlines()
    (row,) = [line for line in rows if line.startswith(f"{txid},")]
    rows.remove(row)
    rows.insert(next(at for at, line in enumerate(rows) if line.startswith(f"{before},")), row)
    path.write_text("\n".join([header, *rows]) + "\n")
    return path


def test_a_written_order_that_runs_an_asset_below_zero_is_refused(tmp_path):
    # The sell's EUR credit first and its ALGO debit after the buy, one second: each balance chains, and the sell,
    # written at its first row, spends ALGO the buy has not yet credited.
    at = "2031-03-03 10:00:00"
    edits = [
        ("LFX006-SYNTH-LEDGER", "time", at),
        ("LFX006-SYNTH-LEDGER", "balance", "1309.76"),
        ("LFX003-SYNTH-LEDGER", "balance", "1189.28"),
        ("LFX005-SYNTH-LEDGER", "time", at),
    ]
    ledger = _moved(_edited(tmp_path, LEDGER_1, edits), "LFX006-SYNTH-LEDGER", before="LFX003-SYNTH-LEDGER")
    before = sorted(tmp_path.iterdir())
    with pytest.raises(Refused) as caught:
        _run(tmp_path, ledger=ledger)
    assert [refusal.line() for refusal in caught.value.refusals] == [
        "refused TFX002-SYNTH-TRADES [order]: ALGO runs to -160 at this row in the written order"
    ]
    assert sorted(tmp_path.iterdir()) == before
```

- [ ] **Step 3: Run them and read the failure** — Expected: the 49 new cases fail with `AttributeError` on `transform` or `check_unique`.
- [ ] **Step 4: The checks and the run** — appended to `cli/tax/blockpit.py`:

```python
def check_chain(ledger: list[LedgerRow]) -> tuple[dict[str, Decimal], dict[str, Decimal], list[Refusal]]:
    opening: dict[str, Decimal] = {}
    closing: dict[str, Decimal] = {}
    refusals = []
    for row in ledger:
        moved = row.dec("amount") - row.dec("fee")
        if row.asset not in closing:
            opening[row.asset] = row.dec("balance") - moved
        elif closing[row.asset] + moved != row.dec("balance"):
            reason = (
                f"{row.asset} balance {row.balance} is not the previous {_plain(closing[row.asset])} + {row.amount} - {row.fee}"
            )
            refusals.append(Refusal((row.txid,), "balance", reason))
        closing[row.asset] = row.dec("balance")
    return opening, closing, refusals


def check_conservation(ledger: list[LedgerRow], rows: list[OutRow]) -> list[Refusal]:
    want: dict[str, Decimal] = defaultdict(Decimal)
    got: dict[str, Decimal] = defaultdict(Decimal)
    for row in ledger:
        want[row.asset] += row.dec("amount") - row.dec("fee")
    for row in rows:
        for asset, moved in _moves(row):
            got[asset] += moved
    return [
        Refusal((), "conservation", f"{asset} moves {_plain(got[asset])} in the output and {_plain(want[asset])} in the ledger")
        for asset in sorted(set(want) | set(got))
        if got[asset] != want[asset]
    ]


def check_order(opening: dict[str, Decimal], rows: list[OutRow]) -> list[Refusal]:
    held = dict(opening)
    refusals = []
    for row in _written(rows):
        moved: dict[str, Decimal] = defaultdict(Decimal)
        for asset, amount in _moves(row):
            moved[asset] += amount
        for asset, amount in moved.items():
            held[asset] = held.get(asset, Decimal(0)) + amount
            if held[asset] < 0:
                reason = f"{asset} runs to {_plain(held[asset])} at this row in the written order"
                refusals.append(Refusal((row.trx_id,), "order", reason))
    return refusals


def check_unique(rows: list[OutRow]) -> list[Refusal]:
    counts = Counter(row.trx_id for row in rows)
    return [
        Refusal((trx_id,), "trx-id", f"{count} output rows carry this Trx. ID")
        for trx_id, count in sorted(counts.items())
        if count > 1
    ]


def _label_sums(rows: list[OutRow]) -> dict:
    sums: dict = {}
    for row in rows:
        for asset, amount, column in (
            (row.in_asset, row.in_amount, "incoming"),
            (row.out_asset, row.out_amount, "outgoing"),
            (row.fee_asset, row.fee_amount, "fee"),
        ):
            if asset:
                entry = sums.setdefault(row.label, {}).setdefault(
                    asset, {"rows": 0, "incoming": Decimal(0), "outgoing": Decimal(0), "fee": Decimal(0)}
                )
                entry[column] += Decimal(amount)
        for asset in {row.in_asset, row.out_asset} - {""}:
            sums[row.label][asset]["rows"] += 1
    return {
        label: {
            asset: {key: value if key == "rows" else _plain(value) for key, value in entry.items()}
            for asset, entry in assets.items()
        }
        for label, assets in sums.items()
    }


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class Written:
    out: Path
    provenance: Path
    rows: int
    label_rows: dict[str, int]
    closing: dict[str, str]
    sha256: str
    provenance_sha256: str


def transform(ledgers: Path, trades: Path, out: Path) -> Written:
    provenance_path = out.with_name(out.name + ".provenance.json")
    for path in (out, provenance_path):
        if path.exists():
            raise TaxExportError(f"{path} exists, and a run never overwrites a file")
    ledger_bytes, trades_bytes = ledgers.read_bytes(), trades.read_bytes()
    ledger, trade_rows = read_ledger(ledgers, ledger_bytes), read_trades(trades, trades_bytes)
    mapped = map_rows(ledger, trade_rows)
    opening, closing, chain = check_chain(ledger)
    first_time = ledger[0].time if ledger else None
    refusals = [
        *mapped.refusals,
        *check_cross(ledger, trade_rows),
        *chain,
        *check_conservation(ledger, mapped.rows),
        *check_order(opening, mapped.rows),
        *check_unique(mapped.rows),
    ]
    if refusals:
        raise Refused(refusals)
    body = render_csv(mapped.rows)
    closing_all = {asset: _plain(value) for asset, value in sorted(closing.items())}
    last_time = ledger[-1].time if ledger else None
    record = {
        "inputs": {
            "ledgers": {
                "file": ledgers.name,
                "sha256": _sha256(ledger_bytes),
                "rows": len(ledger),
                "first_time": first_time,
                "last_time": last_time,
            },
            "trades": {"file": trades.name, "sha256": _sha256(trades_bytes), "rows": len(trade_rows)},
        },
        "output": {"file": out.name, "sha256": _sha256(body), "rows": len(mapped.rows)},
        "labels": _label_sums(mapped.rows),
        "opening": {asset: _plain(value) for asset, value in sorted(opening.items())},
        "closing": closing_all,
        "positions": {position: sorted(txids) for position, txids in sorted(mapped.positions.items())},
        "no_movement": mapped.no_movement,
        "previous": None,
        "zcrypto": version("zcrypto"),
    }
    provenance = (json.dumps(record, indent=2, sort_keys=True) + "\n").encode("utf-8")
    out.write_bytes(body)
    provenance_path.write_bytes(provenance)
    label_rows = dict(Counter(row.label for row in mapped.rows))
    return Written(out, provenance_path, len(mapped.rows), label_rows, closing_all, _sha256(body), _sha256(provenance))
```

- [ ] **Step 5: Run the tests** — Expected: `106 passed`.
- [ ] **Step 6: The consumers** — the tax consumers command, then the consumers' run; Expected: no failure.
- [ ] **Step 7: The commit gate**
- [ ] **Step 8: Commit**

```bash
git add cli/tax/blockpit.py tests/test_tax_blockpit.py tests/fixtures/tax_blockpit/window-1-blockpit.csv.provenance.json
git commit -F- <<'MSG'
feat(tax): a run writes the import file and its provenance, or refuses and writes nothing

Before anything is written the run checks each asset's balance chain in the export's row
order, that the output moves each asset exactly as the ledger does, that no asset's balance runs
below zero in the written order, and that no two rows carry one Trx. ID; a refusal raises with every reason and leaves the directory as it was, and an output or
provenance file that exists is never overwritten. The provenance carries the sha256 of both inputs
and of the output, the per-label sums, the opening and closing balances and each position's rows,
and no wall-clock time, so the same inputs give byte-identical files.

PROBE_VERDICT

Co-Authored-By: Claude <actual executing model> <noreply@anthropic.com>
MSG
```

- [ ] **Step 9: The tree is clean**
- [ ] **Step 10: Prove the guards, then record their verdicts** — sixteen probes; Expected: each KILLED; then the message-only amend.

```bash
infra/scripts/mutate-probe.sh --file cli/tax/blockpit.py --control '1,$d' \
  --mutation '/^        "positions": /d' \
  -- uv run pytest tests/test_tax_blockpit.py -k golden_rows_and_provenance -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file cli/tax/blockpit.py --control '1,$d' \
  --mutation 's/json.dumps(record, indent=2, sort_keys=True)/json.dumps(record, indent=2)/' \
  -- uv run pytest tests/test_tax_blockpit.py -k golden_rows_and_provenance -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file cli/tax/blockpit.py --control '1,$d' \
  --mutation 's/^        "no_movement": mapped.no_movement,$/        "no_movement": str(out.parent),/' \
  -- uv run pytest tests/test_tax_blockpit.py -k byte_equal -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file cli/tax/blockpit.py --control '1,$d' \
  --mutation 's|^        comment = f"kraken trade/tradespot {trade.pair}"$|        comment = f"kraken trade/tradespot {next(iter(trades))}"|' \
  -- uv run pytest tests/test_tax_blockpit.py -k trades_rows_reordered -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file cli/tax/blockpit.py --control '1,$d' \
  --mutation 's/"sha256": _sha256(body), "rows"/"sha256": _sha256(body[1:]), "rows"/' \
  -- uv run pytest tests/test_tax_blockpit.py -k hashes_are_the_files -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file cli/tax/blockpit.py --control '1,$d' \
  --mutation 's/^        elif closing\[row.asset\] + moved != row.dec("balance"):$/        elif False:/' \
  -- uv run pytest tests/test_tax_blockpit.py -k 'balance_edited or row_removed' -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file cli/tax/blockpit.py --control '1,$d' \
  --mutation 's/^        if got\[asset\] != want\[asset\]$/        if False/' \
  -- uv run pytest tests/test_tax_blockpit.py -k loses_a_movement -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file cli/tax/blockpit.py --control '1,$d' \
  --mutation '/^        \*check_order(opening, mapped.rows),$/d' \
  -- uv run pytest tests/test_tax_blockpit.py -k written_order_that_runs -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file cli/tax/blockpit.py --control '1,$d' \
  --mutation 's/^        if count > 1$/        if False/' \
  -- uv run pytest tests/test_tax_blockpit.py -k one_trx_id -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file cli/tax/blockpit.py --control '1,$d' \
  --mutation '/^        \*check_cross(ledger, trade_rows),$/d' \
  -- uv run pytest tests/test_tax_blockpit.py -k run_refuses_a_trades_row -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file cli/tax/blockpit.py --control '1,$d' \
  --mutation '/^        \*check_unique(mapped.rows),$/d' \
  -- uv run pytest tests/test_tax_blockpit.py -k run_refuses_two_rows -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file cli/tax/blockpit.py --control '1,$d' \
  --mutation 's/^        if path.exists():$/        if False:/' \
  -- uv run pytest tests/test_tax_blockpit.py -k never_overwritten -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file cli/tax/blockpit.py --control '1,$d' \
  --mutation 's/^    for path in (out, provenance_path):$/    for path in (provenance_path,):/' \
  -- uv run pytest tests/test_tax_blockpit.py -k never_overwritten -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file cli/tax/blockpit.py --control '1,$d' \
  --mutation 's/^            mapped.no_movement += 1$/            pass/' \
  -- uv run pytest tests/test_tax_blockpit.py -k moving_nothing -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file cli/tax/blockpit.py --control '1,$d' \
  --mutation 's/^    if refusals:$/    if False:/' \
  -- uv run pytest tests/test_tax_blockpit.py -k 'nothing_is_written or writes_nothing' -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file cli/tax/blockpit.py --control '1,$d' \
  --mutation 's/^    ledger_bytes, trades_bytes = ledgers.read_bytes(), trades.read_bytes()$/    out.write_bytes(b"")\n    ledger_bytes, trades_bytes = ledgers.read_bytes(), trades.read_bytes()/' \
  -- uv run pytest tests/test_tax_blockpit.py -k ledger_without_a_column -q -p no:cacheprovider
```

---

### Task 5: The `--after` chain — each window opens where the one before closed

**Files:**
- Modify: `cli/tax/blockpit.py` (`transform` replaced; `check_continuity` and `_previous` appended)
- Create: `tests/fixtures/tax_blockpit/window-2-blockpit.csv`, `window-2-blockpit.csv.provenance.json`
- Test: `tests/test_tax_blockpit.py` (`_run` replaced; `_empty_window` appended; eight tests, fifteen cases)

**Interfaces:**
- Consumes: Task 4's run and provenance.
- Produces: `transform(ledgers, trades, out, after=None)` — without `after` every asset opens at zero; with it, each opening equals the previous `closing` (an asset it never saw at zero), this ledger's first `time` is after its `inputs.ledgers.last_time`, the provenance's `closing` carries the previous closing of each asset this window does not move, and `previous` is the previous file's sha256; `check_continuity`.

**What this task decides, where the spec leaves it open:** an empty window keeps the previous `last_time`, so the next window chains past it — one test chains window one, an empty window and window two, another opens window one after an empty first window, and each drives one of `check_continuity`'s two `None` guards on the times; a file that is not a provenance this command wrote — not JSON, without `closing` or `inputs.ledgers.last_time`, with them of the wrong type, or with a `closing` value that is not a finite decimal string, the error then naming that value's asset — is a `TaxExportError`, each member of `_previous`'s caught errors (`ValueError`, `KeyError`, `TypeError`), of its type check (`closing`, `last_time`) and of its value check (a string, a finite value, and the `InvalidOperation` a string that is no decimal raises) a case it alone decides and a probe dropping it, a `null` value a fourth case the string member decides; each of the three continuity refusals' tests reads the directory's listing unchanged, and a probe that writes before the refusal fails each.

- [ ] **Step 1: Window two's golden pair** — `tests/fixtures/tax_blockpit/window-2-blockpit.csv`:

```csv
Date (UTC),Integration Name,Label,Outgoing Asset,Outgoing Amount,Incoming Asset,Incoming Amount,Fee Asset (optional),Fee Amount (optional),Comment (optional),Trx. ID (optional)
01.04.2031 10:00:00,Kraken manual import,Margin Fee,EUR,0.0035,,,,,kraken rollover position TFX012-SYNTH-TRADES,LFX101-SYNTH-LEDGER
02.04.2031 09:00:00,Kraken manual import,Margin Profit,,,EUR,2.25,,,kraken margin ALGO/EUR position TFX012-SYNTH-TRADES,LFX102-SYNTH-LEDGER
02.04.2031 09:00:00,Kraken manual import,Margin Fee,EUR,0.065,,,,,kraken margin ALGO/EUR position TFX012-SYNTH-TRADES,LFX102-SYNTH-LEDGER-fee
03.04.2031 12:00:00,Kraken manual import,Trade,ATOM,8.5,EUR,54.4,EUR,0.2176,kraken trade/tradespot ATOM/EUR,TFX014-SYNTH-TRADES
```

and `tests/fixtures/tax_blockpit/window-2-blockpit.csv.provenance.json`, one line:

```json
{"closing": {"ALGO": "160.245", "ATOM": "2.6025", "EUR": "1230.4772", "EURC": "0", "NEAR": "0", "XTZ": "0"}, "inputs": {"ledgers": {"file": "window-2-ledgers.csv", "first_time": "2031-04-01 10:00:00", "last_time": "2031-04-03 12:00:00", "rows": 4, "sha256": "ccc8609590662862c89896842e1aaba32f42fd956aa4a3b72e030c734e2a0b6d"}, "trades": {"file": "window-2-trades.csv", "rows": 2, "sha256": "b663b23967bb5b005fe9517742bddd23382fe5a0532553820a8244a0a0ab0500"}}, "labels": {"Margin Fee": {"EUR": {"fee": "0", "incoming": "0", "outgoing": "0.0685", "rows": 2}}, "Margin Profit": {"EUR": {"fee": "0", "incoming": "2.25", "outgoing": "0", "rows": 1}}, "Trade": {"ATOM": {"fee": "0", "incoming": "0", "outgoing": "8.5", "rows": 1}, "EUR": {"fee": "0.2176", "incoming": "54.4", "outgoing": "0", "rows": 1}}}, "no_movement": 0, "opening": {"ATOM": "11.1025", "EUR": "1174.1133"}, "output": {"file": "window-2-blockpit.csv", "rows": 4, "sha256": "3a8405af9f1a56ee89575f52261eab6ec9ac78619892457cce8cbfcdaf443a52"}, "positions": {"TFX012-SYNTH-TRADES": ["LFX101-SYNTH-LEDGER", "LFX102-SYNTH-LEDGER"]}}
```

- [ ] **Step 2: Write the failing tests** — `_run` replaced by its final form, and the chain's cases appended:

```python
def _run(
    tmp_path: Path, ledger: Path = LEDGER_1, trades: Path = TRADES_1, after: Path | None = None, name: str = "window-1-blockpit.csv"
):
    return blockpit.transform(ledger, trades, tmp_path / name, after)


def test_window_two_after_window_one_maps_to_its_golden(tmp_path):
    first = _run(tmp_path)
    second = _run(tmp_path, LEDGER_2, TRADES_2, after=first.provenance, name="window-2-blockpit.csv")
    assert second.out.read_bytes() == (FIXTURES / "window-2-blockpit.csv").read_bytes()
    assert _provenance(second.provenance) == json.loads((FIXTURES / "window-2-blockpit.csv.provenance.json").read_text())
    assert json.loads(second.provenance.read_text())["previous"] == hashlib.sha256(first.provenance.read_bytes()).hexdigest()


def test_window_two_without_after_is_refused(tmp_path):
    before = sorted(tmp_path.iterdir())
    with pytest.raises(Refused) as caught:
        _run(tmp_path, LEDGER_2, TRADES_2, name="window-2-blockpit.csv")
    assert {refusal.reason for refusal in caught.value.refusals} == {
        "ATOM opens at 11.1025 and no --after names the window before",
        "EUR opens at 1174.1133 and no --after names the window before",
    }
    assert sorted(tmp_path.iterdir()) == before


def test_an_opening_unequal_to_the_previous_closing_is_refused(tmp_path):
    first = _run(tmp_path)
    record = json.loads(first.provenance.read_text())
    record["closing"]["EUR"] = "1174.1130"
    edited = tmp_path / "edited.provenance.json"
    edited.write_text(json.dumps(record))
    before = sorted(tmp_path.iterdir())
    with pytest.raises(Refused) as caught:
        _run(tmp_path, LEDGER_2, TRADES_2, after=edited, name="window-2-blockpit.csv")
    assert [refusal.reason for refusal in caught.value.refusals] == [
        "EUR opens at 1174.1133 where the window before closed at 1174.113"
    ]
    assert sorted(tmp_path.iterdir()) == before


def test_a_previous_window_that_does_not_end_before_this_one_is_refused(tmp_path):
    first = _run(tmp_path)
    record = json.loads(first.provenance.read_text())
    record["inputs"]["ledgers"]["last_time"] = "2031-04-01 10:00:00"
    edited = tmp_path / "edited.provenance.json"
    edited.write_text(json.dumps(record))
    before = sorted(tmp_path.iterdir())
    with pytest.raises(Refused) as caught:
        _run(tmp_path, LEDGER_2, TRADES_2, after=edited, name="window-2-blockpit.csv")
    assert [refusal.reason for refusal in caught.value.refusals] == [
        "this ledger's first time 2031-04-01 10:00:00 is not after the window before's last, 2031-04-01 10:00:00"
    ]
    assert sorted(tmp_path.iterdir()) == before


def _empty_window(tmp_path: Path) -> tuple[Path, Path]:
    (tmp_path / "empty").mkdir()
    ledger, trades = tmp_path / "empty" / LEDGER_1.name, tmp_path / "empty" / TRADES_1.name
    ledger.write_text(LEDGER_1.read_text().splitlines()[0] + "\n")
    trades.write_text(TRADES_1.read_text().splitlines()[0] + "\n")
    return ledger, trades


def test_an_empty_window_carries_the_chain_to_the_next(tmp_path):
    first = _run(tmp_path)
    empty = _run(tmp_path, *_empty_window(tmp_path), after=first.provenance, name="empty.csv")
    assert json.loads(empty.provenance.read_text())["inputs"]["ledgers"]["last_time"] == "2031-03-28 22:00:00"
    second = _run(tmp_path, LEDGER_2, TRADES_2, after=empty.provenance, name="window-2-blockpit.csv")
    assert second.out.read_bytes() == (FIXTURES / "window-2-blockpit.csv").read_bytes()


def test_a_window_after_an_empty_first_window_opens_from_zero(tmp_path):
    empty = _run(tmp_path, *_empty_window(tmp_path), name="empty.csv")
    assert json.loads(empty.provenance.read_text())["inputs"]["ledgers"]["last_time"] is None
    first = _run(tmp_path, after=empty.provenance)
    assert first.out.read_bytes() == (FIXTURES / "window-1-blockpit.csv").read_bytes()


@pytest.mark.parametrize(
    "text",
    [
        "",
        "{}",
        '{"closing": {}, "inputs": []}',
        '{"closing": [], "inputs": {"ledgers": {"last_time": null}}}',
        '{"closing": {}, "inputs": {"ledgers": {"last_time": 5}}}',
    ],
    ids=["empty", "no_keys", "inputs_not_a_map", "closing_not_a_map", "last_time_not_a_string"],
)
def test_a_file_that_is_no_provenance_is_refused_as_after(tmp_path, text):
    after = tmp_path / "after.json"
    after.write_text(text)
    with pytest.raises(TaxExportError, match="not a provenance file"):
        _run(tmp_path, LEDGER_2, TRADES_2, after=after, name="window-2-blockpit.csv")


@pytest.mark.parametrize(
    "value",
    [None, 11.1025, "NaN", "abc"],
    ids=["closing_value_null", "closing_value_a_number", "closing_value_not_finite", "closing_value_not_a_decimal"],
)
def test_a_previous_closing_that_is_no_decimal_string_is_refused_by_its_asset(tmp_path, value):
    after = tmp_path / "after.json"
    after.write_text(json.dumps({"closing": {"ATOM": value, "EUR": "1174.1133"}, "inputs": {"ledgers": {"last_time": None}}}))
    with pytest.raises(TaxExportError, match="its closing ATOM is not a decimal string"):
        _run(tmp_path, LEDGER_2, TRADES_2, after=after, name="window-2-blockpit.csv")
```

- [ ] **Step 3: Run them and read the failure** — Expected: every run case fails with `TypeError: transform() takes 3 positional arguments but 4 were given`.
- [ ] **Step 4: The chain** — `transform` replaced by this form, and the two functions appended:

```python
def transform(ledgers: Path, trades: Path, out: Path, after: Path | None = None) -> Written:
    provenance_path = out.with_name(out.name + ".provenance.json")
    for path in (out, provenance_path):
        if path.exists():
            raise TaxExportError(f"{path} exists, and a run never overwrites a file")
    ledger_bytes, trades_bytes = ledgers.read_bytes(), trades.read_bytes()
    ledger, trade_rows = read_ledger(ledgers, ledger_bytes), read_trades(trades, trades_bytes)
    previous_bytes = after.read_bytes() if after else None
    previous = _previous(after, previous_bytes) if after else None
    mapped = map_rows(ledger, trade_rows)
    opening, closing, chain = check_chain(ledger)
    first_time = ledger[0].time if ledger else None
    refusals = [
        *mapped.refusals,
        *check_cross(ledger, trade_rows),
        *chain,
        *check_conservation(ledger, mapped.rows),
        *check_order(opening, mapped.rows),
        *check_unique(mapped.rows),
        *check_continuity(opening, first_time, previous),
    ]
    if refusals:
        raise Refused(refusals)
    body = render_csv(mapped.rows)
    carried = {asset: Decimal(value) for asset, value in previous["closing"].items()} if previous else {}
    closing_all = {asset: _plain(value) for asset, value in sorted({**carried, **closing}.items())}
    last_time = ledger[-1].time if ledger else (previous["inputs"]["ledgers"]["last_time"] if previous else None)
    record = {
        "inputs": {
            "ledgers": {
                "file": ledgers.name,
                "sha256": _sha256(ledger_bytes),
                "rows": len(ledger),
                "first_time": first_time,
                "last_time": last_time,
            },
            "trades": {"file": trades.name, "sha256": _sha256(trades_bytes), "rows": len(trade_rows)},
        },
        "output": {"file": out.name, "sha256": _sha256(body), "rows": len(mapped.rows)},
        "labels": _label_sums(mapped.rows),
        "opening": {asset: _plain(value) for asset, value in sorted(opening.items())},
        "closing": closing_all,
        "positions": {position: sorted(txids) for position, txids in sorted(mapped.positions.items())},
        "no_movement": mapped.no_movement,
        "previous": _sha256(previous_bytes) if previous_bytes else None,
        "zcrypto": version("zcrypto"),
    }
    provenance = (json.dumps(record, indent=2, sort_keys=True) + "\n").encode("utf-8")
    out.write_bytes(body)
    provenance_path.write_bytes(provenance)
    label_rows = dict(Counter(row.label for row in mapped.rows))
    return Written(out, provenance_path, len(mapped.rows), label_rows, closing_all, _sha256(body), _sha256(provenance))


def check_continuity(opening: dict[str, Decimal], first_time: str | None, previous: dict | None) -> list[Refusal]:
    if previous is None:
        return [
            Refusal((), "continuity", f"{asset} opens at {_plain(value)} and no --after names the window before")
            for asset, value in sorted(opening.items())
            if value != 0
        ]
    closed = {asset: Decimal(value) for asset, value in previous["closing"].items()}
    refusals = [
        Refusal(
            (),
            "continuity",
            f"{asset} opens at {_plain(value)} where the window before closed at {_plain(closed.get(asset, Decimal(0)))}",
        )
        for asset, value in sorted(opening.items())
        if value != closed.get(asset, Decimal(0))
    ]
    last = previous["inputs"]["ledgers"]["last_time"]
    if first_time is not None and last is not None and first_time <= last:
        refusals.append(
            Refusal((), "continuity", f"this ledger's first time {first_time} is not after the window before's last, {last}")
        )
    return refusals


def _previous(after: Path, data: bytes) -> dict:
    try:
        previous = json.loads(data)
        closing, last_time = previous["closing"], previous["inputs"]["ledgers"]["last_time"]
    except (ValueError, KeyError, TypeError) as exc:
        raise TaxExportError(f"{after} is not a provenance file this command wrote") from exc
    if not isinstance(closing, dict) or not (last_time is None or isinstance(last_time, str)):
        raise TaxExportError(f"{after} is not a provenance file this command wrote")
    for asset, value in sorted(closing.items()):
        try:
            is_decimal = isinstance(value, str) and Decimal(value).is_finite()
        except InvalidOperation:
            is_decimal = False
        if not is_decimal:
            raise TaxExportError(
                f"{after} is not a provenance file this command wrote: its closing {asset} is not a decimal string"
            )
    return previous
```

- [ ] **Step 5: Run the tests** — Expected: `121 passed`.
- [ ] **Step 6: The consumers** — the tax consumers command, then the consumers' run; Expected: no failure.
- [ ] **Step 7: The commit gate**
- [ ] **Step 8: Commit**

```bash
git add cli/tax/blockpit.py tests/test_tax_blockpit.py tests/fixtures/tax_blockpit/window-2-blockpit.csv tests/fixtures/tax_blockpit/window-2-blockpit.csv.provenance.json
git commit -F- <<'MSG'
feat(tax): each window chains to the one before through --after, and the first opens at zero

A window run with --after refuses an asset whose opening balance is not the previous window's
closing one, and a ledger that does not start after the previous window's last row; without --after
every asset must open at zero, as a whole-history window does. A month skipped or exported twice
stops here rather than reaching Blockpit. The provenance carries the previous file's sha256 and the
closing balance of every asset seen so far. An --after file this command did not write is refused,
down to a closing balance that is not a decimal string.

PROBE_VERDICT

Co-Authored-By: Claude <actual executing model> <noreply@anthropic.com>
MSG
```

- [ ] **Step 9: The tree is clean**
- [ ] **Step 10: Prove the guards, then record their verdicts** — nineteen probes; Expected: each KILLED; then the message-only amend.

```bash
infra/scripts/mutate-probe.sh --file cli/tax/blockpit.py --control '1,$d' \
  --mutation 's/^            if value != 0$/            if False/' \
  -- uv run pytest tests/test_tax_blockpit.py -k without_after -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file cli/tax/blockpit.py --control '1,$d' \
  --mutation 's/^        if value != closed.get(asset, Decimal(0))$/        if False/' \
  -- uv run pytest tests/test_tax_blockpit.py -k opening_unequal -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file cli/tax/blockpit.py --control '1,$d' \
  --mutation 's/^    if first_time is not None and last is not None and first_time <= last:$/    if False:/' \
  -- uv run pytest tests/test_tax_blockpit.py -k does_not_end_before -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file cli/tax/blockpit.py --control '1,$d' \
  --mutation 's/^    if first_time is not None and last is not None and first_time <= last:$/    if last is not None and first_time <= last:/' \
  -- uv run pytest tests/test_tax_blockpit.py -k carries_the_chain -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file cli/tax/blockpit.py --control '1,$d' \
  --mutation 's/^    if first_time is not None and last is not None and first_time <= last:$/    if first_time is not None and first_time <= last:/' \
  -- uv run pytest tests/test_tax_blockpit.py -k after_an_empty_first_window -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file cli/tax/blockpit.py --control '1,$d' \
  --mutation 's/^    last_time = ledger\[-1\].time if ledger else (previous\["inputs"\]\["ledgers"\]\["last_time"\] if previous else None)$/    last_time = ledger[-1].time if ledger else None/' \
  -- uv run pytest tests/test_tax_blockpit.py -k carries_the_chain -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file cli/tax/blockpit.py --control '1,$d' \
  --mutation 's/^    except (ValueError, KeyError, TypeError) as exc:$/    except ValueError as exc:/' \
  -- uv run pytest tests/test_tax_blockpit.py -k no_keys -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file cli/tax/blockpit.py --control '1,$d' \
  --mutation 's/^    except (ValueError, KeyError, TypeError) as exc:$/    except (KeyError, TypeError) as exc:/' \
  -- uv run pytest tests/test_tax_blockpit.py -k 'no_provenance and empty' -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file cli/tax/blockpit.py --control '1,$d' \
  --mutation 's/^    except (ValueError, KeyError, TypeError) as exc:$/    except (ValueError, KeyError) as exc:/' \
  -- uv run pytest tests/test_tax_blockpit.py -k inputs_not_a_map -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file cli/tax/blockpit.py --control '1,$d' \
  --mutation 's/^    if not isinstance(closing, dict) or not (last_time is None or isinstance(last_time, str)):$/    if False:/' \
  -- uv run pytest tests/test_tax_blockpit.py -k closing_not_a_map -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file cli/tax/blockpit.py --control '1,$d' \
  --mutation 's/^    if not isinstance(closing, dict) or not (last_time is None or isinstance(last_time, str)):$/    if not isinstance(closing, dict):/' \
  -- uv run pytest tests/test_tax_blockpit.py -k last_time_not_a_string -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file cli/tax/blockpit.py --control '1,$d' \
  --mutation 's/^            is_decimal = isinstance(value, str) and Decimal(value).is_finite()$/            is_decimal = Decimal(value).is_finite()/' \
  -- uv run pytest tests/test_tax_blockpit.py -k closing_value_a_number -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file cli/tax/blockpit.py --control '1,$d' \
  --mutation 's/ and Decimal(value).is_finite()$/ and Decimal(value) is not None/' \
  -- uv run pytest tests/test_tax_blockpit.py -k closing_value_not_finite -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file cli/tax/blockpit.py --control '1,$d' \
  --mutation 's/^        except InvalidOperation:$/        except ZeroDivisionError:/' \
  -- uv run pytest tests/test_tax_blockpit.py -k closing_value_not_a_decimal -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file cli/tax/blockpit.py --control '1,$d' \
  --mutation 's/^        "previous": _sha256(previous_bytes) if previous_bytes else None,$/        "previous": None,/' \
  -- uv run pytest tests/test_tax_blockpit.py -k window_two_after -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file cli/tax/blockpit.py --control '1,$d' \
  --mutation 's/^    carried = .*$/    carried = {}/' \
  -- uv run pytest tests/test_tax_blockpit.py -k window_two_after -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file cli/tax/blockpit.py --control '1,$d' \
  --mutation 's/^    if refusals:$/    out.write_bytes(b"")\n    if refusals:/' \
  -- uv run pytest tests/test_tax_blockpit.py -k window_two_without_after -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file cli/tax/blockpit.py --control '1,$d' \
  --mutation 's/^    if refusals:$/    out.write_bytes(b"")\n    if refusals:/' \
  -- uv run pytest tests/test_tax_blockpit.py -k opening_unequal -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file cli/tax/blockpit.py --control '1,$d' \
  --mutation 's/^    if refusals:$/    out.write_bytes(b"")\n    if refusals:/' \
  -- uv run pytest tests/test_tax_blockpit.py -k does_not_end_before -q -p no:cacheprovider
```

---

### Task 6: `zcrypto tax blockpit` and its README section

**Files:**
- Create: `cli/tax/command.py`
- Modify: `cli/__main__.py` (after `:17`, `from cli.snapshot.command import snapshot_app`, the import `from cli.tax.command import tax_app`; after `:32`, `app.add_typer(snapshot_app, name="snapshot")`, the line `app.add_typer(tax_app, name="tax")`)
- Modify: `README.md` (a `### zcrypto tax` section after `### zcrypto snapshot`'s last paragraph, `:402`, before `## Configuration`, `:404`)
- Test: `tests/test_tax_blockpit.py`

**Interfaces:**
- Consumes: Task 5's `transform`, `Refused`, `TaxExportError`.
- Produces: `zcrypto tax blockpit --ledgers <PATH> --trades <PATH> --out <PATH> [--after <PATH>]` — exit 0 printing the rows, the two hashes, the rows per label and the closing balances; exit 1 printing each refusal, or logging an unreadable input; exit 2 on a usage error — the command Task 8's page and the Rollout run; a test holding `cli/tax/`'s imports to an allowlist, the spec's invariant that the transform reaches nothing.

- [ ] **Step 1: Write the failing tests**

```python
RUNNER = CliRunner()


def test_the_command_writes_both_files_and_exits_0(tmp_path):
    out = tmp_path / "window-1-blockpit.csv"
    result = RUNNER.invoke(app, ["tax", "blockpit", "--ledgers", str(LEDGER_1), "--trades", str(TRADES_1), "--out", str(out)])
    assert result.exit_code == 0, result.output
    assert out.read_bytes() == (FIXTURES / "window-1-blockpit.csv").read_bytes()
    assert f"wrote 26 rows to {out}" in result.output
    assert "  Trade: 9 rows\n" in result.output
    assert "closing balances: ALGO 160.245, ATOM 11.1025, EUR 1174.1133, EURC 0, NEAR 0, XTZ 0" in result.output


def test_the_command_prints_each_refusal_and_exits_1(tmp_path):
    ledger = _edited(tmp_path, LEDGER_1, [("LFX027-SYNTH-LEDGER", "subtype", "allocation")])
    result = RUNNER.invoke(
        app, ["tax", "blockpit", "--ledgers", str(ledger), "--trades", str(TRADES_1), "--out", str(tmp_path / "o.csv")]
    )
    assert result.exit_code == 1
    assert "refused LFX027-SYNTH-LEDGER [earn/allocation]: no mapping is written for this type and subtype" in result.output
    assert not (tmp_path / "o.csv").exists()


def test_the_command_refuses_an_unreadable_input_with_exit_1(tmp_path):
    result = RUNNER.invoke(
        app,
        ["tax", "blockpit", "--ledgers", str(tmp_path / "absent.csv"), "--trades", str(TRADES_1), "--out", str(tmp_path / "o.csv")],
    )
    assert result.exit_code == 1
    assert not (tmp_path / "o.csv").exists()


def test_the_command_refuses_an_existing_output_with_exit_1(tmp_path):
    out = tmp_path / "o.csv"
    out.write_text("{}")
    result = RUNNER.invoke(app, ["tax", "blockpit", "--ledgers", str(LEDGER_1), "--trades", str(TRADES_1), "--out", str(out)])
    assert result.exit_code == 1 and isinstance(result.exception, SystemExit)
    assert out.read_text() == "{}"


def test_the_command_refuses_a_usage_error_with_exit_2():
    result = RUNNER.invoke(app, ["tax", "blockpit", "--ledgers", str(LEDGER_1), "--trades", str(TRADES_1)])
    assert result.exit_code == 2
    assert "Missing option" in result.output


def test_the_transform_imports_nothing_outside_its_allowlist():
    allowed = {
        "__future__",
        "csv",
        "collections",
        "dataclasses",
        "datetime",
        "decimal",
        "hashlib",
        "importlib.metadata",
        "io",
        "json",
        "pathlib",
        "typing",
        "typer",
        "cli.logging",
    }
    paths = sorted((Path(__file__).resolve().parents[1] / "cli" / "tax").glob("*.py"))
    assert paths
    for path in paths:
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            for name in names:
                assert name in allowed or name.startswith("cli.tax."), (path.name, name)


def test_the_readme_names_the_tax_command_and_each_of_its_options():
    section = (Path(__file__).resolve().parents[1] / "README.md").read_text().split("### `zcrypto tax`", 1)[1].split("\n## ", 1)[0]
    assert "zcrypto tax blockpit --ledgers <PATH> --trades <PATH> --out <PATH> [--after <PATH>]" in section
    for option in ("--ledgers", "--trades", "--out", "--after"):
        assert f"| `{option} <PATH>` |" in section, option
```

- [ ] **Step 2: Run them and read the failure** — Expected: the four command cases that expect exit 0 or 1 exit 2 on `No such command 'tax'`, the usage case fails on `Missing option`, the README case fails on its `split`, and the imports case passes, the three modules already within its allowlist.
- [ ] **Step 3: The command, its registration and its section** — `cli/tax/command.py`:

```python
"""The `zcrypto tax` Typer sub-app: wiring and exit codes only."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from cli.logging import get_logger
from cli.tax.blockpit import transform
from cli.tax.errors import Refused, TaxExportError

logger = get_logger("tax.command")

tax_app = typer.Typer(
    no_args_is_help=True,
    help="Tax bookkeeping: Kraken's ledger and trades exports turned into the tax tool's import file.",
)


@tax_app.command()
def blockpit(
    ledgers: Path = typer.Option(..., "--ledgers", help="Kraken's ledger CSV export for the window."),
    trades: Path = typer.Option(..., "--trades", help="Kraken's trades CSV export for the same window."),
    out: Path = typer.Option(
        ..., "--out", help="The import file to write; its provenance is written beside it as <out>.provenance.json."
    ),
    after: Optional[Path] = typer.Option(
        None,
        "--after",
        help="The window before's provenance file. Required on every window but the first, whose opening balances must all be zero.",
    ),
) -> None:
    """Map one window of Kraken's ledger and trades exports onto Blockpit's manual-import rows, the provenance beside them.

    A row it cannot map, a balance that does not chain, or a window that does not follow the one before refuses the run:
    every refusal is printed and nothing is written. Neither output file may exist beforehand.
    """
    try:
        written = transform(ledgers, trades, out, after)
    except Refused as exc:
        for refusal in exc.refusals:
            typer.echo(refusal.line())
        raise typer.Exit(code=1) from exc
    except (TaxExportError, OSError) as exc:
        logger.error(str(exc))
        raise typer.Exit(code=1) from exc
    typer.echo(f"wrote {written.rows} rows to {written.out} (sha256 {written.sha256})")
    typer.echo(f"provenance {written.provenance} (sha256 {written.provenance_sha256})")
    for label, count in sorted(written.label_rows.items()):
        typer.echo(f"  {label}: {count} rows")
    typer.echo("closing balances: " + ", ".join(f"{asset} {value}" for asset, value in written.closing.items()))
```

the two `cli/__main__.py` lines the Files name, and the README section — the commit gate's `mdformat-toc` then adds `  - [`zcrypto tax`](#zcrypto-tax)` to the README's contents after the `zcrypto snapshot` line, a rewrite staged with the rest:

````markdown
### `zcrypto tax`<a name="zcrypto-tax"></a>

Tax bookkeeping: one window of Kraken's ledger and trades CSV exports mapped onto Blockpit's manual-import rows, with a provenance file beside them.

```bash
zcrypto tax blockpit --ledgers <PATH> --trades <PATH> --out <PATH> [--after <PATH>]
```

| Option | Description |
| -- | -- |
| `--ledgers <PATH>` | Kraken's ledger CSV export for the window, read by header name. |
| `--trades <PATH>` | Kraken's trades CSV export for the same window: a one-leg trade's pair, the position a margin row belongs to, and the cross-check that both files describe the same activity. |
| `--out <PATH>` | The import file to write, in the template's columns; its provenance is written beside it as `<PATH>.provenance.json`. Neither file may exist beforehand. |
| `--after <PATH>` | The window before's provenance file: this window's opening balances must equal its closing ones, and this ledger must start after it. Absent, every opening balance must be zero — the first window. |

Each label written is one of the template's own. A row it cannot map, a balance that does not chain, a movement the output does not carry, or a window that does not follow the one before refuses the run: each refusal is printed, nothing is written, and the exit is `1`. Exit `0` prints the rows per label and the closing balances; a usage error, such as an option missing, exits `2`. The provenance carries the sha256 of both inputs and of the output, the per-label sums, the opening and closing balances, each margin position's ledger rows and the previous window's provenance hash; the same inputs give byte-identical files. Read-only on its inputs, offline, and holding no key.
````

- [ ] **Step 4: Run the tests** — Expected: `128 passed`.
- [ ] **Step 5: The consumers**

```bash
uv run pytest tests/test_tax_blockpit.py tests/test_internal_terms_not_operator_visible.py tests/test_code_prose_citations.py tests/test_live_venue_opt_in.py tests/test_guidance_refs_resolve.py tests/test_cli_help_hygiene.py tests/test_engine_command.py tests/test_error_paths_are_logged.py -q -p no:cacheprovider
```

Expected: no failure; `tests/test_cli_help_hygiene.py` walks every subcommand's help, the new one's among them. Then the consumers' run (Global Constraints).

- [ ] **Step 6: The smoke run over the owner's export** — outside the tree, its output under `.tmp/` and deleted at the step's end, no value of it copied anywhere:

```bash
S=/home/zhaow/Projects/zcrypto-kraken/.claude/worktrees/t0215-blockpit/.tmp/spec-00126
mkdir -p "$S/smoke"
uv run zcrypto tax blockpit --ledgers "$S/ledgers-full/kraken-spot-ledgers-2026-07-01-2026-10-09.csv" --trades "$S/trades-full/kraken-spot-trades-2026-07-01-2026-10-09.csv" --out "$S/smoke/blockpit.csv" > "$S/smoke/stdout.txt"; echo "rc $?"
echo "refusals $(grep -c '^refused ' "$S/smoke/stdout.txt")"
sed -n 's/^refused [^ ]* \[\([^]]*\)\]:.*/\1/p' "$S/smoke/stdout.txt" | sort | uniq -c
sed -n 's/^wrote \([0-9]*\) rows to .*/rows \1/p' "$S/smoke/stdout.txt"
rm -r "$S/smoke"
```

Expected: `rc 0`, `refusals 0` and `rows 72`, the count spec 00126's measured basis gives. The step prints counts and never a line of the run's output, since a refusal's line carries the owner's ledger ids: a refusal reads `rc 1`, its count, and each refusal kind with its count. A refusal here is a shape of the owner's export the fixture lacks, and stops the plan for a fixture row and a test of its own before Task 7.

- [ ] **Step 7: The commit gate**
- [ ] **Step 8: Commit**

```bash
git add cli/tax/command.py cli/__main__.py README.md tests/test_tax_blockpit.py
git commit -F- <<'MSG'
feat(tax): zcrypto tax blockpit maps one window of Kraken's exports onto Blockpit's import file

The command wires the transform to its exit codes: 0 with the rows written, both hashes, the rows
per label and the closing balances; 1 with each refusal printed and nothing written, or an unreadable
input logged; 2 on a usage error. README.md's new section names its four options and the refusal rule.
It reads two local files and writes two, holds no key and reaches nothing; a test holds the package's
imports to an allowlist with no network module in it.

PROBE_VERDICT

Co-Authored-By: Claude <actual executing model> <noreply@anthropic.com>
MSG
```

- [ ] **Step 9: The tree is clean**
- [ ] **Step 10: Prove the guards, then record their verdicts** — nine probes, the last on the test's own walk; Expected: each KILLED; then the message-only amend.

```bash
infra/scripts/mutate-probe.sh --file cli/tax/command.py --control '1,$d' \
  --mutation 's/^            typer.echo(refusal.line())$/            pass/' \
  -- uv run pytest tests/test_tax_blockpit.py -k prints_each_refusal -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file cli/tax/command.py --control '1,$d' \
  --mutation '/^    except Refused as exc:$/,/raise typer.Exit/s/code=1/code=0/' \
  -- uv run pytest tests/test_tax_blockpit.py -k prints_each_refusal -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file cli/tax/command.py --control '1,$d' \
  --mutation '/^    except (TaxExportError, OSError) as exc:$/,/raise typer.Exit/s/code=1/code=0/' \
  -- uv run pytest tests/test_tax_blockpit.py -k unreadable_input -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file cli/tax/command.py --control '1,$d' \
  --mutation 's/^    except (TaxExportError, OSError) as exc:$/    except OSError as exc:/' \
  -- uv run pytest tests/test_tax_blockpit.py -k existing_output_with_exit_1 -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file cli/tax/command.py --control '1,$d' \
  --mutation 's/^        typer.echo(f"  {label}: {count} rows")$/        typer.echo(f"  {label}: {count + 1} rows")/' \
  -- uv run pytest tests/test_tax_blockpit.py -k writes_both_files -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file cli/tax/command.py --control '1,$d' \
  --mutation 's/^        \.\.\., "--out", help=/        None, "--out", help=/' \
  -- uv run pytest tests/test_tax_blockpit.py -k usage_error -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file cli/tax/kraken_export.py --control '1,$d' \
  --mutation 's/^import csv$/import csv\nimport urllib.request/' \
  -- uv run pytest tests/test_tax_blockpit.py -k imports_nothing -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file tests/test_tax_blockpit.py --control '1,$d' \
  --mutation 's/\.glob("\*\.py"))$/.glob("*.absent"))/' \
  -- uv run pytest tests/test_tax_blockpit.py -k imports_nothing -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file README.md --control '1,$d' \
  --mutation '/^| `--after <PATH>` |/d' \
  -- uv run pytest tests/test_tax_blockpit.py -k readme_names -q -p no:cacheprovider
```

---

### Task 7: The tracking report reads the export's spelling of a reward, `earn`

**Files:**
- Modify: `cli/engine/tracking.py` (`:436`, the last line of the comment above the allowlist, with a constant after the allowlist, `:437`; `reconcile_ledger`'s no-fill branch, `:515`)
- Modify: `README.md` (`:121`, the `tracking-report` row's sentence on the no-fill types)
- Modify: `infra/runbooks/engine-procedures.md` (`:379`, the sentence on the conversion rows' spelling; `:584` and `:761`, rung 2's and rung 3's weekly reads of the no-fill line; `:611`, the box's exit tally)
- Test: `tests/test_engine_tracking.py` (one case before `test_a_transfer_row_is_a_known_no_fill_type`, `:882`)

**Interfaces:**
- Consumes: spec 00126 D10 and its measured basis — the CSV export writes Auto Earn's credit as `earn` with subtype `reward`, which the API writes `staking`.
- Produces: `_EARN_REWARD`, an `earn` row under subtype `reward` counted as `earn` on the `rows with no fill behind them by construction:` line, and an `earn` row under another subtype left on the `row types this reader places nowhere:` line.

- [ ] **Step 1: Write the failing test**

```python
def test_an_earn_reward_row_is_a_known_no_fill_type_and_another_earn_subtype_is_not(tmp_path):
    reward = _real_row("L1", "EX-1", "2031-03-25 14:00:00", "earn", "reward", "NEAR", "0.0000035", "0.00000105", "NEAR")
    allocation = _real_row("L2", "EX-2", "2031-03-25 14:00:00", "earn", "allocation", "NEAR", "0.0000035", "0", "")
    out = reconcile_ledger(read_ledger_export(_export(tmp_path, [reward, allocation], header=_REAL_HEADER)), [])
    assert (out["known"], out["ignored"], out["unmatched"]) == ({"earn": 1}, {"earn": 1}, [])
    assert out["status"] == "insufficient-data"
```

- [ ] **Step 2: Run it and read the failure** — `uv run pytest tests/test_engine_tracking.py -k earn_reward_row -q -p no:cacheprovider`; Expected: it fails, `out["ignored"]` reading `{'earn': 2}`.
- [ ] **Step 3: The match, the comment and the two texts** — in `cli/engine/tracking.py`, the comment's last line and the allowlist below it become these five lines, the allowlist itself unchanged and a constant after it:

```python
# opening trade; `staking` is a reward the venue credits on a spot holding, in the API's spelling.
_NO_FILL_LEDGER_TYPES = frozenset({"deposit", "withdrawal", "transfer", "settled", "collateralconversion", "staking"})
# The same reward in the CSV export's spelling, type `earn` under subtype `reward`; an `earn` row under another subtype
# lands on the places-nowhere line, a type to decide.
_EARN_REWARD = ("earn", "reward")
```

and in `reconcile_ledger` the line `elif row.type in _NO_FILL_LEDGER_TYPES:` becomes `elif row.type in _NO_FILL_LEDGER_TYPES or (row.type, row.subtype) == _EARN_REWARD:`, the small-balance conversion's rows being matched on their subtype the same way. In `README.md:121`, the clause `` `settled`, `collateralconversion` and `staking` rows have no fill behind them `` becomes `` `settled`, `collateralconversion` and `staking` rows, and `earn` rows of subtype `reward`, have no fill behind them — `staking` and `earn`/`reward` one reward credit, the API's spelling and the CSV export's — ``. In `infra/runbooks/engine-procedures.md:379`, the sentence beginning `Those conversion rows were read through` and ending `a decision to record here.` becomes: `The CSV export spells the conversion rows as `` `kraken ledgers -o json` `` does and a reward credit `` `earn` `` with subtype `` `reward` ``, where the API writes `` `staking` ``, and the reader counts both spellings; a type the reader has not met, or an `` `earn` `` row under another subtype, lands on the `` `row types this reader places nowhere:` `` line, and a type appearing there is a decision to record here.` — the old sentence's `never` goes with it. In `:584` and `:761`, each of the two occurrences of `` the week's reward credits as `staking <n>` `` becomes `` the week's reward credits as `earn <n>` ``, the token the line prints for the CSV export. In `:611`, `` the ledger export's `staking` credits `` becomes `` the ledger export's `earn` reward credits ``.

- [ ] **Step 4: Run the test** — Step 2's command; Expected: `1 passed`.
- [ ] **Step 5: The consumers**

```bash
uv run pytest tests/test_engine_tracking.py tests/test_engine_command.py tests/test_engine_draftplan.py tests/test_internal_terms_not_operator_visible.py tests/test_runbook_internal_tokens.py tests/test_runbook_triggers.py tests/test_guidance_guard.py tests/test_guidance_refs_resolve.py tests/test_code_prose_citations.py tests/test_ops_daily.py -q -p no:cacheprovider
uv run python infra/scripts/guidance-guard.py --uncounted infra/runbooks/engine-procedures.md
```

Expected: no failure, and the guard prints nothing. Then the consumers' run (Global Constraints).

- [ ] **Step 6: The commit gate**
- [ ] **Step 7: Commit**

```bash
git add cli/engine/tracking.py tests/test_engine_tracking.py README.md infra/runbooks/engine-procedures.md
git commit -F- <<'MSG'
fix(engine): the tracking report counts the ledger export's earn reward rows among the rows with no fill

Kraken's CSV ledger export writes Auto Earn's credit as type earn, subtype reward, where the API
the allowlist was written from writes staking, so on the export the reader printed every reward row on
its places-nowhere line. Both spellings are now counted with no fill behind them, the export's matched
on its type and subtype, so an earn row under another subtype stays on the places-nowhere line; the
README row and the engine procedures' four sentences name the export's spelling.

PROBE_VERDICT

Co-Authored-By: Claude <actual executing model> <noreply@anthropic.com>
MSG
```

- [ ] **Step 8: The tree is clean**
- [ ] **Step 9: Prove the guards, then record their verdicts** — two probes, the match's two members; Expected: each KILLED; then the message-only amend.

```bash
infra/scripts/mutate-probe.sh --file cli/engine/tracking.py --control '1,$d' \
  --mutation 's/^        elif row.type in _NO_FILL_LEDGER_TYPES or (row.type, row.subtype) == _EARN_REWARD:$/        elif row.type in _NO_FILL_LEDGER_TYPES:/' \
  -- uv run pytest tests/test_engine_tracking.py -k earn_reward_row -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file cli/engine/tracking.py --control '1,$d' \
  --mutation 's/ or (row.type, row.subtype) == _EARN_REWARD:$/ or row.type == _EARN_REWARD[0]:/' \
  -- uv run pytest tests/test_engine_tracking.py -k earn_reward_row -q -p no:cacheprovider
```

---

### Task 8: The bookkeeping page, the NAS tree's two mentions, and the daily pass's reminder

**Files:**
- Create: `infra/runbooks/bookkeeping.md`
- Modify: `infra/runbooks/nas.md` (`:21`, the archive's trees; `:43`, step 3's list of what each tree is), `docs/reference/fleet.md` (`:66`, the mount's trees)
- Modify: `infra/scripts/ops_daily.py` (four constants after `HEALABLE_RUNBOOK`, `:345`; three functions before `read_reminders`, `:382`; its `statements` parameter after `deploy_log`, `:389`; its two due-status lines, `:411` and `:429`, calling the third; the reminder before `hours = max(1, …)` inside it, `:433`)
- Test: `tests/test_ops_daily.py` (an autouse fixture before `live_soak_run`, `:126`; the reminder sets of `:2241` and `:2318` gain `kraken bookkeeping`; four tests, nine cases, before `_PATCH_PASS_HOSTS`, `:2244`)

**Interfaces:**
- Consumes: spec D7's path, steps and cadence, and the export commands' flags its measured basis records from their `--help`.
- Produces: `infra/runbooks/bookkeeping.md#kraken-monthly-bookkeeping` (PROCEDURE) and `#kraken-bookkeeping-due` (SCHEDULED REMINDER), the procedure Task 9's next steps and the Rollout run; `ops_daily.STATEMENTS`, `newest_window_end(statements)`, and the `kraken bookkeeping` reminder.

**What this task decides, where the spec leaves it open:** the reminder is owed from the 2nd of the month after the newest archived window's end month, from 2026-11-02 while none is archived; a directory counts as a window only once it holds a `*.provenance.json`; the mount is a systemd automount (`infra/ansible/roles/ops/tasks/main.yml`, `x-systemd.automount`), whose directory stands whether or not the NAS answers, so the mount is proven by listing it, and the automount's states are five, each with a case: the mount's listing fails — unreadable; the mount lists nothing — unreadable, the NAS export never being empty (`infra/runbooks/nas.md:21`); `kraken-statements/` absent beneath it — a tree with no window yet; the tree's listing fails otherwise — unreadable; a window's listing fails — unreadable, each window read by listing it, since `Path.glob` passes over a directory it cannot list. The tests never read the real mount: an autouse fixture points `STATEMENTS` at a tmp tree under a populated parent, as `live_soak_run` keeps the soak runner off the journal mount.

- [ ] **Step 1: Load `zcrypto-refine-rules`** and measure the runbook-read floor before the page:

```bash
uv run python -c 'import tests.test_ops_daily as t; r=[c for c in t._runbook_commands() if not t._destructive(c)]; a=[c for c in r if t.ops_daily.classify_action(chr(96)+c+chr(96), host="ops", resolve=t._identity) is t.ops_daily.Tier.AUTONOMOUS]; print(f"{len(a)}/{len(r)}")'
```

Expected: `345/487`, at least 0.70.

- [ ] **Step 2: Write the failing tests** — in `tests/test_ops_daily.py`, the autouse fixture before `live_soak_run`:

```python
@pytest.fixture(autouse=True)
def statements_off_the_mount(monkeypatch, tmp_path):
    """Points every reminders read here at a tmp statements tree, under a parent that lists one entry, never at the NAS
    mount."""
    root = tmp_path / "mnt" / "kraken-statements"
    (root.parent / "kraken-trades").mkdir(parents=True)
    monkeypatch.setattr(ops_daily, "STATEMENTS", root)
    return root
```

the set at `:2241`, `{"refdata sweep", "healable re-derivation"}`, and the set at `:2318`, the same two names before `| {_PATCH_PASS_NAMES[o] for o in others}`, each gaining `"kraken bookkeeping"`; and before `_PATCH_PASS_HOSTS`:

```python
def _statements(root, *windows, provenance=True):
    root.mkdir()
    for name in windows:
        (root / name).mkdir()
        if provenance:
            (root / name / f"blockpit-{name}.csv.provenance.json").write_text("{}")
    return root


@pytest.mark.parametrize(
    "windows,now,status,owed",
    [
        ((), datetime(2026, 10, 30, 3, 0, tzinfo=timezone.utc), "due in 3 days (no window archived yet)", False),
        ((), datetime(2026, 11, 2, 3, 0, tzinfo=timezone.utc), "due in 0 days (no window archived yet)", True),
        (
            ("2026-07-01_2026-11-01",),
            datetime(2026, 11, 20, 3, 0, tzinfo=timezone.utc),
            "due in 12 days (newest window ends 2026-11-01)",
            False,
        ),
        (
            ("2026-07-01_2026-11-01", "2026-11-01_2026-12-01"),
            datetime(2027, 1, 5, 3, 0, tzinfo=timezone.utc),
            "OVERDUE by 3 days (newest window ends 2026-12-01)",
            True,
        ),
    ],
    ids=["first_window_ahead", "first_window_due", "next_window_ahead", "next_window_overdue"],
)
def test_the_bookkeeping_reminder_is_due_from_the_newest_archived_window(
    tmp_path, statements_off_the_mount, windows, now, status, owed
):
    _statements(statements_off_the_mount, *windows)
    read = ops_daily.read_reminders(
        "tok", now=now, window=DAY, opener=_canned(_counter(0)), register=_register(tmp_path, *_TWO_SWEEPS)
    )
    bookkeeping = _reminder(read, "kraken bookkeeping")
    assert (bookkeeping.status, bookkeeping.owed) == (status, owed)
    assert bookkeeping.runbook == "infra/runbooks/bookkeeping.md#kraken-bookkeeping-due"
    assert read.unreadable is None


def test_a_window_without_a_provenance_file_is_passed_over(tmp_path, statements_off_the_mount):
    _statements(statements_off_the_mount, "2026-07-01_2026-11-01")
    (statements_off_the_mount / "2026-11-01_2026-12-01").mkdir()
    now = datetime(2026, 12, 3, 3, 0, tzinfo=timezone.utc)
    read = ops_daily.read_reminders(
        "tok", now=now, window=DAY, opener=_canned(_counter(0)), register=_register(tmp_path, *_TWO_SWEEPS)
    )
    assert _reminder(read, "kraken bookkeeping").status == "OVERDUE by 1 days (newest window ends 2026-11-01)"


def _unreadable_statements(tmp_path, statements):
    read = ops_daily.read_reminders(
        "tok",
        now=NOW,
        window=DAY,
        opener=_canned(_counter(0)),
        register=_register(tmp_path, *_TWO_SWEEPS),
        statements=statements,
    )
    assert read.unreadable and "the statements tree could not be read" in read.unreadable, read.unreadable
    assert not [r for r in read.reminders if r.name == "kraken bookkeeping"]
    assert _reminder(read, "refdata sweep")


def test_an_empty_mountpoint_is_an_unreadable_source(tmp_path):
    (tmp_path / "automount").mkdir()
    _unreadable_statements(tmp_path, tmp_path / "automount" / "kraken-statements")


@pytest.mark.parametrize("where", ["mount", "tree", "window"])
def test_a_listing_that_fails_is_an_unreadable_source(tmp_path, monkeypatch, statements_off_the_mount, where):
    if where != "mount":
        _statements(statements_off_the_mount, "2026-07-01_2026-11-01")
    target = {
        "mount": statements_off_the_mount.parent,
        "tree": statements_off_the_mount,
        "window": statements_off_the_mount / "2026-07-01_2026-11-01",
    }[where]
    listing = Path.iterdir

    def failing(path):
        if path == target:
            raise OSError("Input/output error")
        return listing(path)

    monkeypatch.setattr(Path, "iterdir", failing)
    _unreadable_statements(tmp_path, statements_off_the_mount)
```

- [ ] **Step 3: Run them and read the failure** — `uv run pytest tests/test_ops_daily.py -q -p no:cacheprovider`; Expected: the fixture errors on `ops_daily` having no attribute `STATEMENTS` in every case.
- [ ] **Step 4: The reminder** — in `infra/scripts/ops_daily.py`, after `HEALABLE_RUNBOOK`:

```python
BOOKKEEPING_RUNBOOK = "infra/runbooks/bookkeeping.md#kraken-bookkeeping-due"
STATEMENTS = Path("/mnt/zhao-crypto/kraken-statements")
# The first window's due day (spec 00126 D7, D9).
BOOKKEEPING_FIRST_DUE = date(2026, 11, 2)
_WINDOW_DIR = re.compile(r"^\d{4}-\d{2}-\d{2}_(\d{4}-\d{2}-\d{2})$")
```

before `read_reminders`:

```python
def newest_window_end(statements: Path) -> date | None:
    """The exclusive end of the newest archived window: a `<start>_<end>` directory holding a provenance file."""
    # A listing proves the mount: an automount's directory stands whether or not the NAS answers, and one that lists
    # nothing is read as unmounted.
    if next(statements.parent.iterdir(), None) is None:
        raise OSError(f"{statements.parent} lists nothing, so the NAS export is not mounted")
    try:
        entries = list(statements.iterdir())
    except FileNotFoundError:
        return None
    ends = [
        date.fromisoformat(match.group(1))
        for entry in entries
        if (match := _WINDOW_DIR.match(entry.name)) and any(path.name.endswith(".provenance.json") for path in entry.iterdir())
    ]
    return max(ends, default=None)


def _bookkeeping_due(end: date | None) -> date:
    if end is None:
        return BOOKKEEPING_FIRST_DUE
    following = date(end.year + 1, 1, 1) if end.month == 12 else date(end.year, end.month + 1, 1)
    return following + timedelta(days=1)


def _due_status(days: int) -> str:
    return f"due in {days} days" if days >= 0 else f"OVERDUE by {-days} days"
```

`read_reminders` gains `statements: Path | None = None,` after `deploy_log: Path = DEPLOY_LOG,`; its two lines `status = f"due in {days} days" if days >= 0 else f"OVERDUE by {-days} days"`, the refdata sweep's at `:411` and the patch pass's at `:429`, each become `status = _due_status(days)`, the form the third reminder takes; and before its `hours = max(1, int(window.total_seconds() // 3600))`:

```python
    try:
        end = newest_window_end(statements or STATEMENTS)
    except _UNREACHABLE as exc:
        note(f"the statements tree could not be read: {exc}")
    else:
        days = (_bookkeeping_due(end) - now.date()).days
        status = _due_status(days)
        newest = f"newest window ends {end.isoformat()}" if end else "no window archived yet"
        read.reminders.append(Reminder("kraken bookkeeping", f"{status} ({newest})", owed=days <= 0, runbook=BOOKKEEPING_RUNBOOK))
```

- [ ] **Step 5: The page and the two tree mentions** — `infra/runbooks/bookkeeping.md`, its steps 1 to 3 carrying the flags of `kraken export-report`, `export-status`, `export-retrieve`, `ledgers` and `trades-history` that spec 00126's measured basis records:

````markdown
# Bookkeeping runbooks — Kraken's statements and the tax tool's import file

You are here to run a month's bookkeeping, or because the daily pass's report listed the bookkeeping reminder as **OWED** under `## Reminders`. Nothing is wrong and nothing fired. Blockpit, the tax tool, takes the account's history from a manual-import file that `zcrypto tax blockpit` writes from Kraken's own ledger and trades exports; the exports, the file and its provenance are archived on the NAS as the audit trail.

`README.md` beside this file states what belongs in a runbook at all; a reminder names a section by file and anchor, and a procedure is found by its file and heading.

______________________________________________________________________

<a name="kraken-monthly-bookkeeping"></a>

## kraken-monthly-bookkeeping — PROCEDURE

### What you are seeing

A month has closed, and its Kraken activity is not yet in the Blockpit manual integration that holds the account's history. Each window is one directory on the NAS, `/volume1/ZhaoCrypto/kraken-statements/<start>_<end>/`, named by its UTC start date and its exclusive UTC end date; the first window runs from 2026-07-01 to 2026-11-01, and each later window is the calendar month after the newest archived one, so a month missed is run as its own window before the month after it.

### What it means

Blockpit computes FIFO per integration, so the manual integration carries the whole history and each window extends it without a gap or an overlap. The transform refuses a window whose opening balances are not the closing balances of the window before (`--after`), so a skipped or doubled month stops at step 4 rather than reaching Blockpit. One export spans the whole window — Kraken's export article states no maximum period — and expires 14 days after it is requested.

### What to do

From the workstation at the repository root; `<W>` is the window's directory name and `<P>` the newest archived window's, the last name `ls /mnt/zhao-crypto/kraken-statements/` prints — for a re-run of `<W>` (step 5's last sentence), the last name it prints before `<W>`, the window before `<W>` or that window's newest sibling.

1. **Request the two exports**: `kraken export-report --report ledgers --starttm <start epoch> --endtm <end epoch>` and the same with `--report trades`, each epoch the UTC midnight of its date (`date -u -d <date> +%s`); each prints a report id.
2. **Fetch and test them** once `kraken export-status --report ledgers` and `--report trades` read each report `Processed`, before its `expiretm`: `mkdir -p data/kraken-statements/<W>`, then `kraken export-retrieve --output-file data/kraken-statements/<W>/ledgers.zip <the ledgers id>` and the same with `trades.zip` and the trades id. Test each zip with `uv run python -I -c 'import sys, zipfile; print(zipfile.ZipFile(sys.argv[1]).testzip())' <the zip>`, which checks its member's CRC and prints `None`; then `unzip` each zip there, and the directory holds two zips and two CSVs. A zip that fails its test is refused: run its retrieve again.
3. **Read the CSVs**: each CSV's data rows (`tail -n +2 <the CSV> | wc -l`) equal the `count` that `kraken ledgers -o json` and `kraken trades-history -o json` print with `--start <start epoch>` and `--end <end epoch>`, the API's start bound exclusive and its end inclusive, and its times carry a fraction of a second, so these bounds read the window's rows unless one is stamped exactly on its start or end second; and the ledger's first and last `time` lie inside the window (`head -2` and `tail -1` of each CSV). A CSV whose rows differ from the count refuses its zip: run that retrieve again.
4. **Write the import file**: `uv run zcrypto tax blockpit --ledgers data/kraken-statements/<W>/<the ledgers CSV> --trades data/kraken-statements/<W>/<the trades CSV> --out data/kraken-statements/<W>/blockpit-<W>.csv --after /mnt/zhao-crypto/kraken-statements/<P>/blockpit-<P>.csv.provenance.json` — the first window takes no `--after`. Exit 0 prints the rows per label and the closing balances. Exit 1 prints each refusal and writes nothing: a row type the mapping has not met, or a window that does not follow the one before, is a decision for the owner, and the window waits for it.
5. **Archive the window**: `ssh nas 'mkdir -p /volume1/ZhaoCrypto/kraken-statements && mkdir /volume1/ZhaoCrypto/kraken-statements/<W>'` — a window already archived fails the second `mkdir` and stops here, an archived file being replaced by a sibling and not written over ([`nas.md#nas-file-transfer`](nas.md#nas-file-transfer) step 3) — then `scp data/kraken-statements/<W>/* nas:/ZhaoCrypto/kraken-statements/<W>/` — the path without `/volume1`, as the same section says — then `ssh nas 'sudo bash -s /volume1/ZhaoCrypto/kraken-statements' < infra/nas/normalize-archive-perms.sh`, which gives the tree the archive's group and modes, so the mount's readers can open it, then `sha256sum /mnt/zhao-crypto/kraken-statements/<W>/*`, read through the mount as the daily pass and the next window read it: the two CSVs' and the import file's hashes equal the three `jq -r '.inputs.ledgers.sha256, .inputs.trades.sha256, .output.sha256'` prints over the provenance, and the two zips' and the provenance's equal `sha256sum data/kraken-statements/<W>/*`'s. A window run again, once step 6 or 7 stopped it and the owner ruled the change, is the sibling `<W>-r2` (then `-r3`): its directory under `data/kraken-statements/` takes the window's two zips and two Kraken CSVs, step 4 writes `blockpit-<W>-r2.csv` there, and this step archives it as `<W>-r2/`, which the next window's `<P>` then names.
6. **Import into Blockpit**: Integrations → the manual integration → the upload icon beside Sync → the Blockpit Template tab → `blockpit-<W>.csv`, once; a second upload of one file duplicates its rows, so a re-import follows the deletion of that file's rows in Blockpit. A `Deposit` row is a crypto deposit, Blockpit's unlabeled incoming type, which Blockpit values at market on arrival until it is labelled: label it in Blockpit from what you know of its origin, such as a Transfer from the wallet it left, which carries the acquisition date and cost.
7. **Read the balances**: in Blockpit's Ledger view of the manual integration, each asset's balance at the window's end equals the provenance's `closing` value for it (`jq .closing` on the provenance file). A difference stops the month: read that asset's transactions in the window against the import file before anything else is imported.

### Retire when

`cli/tax/blockpit.py` is absent from the repo — the transform this procedure runs.

______________________________________________________________________

<a name="kraken-bookkeeping-due"></a>

## kraken-bookkeeping-due — SCHEDULED REMINDER

### What you are seeing

The daily pass's report (`ops-daily.py report`) names `kraken bookkeeping` under `## Reminders` — `due in N days` or `OVERDUE by N days`, with the newest archived window's end date, or `no window archived yet`. The **OWED** marker in front of it, set from the due day onward, is the trigger. It is not an alert: nothing is wrong.

### What it means

The pass reads the newest `<start>_<end>` directory under `/mnt/zhao-crypto/kraken-statements/` that holds a provenance file; the next window is due on the 2nd of the month after that window's end month, and the first on 2026-11-02. A directory without a provenance file is a window not yet written, and the pass reads past it.

### What to do

Run [`kraken-monthly-bookkeeping`](#kraken-monthly-bookkeeping) for the owed window. The reminder clears at the next pass once the window's directory on the NAS holds its provenance file.

### Retire when

`BOOKKEEPING_RUNBOOK` is absent from `infra/scripts/ops_daily.py` — the reminder that sends you here.
````

In `infra/runbooks/nas.md:21`, `` plus the hand-downloaded Kraken history dumps `kraken-ohlcvt-updates/` and `kraken-trades/`) `` becomes `` plus the hand-downloaded Kraken history dumps `kraken-ohlcvt-updates/` and `kraken-trades/`, and the monthly bookkeeping's `kraken-statements/`) ``; in `:43`, after `` `kraken-ohlcvt-updates/` and `kraken-trades/` are the hand-downloaded Kraken history dumps the datasets are rebuilt from. `` the sentence `` `kraken-statements/` is the tax depot's audit trail, Kraken's exports and the import files written from them ([`bookkeeping.md`](bookkeeping.md#kraken-monthly-bookkeeping)). ``; in `docs/reference/fleet.md:66`, `` `kraken-ohlcvt-updates/`, `kraken-trades/`, `` becomes `` `kraken-ohlcvt-updates/`, `kraken-statements/`, `kraken-trades/`, ``.

- [ ] **Step 6: Run the tests** — Step 3's command; Expected: no failure.
- [ ] **Step 7: The consumers and the page's reads**

```bash
uv run pytest tests/test_ops_daily.py tests/test_ops_daily_soak.py tests/test_hc_provision.py tests/test_fleet_contracts.py tests/test_runbook_triggers.py tests/test_runbook_internal_tokens.py tests/test_internal_terms_not_operator_visible.py tests/test_guidance_guard.py tests/test_guidance_refs_resolve.py tests/test_code_prose_citations.py tests/test_scripts_have_tests.py -q -p no:cacheprovider
uv run python infra/scripts/guidance-guard.py --uncounted infra/runbooks/bookkeeping.md infra/runbooks/nas.md docs/reference/fleet.md
```

Expected: no failure; the guard prints nothing. Then the consumers' run (Global Constraints), and Step 1's ratio again: `346/492` on the draft this plan was checked with, at least 0.70; the two readings go into the pull request body.

- [ ] **Step 8: The commit gate, then the page's trigger reads** — the gate stages the new page, and `runbook-triggers.py` reads the sections of the files `git ls-files` lists, which holds a new file once it is staged:

```bash
uv run python infra/scripts/runbook-triggers.py triggers
uv run python infra/scripts/runbook-triggers.py retire-when
```

Expected: both counts `0`.
- [ ] **Step 9: Commit**

```bash
git add infra/runbooks/bookkeeping.md infra/runbooks/nas.md docs/reference/fleet.md infra/scripts/ops_daily.py tests/test_ops_daily.py
git commit -F- <<'MSG'
feat(ops): the monthly Kraken bookkeeping — its runbook page, its NAS tree, and the daily pass's reminder

A new page carries the monthly procedure, from the two exports' request and the tests of their zips
to the read of Blockpit's balances against the provenance, and the reminder's section. Each window is one directory under the
NAS's kraken-statements tree, which the NAS runbook and the fleet page now name. The daily pass reads
the newest window holding a provenance file through the read-only mount and owes the next window from
the 2nd of the month after its end, from 2026-11-02 while none is archived. The mount is an
automount whose directory stands whether or not the NAS answers, so a listing that fails or comes
back empty is an unreadable source, as is a window whose listing fails; its tests point the tree at a
tmp directory and never read the mount. The due-or-overdue wording is one helper the three
reminders share.

PROBE_VERDICT

Co-Authored-By: Claude <actual executing model> <noreply@anthropic.com>
MSG
```

- [ ] **Step 10: The tree is clean**
- [ ] **Step 11: Prove the guards, then record their verdicts** — nine probes, the last on the page's anchor; Expected: each KILLED; then the message-only amend.

```bash
infra/scripts/mutate-probe.sh --file infra/scripts/ops_daily.py --control '1,$d' \
  --mutation 's/ and any(path.name.endswith(".provenance.json") for path in entry.iterdir())$//' \
  -- uv run pytest tests/test_ops_daily.py -k without_a_provenance_file -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file infra/scripts/ops_daily.py --control '1,$d' \
  --mutation 's/any(path.name.endswith(".provenance.json") for path in entry.iterdir())$/any(entry.glob("*.provenance.json"))/' \
  -- uv run pytest tests/test_ops_daily.py -k 'listing_that_fails and window' -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file infra/scripts/ops_daily.py --control '1,$d' \
  --mutation 's/owed=days <= 0, runbook=BOOKKEEPING_RUNBOOK/owed=days < 0, runbook=BOOKKEEPING_RUNBOOK/' \
  -- uv run pytest tests/test_ops_daily.py -k bookkeeping_reminder_is_due -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file infra/scripts/ops_daily.py --control '1,$d' \
  --mutation 's/^BOOKKEEPING_FIRST_DUE = date(2026, 11, 2)$/BOOKKEEPING_FIRST_DUE = date(2026, 11, 1)/' \
  -- uv run pytest tests/test_ops_daily.py -k bookkeeping_reminder_is_due -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file infra/scripts/ops_daily.py --control '1,$d' \
  --mutation 's/^    return following + timedelta(days=1)$/    return following/' \
  -- uv run pytest tests/test_ops_daily.py -k bookkeeping_reminder_is_due -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file infra/scripts/ops_daily.py --control '1,$d' \
  --mutation 's/^    if next(statements.parent.iterdir(), None) is None:$/    if False:/' \
  -- uv run pytest tests/test_ops_daily.py -k empty_mountpoint -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file infra/scripts/ops_daily.py --control '1,$d' \
  --mutation 's/^    if next(statements.parent.iterdir(), None) is None:$/    if not statements.parent.is_dir():/' \
  -- uv run pytest tests/test_ops_daily.py -k listing_that_fails -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file infra/scripts/ops_daily.py --control '1,$d' \
  --mutation 's/^    except FileNotFoundError:$/    except OSError:/' \
  -- uv run pytest tests/test_ops_daily.py -k listing_that_fails -q -p no:cacheprovider
infra/scripts/mutate-probe.sh --file infra/runbooks/bookkeeping.md --control '1,$d' \
  --mutation 's/^<a name="kraken-bookkeeping-due"><\/a>$/<a name="kraken-bookkeeping"><\/a>/' \
  -- uv run pytest tests/test_ops_daily.py -k instrument_itself_prints_resolves -q -p no:cacheprovider
```

---

### Task 9: T0215 partial — its autonomous step done, the import, the re-read and the decision open

**Runs after R1 has opened the pull request as a draft, so its number exists; R1's undraft follows this task.**

**Files:**
- Modify: `docs/open-topics/T0215-blockpit-fallback-pre-transform.md`, and `docs/open-topics/README.md` by the render

- [ ] **Step 1: Load `topic-ops`** and follow its partial mechanics, each section edit anchored on a string `grep -c` reads once and the heading set compared before and after.
- [ ] **Step 2: The frontmatter** — `status: open` becomes `status: partial`, and `ripe_when` becomes:

```yaml
ripe_when: "a date: 2026-11-02, the Monday after rung 2's box, when October's exports are complete and the first whole-history window, 2026-07-01 to 2026-11-01, closes on a month boundary; check: `date -u +%F` reads 2026-11-02 or later"
```

- [ ] **Step 3: `## Done so far`** — inserted after `## Findings so far`:

```markdown
## Done so far

- The transform is built: `zcrypto tax blockpit` (`cli/tax/`) maps one window of Kraken's ledger and trades CSV exports onto Blockpit's manual-import rows — the conversion pair a Trade EUR → EURC, a margin close's fee its own Margin Fee row — and writes a provenance file beside them, refusing and writing nothing on a row it cannot map; spec `docs/specs/00126-blockpit-fallback-transform-design.md`, plan `docs/plans/00126-blockpit-fallback-transform.md`, pull request #<the number R1 opened>.
- The monthly procedure and its reminder: `infra/runbooks/bookkeeping.md`, the windows archived under the NAS's `/volume1/ZhaoCrypto/kraken-statements/`, the daily pass owing the next window from 2026-11-02.
- The tracking report reads the export's `earn` reward rows (spec 00126 D10).
```

- [ ] **Step 4: `## Suggested next steps`** — replaced by the remainder:

```markdown
## Suggested next steps

- **(human, from 2026-11-02)** The first window into a fresh depot, per spec 00126 D9: run steps 1 to 5 of `infra/runbooks/bookkeeping.md#kraken-monthly-bookkeeping` for the window `2026-07-01_2026-11-01`, step 4 with no `--after`; then in Blockpit, Integrations → + Integration → Manual Integration, named `Kraken manual import`; then the page's steps 6 and 7 into it, step 6's upload once and its `Deposit` row, the crypto deposit, labelled from its origin, and step 7's balances equal to the provenance's `closing` on every asset, a difference stopping the window before the re-read. At that upload, read whether the Blockpit Template tab took the `.csv` and whether Blockpit took the one-leg trade's `0` amount, a refusal of either stopping the window for a change of its own — the file in another form, or that row a refusal of the transform — on which the owner rules again; a refusal by the transform itself stops the window for the owner's decision. Then re-read Step 7's five criteria on that integration: the Margin Profit and Loss rows and the spot disposals under §23 as `[iter-172]` read them; every margin and rollover fee in a summed figure, Blockpit's Margin Fee transactions summed per asset equal to the provenance's `Margin Fee` sums and the Steuerbericht's Margin-Gebühr total equal to those transactions' euro values as Blockpit values them, a EURC fee at its EURC price; FIFO lots intact; EURC never negative and no `Auto-Korrektur` lot; the disposal's gain off the settle's basis — read per integration with both present, then with the connector's integration hidden for the Steuerbericht's read, noting whether a hidden integration leaves the report. Record pass or fail beside `[iter-172]` in `docs/research/14.phase6-decisions.md` through the `iteration-closeout` skill; on a fail, unhide the connector's integration and keep it, delete nothing, and this item becomes the failing criterion's change.
- **(decision, once every criterion passes)** Whether the connector's integration is hidden for good or deleted — deletion cannot be undone and splits merged transfers back into unlabeled deposits and withdrawals.
```

- [ ] **Step 5: The index** — `uv run python infra/scripts/topics-index.py`; then `uv run pytest tests/test_open_topics_frontmatter.py tests/test_topics_index.py tests/test_internal_terms_not_operator_visible.py -q -p no:cacheprovider`; then `infra/scripts/count-list.sh live-topics-without-a-trigger`; then the consumers' run (Global Constraints); Expected: no failure, and the count reading `0`.
- [ ] **Step 6: The commit gate**
- [ ] **Step 7: Commit**

```bash
git add docs/open-topics/T0215-blockpit-fallback-pre-transform.md docs/open-topics/README.md
git commit -F- <<'MSG'
docs(topics): T0215 partial — the transform, its procedure and its reminder built; the first window, the re-read and the decision open

The autonomous step is done: the transform, the monthly procedure with its reminder, and the
tracking report's spelling of a reward. The topic now waits on 2026-11-02, the first month boundary
after rung 2's box with October's exports complete, for the whole-history import into a fresh manual
integration, the five criteria's re-read, and the decision on the connector's integration.

Co-Authored-By: Claude <actual executing model> <noreply@anthropic.com>
MSG
```

- [ ] **Step 8: The tree is clean**

---

## Rollout (attended)

**Operator steps.** Nothing below is an executor step: each reaches Kraken, the NAS, Blockpit or GitHub. Each command runs on the workstation at the repository root; `kraken` runs on the workstation alone. The owner's exports never enter the tree; their counts go into the decisions log and the topic, never a value.

**R1. The pull request** (after Task 8, before Task 9). Through the `open-pr` skill over the branch, opened as a draft (`gh pr create --draft`): `open-pr`'s Step 0 is read at the undraft, not the create, and T0215 reads `status: open` until Task 9. The `pre-review` workflow over the range's prose and messages, then `review` once the branch is complete, `re-review` over a fix range at most twice, every reviewer on Opus; the body names every probe's verdict, the runbook-read ratio before and after (Task 8), and the smoke run's row count (Task 6), and its `Read before push by:` line, naming the read and its tip, is written at the undraft. Task 9 then commits with the number the draft carries, flipping T0215 to `partial`, and that commit takes its own read; the undraft follows Task 9, Step 0's gate read then, the topic `partial` with its remainder registered. `merge-pr` merges it; `git switch develop && git pull --ff-only && git status --porcelain` reads empty.

**R2. The first window** (from 2026-11-02, the topic's date, rung 2's box closed the day before). From merged `develop`, steps 1 to 5 of `infra/runbooks/bookkeeping.md#kraken-monthly-bookkeeping` for the window `2026-07-01_2026-11-01`, its epochs `date -u -d 2026-07-01 +%s` and `date -u -d 2026-11-01 +%s`, step 4 with no `--after`, this being the first window. Expected: each step's reading as the page states it, the transform exiting 0 and printing the rows per label and the closing balances. A refusal stops here: it names a row type or a shape the mapping has not met, a decision for the owner and a change of its own before the window is imported. The readings fill [[ROLLOUT: R2 — the first window's row counts by label and the transform's exit]].

**R3. The fresh depot** — Task 9 Step 4's human item, from the manual integration's creation through the page's steps 6 and 7. The readings fill [[ROLLOUT: R3 — whether the Blockpit Template tab took the .csv]] — a refusal stops R3, and the file in another form is a change of its own the owner rules on, spec D5's ruling 9 — [[ROLLOUT: R3 — whether Blockpit took the one-leg trade's zero amount]] — a refusal of that row makes it a refusal of the transform by a change of its own, spec D3 — [[ROLLOUT: R3 — whether every asset's Blockpit balance equals the provenance's closing, or the asset codes that differ]], a difference a stop before R4, and [[ROLLOUT: R3 — whether the Deposit row is labelled from its origin]], spec D3's ruling 3. The amounts read stay in Blockpit and the provenance; the slots carry outcomes and asset codes.

**R4. The five criteria's re-read** (spec D9) — the same item's re-read, on the manual integration against Kraken's ledger, per integration with both integrations present, then with the connector's integration hidden for the Steuerbericht's read, nothing deleted. The verdict is recorded beside `[iter-172]` in `docs/research/14.phase6-decisions.md` through `iteration-closeout`. The readings fill [[ROLLOUT: R4 — each criterion pass or fail, and the verdict]] and [[ROLLOUT: R4 — whether a hidden integration leaves Blockpit's report]].

**R5. The owner's decision**, on R4's pass: the connector's integration hidden for good or deleted, recorded with R4's entry; with R4's verdict and this decision on the record, T0215 resolves by `topic-ops` in the pull request that records them. On a fail at R4, the connector's integration is unhidden and kept, nothing is deleted, and T0215 stays `partial`, its human item rewritten by `topic-ops` to the failing criterion's change, on which the owner rules. The decision fills [[ROLLOUT: R5 — the connector's integration hidden or deleted, or kept on R4's fail]].

**R6. The monthly cadence** from then on: `infra/runbooks/bookkeeping.md#kraken-monthly-bookkeeping` each month, each window run with `--after` the previous window's provenance read through the mount, the daily pass's reminder owing it from the 2nd.

## Resolution

This plan delivers T0215's autonomous step: the transform, its tests, the monthly procedure and its reminder, and the tracking report's spelling of a reward. Task 9 flips the topic to `partial` with its `## Done so far` naming spec 00126, this plan and the pull request, and its `ripe_when` the date 2026-11-02; the remainder — the whole-history import into a fresh manual integration, the five criteria's re-read recorded beside `[iter-172]`, and the decision on the connector's integration — is R2 to R5, after which the topic resolves in the pull request that records R4's pass and the decision, and stays `partial` on R4's fail.

## Slots the rollout fills

- [[ROLLOUT: R2 — the first window's row counts by label and the transform's exit]] (R2; the decisions-log entry).
- [[ROLLOUT: R3 — whether the Blockpit Template tab took the .csv]] (R3; the decisions-log entry, spec D5's ruling 9).
- [[ROLLOUT: R3 — whether Blockpit took the one-leg trade's zero amount]] (R3; spec D3's ruling 6).
- [[ROLLOUT: R3 — whether every asset's Blockpit balance equals the provenance's closing, or the asset codes that differ]] (R3; the decisions-log entry).
- [[ROLLOUT: R3 — whether the Deposit row is labelled from its origin]] (R3; the decisions-log entry, spec D3's ruling 3).
- [[ROLLOUT: R4 — each criterion pass or fail, and the verdict]] (R4; beside `[iter-172]`).
- [[ROLLOUT: R4 — whether a hidden integration leaves Blockpit's report]] (R4; the decisions-log entry).
- [[ROLLOUT: R5 — the connector's integration hidden or deleted, or kept on R4's fail]] (R5; T0215's resolution, or its next step on a fail).
