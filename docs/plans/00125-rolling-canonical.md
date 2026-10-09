# One growing OHLC canonical: `ohlc-rolling`, the Q3 15-minute frame extended daily from tape-bars — implementation plan

> Every value a rollout reading decides is a marked slot, `ROLLOUT:` inside double square brackets, listed at the end.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Research reads one canonical that reaches the present: `ohlc-rolling`, the 12 files of `ohlc-15m-20261007` copied byte for byte as its base and tape-bars' daily finals copied from 2026-10-01 as its extension, 60/240/1440 derived on read, every day a write-once index line chained to the one before it, so a trial pins an as-of day by one hash. The ops node extends it after each tape-bars sweep through its `hot-out` outbox, the NAS's hot pull carries it to the hub, `data fetch` attests it, the daily pass reads its head, and the searches, the universe rebuild and the engine seed read it; the reach round retires (spec 00125).

**Architecture:** Thirteen tasks on `docs/00125-rolling-canonical`, one pull request, then an attended rollout. The reader first, because every later task reads the set through it; then the writer the ops node runs, the fetch's attestation, the registry's record and conformance walk, the daily pass's head check, the three readers' migration with the reach round's retirement, the runner step, and last the catalog, the README, the fleet reference, the runbook and the daily-ops skill. The Rollout converges the ops node onto the image built from the merge, stages the base on the owner's word, runs the first extension, reads the head on the hub by value, and leaves the retirements to the owner.

**Tech Stack:** Python 3.14 through `uv run`, polars 1.44.2, Typer (`cli/data/command.py`, `cli/research/command.py`, `cli/engine/command.py`), the tape-bars runner (`infra/ansible/roles/ops/templates/tape-bars.sh.j2`, bash), the ops role (Ansible, the Templar test substrate of `tests/test_infra_converge_guards.py`), the daily pass (`infra/scripts/ops_daily.py`), pytest, `infra/scripts/mutate-probe.sh` for guard verdicts.

**Spec:** `docs/specs/00125-rolling-canonical-design.md`, D1 to D8 as the owner ruled them on 2026-10-09 ("accept all eleven as recommended"), with "What changes in the repo", the invariants and the measured basis; the spec is the one text of every decision this plan implements without restating it.

## Global Constraints

- Every line number this plan gives for existing code or text is a reading at `f70be7dae`, this branch's base; a task that edits a file reads the lines it cites again before its first edit, since an earlier task may have moved them.
- No executor step reaches a host, the NAS, the hub, a registry, a venue or Grafana: every such step is an operator step of the Rollout, attended. `ansible-playbook` and `infra/ansible/scripts/converge.sh` are never run by an executor in any form — this workstation is the fleet host `zcrypto-ops`; a role's YAML is proven by the tests' walk and the commit gate's `ansible-lint`. No executor step writes under `/var/lib/zcrypto-ops/`, `/mnt/zhao-crypto/` or the main checkout's `data/`: every test builds its tree under `tmp_path`.
- Every commit is green over its consumers, the files `infra/scripts/consumers.sh` prints for the task's changed files, run as each task's consumer step writes it; the full suite runs in CI alone. A task that adds or edits text `tests/test_internal_terms_not_operator_visible.py` walks — a CLI help string, a string literal under `infra/scripts/`, a role task name or message, a runbook page, the README — runs that file too, and its allowlist is never widened.
- A guard is proven by `infra/scripts/mutate-probe.sh`, never a hand-rolled mutate-and-restore. The script refuses a dirty tree, so a task commits with the line `PROBE_VERDICT` in its message, runs one probe per guard on the committed tree in this form, `--control '1,$d'` emptying the mutated file unless the probe still passes on an empty file, when the control is a mutation its test must fail:

```bash
infra/scripts/mutate-probe.sh --file "$FILE" --control '1,$d' --mutation "$SED" -- uv run pytest "$TESTS" -q -p no:cacheprovider -k "$NAME"
```

  each ending `mutate-probe: KILLED (control proven, tree restored byte-identically)`; then a message-only amend with the tree clean replaces `PROBE_VERDICT` with each probe's command and its verbatim verdict — the branch is unpushed and unread while the tasks run, so the amend rewrites nothing a reader holds. A mutation's sed is written against the committed text and addressed to the one line it mutates, a line number read from the committed file. A `that:` or `when:` made always true writes the string `"true"`, never the YAML boolean.
- The commit gate, before every commit: the commit's files staged by path, its new and deleted files among them, then `uv run pre-commit run -a` until clean, its rewrites staged. One file kind per commit: a `.claude/` change rides a `claude(...)` commit carrying no other file (Task 12), and `zcrypto-refine-rules` is loaded before the edit to the runbook page and the skill (Tasks 11 and 12).
- A commit message ends with the trailer `Co-Authored-By: Claude <actual executing model> <noreply@anthropic.com>`, the placeholder replaced by the executing model's own name, followed by the executing session's `Claude-Session:` line where its harness supplies one; each commit fence below carries the trailer in that form.
- A code comment, task name, task message or docstring a task's edit falsifies is re-trued in that task's commit, and its Files entry names it; a new one stays only if a reader would act differently without it.
- Never print a container's environment; a `docker inspect` names one field. A recursive grep given `infra/` carries `--exclude='*vault*' --exclude='*.sops.*'`; no vault file is read, printed, grepped or diffed.
- Every reviewer runs on Opus, the model passed explicitly.

## File structure

- `cli/data/rolling.py` (new): the index line's format, the chain walk, the head, the verify, the rolling read and its hole refusal (Task 1); the base staging and the daily extension (Task 2).
- `tests/rolling_fixtures.py` (new, Task 1): `write_chain`, the hand-written fixture chain every later task's tests build on, independent of the code under test.
- `cli/data/command.py`: the `data rolling` group — `verify` (Task 1), `base` and `extend` (Task 2); the `rebuild` help's set list loses `ohlc-reach` (Task 8).
- `cli/data/sync.py`: the fetch's attestation of a chained set (Task 3).
- `cli/registry/observed.py`: `read_rolling` and its record (Task 4).
- `infra/scripts/ops_daily.py`: the `rolling canonical head` row (Task 5).
- `cli/research/command.py`, `cli/research/subjects.py`: `--as-of`, `--accept-holes`, the rolling resolution (Task 6).
- `cli/engine/command.py`: `seed` reads the rolling set; the `CANONICAL_DIR` comment re-trued (Task 7).
- `cli/data/rebuild.py`: the universe on the rolling set; the reach target, `resolve_canonical_root`, `resolve_ohlc_source` and their helpers deleted; `cli/ohlc/reach.py` deleted; the comments naming it re-trued in `cli/engine/store.py`, `cli/ohlc/dataset.py` and `cli/ohlc/seam.py`; `zcrypto.toml`'s `authored_sets` (Task 8).
- `infra/ansible/roles/ops/templates/tape-bars.sh.j2`, `infra/ansible/roles/ops/defaults/main.yml`, `infra/ansible/roles/ops/tasks/main.yml` (Task 9).
- `docs/reference/data-catalog-full.md`, `docs/reference/fleet.md`, `README.md` (Task 10); `infra/runbooks/ops.md` (Task 11); `.claude/skills/zcrypto-daily-ops/SKILL.md` (Task 12).
- Tests: `tests/test_rolling_reader.py` (new, Task 1), `tests/test_rolling_extend.py` (new, Task 2), `tests/test_data_sync.py` (Task 3), `tests/test_registry_observed.py` and `tests/test_registry_conformance.py` (Task 4), `tests/test_ops_daily.py` (Task 5), `tests/test_research_command.py` (Task 6), `tests/test_engine_command.py` (Task 7), `tests/test_data_rebuild.py`, `tests/test_data_command.py`, `tests/test_data_manifest.py` and `tests/test_ohlc_reach.py` (deleted) (Task 8), `tests/test_infra_tape_bars_template.py` and `tests/test_infra_converge_guards.py` (Task 9), `tests/test_data_gated_run.py` (Task 2).

## Review Focus

- The chain: `prev` is the sha256 of the predecessor line's bytes, the days are contiguous from the base line, whose `prev` is null, and a broken link anywhere at or below the as-of day refuses — never skipped, never read past.
- One author, one channel: the extender writes under the outbox and its staging directory alone, renames every file in from a staging directory on the same mount, rewrites no existing file, and writes no day's line before its files or its predecessor's line.
- The pin: a rolling read records the as-of line alone; `dataset_hash` is the registry's own derivation, unchanged; a second as-of on one set is refused; nothing writes to `ohlc-full`, `ohlc-15m`, `ohlc-holdout-2026-07-10` or the registry.
- The seam: the base is the Q3 15-minute frame byte for byte; every frame the reader returns is in `FRAME_SCHEMA`'s column order; the coarse grids are `derive_bars` over the base and the days together.
- The holes: a pair-day becomes a hole only past the materializer's re-scan window, and a read whose window covers one refuses unless the caller accepts it.
- The retirement: nothing reads `ohlc-reach` or the frozen-sibling resolvers after Task 8, and `soak-check`, record 44's legs and the legacy pins keep reading `ohlc-full` and `ohlc-15m`.
- The runner: the extension runs after the sweep's gauges are written, as the data user in the outbox's group, the tape tree mounted read-only beside the one writable data mount, and its failure fails the unit without rewriting the sweep's gauges.

---

### Before Task 1: the branch is at develop's tip and the plan's premises hold

- [ ] **Step 1: The branch holds develop's tip**

```bash
git fetch origin develop && git merge-base --is-ancestor origin/develop HEAD; echo "rc $?"
```

Expected: `rc 0`. On `rc 1`, `git merge origin/develop` into the branch — never a rebase, the spec and plan commits having been read — and re-check.

- [ ] **Step 2: The code the plan names is where it says**

```bash
grep -n 'def resolve_canonical_root\|def resolve_ohlc_source\|def _refresh_universe' cli/data/rebuild.py
grep -n '^TAPE_SETTLE\|^RESCAN_DAYS\|^def derive_bars' cli/tick/materialize.py
grep -n '^CANONICAL_DIR\|^def seed' cli/engine/command.py
```

Expected: `141:`, `166:` and `184:` for the three definitions; `52:def derive_bars`, `78:TAPE_SETTLE` and `79:RESCAN_DAYS`; `86:CANONICAL_DIR` and `375:def seed`.

---

### Task 1: The reader — the index chain walked, a pair read to an as-of day, a hole refused

**Files:**
- Create: `cli/data/rolling.py` (the reader half), `tests/rolling_fixtures.py`, `tests/test_rolling_reader.py`
- Modify: `cli/data/command.py` (a `rolling` sub-app under `data_app`, :18-21, holding `verify`)

**Interfaces:**
- Consumes: `cli.ohlc.dataset.FRAME_SCHEMA` (`cli/ohlc/dataset.py:15`) and `read_parquet`; `cli.tick.materialize.derive_bars` (`cli/tick/materialize.py:52-72`).
- Produces, for every later task: `ROLLING_SET = "ohlc-rolling"`; `RollingError(Exception)`; `Line`, a frozen dataclass of `day: date`, `prev: str | None`, `files: dict[str, str]`, `holes: dict[str, str]`, `notes: dict[str, str]`, `relpath: str`, `sha256: str`; `line_relpath(day) -> str` (`index/<YYYY>/<MM>/<DD>.json`); `line_days(root) -> list[date]`, the days with a line file, sorted, read by listing; `is_chained(root) -> bool`; `pairs(root) -> tuple[str, ...]`; `walk_chain(root, as_of: date) -> list[Line]` (the base line first); `head(root) -> Line`; `verify_line(root, line) -> None`; `verify(root, as_of: date) -> Line`; `RollingRead`, a frozen dataclass of `frame: pl.DataFrame`, `holes: tuple[date, ...]`, `line: Line`; `read_rolling(root, pair, interval, as_of: date, *, window: tuple[datetime, datetime] | None = None, accept_holes: bool = False) -> RollingRead`; `zcrypto data rolling verify [--root DIR] --as-of YYYY-MM-DD`.

**What this task decides, where the spec leaves it open:**
- A line is JSON in one canonical form, `json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"`, its keys exactly `day`, `prev`, `files`, `holes`, and `notes` on the base line alone; the base line is the one whose `prev` is null, its `files` the `base/<BASE>/<QUOTE>/15.parquet` files, and the set's pairs are the pairs its `files` name. A day line's `files` keys are `days/<BASE>/<QUOTE>/<YYYY>/<MM>/<DD>.parquet` of its own day, its `holes` keys pairs, the two disjoint and together the set's pairs exactly; any other shape is a `RollingError` naming the line.
- `is_chained(root)` is `(root / "index").is_dir()`: no caller names the set to know it is chained.
- `walk_chain` reads from the as-of line down to the base line, each line's `day` one day after its predecessor's and its `prev` the sha256 of the predecessor line's bytes; a missing line, a gap in the days or a wrong `prev` refuses, naming the line. `head(root)` is the newest line whose listed files are all present, its chain then walked; a broken link at or below it refuses, never read past.
- `read_rolling` walks the chain to `as_of`, opens the pair's base file and each of its day files, hashes each file's bytes against its listing before reading it, selects the columns by name into `FRAME_SCHEMA`'s order, concatenates, derives 60, 240 and 1440 by `derive_bars` and returns 15 as it is, refusing any other interval, and applies `window` to the result. A day whose line names the pair under `holes` and whose span meets the window refuses, naming the pair and the day, unless `accept_holes`, when it is returned in `holes`.

The fixture helper, `write_chain(root: Path, *, pairs=("BTC/EUR", "ETH/BTC"), days: int = 3, holes: dict[date, set[str]] | None = None) -> list[str]`, writes the base files in `FRAME_SCHEMA`'s order (96 bars on 2026-09-30), the day files in `ticks_to_bars`' order (96 bars a day from 2026-10-01) and every line in the canonical form, each `prev` the sha256 of the line before it, and returns the lines' relpaths, the base line's first.

- [ ] **Step 1: Read** spec 00125 D1 (the trees, the columns), D2 (the lines, the pin, the proof) and D6 (the hole refusal); `cli/tick/materialize.py:52-72`; `cli/ohlc/dataset.py:10-57`; `cli/data/command.py:1-30`.
- [ ] **Step 2: Write the failing tests** in `tests/test_rolling_reader.py`, every tree built by `write_chain` under `tmp_path`: `test_the_read_returns_the_base_and_the_days_up_to_the_as_of_day`; `test_the_read_returns_frame_schema_columns_from_tape_order_day_files`; `test_a_coarse_grid_is_derived_across_the_seam_as_bars_computed_by_hand` (1440 over the base day and two extension days, against three bars written out in the test); `test_an_edited_line_breaks_the_chain` (one byte of the first day line changed: the read at the third day refuses naming that line); `test_a_skipped_day_breaks_the_chain` (the second day's line removed); `test_two_day_files_swapped_between_pairs_are_refused`; `test_a_listed_file_absent_is_refused`; `test_an_as_of_past_the_head_is_refused`; `test_a_line_naming_a_pair_outside_the_base_is_refused`; `test_a_hole_inside_the_window_is_refused_without_accept_holes`; `test_an_accepted_hole_is_reported_and_its_day_left_out`; `test_a_hole_outside_the_window_is_not_a_refusal`; `test_the_head_is_the_newest_line_whose_files_are_present` (the newest line's day file removed: the head is the line before it); `test_verify_prints_the_as_of_lines_sha256_and_exits_0` and `test_verify_names_the_first_broken_link_and_exits_1`, through `typer.testing.CliRunner` over `cli.__main__.app`.
- [ ] **Step 3: Run them and read the failure**

```bash
uv run pytest tests/test_rolling_reader.py -q -p no:cacheprovider
```

Expected: the file fails to collect, one error, on the missing module `cli.data.rolling`.

- [ ] **Step 4: Implement** `cli/data/rolling.py`'s reader half and the `verify` command per the decisions above: `verify` prints `<as-of> <sha256> files=<n>` and exits 0, or logs the `RollingError` as one line and exits 1; its `--root` defaults to `resolve_data_dir(load_config()) / ROLLING_SET`; its help text one operator-readable sentence with no internal term.
- [ ] **Step 5: Run the tests** — Step 3's command; Expected: `15 passed`.
- [ ] **Step 6: The consumers**

```bash
uv run pytest $(infra/scripts/consumers.sh cli/data/rolling.py cli/data/command.py | grep -E '^tests/test_[^ ]*\.py$' | sort -u) tests/test_rolling_reader.py tests/test_cli_help_hygiene.py tests/test_internal_terms_not_operator_visible.py -q -p no:cacheprovider
```

Expected: no failure.

- [ ] **Step 7: The commit gate**

```bash
git add cli/data/rolling.py cli/data/command.py tests/rolling_fixtures.py tests/test_rolling_reader.py && uv run pre-commit run -a
```

Expected: every hook `Passed` or `Skipped`; on a rewrite, stage it and run again.

- [ ] **Step 8: Commit**

```bash
git commit -F - <<'EOF'
feat(data): the rolling canonical's reader — its index chain walked, a pair read to an as-of day, a hole refused

PROBE_VERDICT

Co-Authored-By: Claude <actual executing model> <noreply@anthropic.com>
EOF
```

- [ ] **Step 9: Prove the guards**, `--file cli/data/rolling.py`, `TESTS=tests/test_rolling_reader.py`: the `prev` comparison made always equal, against `-k test_an_edited_line_breaks_the_chain`; the day-contiguity check dropped, against `-k test_a_skipped_day_breaks_the_chain`; the per-file byte hash before the read dropped, against `-k test_two_day_files_swapped_between_pairs_are_refused`; the absent-file refusal made a skip, against `-k test_a_listed_file_absent_is_refused`; the as-of bound dropped from the walk, against `-k test_an_as_of_past_the_head_is_refused`; the pair-set check of a line dropped, against `-k test_a_line_naming_a_pair_outside_the_base_is_refused`; the hole refusal's `accept_holes` test inverted, against `-k test_a_hole_inside_the_window_is_refused_without_accept_holes`; the window test of a hole made always true, against `-k test_a_hole_outside_the_window_is_not_a_refusal`; the select into `FRAME_SCHEMA`'s order dropped, against `-k test_the_read_returns_frame_schema_columns_from_tape_order_day_files`; `derive_bars` replaced by the 15-minute frame unchanged, against `-k test_a_coarse_grid_is_derived_across_the_seam_as_bars_computed_by_hand`; `head`'s present-files test dropped, against `-k test_the_head_is_the_newest_line_whose_files_are_present`; and, `--file cli/data/command.py`, `verify`'s refusal exit made 0, against `-k test_verify_names_the_first_broken_link_and_exits_1` — each `KILLED`; then the message-only amend.
- [ ] **Step 10: The tree is clean** — `git status --porcelain`; Expected: empty.

---

### Task 2: The writer — the base staged once and the days extended from tape-bars' finals

**Files:**
- Modify: `cli/data/rolling.py` (the writer half), `cli/data/command.py` (`rolling base`, `rolling extend`), `tests/test_data_gated_run.py` (`_DATA_ABSENT_REASONS`, :114-139, gains the two skip reasons below)
- Create: `tests/test_rolling_extend.py`

**Interfaces:**
- Consumes: Task 1's line format and `walk_chain`; `cli.tick.materialize.TAPE_SETTLE` and `RESCAN_DAYS` (:78-79), imported so the extender's re-scan window cannot drift from the materializer's; tape-bars' layout and sidecar (`cli/tick/materialize.py:116-141`, `<digest>  <name>\n`); `cli.data.manifest.read_manifest` for the source's attestations.
- Produces, for Task 9 and the Rollout: `stage_base(source, out, staging) -> Line`; `extend(tape_root, out, staging, *, now: datetime) -> ExtendResult` (`days_written: int`, `holes: int`, `head: Line`); `zcrypto data rolling base --source DIR --out DIR --staging DIR`, printing `base <sha256> files=<n>`; `zcrypto data rolling extend --tape-root DIR --out DIR --staging DIR`, printing `head=<YYYY-MM-DD> days_written=<n> holes=<n>`; both exit 1 on a `RollingError`, logged as one line.

**What this task decides, where the spec leaves it open:**
- Every file is written to a temporary name under `staging`, its data fsynced, then `os.replace`d into `out`, the destination directory fsynced, as `publish_day` does; `staging` and `out` must share a filesystem, the replace refusing otherwise. A day's files land before its line, and no line is written while its predecessor's is absent.
- No existing file is rewritten: a destination present with the bytes the write would give is accepted, so a run stopped between a day's files and its line completes the day on the next run; present with other bytes, it refuses.
- Every directory the writer creates is mode `0o2775` and every file `0o664`, set explicitly whatever the umask, so the research user who stages the base and the ops container that extends it can both add to the tree through the outbox's group.
- `stage_base` copies each `<BASE>/<QUOTE>/15.parquet` of `source`, refuses a file whose frame's `dataset_hash` is not the value the source's conformant manifest attests for that path, and writes the base line, `day` 2026-09-30, whose `notes` are `seam` (`2026-10-01T00:00:00+00:00`), `base_from` (the source directory's name), `base_identity_digest` (the source manifest's identity digest) and `vwap` (the dump's close-weighted proxy before the seam, the tape's tick-weighted mean from it); a second run over a written base refuses unless every file and the line are byte-equal.
- `extend` refuses an `out` with no base line. From the day after the head: when each of the set's pairs has a final in `tape_root` whose bytes hash to its sidecar, it writes the day; when some pair has none and the day is older than the newest settled day — `(now - TAPE_SETTLE).date()` less one day — less `RESCAN_DAYS`, it writes the day with each such pair under `holes` as `"no tape-bars final past the re-scan window"`; otherwise it stops. A final present without its sidecar, or disagreeing with it, refuses and writes nothing of that day.

The two data-gated tests read the main checkout's set once the Rollout has fetched it, and `Q3_15M_SHA256`, the test's literal, is this table — the bytes of `ohlc-15m-20261007`'s files as read on 2026-10-09 (`sha256sum */*/15.parquet` in it, the hub's copy hashing the same):

| Pair | sha256 of `ohlc-15m-20261007`'s `15.parquet` |
| --- | --- |
| ADA/EUR | `2f97a4e799d4f7232e813c8d7b937680046c1e52cd16391cdae853bc37f8fe74` |
| AVAX/EUR | `3613a84673b0bb70c7f0568a051561c1cd18dfa834aad6c6121b99c304e0b918` |
| BTC/EUR | `5b4f4a1ca279e1787791bad3613d238ab709a7243f782d3e5a8f5dac5445d8a8` |
| DOGE/EUR | `ad39c224de57b3d373284c0b9234938a3028fc5a97bd4953ad65f502f18c84d2` |
| DOT/EUR | `40bb776753c1844fd67d3462b14626ccff6de83ae463bb5fb1a9ca39f1c3f574` |
| ETH/BTC | `30e1bc25f4723b90213220a84b3bf5477478471711503a6fa89e691bc3cbcf7a` |
| ETH/EUR | `190a577355181c6a45c5ae58d6ef3bd702fac6c3ade1c014ebd968f20bfc6aa2` |
| LINK/EUR | `82ecb1abc7460e5e6f042b5466f0b0377e309a2432ce6a5ef31da1f04cbee7ea` |
| LTC/EUR | `19316cec547ef142d0fefa58b2a8d283d8724703b253f85420c6e4efab58f5f4` |
| SOL/BTC | `51bf01fe3a64fdbaa80aabfa7bec461de42a10cf3d30fc40b03cf6b69321425e` |
| SOL/EUR | `74e02128964419a9adee8079bb23c37d13474acc44efdd6a72a15a5607cf56c4` |
| XRP/EUR | `9f294239916b7c1afe679fbcd440bbcca9900a252fcab65f9f0539320813982b` |

- [ ] **Step 1: Read** spec 00125 D1, D3 (the outbox, the staging, the order) and D6 (the hole); `cli/tick/materialize.py:116-219`; `cli/data/manifest.py:116-189`; `tests/test_data_gated_run.py:108-139`.
- [ ] **Step 2: Write the failing tests** in `tests/test_rolling_extend.py`, every tree under `tmp_path` — a tape-bars tree written in its own layout with sidecars, a source set with a conformant manifest — and `now` injected: `test_the_base_copies_the_source_byte_for_byte_and_writes_the_base_line`; `test_the_base_refuses_a_source_file_its_manifest_does_not_attest`; `test_a_days_line_is_written_only_after_its_files` (`os.replace` patched to raise on the line: the day's files are present and no line); `test_a_rerun_after_a_stop_between_files_and_line_completes_the_day`; `test_a_final_disagreeing_with_its_sidecar_is_refused_and_nothing_of_that_day_written`; `test_no_existing_file_is_rewritten` (a line already present with other bytes: refused, its bytes unchanged); `test_day_d_plus_one_waits_while_d_is_pending` (one pair's final for D absent inside the window, D+1 complete: the head stays D−1); `test_a_hole_is_written_only_past_the_rescan_window` (the same tree with `now` moved past the window: D written with the pair under `holes`, then D+1); `test_prev_is_the_sha256_of_the_predecessors_bytes`; `test_only_finished_names_appear_under_the_outbox` (the outbox listed from inside a patched `os.replace`: no temporary name); `test_every_directory_is_group_writable_and_setgid` (`os.umask(0o022)` around the run: every directory `0o2775`, every file `0o664`); `test_extend_refuses_an_outbox_without_a_base_line`; `test_the_extend_summary_line_names_the_head_the_days_and_the_holes` (through `CliRunner`). Data-gated, each skipping with its reason where the set is absent: `test_the_staged_base_is_the_q3_15m_frame_byte_for_byte` (the twelve base files' sha256 equal `Q3_15M_SHA256`; reason `data/ohlc-rolling absent — the staged base is on the data-bearing workstation only`) and `test_the_grids_derived_from_the_staged_base_equal_the_q3_coarse_frames` (`read_rolling` at the base line for 60, 240 and 1440 against `data/ohlc-full-20261007`: identical timestamps, open/high/low/close and count equal, volume and vwap within `1e-12` relative; reason `data/ohlc-rolling or data/ohlc-full-20261007 absent — the base's derivation is checked on the data-bearing workstation only`). The two reasons join `_DATA_ABSENT_REASONS`.
- [ ] **Step 3: Run them and read the failure**

```bash
uv run pytest tests/test_rolling_extend.py -q -p no:cacheprovider
```

Expected: the file fails to collect, one error, on the import of `stage_base` and `extend` from `cli.data.rolling`.

- [ ] **Step 4: Implement** the writer half and the two commands per the decisions above, the commands' help text operator-readable with no internal term.
- [ ] **Step 5: Run the tests** — Step 3's command; Expected: `13 passed, 2 skipped`, the two data-gated cases skipping with their reasons in a worktree, whose `data/` is empty.
- [ ] **Step 6: The consumers**

```bash
uv run pytest $(infra/scripts/consumers.sh cli/data/rolling.py cli/data/command.py tests/test_data_gated_run.py | grep -E '^tests/test_[^ ]*\.py$' | sort -u) tests/test_rolling_extend.py tests/test_rolling_reader.py tests/test_cli_help_hygiene.py tests/test_internal_terms_not_operator_visible.py -q -p no:cacheprovider
```

Expected: no failure.

- [ ] **Step 7: The commit gate**

```bash
git add cli/data/rolling.py cli/data/command.py tests/test_rolling_extend.py tests/test_data_gated_run.py && uv run pre-commit run -a
```

Expected: every hook `Passed` or `Skipped`.

- [ ] **Step 8: Commit**

```bash
git commit -F - <<'EOF'
feat(data): the rolling canonical's base is staged once and its days are extended from tape-bars' finals

PROBE_VERDICT

Co-Authored-By: Claude <actual executing model> <noreply@anthropic.com>
EOF
```

- [ ] **Step 9: Prove the guards**, `--file cli/data/rolling.py`, `TESTS=tests/test_rolling_extend.py`: the line's write moved ahead of the day's files, against `-k test_a_days_line_is_written_only_after_its_files`; the sidecar comparison made always equal, against `-k test_a_final_disagreeing_with_its_sidecar_is_refused_and_nothing_of_that_day_written`; the existing-destination refusal made an overwrite, against `-k test_no_existing_file_is_rewritten`; the byte-equal acceptance of an existing destination dropped, against `-k test_a_rerun_after_a_stop_between_files_and_line_completes_the_day`; the pending stop made a hole, against `-k test_day_d_plus_one_waits_while_d_is_pending`; `RESCAN_DAYS` dropped from the hole's bound, against `-k test_a_hole_is_written_only_past_the_rescan_window`; `prev` taken over the predecessor's parsed object re-serialised in place of its bytes, against `-k test_prev_is_the_sha256_of_the_predecessors_bytes`; the temporary name put under `out` in place of `staging`, against `-k test_only_finished_names_appear_under_the_outbox`; the explicit `0o2775` dropped from the directory creation, against `-k test_every_directory_is_group_writable_and_setgid`; the no-base refusal dropped, against `-k test_extend_refuses_an_outbox_without_a_base_line`; the manifest attestation of a base file dropped, against `-k test_the_base_refuses_a_source_file_its_manifest_does_not_attest` — each `KILLED`; then the message-only amend.
- [ ] **Step 10: The tree is clean** — `git status --porcelain`; Expected: empty.

---

### Task 3: The fetch attests the rolling canonical by its index

**Files:**
- Modify: `cli/data/sync.py` (`_verify_new_files`, :199-219, gains the chained arm)
- Test: `tests/test_data_sync.py`

**Interfaces:**
- Consumes: Task 1's `is_chained`, `walk_chain`, `head`; `_verify_new_files`' per-set loop.
- Produces: a fetch that refuses a chained set's file whose bytes disagree with the line naming it, refuses a fetched chain whose head does not walk, and reports a day file no line names yet as pending, unread.

**What this task decides, where the spec leaves it open:**
- For a set whose hub directory `is_chained`, the attestation is the union of every hub line's `files`, path to the sha256 of the bytes — the identity grade, never the manifests' frame-content grade — and each new parquet of the local copy is compared by its bytes; the manifest and vouched-sidecar arm is not consulted for it. After the per-file checks, `head` over the local copy must walk, or the fetch refuses naming the link. A new parquet no line names is logged as pending with its path and left in place, since no reader reaches a file but through a line.

- [ ] **Step 1: Read** spec 00125 D3 (the fetch); `cli/data/sync.py:109-236`; `tests/test_data_sync.py:1-40` and `:116-200`.
- [ ] **Step 2: Write the failing tests**, the hub tree built by `write_chain` under `tmp_path` and fetched through `fetch_hot` with the real `rsync`: `test_fetch_admits_a_rolling_day_file_matching_its_line`; `test_fetch_refuses_a_rolling_day_file_disagreeing_with_its_line` (one day file's byte flipped on the hub after its line was written); `test_fetch_leaves_a_rolling_day_file_no_line_names_pending` (a day file without its line: the fetch succeeds and the log names the file); `test_fetch_refuses_a_fetched_chain_whose_link_is_broken`.
- [ ] **Step 3: Run them and read the failure**

```bash
uv run pytest tests/test_data_sync.py -q -p no:cacheprovider -k "test_fetch_admits_a_rolling_day_file_matching_its_line or test_fetch_refuses_a_rolling_day_file_disagreeing_with_its_line or test_fetch_leaves_a_rolling_day_file_no_line_names_pending or test_fetch_refuses_a_fetched_chain_whose_link_is_broken"
```

Expected: the admit and pending cases fail on `attested by neither its manifest nor`, the two refusal cases on a refusal of that same text rather than the chain's.

- [ ] **Step 4: Implement** the arm per the decision above.
- [ ] **Step 5: Run the tests** — `uv run pytest tests/test_data_sync.py -q -p no:cacheprovider`; Expected: no failure.
- [ ] **Step 6: The consumers**

```bash
uv run pytest $(infra/scripts/consumers.sh cli/data/sync.py | grep -E '^tests/test_[^ ]*\.py$' | sort -u) -q -p no:cacheprovider
```

Expected: no failure.

- [ ] **Step 7: The commit gate**

```bash
git add cli/data/sync.py tests/test_data_sync.py && uv run pre-commit run -a
```

Expected: every hook `Passed` or `Skipped`.

- [ ] **Step 8: Commit**

```bash
git commit -F - <<'EOF'
feat(data): data fetch attests the rolling canonical's files by its index and leaves a file no line names pending

PROBE_VERDICT

Co-Authored-By: Claude <actual executing model> <noreply@anthropic.com>
EOF
```

- [ ] **Step 9: Prove the guards**, `--file cli/data/sync.py`, `TESTS=tests/test_data_sync.py`: the byte comparison made always equal, against `-k test_fetch_refuses_a_rolling_day_file_disagreeing_with_its_line`; the head walk after the checks dropped, against `-k test_fetch_refuses_a_fetched_chain_whose_link_is_broken`; the pending arm made a refusal, against `-k test_fetch_leaves_a_rolling_day_file_no_line_names_pending`; the chained arm's `is_chained` test made false, against `-k test_fetch_admits_a_rolling_day_file_matching_its_line` — each `KILLED`; then the message-only amend.
- [ ] **Step 10: The tree is clean** — `git status --porcelain`; Expected: empty.

---

### Task 4: The registry records the as-of line, and the conformance pass walks the chain from it

**Files:**
- Modify: `cli/registry/observed.py` (`read_rolling` beside `read_series`, :72-127; `block`, :129-139, unchanged), `tests/test_registry_conformance.py` (`conformance`, :59-87)
- Test: `tests/test_registry_observed.py`, `tests/test_registry_conformance.py`

**Interfaces:**
- Consumes: Task 1's `read_rolling`, `verify`, `line_relpath`; the registry's `compute_hash` (`cli/registry/record.py:35-36`), untouched.
- Produces, for Task 6: `ObservedReader.read_rolling(dataset: str, pair: str, interval: int, as_of: str, window: tuple[str, str] | None = None, accept_holes: bool = False) -> pl.DataFrame` and `ObservedReader.holes() -> dict[str, list[str]]`, the holes each dataset's reads accepted.

**What this task decides, where the spec leaves it open:**
- A rolling read records, for its dataset, `files` exactly `{line.relpath: line.sha256}` of the as-of line, and the rows and span of the frames it returns, accumulated as `read_series` accumulates them; it parses `as_of` as `YYYY-MM-DD` and `window` as `read_series` does (:98-117), refusing the same malformed bounds. A second rolling read of the same dataset at another as-of day is refused, and so is a `read_series` of a dataset already read as rolling, or the reverse. The manifest cross-check is not run for a rolling read: the chain attests every file at the identity grade.
- In the conformance pass, a cited relpath under `index/` whose bytes re-hash as recorded is then `verify`'d to its day; a `RollingError` is a finding with its text.

- [ ] **Step 1: Read** spec 00125 D2 (the registry, the proof); `cli/registry/observed.py`; `tests/test_registry_conformance.py:59-160`; `tests/test_registry_observed.py:1-60`.
- [ ] **Step 2: Write the failing tests** — in `tests/test_registry_observed.py`: `test_a_rolling_read_records_the_as_of_line_alone`; `test_a_rolling_pin_reproduces_one_block_read_twice` (two readers over one `write_chain` tree give equal blocks and equal `compute_hash`); `test_a_second_as_of_on_one_rolling_set_is_refused`; `test_a_rolling_read_honours_the_window_in_rows_and_span`. In `tests/test_registry_conformance.py`: `test_a_record_citing_a_line_walks_the_chain_and_a_broken_link_is_a_finding` (a record appended through `TrialRegistry.append` whose block names a `write_chain` tree's third day line and its sha256, written by hand as `_fabricated` writes its block; the pass rederives it; one byte of an earlier line flipped, the pass reads a finding naming that line).
- [ ] **Step 3: Run them and read the failure**

```bash
uv run pytest tests/test_registry_observed.py tests/test_registry_conformance.py -q -p no:cacheprovider -k "test_a_rolling_read_records_the_as_of_line_alone or test_a_rolling_pin_reproduces_one_block_read_twice or test_a_second_as_of_on_one_rolling_set_is_refused or test_a_rolling_read_honours_the_window_in_rows_and_span or test_a_record_citing_a_line_walks_the_chain_and_a_broken_link_is_a_finding"
```

Expected: the four observed cases fail on `ObservedReader` having no `read_rolling`; the conformance case fails at its broken-link half, the pass reading `rederived`.

- [ ] **Step 4: Implement** per the decisions above.
- [ ] **Step 5: Run the tests**

```bash
uv run pytest tests/test_registry_observed.py tests/test_registry_conformance.py tests/test_registry_store.py -q -p no:cacheprovider
```

Expected: no failure.

- [ ] **Step 6: The consumers**

```bash
uv run pytest $(infra/scripts/consumers.sh cli/registry/observed.py tests/test_registry_conformance.py | grep -E '^tests/test_[^ ]*\.py$' | sort -u) -q -p no:cacheprovider
```

Expected: no failure.

- [ ] **Step 7: The commit gate**

```bash
git add cli/registry/observed.py tests/test_registry_observed.py tests/test_registry_conformance.py && uv run pre-commit run -a
```

Expected: every hook `Passed` or `Skipped`.

- [ ] **Step 8: Commit**

```bash
git commit -F - <<'EOF'
feat(registry): a rolling read records its as-of index line, and the conformance pass walks the chain from it

PROBE_VERDICT

Co-Authored-By: Claude <actual executing model> <noreply@anthropic.com>
EOF
```

- [ ] **Step 9: Prove the guards**: in `cli/registry/observed.py`, `TESTS=tests/test_registry_observed.py`, the recorded `files` made every file the read opened, against `-k test_a_rolling_read_records_the_as_of_line_alone`; the second-as-of refusal dropped, against `-k test_a_second_as_of_on_one_rolling_set_is_refused`; the window dropped from the rolling read, against `-k test_a_rolling_read_honours_the_window_in_rows_and_span`; in `tests/test_registry_conformance.py`, `TESTS` the same file, the `verify` call dropped from `conformance`, against `-k test_a_record_citing_a_line_walks_the_chain_and_a_broken_link_is_a_finding` — each `KILLED`; then the message-only amend.
- [ ] **Step 10: The tree is clean** — `git status --porcelain`; Expected: empty.

---

### Task 5: The daily pass reads the rolling canonical's head on the hub

**Files:**
- Modify: `infra/scripts/ops_daily.py` (`ROLLING_CHECK`, `ROLLING_HUB`, `ROLLING_STALE_AFTER_DAYS` and `read_rolling_head` after `read_soak_verdict`, :968; `main`'s appends, :1314-1316, gain the row after the soak row)
- Test: `tests/test_ops_daily.py`

**Interfaces:**
- Consumes: Task 1's `line_days`, `walk_chain` and `verify_line`, imported inside the reader as `derive_soak_store` imports the engine's (:900-903); `Check` (:531).
- Produces: `ROLLING_CHECK = "rolling canonical head"`, `ROLLING_HUB = Path("/mnt/zhao-crypto/hot/ohlc-rolling")`, `ROLLING_STALE_AFTER_DAYS = 3`, `read_rolling_head(*, now: datetime, root: Path) -> Check`, keyword-only with no default.

**What this task decides, where the spec leaves it open:**
- `ok` is the newest line — read by `line_days`, never by `head`, which steps past a line whose files are absent — dated at or after `now`'s UTC date less three days, its chain walked from it and its own files re-hashed by `verify_line`; the value names the head's day, its age in days and the first twelve hex of its line's sha256, or why it failed. A root with no index, an unreadable mount or a `RollingError` is `unreadable: …` with `ok` false, never a pass.

- [ ] **Step 1: Read** spec 00125 D3 (the daily pass) and D7 (the check, its fixtures, its threshold); `infra/scripts/ops_daily.py:523-545`, `:720-830` and `:1264-1330`; `tests/test_ops_daily.py:3252-3330`.
- [ ] **Step 2: Write the failing tests**, the hub a `write_chain` tree under `tmp_path`: `test_the_rolling_head_is_ok_three_days_back`; `test_a_rolling_head_four_days_back_fails`; `test_a_rolling_head_whose_prev_disagrees_fails`; `test_a_rolling_head_naming_an_absent_file_fails`; `test_a_rolling_head_file_with_a_flipped_byte_fails`; `test_an_unreadable_rolling_hub_is_unreadable_not_ok`.
- [ ] **Step 3: Run them and read the failure**

```bash
uv run pytest tests/test_ops_daily.py -q -p no:cacheprovider -k "test_the_rolling_head_is_ok_three_days_back or test_a_rolling_head_four_days_back_fails or test_a_rolling_head_whose_prev_disagrees_fails or test_a_rolling_head_naming_an_absent_file_fails or test_a_rolling_head_file_with_a_flipped_byte_fails or test_an_unreadable_rolling_hub_is_unreadable_not_ok"
```

Expected: every case fails on `ops_daily` having no `read_rolling_head`.

- [ ] **Step 4: Implement** per the decision above, its strings carrying no internal term.
- [ ] **Step 5: Run the tests** — `uv run pytest tests/test_ops_daily.py tests/test_ops_daily_soak.py -q -p no:cacheprovider`; Expected: no failure.
- [ ] **Step 6: The consumers**

```bash
uv run pytest $(infra/scripts/consumers.sh infra/scripts/ops_daily.py | grep -E '^tests/test_[^ ]*\.py$' | sort -u) tests/test_internal_terms_not_operator_visible.py -q -p no:cacheprovider
```

Expected: no failure.

- [ ] **Step 7: The commit gate**

```bash
git add infra/scripts/ops_daily.py tests/test_ops_daily.py && uv run pre-commit run -a
```

Expected: every hook `Passed` or `Skipped`.

- [ ] **Step 8: Commit**

```bash
git commit -F - <<'EOF'
feat(ops): the daily pass reads the rolling canonical's head on the hub

PROBE_VERDICT

Co-Authored-By: Claude <actual executing model> <noreply@anthropic.com>
EOF
```

- [ ] **Step 9: Prove the guards**, `--file infra/scripts/ops_daily.py`, `TESTS=tests/test_ops_daily.py`: `ROLLING_STALE_AFTER_DAYS` made 4, against `-k test_a_rolling_head_four_days_back_fails`; the chain walk from the newest line dropped, against `-k test_a_rolling_head_whose_prev_disagrees_fails`; `verify_line` dropped, against `-k test_a_rolling_head_file_with_a_flipped_byte_fails` and `-k test_a_rolling_head_naming_an_absent_file_fails`; the unreadable arm's `ok=False` made `ok=True`, against `-k test_an_unreadable_rolling_hub_is_unreadable_not_ok` — each `KILLED`; then the message-only amend.
- [ ] **Step 10: The tree is clean** — `git status --porcelain`; Expected: empty.

---

### Task 6: `research eval` reads the rolling canonical at a required as-of day

**Files:**
- Modify: `cli/research/command.py` (`--as-of`, `--accept-holes`; the series check, :87-90; the report, :100-103), `cli/research/subjects.py` (`Subject.build`'s signature, :22-27; `_capturing_union`, :34-40; the two builds, :43-67)
- Test: `tests/test_research_command.py`

**Interfaces:**
- Consumes: Task 1's `is_chained` and `pairs`; Task 4's `ObservedReader.read_rolling` and `holes`.
- Produces: `zcrypto research eval --dataset ohlc-rolling --as-of YYYY-MM-DD [--accept-holes]`; `Subject.build(reader, dataset, window, as_of=None, accept_holes=False)`.

**What this task decides, where the spec leaves it open:**
- A chained dataset requires `--as-of`, and an unchained one refuses `--as-of` and `--accept-holes`, each before the fit. For a chained set the series check reads `pairs` — a required asset's `<asset>/EUR` absent from the set is refused, naming every one — and `_capturing_union` hands each path `load_union` composes to `read_rolling` as the pair its first two parts name and the interval its stem names. The report prints `as of: <day>` under `window:` and each accepted hole as `hole: <pair> <day>`.

- [ ] **Step 1: Read** spec 00125 D4 (the searches); `cli/research/command.py`; `cli/research/subjects.py`; `cli/portfolio/record44_legs.py:48-60` (`load_union`); `tests/test_research_command.py:1-100` and `:196-260`.
- [ ] **Step 2: Write the failing tests**, the set a `write_chain` tree over the subject's ten `/EUR` assets: `test_eval_on_a_chained_set_requires_as_of`; `test_eval_on_an_unchained_set_refuses_as_of`; `test_eval_on_the_rolling_set_records_the_as_of_line` (with `--register` into a `tmp_path` registry: the record's `datasets` is the line alone and its `dataset_hash` derives from it); `test_eval_refuses_a_hole_and_reads_across_it_with_accept_holes`; `test_a_chained_set_missing_a_required_pair_is_refused_naming_it`; `test_the_window_reaches_the_rolling_reads`.
- [ ] **Step 3: Run them and read the failure**

```bash
uv run pytest tests/test_research_command.py -q -p no:cacheprovider -k "test_eval_on_a_chained_set_requires_as_of or test_eval_on_an_unchained_set_refuses_as_of or test_eval_on_the_rolling_set_records_the_as_of_line or test_eval_refuses_a_hole_and_reads_across_it_with_accept_holes or test_a_chained_set_missing_a_required_pair_is_refused_naming_it or test_the_window_reaches_the_rolling_reads"
```

Expected: every case fails on `No such option: --as-of` or on the missing-series refusal of `<asset>/EUR/<interval>.parquet`.

- [ ] **Step 4: Implement** per the decision above; the two options' help text operator-readable with no internal term.
- [ ] **Step 5: Run the tests** — `uv run pytest tests/test_research_command.py tests/test_research_control.py -q -p no:cacheprovider`; Expected: no failure, the control skipping in a worktree.
- [ ] **Step 6: The consumers**

```bash
uv run pytest $(infra/scripts/consumers.sh cli/research/command.py cli/research/subjects.py | grep -E '^tests/test_[^ ]*\.py$' | sort -u) tests/test_cli_help_hygiene.py tests/test_internal_terms_not_operator_visible.py -q -p no:cacheprovider
```

Expected: no failure.

- [ ] **Step 7: The commit gate**

```bash
git add cli/research/command.py cli/research/subjects.py tests/test_research_command.py && uv run pre-commit run -a
```

Expected: every hook `Passed` or `Skipped`.

- [ ] **Step 8: Commit**

```bash
git commit -F - <<'EOF'
feat(research): research eval reads the rolling canonical at a required as-of day

PROBE_VERDICT

Co-Authored-By: Claude <actual executing model> <noreply@anthropic.com>
EOF
```

- [ ] **Step 9: Prove the guards**: in `cli/research/command.py`, `TESTS=tests/test_research_command.py`, the as-of requirement dropped, against `-k test_eval_on_a_chained_set_requires_as_of`; the unchained refusal dropped, against `-k test_eval_on_an_unchained_set_refuses_as_of`; the chained series check made the file check, against `-k test_a_chained_set_missing_a_required_pair_is_refused_naming_it`; `--accept-holes` not handed to the build, against `-k test_eval_refuses_a_hole_and_reads_across_it_with_accept_holes`; in `cli/research/subjects.py`, the window dropped from the rolling read, against `-k test_the_window_reaches_the_rolling_reads` — each `KILLED`; then the message-only amend.
- [ ] **Step 10: The tree is clean** — `git status --porcelain`; Expected: empty.

---

### Task 7: `engine seed` copies an absent store file from the rolling canonical at its head

**Files:**
- Modify: `cli/engine/command.py` (`seed`, :374-418; the `CANONICAL_DIR` comment, :82-85, whose second sentence names the frozen sibling the seed no longer reads)
- Test: `tests/test_engine_command.py` (the seed tests, :160-283)

**Interfaces:**
- Consumes: Task 1's `head` and `read_rolling`; `seed_store(store_dir, canonical_dir)` (`cli/engine/store.py:341-407`), unchanged; `BASKET` and `GRID_INTERVALS` (`cli/engine/store.py:24-43`).
- Produces: a seed whose canonical, for an absent store file, is the rolling set under the configured data root at its local head.

**What this task decides, where the spec leaves it open:**
- `seed_store` keeps its directory argument: the seed writes, for every `BASKET` pair and `GRID_INTERVALS` interval, `read_rolling`'s frame at the head into a temporary store-shaped directory, `<scratch>/<BASE>/<QUOTE>/<interval>.parquet`, and hands it over, so `cli/engine/store.py` and its tests are unchanged, which the spec's file list leaves open. Its summary names `canonical ohlc-rolling as of <day> (<first twelve hex>)`; a `RollingError` or a missing set is the seed's refusal with its existing prefix (:396-401). A seed over a complete store reads no rolling set, as it reads no canonical today.

- [ ] **Step 1: Read** spec 00125 D4 (the seed); `cli/engine/command.py:80-90` and `:374-418`; `cli/engine/store.py:341-407`; `tests/test_engine_command.py:160-283`.
- [ ] **Step 2: Write the failing tests** — `test_seed_copies_absent_series_from_the_rolling_set_at_its_head` (a `write_chain` tree over the twelve `BASKET` pairs as the configured data root's `ohlc-rolling`; `seed_store` stubbed to record the directory it was handed and the frames under it, each equal to `read_rolling` at the head); `test_seed_refuses_naming_the_rolling_set_when_it_cannot_be_read` (replacing `test_seed_refuses_when_no_whole_frozen_set_resolves`); `test_seed_prints_per_pair_overlap_summary`, `test_seed_engine_error_is_a_clean_exit_1`, `test_seed_refuses_without_a_configured_data_dir` and `test_seed_reads_no_canonical_when_every_store_file_is_present` re-pointed from `resolve_canonical_root` to the rolling set.
- [ ] **Step 3: Run them and read the failure**

```bash
uv run pytest tests/test_engine_command.py -q -p no:cacheprovider -k "test_seed_copies_absent_series_from_the_rolling_set_at_its_head or test_seed_refuses_naming_the_rolling_set_when_it_cannot_be_read"
```

Expected: both fail, the seed resolving a frozen sibling.

- [ ] **Step 4: Implement** per the decision above and re-true the comment.
- [ ] **Step 5: Run the tests** — `uv run pytest tests/test_engine_command.py -q -p no:cacheprovider`; Expected: no failure.
- [ ] **Step 6: The consumers**

```bash
uv run pytest $(infra/scripts/consumers.sh cli/engine/command.py | grep -E '^tests/test_[^ ]*\.py$' | sort -u) tests/test_cli_help_hygiene.py -q -p no:cacheprovider
```

Expected: no failure.

- [ ] **Step 7: The commit gate**

```bash
git add cli/engine/command.py tests/test_engine_command.py && uv run pre-commit run -a
```

Expected: every hook `Passed` or `Skipped`.

- [ ] **Step 8: Commit**

```bash
git commit -F - <<'EOF'
feat(engine): engine seed copies an absent store file from the rolling canonical at its head

PROBE_VERDICT

Co-Authored-By: Claude <actual executing model> <noreply@anthropic.com>
EOF
```

- [ ] **Step 9: Prove the guards**, `--file cli/engine/command.py`, `TESTS=tests/test_engine_command.py`: the head replaced by the base line, against `-k test_seed_copies_absent_series_from_the_rolling_set_at_its_head`; the `RollingError` arm dropped, against `-k test_seed_refuses_naming_the_rolling_set_when_it_cannot_be_read`; the absent-only gate on the rolling read dropped, against `-k test_seed_reads_no_canonical_when_every_store_file_is_present` — each `KILLED`; then the message-only amend.
- [ ] **Step 10: The tree is clean** — `git status --porcelain`; Expected: empty.

---

### Task 8: The universe rebuild reads the rolling canonical; the reach round and the frozen-sibling resolvers retire

**Files:**
- Modify: `cli/data/rebuild.py` (`_refresh_universe`, :184-287, on the rolling set; `_rebuild_ohlc_reach`, :77-90, its import, :27, and its `REBUILDABLE` entry, :293, deleted; `_STAMPED_REACH`, `_STAMPED_FULL`, `_basket_legs`, `_missing_from_whole_set`, `resolve_canonical_root` and `resolve_ohlc_source`, :126-181, deleted; `_require_fresh_ohlc`'s refusal text, :117-123, naming the rolling set), `cli/data/command.py` (the `rebuild` help, :72), `zcrypto.toml` (`ohlc-reach` out of `authored_sets`, :12), `cli/engine/store.py` (:104 and :314, each naming `cli/ohlc/reach.py` as a sibling), `cli/ohlc/dataset.py` (:13-14), `cli/ohlc/seam.py` (:1)
- Delete: `cli/ohlc/reach.py`, `tests/test_ohlc_reach.py`
- Test: `tests/test_data_rebuild.py` (the universe tests, :162-530, re-pointed; the resolver tests, :465-484 and :521-581, and the reach tests, :584-670, deleted), `tests/test_data_command.py` (`test_rebuild_ohlc_reach_aborts_naming_a_canonical_file_it_cannot_join`, :185-219, deleted); `tests/test_data_rebuild.py::test_every_rebuildable_dataset_is_an_authored_set` (:673), unchanged, holds `REBUILDABLE`'s names inside `authored_sets`, so `ohlc-reach` leaves both in this commit; `tests/test_data_manifest.py` (`_PRODUCERS`, :436-443, and its reach case, :452-453, lose `cli/ohlc/reach.py`)

**Interfaces:**
- Consumes: Task 1's `head`, `pairs`, `read_rolling`, `ROLLING_SET`.
- Produces: a universe file whose provenance is `snapshot_sha256`, `ohlc_dataset_hash` (the head line's sha256), `ohlc_dataset_dir` (`ohlc-rolling`), `ohlc_as_of` (the head's day) and `ohlc_stalest_daily_bar`.

**What this task decides, where the spec leaves it open:**
- The universe reads each candidate symbol's 1440 frame by `read_rolling` at the head, holes refused, the missing-leg refusal reading `pairs`; the manifest identity block (:239-270) goes, the head line being the identity. `data rebuild ohlc-reach` becomes an unknown set, refused by the existing arm. `cli/ohlc/fetch.py` and `cli/ohlc/seam.py` stay, the engine's store importing both.

- [ ] **Step 1: Read** spec 00125 D4 (the universe, the resolvers) and D5; `cli/data/rebuild.py`; `tests/test_data_rebuild.py:140-670`; `tests/test_data_command.py:180-225`; `tests/test_data_manifest.py:360-460`.
- [ ] **Step 2: Write the failing tests** — `test_refresh_universe_reads_the_rolling_set_at_its_head`; `test_refresh_universe_provenance_names_the_set_the_as_of_and_the_line`; `test_refresh_universe_refuses_a_rolling_set_whose_chain_does_not_walk` (replacing the two manifest refusals, :244-296); `test_rebuild_refuses_ohlc_reach_as_an_unknown_set`; the remaining universe tests' fixtures built by `write_chain` in place of a manifest-bearing `ohlc-full` or reach sibling, their freshness cases unchanged in what they assert.
- [ ] **Step 3: Run them and read the failure**

```bash
uv run pytest tests/test_data_rebuild.py -q -p no:cacheprovider -k "test_refresh_universe_reads_the_rolling_set_at_its_head or test_refresh_universe_provenance_names_the_set_the_as_of_and_the_line or test_refresh_universe_refuses_a_rolling_set_whose_chain_does_not_walk or test_rebuild_refuses_ohlc_reach_as_an_unknown_set"
```

Expected: all four fail, the universe reading `resolve_ohlc_source`'s source and `ohlc-reach` rebuilding.

- [ ] **Step 4: Implement** the universe's source and delete what Files names; re-true the four comments the Files entry names; then confirm nothing names the deleted code:

```bash
git grep -n -E 'reach_round|cli\.ohlc\.reach|cli/ohlc/reach\.py|resolve_canonical_root|resolve_ohlc_source|_STAMPED_(REACH|FULL)' -- cli tests infra .claude zcrypto.toml ':!*vault*' ':!*.sops.*'
```

Expected: no output.

- [ ] **Step 5: Run the tests**

```bash
uv run pytest tests/test_data_rebuild.py tests/test_data_command.py tests/test_data_manifest.py tests/test_universe_provenance.py -q -p no:cacheprovider
```

Expected: no failure.

- [ ] **Step 6: The consumers**

```bash
uv run pytest $(infra/scripts/consumers.sh cli/data/rebuild.py cli/data/command.py cli/ohlc/reach.py cli/ohlc/seam.py cli/ohlc/dataset.py cli/engine/store.py zcrypto.toml | grep -E '^tests/test_[^ ]*\.py$' | sort -u) tests/test_cli_help_hygiene.py -q -p no:cacheprovider
```

Expected: no failure; `tests/test_ohlc_reach.py`, deleted, is absent from the list.

- [ ] **Step 7: The commit gate**

```bash
git add cli/data/rebuild.py cli/data/command.py zcrypto.toml cli/engine/store.py cli/ohlc/dataset.py cli/ohlc/seam.py cli/ohlc/reach.py tests/test_ohlc_reach.py tests/test_data_rebuild.py tests/test_data_command.py tests/test_data_manifest.py && uv run pre-commit run -a
```

Expected: every hook `Passed` or `Skipped`.

- [ ] **Step 8: Commit**

```bash
git commit -F - <<'EOF'
feat(data): the universe rebuild reads the rolling canonical; the reach round and the frozen-sibling resolvers retire

PROBE_VERDICT

Co-Authored-By: Claude <actual executing model> <noreply@anthropic.com>
EOF
```

- [ ] **Step 9: Prove the guards**, `--file cli/data/rebuild.py`, `TESTS=tests/test_data_rebuild.py`: the head replaced by the base line, against `-k test_refresh_universe_reads_the_rolling_set_at_its_head`; `ohlc_as_of` dropped from the provenance, against `-k test_refresh_universe_provenance_names_the_set_the_as_of_and_the_line`; the head read made a listing of the newest line without its walk, against `-k test_refresh_universe_refuses_a_rolling_set_whose_chain_does_not_walk`; `"ohlc-reach": _refresh_universe` added to `REBUILDABLE`, against `-k test_rebuild_refuses_ohlc_reach_as_an_unknown_set` — each `KILLED`; then the message-only amend.
- [ ] **Step 10: The tree is clean** — `git status --porcelain`; Expected: empty.

---

### Task 9: The tape-bars runner extends the rolling canonical after each sweep

**Files:**
- Modify: `infra/ansible/roles/ops/templates/tape-bars.sh.j2` (the extension after the gauge export, :97-126, before `exit "$rc"`, :128; the comment at :9-10, which claims a NAS pull of tape-bars' output that no channel makes), `infra/ansible/roles/ops/defaults/main.yml` (`ops_rolling_staging_subdir: hot-out-staging` after `ops_hot_out_subdir`, :33), `infra/ansible/roles/ops/tasks/main.yml` (a staging-directory task after the outbox's, :245-251; the outbox group's gid looked up beside the data user's uid and gid, :339-347)
- Test: `tests/test_infra_tape_bars_template.py` (`CONTEXT`, :22-35, gains `ops_hot_out_subdir`, `ops_rolling_staging_subdir` and `ops_hot_gid`), `tests/test_infra_converge_guards.py`

**Interfaces:**
- Consumes: Task 2's `zcrypto data rolling extend` and its summary line.
- Produces: the unit that, after each sweep, runs the extension in the same pinned image and exits with the sweep's code when the sweep failed, else the extension's.

**What this task decides, where the spec leaves it open:**
- The extension is a second `docker run --rm --pull never --name zcrypto-rolling-extend --user "{{ ops_uid }}:{{ ops_gid }}" --group-add "{{ ops_hot_gid }}"`, mounting `{{ ops_data_dir }}:/data` and `{{ ops_data_dir }}/{{ ops_tape_bars_subdir }}:/data/{{ ops_tape_bars_subdir }}:ro` and nothing else, running `data rolling extend --tape-root "/data/{{ ops_tape_bars_subdir }}" --out "/data/{{ ops_hot_out_subdir }}/ohlc-rolling" --staging "/data/{{ ops_rolling_staging_subdir }}"`: the outbox and the staging directory sit on one mount, so the writer's rename stays on one filesystem, and the tape tree is read-only to it. It runs after the gauge export, so its outcome never rewrites the sweep's gauges; its output is replayed to the journal as the sweep's is.
- `--group-add` is load-bearing: `--user` with a numeric uid and gid gives the container no supplementary group, and the base's directories, created by the research user, are writable to the outbox's group alone, `zcrypto-hot` (gid 1002 on `zcrypto-ops`, `zcrypto-data` a member — `getent group zcrypto-hot`). `ops_hot_gid` is set from an `ansible.builtin.getent` of `{{ ops_hot_group }}` beside the uid and gid derivation, so every digest-gated block can read it.
- The staging directory is the outbox's sibling, `{{ ops_data_dir }}/{{ ops_rolling_staging_subdir }}`, owner `{{ ops_data_user }}`, group `{{ ops_hot_group }}`, mode `"2775"`, ungated as the outbox is: the NAS pull pins `hot-out` alone, so nothing under the staging directory is ever pulled.

- [ ] **Step 1: Read** spec 00125 D3; `infra/ansible/roles/ops/templates/tape-bars.sh.j2`; `infra/ansible/roles/ops/tasks/main.yml:238-252`; `tests/test_infra_tape_bars_template.py`; `tests/test_infra_converge_guards.py:20-80` and `:2150-2170`.
- [ ] **Step 2: Write the failing tests** — in `tests/test_infra_tape_bars_template.py`, a helper slicing the second `docker run` up to its redirection: `test_the_extend_step_hands_the_cli_the_tape_the_outbox_and_the_staging` (the CLI's own option names read through `get_command(app)`, as the materialize case reads its positionals); `test_the_extend_step_mounts_the_data_dir_once_and_the_tape_read_only` (the mounts exactly the two); `test_the_extend_step_runs_as_the_data_user_in_the_outbox_group` (`--user 998:998` and `--group-add` with `CONTEXT`'s `ops_hot_gid`); `test_the_extend_step_runs_after_the_gauges_are_written` (its `docker run` after `mv "$tmp" "$PROM"`); `test_a_failed_extend_fails_the_unit_and_a_failed_sweep_keeps_its_own_rc` (the tail from the extension to `exit` run in `bash` with `docker` a shell function answering a given code: sweep 0 and extension 1 exit 1, sweep 2 and extension 0 exit 2, both 0 exit 0). In `tests/test_infra_converge_guards.py`: `test_the_rolling_staging_dir_is_the_outboxs_sibling_with_its_owner_group_and_mode` (the task named `ensure the rolling canonical's staging directory exists` by `find_task(load_tasks(OPS_TASKS), …)`: its path, owner, group and mode as above, no `when`, after the outbox's task by `task_index`); `test_the_outbox_groups_gid_is_derived_beside_the_data_users` (an `ansible.builtin.getent` of `{{ ops_hot_group }}` in the group database and a `set_fact` of `ops_hot_gid` from it, both before the first digest-gated block).
- [ ] **Step 3: Run them and read the failure**

```bash
uv run pytest tests/test_infra_tape_bars_template.py tests/test_infra_converge_guards.py -q -p no:cacheprovider -k "test_the_extend_step_hands_the_cli_the_tape_the_outbox_and_the_staging or test_the_extend_step_mounts_the_data_dir_once_and_the_tape_read_only or test_the_extend_step_runs_as_the_data_user_in_the_outbox_group or test_the_extend_step_runs_after_the_gauges_are_written or test_a_failed_extend_fails_the_unit_and_a_failed_sweep_keeps_its_own_rc or test_the_rolling_staging_dir_is_the_outboxs_sibling_with_its_owner_group_and_mode or test_the_outbox_groups_gid_is_derived_beside_the_data_users"
```

Expected: the five template cases fail on the absent second `docker run`; the two guard cases on the absent tasks.

- [ ] **Step 4: Implement** per the decisions above; correct the :9-10 comment to say the tree stays on the ops host and the rolling set's day files reach the NAS through the outbox.
- [ ] **Step 5: Run the tests**

```bash
uv run pytest tests/test_infra_tape_bars_template.py tests/test_infra_converge_guards.py tests/test_infra_shell_templates_render.py -q -p no:cacheprovider
```

Expected: no failure.

- [ ] **Step 6: The consumers**

```bash
uv run pytest $(infra/scripts/consumers.sh infra/ansible/roles/ops/templates/tape-bars.sh.j2 infra/ansible/roles/ops/defaults/main.yml infra/ansible/roles/ops/tasks/main.yml | grep -E '^tests/test_[^ ]*\.py$' | sort -u) tests/test_internal_terms_not_operator_visible.py -q -p no:cacheprovider
```

Expected: no failure.

- [ ] **Step 7: The commit gate**

```bash
git add infra/ansible/roles/ops/templates/tape-bars.sh.j2 infra/ansible/roles/ops/defaults/main.yml infra/ansible/roles/ops/tasks/main.yml tests/test_infra_tape_bars_template.py tests/test_infra_converge_guards.py && uv run pre-commit run -a
```

Expected: every hook `Passed` or `Skipped`, `ansible-lint` and `shellcheck` among them.

- [ ] **Step 8: Commit**

```bash
git commit -F - <<'EOF'
feat(ops): the tape-bars runner extends the rolling canonical after each sweep

PROBE_VERDICT

Co-Authored-By: Claude <actual executing model> <noreply@anthropic.com>
EOF
```

- [ ] **Step 9: Prove the guards**: in `tape-bars.sh.j2`, `TESTS=tests/test_infra_tape_bars_template.py`, the extension's `--staging` pointed under the outbox, against `-k test_the_extend_step_hands_the_cli_the_tape_the_outbox_and_the_staging`; the `:ro` dropped from the tape mount, against `-k test_the_extend_step_mounts_the_data_dir_once_and_the_tape_read_only`; the `--group-add` line dropped, against `-k test_the_extend_step_runs_as_the_data_user_in_the_outbox_group`; the extension moved above the gauge export (a range move written against the committed text), against `-k test_the_extend_step_runs_after_the_gauges_are_written`; the rc combination made `rc=$extend_rc`, against `-k test_a_failed_extend_fails_the_unit_and_a_failed_sweep_keeps_its_own_rc`; in `tasks/main.yml`, `TESTS=tests/test_infra_converge_guards.py`, the staging task's mode made `"0755"`, against `-k test_the_rolling_staging_dir_is_the_outboxs_sibling_with_its_owner_group_and_mode`; the gid lookup's `database: group` made `database: passwd`, against `-k test_the_outbox_groups_gid_is_derived_beside_the_data_users` — each `KILLED`; then the message-only amend.
- [ ] **Step 10: The tree is clean** — `git status --porcelain`; Expected: empty.

---

### Task 10: The catalog, the fleet reference and the README name the rolling canonical

**Files:**
- Modify: `docs/reference/data-catalog-full.md` (a `### ohlc-rolling` section in `## hot` before `### ohlc-full`; `ohlc-full`'s :13 and `ohlc-15m`'s :67, which still name the retired Q2 siblings; `ohlc-reach`'s :69-80; tape-bars' consumers line, :142; the `engine-store` bullet, :154), `docs/reference/fleet.md` (:66's `hot/` list), `README.md` (the `data` section's reach paragraphs and rebuild list, :328-337, and its universe-source clause, :340; the `research eval` table, :352-368; the `engine seed` row, :112)

- [ ] **Step 1: Read** spec 00125 D8, whose sentences these edits carry out, and the spec's measured basis, from which every figure the catalog states is copied; each page's lines above.
- [ ] **Step 2: The catalog and the fleet reference** — the new section states the set, its three trees, its seam at 2026-10-01, its vwap change, its index and its holes, its author and channel, and how a search names it; `ohlc-full` and `ohlc-15m` are frozen pins for the records citing them, new work reading `ohlc-rolling`, and drop the Q2 names; `ohlc-reach` says its producer retired, records the REST disagreement of D5 and names the two sets the hub keeps and why. New paragraphs one line each; a universal word in a new list item of `fleet.md` carries its `(set: …; count: …)` or `(no count command: …)`.

```bash
uv run python infra/scripts/guidance-guard.py --uncounted docs/reference/fleet.md
```

Expected: no output.

- [ ] **Step 3: The README** — the `data` section gains the `rolling` group's three commands with their options, loses the reach paragraphs and `ohlc-reach` from the rebuild list, and names the rolling set as the universe's source; `research eval` gains `--as-of` and `--accept-holes`; `engine seed`'s row names the rolling set at its head; no internal term enters.
- [ ] **Step 4: The consumers**

```bash
uv run pytest $(infra/scripts/consumers.sh docs/reference/data-catalog-full.md docs/reference/fleet.md README.md | grep -E '^tests/test_[^ ]*\.py$' | sort -u) tests/test_internal_terms_not_operator_visible.py -q -p no:cacheprovider
```

Expected: no failure.

- [ ] **Step 5: The commit gate and the two commits** — the reference pages first, then the README, each staged by path and gated:

```bash
git add docs/reference/data-catalog-full.md docs/reference/fleet.md && uv run pre-commit run -a && git commit -F - <<'EOF'
docs(reference): the catalog and the fleet reference name the rolling canonical, and the reach round retires

Co-Authored-By: Claude <actual executing model> <noreply@anthropic.com>
EOF
```

```bash
git add README.md && uv run pre-commit run -a && git commit -F - <<'EOF'
docs(readme): the data, research and engine rows read the rolling canonical

Co-Authored-By: Claude <actual executing model> <noreply@anthropic.com>
EOF
```

Expected: each commit made, its hooks `Passed` or `Skipped`; `mdformat` rewrites the README where it must, re-staged and the gate re-run.

- [ ] **Step 6: The tree is clean** — `git status --porcelain`; Expected: empty.

---

### Task 11: The ops runbook's section for the head check

**Files:**
- Modify: `infra/runbooks/ops.md` (a section after `## zcrypto-ops-tapebars-not-advancing — ALERT`, :134)

- [ ] **Step 1: Load `zcrypto-refine-rules`** and measure before: the runbook-read ratio as `tests/test_ops_daily.py::test_most_read_only_diagnostics_are_autonomous_on_ops` computes it against its 0.70 floor:

```bash
uv run python -c 'import tests.test_ops_daily as t; r=[c for c in t._runbook_commands() if not t._destructive(c)]; a=[c for c in r if t.ops_daily.classify_action(chr(96)+c+chr(96), host="ops", resolve=t._identity) is t.ops_daily.Tier.AUTONOMOUS]; print(f"{len(a)}/{len(r)}")'
```

Expected: one `<autonomous>/<read-only>` reading, recorded for the pull request body.

- [ ] **Step 2: The section** — `<a name="rolling-canonical-head"></a>` above `## rolling-canonical-head — PROCEDURE: reading a failing row`: a PROCEDURE, `infra/runbooks/README.md`'s kind whose trigger is the intent its heading states, since the pass names no runbook anchor (`tests/test_ops_daily.py::test_every_runbook_citation_the_instrument_itself_prints_resolves` would hold one it did), and Task 12's skill paragraph names it by file and anchor. Its four parts in the README's order: what the row reads; what its three failing shapes mean — a newest line older than three days, a broken link, an absent or changed file; and for each the read-only commands that tell them apart — `zcrypto data rolling verify --root <the hub or the outbox> --as-of <day>`, the tape-bars unit's journal, `zcrypto_tapebars_days_unhealed` for a head held by a pending hole; no internal term; each read-only command one the daily pass's classifier reads as autonomous.

```bash
uv run python infra/scripts/guidance-guard.py --uncounted infra/runbooks/ops.md
```

Expected: no output.

- [ ] **Step 3: Measure after** — Step 1's command; Expected: at or above 0.70, the reading recorded beside Step 1's.
- [ ] **Step 4: The consumers**

```bash
uv run pytest $(infra/scripts/consumers.sh infra/runbooks/ops.md | grep -E '^tests/test_[^ ]*\.py$' | sort -u) tests/test_internal_terms_not_operator_visible.py tests/test_runbook_internal_tokens.py tests/test_runbook_triggers.py tests/test_guidance_guard.py tests/test_guidance_refs_resolve.py -q -p no:cacheprovider
```

Expected: no failure.

- [ ] **Step 5: The commit gate and commit**

```bash
git add infra/runbooks/ops.md && uv run pre-commit run -a && git commit -F - <<'EOF'
docs(runbooks): the ops runbook reads the rolling canonical head row

Co-Authored-By: Claude <actual executing model> <noreply@anthropic.com>
EOF
```

Expected: the commit made, its hooks `Passed` or `Skipped`.

- [ ] **Step 6: The tree is clean** — `git status --porcelain`; Expected: empty.

---

### Task 12: The daily-ops skill reads the row

**Files:**
- Modify: `.claude/skills/zcrypto-daily-ops/SKILL.md` (a paragraph after the `soak verdict` row's, :58)

- [ ] **Step 1: Load `zcrypto-refine-rules`**; read `.claude/skills/zcrypto-daily-ops/SKILL.md:40-70`.
- [ ] **Step 2: The paragraph** — the `rolling canonical head` row is the rolling canonical's freshness and chain on the hub; a failing row is read by `infra/runbooks/ops.md#rolling-canonical-head`, Task 11's section, its anchor read back after the edit (`grep -c '<a name="rolling-canonical-head"></a>' infra/runbooks/ops.md` → `1`), and none of its states is a host action the pass takes. The skill's name and description are unchanged, so the commit carries no `Ambient grows by` line.
- [ ] **Step 3: The consumers**

```bash
uv run pytest $(infra/scripts/consumers.sh .claude/skills/zcrypto-daily-ops/SKILL.md | grep -E '^tests/test_[^ ]*\.py$' | sort -u) tests/test_guidance_refs_resolve.py -q -p no:cacheprovider
```

Expected: no failure.

- [ ] **Step 4: The commit gate and commit**

```bash
git add .claude/skills/zcrypto-daily-ops/SKILL.md && uv run pre-commit run -a && git commit -F - <<'EOF'
claude(skills): the daily-ops skill reads the rolling canonical head row

Co-Authored-By: Claude <actual executing model> <noreply@anthropic.com>
EOF
```

Expected: the commit made, `claude-kind files not mixed with other kinds` `Passed`.

- [ ] **Step 5: The tree is clean** — `git status --porcelain`; Expected: empty.

---

### Task 13: The sweep and the body

**Files:** none new.

- [ ] **Step 1: The gate and the counts**

```bash
uv run pre-commit run -a && infra/scripts/count-list.sh probe-verdicts-without-the-script prose-only-commits-without-the-prover
```

Expected: every hook `Passed` or `Skipped`; `prose-only-commits-without-the-prover` `0`; `probe-verdicts-without-the-script` what it read at this branch's base, `1` at `f70be7dae` — develop's `65997b3bd`, a plan commit before this branch — so the branch's own commits add none.

- [ ] **Step 2: The branch's own tests together**

```bash
uv run pytest tests/test_rolling_reader.py tests/test_rolling_extend.py tests/test_data_sync.py tests/test_registry_observed.py tests/test_registry_conformance.py tests/test_ops_daily.py tests/test_research_command.py tests/test_engine_command.py tests/test_data_rebuild.py tests/test_data_command.py tests/test_data_manifest.py tests/test_infra_tape_bars_template.py tests/test_infra_converge_guards.py tests/test_data_gated_run.py tests/test_cli_help_hygiene.py tests/test_internal_terms_not_operator_visible.py -q -p no:cacheprovider
```

Expected: no failure; the two data-gated cases of `tests/test_rolling_extend.py` skipped in the worktree, their run the Rollout's R6.

- [ ] **Step 3: The pull request body** (through `open-pr`): `## Spec / Plan` names 00125; the read line, the tip and the probes; the `Fable floor substituted by Opus: <reason>` line where the gate asks it (`uv run python infra/scripts/merge-gate.py --fable-paths`); `## Changes` from the diff; Task 11's runbook-read ratio, before and after.

---

## Rollout (attended)

**Operator steps.** Nothing below is an executor step: each reaches the ops host's live trees, the NAS, the hub or the fleet. `W$` is a shell on this workstation, `zcrypto-ops`, at the main checkout's root on merged `develop`. `KRAKEN` is the whole-feed read, `curl -fsS https://status.kraken.com/api/v2/scheduled-maintenances.json | jq .`, read entire and judged by `.claude/rules/fleet-deploys.md`'s test, at planning and again immediately before the converge. `OUTBOX` is `/var/lib/zcrypto-ops/hot-out/ohlc-rolling`, `STAGING` is `/var/lib/zcrypto-ops/hot-out-staging`, `HUB` is `/mnt/zhao-crypto/hot/ohlc-rolling`.

**Stop conditions.** A converge preview naming a file outside the ops role's runner scripts, units, defaults-driven directories and its compose files holds the rollout until the owner has read it. A `RollingError` from `base`, `extend` or `verify`, a fetch refusal, or a head row that does not read ok at R7 stops the rollout for the owner; no file under `OUTBOX` or `HUB` is edited or deleted by hand to get past it — the outbox and the hub never rewrite, so a wrong file is the owner's question, never an operator's fix.

**R1. The pull request** (after Task 13). Through `open-pr`; the `pre-review` workflow over the range's prose and messages, then `review` once the branch is complete, `re-review` over a fix range at most twice, every reviewer on Opus.

**R2. The merge.** `merge-pr`, then `W$ git switch develop && git pull --ff-only && git status --porcelain`, reading empty. From here until R6, an engine seed over an absent store file and a universe rebuild refuse, the local rolling set not yet fetched, and the daily pass's `rolling canonical head` row reads unreadable; a seed over a complete store runs as before.

**R3. The image and the ops converge.** The merge's push builds the image (`.github/workflows/capture-image.yml`); its digest is read and recorded as `.claude/skills/zcrypto-rollout-image/SKILL.md`'s *Ops converges* section says — the running digest's row in `docs/reference/fleet-pins.md` first, then the converge with `liquidations_decision=roll-after`, timed just after a `:52` tape-bars run so R4 lands before the next. `KRAKEN` at planning and immediately before:

```bash
OPS_DIGEST=sha256:0000000000000000000000000000000000000000000000000000000000000000
OPS_ALLOY=sha256:0000000000000000000000000000000000000000000000000000000000000000
infra/ansible/scripts/converge.sh site.yml --limit zcrypto-ops --tags ops -e ops_image_digest="$OPS_DIGEST" -e ops_alloy_digest="$OPS_ALLOY" -e liquidations_decision=roll-after --check
```

the two values replaced by the new image's digest and `alloy_image_digest` in `infra/ansible/group_vars/observed/alloy.yml`. Expected: the preview names the runner scripts and the ops compose file changed — the digest moves in each, and `/usr/local/sbin/zcrypto-tape-bars` carries the extension besides — and `/var/lib/zcrypto-ops/hot-out-staging` created; the scripts and the compose file render `no_log` with `diff: false`, so their read is the source diff from the host's newest qualifying deploy-log row, as the skill's preview bullet says. Then the same without `--check`, and `W$ infra/scripts/ops-postverify.sh`, every check passing; `[[ROLLOUT: the ops image digest the converge lands]]`.

**R4. The base, on the owner's word** (immediately after R3, before the next `:52`):

```bash
uv run zcrypto data rolling base --source /mnt/zhao-crypto/hot/ohlc-15m-20261007 --out /var/lib/zcrypto-ops/hot-out/ohlc-rolling --staging /var/lib/zcrypto-ops/hot-out-staging
uv run zcrypto data rolling verify --root /var/lib/zcrypto-ops/hot-out/ohlc-rolling --as-of 2026-09-30
```

Expected: `base <sha256> files=12`, and the verify printing `2026-09-30`, the same sha256 and `files=12`; `[[ROLLOUT: the base line's sha256]]`.

**R5. The first extension.**

```bash
sudo systemctl start zcrypto-tape-bars.service && journalctl -u zcrypto-tape-bars.service --since '-10 min' --no-pager | grep -E 'days_written=|head='
```

Expected: the sweep's summary line, then `head=<the newest day whose twelve finals exist> days_written=<every day from 2026-10-01 to it> holes=0`. With `HEAD_DAY` set to that `head=` day:

```bash
uv run zcrypto data rolling verify --root /var/lib/zcrypto-ops/hot-out/ohlc-rolling --as-of "$HEAD_DAY"
```

Expected: `HEAD_DAY`, its line's sha256 and `files=` the base's twelve and twelve a day, exit 0; `[[ROLLOUT: the first extension's summary line and its head line's sha256]]`.

**R6. The hub, the fetch and the data-gated tests.** After the NAS's next hourly pull:

```bash
uv run zcrypto data rolling verify --root /mnt/zhao-crypto/hot/ohlc-rolling --as-of "$HEAD_DAY"
uv run zcrypto data fetch
uv run pytest tests/test_rolling_extend.py -q -p no:cacheprovider -k "test_the_staged_base_is_the_q3_15m_frame_byte_for_byte or test_the_grids_derived_from_the_staged_base_equal_the_q3_coarse_frames"
```

Expected: the hub's verify printing R5's sha256 at `HEAD_DAY`; the fetch's `new=` counting the set's files with no refusal; the two data-gated tests `2 passed`, neither skipped; `[[ROLLOUT: the fetch's new-file count and the two data-gated readings]]`.

**R7. The head read by value.**

```bash
uv run python infra/scripts/ops-daily.py report --since 24h; echo "report exit $?"
```

Expected: the `rolling canonical head` row ok, naming the R5 head, its age and its line's first twelve hex; `[[ROLLOUT: the first rolling canonical head row]]`.

**R8. The retirements the owner takes.** By the owner's hand on the NAS, as the Q2 siblings went to `/volume1/ZhaoCrypto/backup-ohlc-squash-2026-10-09/`: `ohlc-reach-20261007` off `hot/` from R2 on, and `ohlc-full-20261007` and `ohlc-15m-20261007` once R6's data-gated tests have passed; each local copy under the main checkout's `data/` the owner removes too, after copying it aside per `CLAUDE.md`'s data rule. No step of this plan moves or deletes a set; `[[ROLLOUT: each retirement's instant and destination]]`.

**R-records.** A records pull request after R7: the converge's deploy-log row and the ops pin row of `docs/reference/fleet-pins.md`; the slots' readings in its message.

## Resolution

This plan delivers spec 00125: the rolling canonical's reader, writer and record; its daily extension on the ops host through the outbox; the fetch's attestation and the daily pass's head row; the searches, the universe rebuild and the engine seed on it; and the reach round's retirement. It moves no set off the hub — the retirements are the owner's — and it touches neither tape-bars' gate and layout nor `soak-check`, record 44's legs and the legacy pins, which keep reading `ohlc-full` and `ohlc-15m`.

## Slots the rollout fills

- `[[ROLLOUT: the ops image digest the converge lands]]` (R3) — into the records' pin row.
- `[[ROLLOUT: the base line's sha256]]` (R4) — the pin of the base alone, the as-of 2026-09-30.
- `[[ROLLOUT: the first extension's summary line and its head line's sha256]]` (R5).
- `[[ROLLOUT: the fetch's new-file count and the two data-gated readings]]` (R6).
- `[[ROLLOUT: the first rolling canonical head row]]` (R7).
- `[[ROLLOUT: each retirement's instant and destination]]` (R8) — the owner's acts, recorded as the owner reports them.
