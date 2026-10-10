# One growing OHLC canonical: `ohlc-rolling`, the Q3 15-minute frame extended daily from tape-bars — implementation plan

> Every value a rollout reading decides is a marked slot, `ROLLOUT:` inside double square brackets, listed at the end.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Research reads one canonical that reaches the present: `ohlc-rolling`, the 12 files of `ohlc-15m-20261007` copied byte for byte as its base and tape-bars' daily finals copied from 2026-10-01 as its extension, 60/240/1440 derived on read, every day a write-once index line chained to the one before it, so a trial pins an as-of day by one hash. The ops node extends it after each tape-bars sweep through its `hot-out` outbox, the NAS's hot pull carries it to the hub, `data fetch` attests it, the daily pass reads its head, and the searches, the universe rebuild and the engine seed read it; the reach round retires (spec 00125).

**Architecture:** Thirteen tasks on `docs/00125-rolling-canonical`, one pull request, then an attended rollout. The reader first, because every later task reads the set through it; then the writer the ops node runs, the fetch's attestation, the registry's record and conformance walk, the daily pass's head check, the three readers' migration with the reach round's retirement, the runner step, then the catalog, the README, the fleet reference, the runbook and the daily-ops skill, and last the master plan's rider beside the sweep. The Rollout converges the ops node onto the image built from the merge, stages the base on the owner's word, runs the first extension, reads the head on the hub by value, and leaves the retirements to the owner.

**Tech Stack:** Python 3.14 through `uv run`, polars 1.44.2, Typer (`cli/data/command.py`, `cli/research/command.py`, `cli/engine/command.py`), the tape-bars runner (`infra/ansible/roles/ops/templates/tape-bars.sh.j2`, bash), the ops role (Ansible, the Templar test substrate of `tests/test_infra_converge_guards.py`), the daily pass (`infra/scripts/ops_daily.py`), pytest, `infra/scripts/mutate-probe.sh` for guard verdicts.

**Spec:** `docs/specs/00125-rolling-canonical-design.md`, D1 to D8 as the owner ruled or confirmed them on 2026-10-09, each ruling quoted in the spec's *Rulings on the open questions* with the words that carry it, with "What changes in the repo", the invariants and the measured basis; the spec is the one text of every decision this plan implements without restating it.

## Global Constraints

- Every line number this plan gives for existing code or text is a reading at `f70be7dae`, this branch's base; a task that edits a file reads the lines it cites again before its first edit, since an earlier task may have moved them.
- No executor step reaches a host, the NAS, the hub, a registry, a venue or Grafana: every such step is an operator step of the Rollout, attended. `ansible-playbook` and `infra/ansible/scripts/converge.sh` are never run by an executor in any form — this workstation is the fleet host `zcrypto-ops`; a role's YAML is proven by the tests' walk and the commit gate's `ansible-lint`. No executor step writes under `/var/lib/zcrypto-ops/`, `/mnt/zhao-crypto/` or the main checkout's `data/`: every test builds its tree under `tmp_path`.
- Every commit is green over its consumers, the files `infra/scripts/consumers.sh` prints for the task's changed files, run as each task's consumer step writes it; the full suite runs in CI alone. A task that adds or edits text `tests/test_internal_terms_not_operator_visible.py` walks — a CLI help string, a string literal under `infra/scripts/`, a role task name or message, a runbook page, the README — runs that file too, and its allowlist is never widened.
- A guard is proven by `infra/scripts/mutate-probe.sh`, never a hand-rolled mutate-and-restore. The script refuses a dirty tree, so a task commits with the line `PROBE_VERDICT` in its message, runs one probe per guard on the committed tree in this form, `--control '1,$d'` emptying the mutated file unless the probe still passes on an empty file, when the control is a mutation its test must fail:

```bash
infra/scripts/mutate-probe.sh --file "$FILE" --control '1,$d' --mutation "$SED" -- uv run pytest "$TESTS" -q -p no:cacheprovider -k "$NAME"
```

  each ending `mutate-probe: KILLED (control proven, tree restored byte-identically)`; then a message-only amend with the tree clean replaces `PROBE_VERDICT` with each probe's command and its verbatim verdict — the branch is unpushed and unread while the tasks run, so the amend rewrites nothing a reader holds. A mutation's sed is written against the committed text and addressed to the one line it mutates, a line number read from the committed file. A `that:` or `when:` made always true writes the string `"true"`, never the YAML boolean. A probe's fixture is one only the mutated check refuses: where a second check on the same path would refuse it the same way, the probe then reading `SURVIVED`, the fixture is chosen so that check passes, or the probe is dropped and the test kept for its behaviour — so written here: Task 1's edited line (a digit of its `prev`, the line still parsing), Task 2's no-base refusal (its own text), Task 2's no-rewrite refusal (a present line that parses and chains, its listed files absent, so the head is the base line), Task 3's head walk (each new line parsed, never walked), Task 8's head (a newest line whose file is absent) and Task 8's unwalkable chain (the reader's refusal, no probe of its own).
- The commit gate, before every commit: the commit's files staged by path, its new and deleted files among them, then `uv run pre-commit run -a` until clean, its rewrites staged. One file kind per commit: a `.claude/` change rides a `claude(...)` commit carrying no other file (Task 12), and `zcrypto-refine-rules` is loaded before the edit to the runbook page and the skill (Tasks 11 and 12).
- A commit message ends with the trailer `Co-Authored-By: Claude <actual executing model> <noreply@anthropic.com>`, the placeholder replaced by the executing model's own name, followed by the executing session's `Claude-Session:` line where its harness supplies one; each commit fence below carries the trailer in that form.
- A code comment, task name, task message or docstring a task's edit falsifies is re-trued in that task's commit, and its Files entry names it; a new one stays only if a reader would act differently without it.
- Never print a container's environment; a `docker inspect` names one field. A search over `infra/` is a `git grep` carrying `infra/scripts/consumers.sh`'s `VAULT_EXCLUDES` pathspecs, as Task 8 Step 4's spells them, never `grep -r`; no vault file is read, printed, grepped or diffed.
- Every reviewer runs on Opus, the model passed explicitly.

## File structure

- `cli/data/rolling.py` (new): the index line's format, the chain walk, the head, the verify, the rolling read and its hole refusal (Task 1); the base staging and the daily extension (Task 2).
- `tests/rolling_fixtures.py` (new, Task 1): `write_chain`, the hand-written fixture chain every later task's tests build on, independent of the code under test.
- `cli/data/command.py`: the `data rolling` group — `verify` (Task 1), `base` and `extend` (Task 2); the `fetch` `--no-verify` help names the index beside the manifest (Task 3); the `rebuild` help's set list loses `ohlc-reach` (Task 8).
- `cli/data/sync.py`: the fetch's attestation of a chained set (Task 3).
- `cli/registry/observed.py`: `read_rolling` and its record (Task 4).
- `infra/scripts/ops_daily.py`: the `rolling canonical head` row (Task 5).
- `cli/research/command.py`, `cli/research/subjects.py`: `--as-of`, `--accept-holes`, the rolling resolution; `cli/portfolio/record44_legs.py`: `load_union`'s docstring (Task 6).
- `cli/engine/command.py`: `seed` reads the rolling set, `--accept-holes` beside it; the `CANONICAL_DIR` comment and the seed's help re-trued; `cli/engine/store.py`'s recovery texts name the rolling set (Task 7).
- `cli/data/rebuild.py`: the universe on the rolling set; the reach target, `resolve_canonical_root`, `resolve_ohlc_source` and their helpers deleted; `BUILDER_REFUSALS` gains `RollingError`; `cli/ohlc/reach.py` deleted; the comments naming it re-trued in `cli/engine/store.py`, `cli/ohlc/dataset.py` and `cli/ohlc/seam.py`; `zcrypto.toml`'s `authored_sets` (Task 8).
- `infra/ansible/roles/ops/templates/tape-bars.sh.j2`, `infra/ansible/roles/ops/defaults/main.yml`, `infra/ansible/roles/ops/tasks/main.yml`, `infra/ops/README.md`, `infra/nas/README.md` (Task 9).
- `docs/reference/data-catalog-full.md`, `docs/reference/fleet.md`, `docs/universe/point-in-time-universe.md`'s two resolver sentences, `README.md` (Task 10); `infra/runbooks/ops.md` and `infra/runbooks/engine.md` (Task 11); `.claude/skills/zcrypto-daily-ops/SKILL.md` and `.claude/skills/zcrypto-rollout-image/SKILL.md` (Task 12); `docs/research/00.master-plan.md`'s eight lines naming the OHLCVT archive, a rider on the owner's word (Task 13).
- Tests: `tests/test_rolling_reader.py` (new, Task 1), `tests/test_rolling_extend.py` (new, Task 2), `tests/test_data_sync.py` (Task 3), `tests/test_registry_observed.py` and `tests/test_registry_conformance.py` (Task 4), `tests/test_ops_daily.py` and `tests/test_ops_daily_soak.py` (Task 5), `tests/test_research_command.py` (Task 6), `tests/test_engine_command.py` and `tests/test_engine_store.py` (Task 7), `tests/test_data_rebuild.py`, `tests/test_data_command.py`, `tests/test_data_manifest.py`, `tests/test_universe_provenance.py` and `tests/test_ohlc_reach.py` (deleted) (Task 8), `tests/test_infra_tape_bars_template.py`, `tests/test_infra_converge_guards.py` and `tests/test_infra_shell_templates_render.py` (Task 9), `tests/test_data_gated_run.py` (Task 2).

## Review Focus

- The chain: `prev` is the sha256 of the predecessor line's bytes, the days are contiguous from the base line, whose `prev` is null, and a broken link anywhere at or below the as-of day refuses — never skipped, never read past.
- One author, one channel: the extender writes under the outbox and its staging directory alone, renames every file in from a staging directory on the same mount, rewrites no existing file, and writes no day's line before its files or its predecessor's line.
- The pin: a rolling read records the as-of line alone; `dataset_hash` is the registry's own derivation, unchanged; a second as-of on one set is refused; nothing writes to `ohlc-full`, `ohlc-15m`, `ohlc-holdout-2026-07-10` or the registry.
- The seam: the base is the Q3 15-minute frame byte for byte; every frame the reader returns is in `FRAME_SCHEMA`'s column order; the coarse grids are `derive_bars` over the base and the days together.
- The holes: a pair-day becomes a hole only once the pair's newest final puts it below the materializer's re-scan floor, which no clock reading does, or once the owner closes the pair explicitly, never by the code's own cut; a read whose window covers one refuses unless the caller accepts it. A line on which every pair is closed is the set's last: a run that reads no clock would otherwise write an all-hole line for each day after it, so the extension stops there (Task 2) and the head row reads it as ended (Task 5).
- The pairs: a rule over the set's pairs is tested with two pairs in its deciding state, so "every", "any" and "the first" read differently; where one of the two decides, the fixture names the two and orders them, so a reading of the first pair alone, sorted or as given, reaches the other verdict — the hole rule's pairs without a final, the close's pairs and the ended set's closed pairs (Task 2), the attention line's pairs, its closed-pair exclusion and the ended state (Task 5), the series check's missing pairs (Task 6), the seed's absent series (Task 7), the universe's closed pairs and its mandatory refusal (Task 8).
- The retirement: nothing reads `ohlc-reach` or the frozen-sibling resolvers after Task 8, and `soak-check`, record 44's legs and the legacy pins keep reading `ohlc-full` and `ohlc-15m`.
- The refusals: a `RollingError` reaches an operator only as the one-line refusal of the command that read the set, never a traceback — `data rolling verify`, `base` and `extend` through their own arm (Tasks 1 and 2), `data fetch` as a `DataSyncError` (Task 3), `research eval` as the reader's `RegistryError` (Task 4) and through its series check's arm (Task 6), `engine seed` under its existing prefix (Task 7), `data rebuild universe` through `BUILDER_REFUSALS` (Task 8), and the daily pass's row as a FAIL (Task 5).
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
- Produces, for every later task: `ROLLING_SET = "ohlc-rolling"`; `RollingError(Exception)`; `Line`, a frozen dataclass of `day: date`, `prev: str | None`, `files: dict[str, str]`, `holes: dict[str, str]`, `notes: dict[str, str]`, `relpath: str`, `sha256: str`; `line_relpath(day) -> str` (`index/<YYYY>/<MM>/<DD>.json`); `line_days(root) -> list[date]`, the days with a line file, sorted, read by listing; `is_chained(root) -> bool`; `pairs(root) -> tuple[str, ...]`; `read_line(root, day: date) -> Line`, that day's line file read and its shape checked, its link to the line before it not walked; `walk_chain(root, as_of: date) -> list[Line]` (the base line first); `head(root) -> Line`; `verify_line(root, line) -> None`; `verify(root, as_of: date) -> Line`; `RollingRead`, a frozen dataclass of `frame: pl.DataFrame`, `holes: tuple[date, ...]`, `line: Line`; `read_rolling(root, pair, interval, as_of: date, *, window: tuple[datetime, datetime] | None = None, accept_holes: bool = False) -> RollingRead`; `zcrypto data rolling verify [--root DIR] --as-of YYYY-MM-DD`.

**What this task decides, where the spec leaves it open:**
- A line is JSON in one canonical form, `json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"`, its keys exactly `day`, `prev`, `files`, `holes`, and `notes` on the base line and on a day line a close is in force on (Task 2), a day line's `notes` holding only `closed <BASE>/<QUOTE>` keys, each such pair under that line's `holes`; the base line is the one whose `prev` is null, its `files` the `base/<BASE>/<QUOTE>/15.parquet` files, and the set's pairs are the pairs its `files` name. A day line's `files` keys are `days/<BASE>/<QUOTE>/<YYYY>/<MM>/<DD>.parquet` of its own day, its `holes` keys pairs, the two disjoint and together the set's pairs exactly; any other shape is a `RollingError` naming the line.
- `is_chained(root)` is `(root / "index").is_dir()`: no caller names the set to know it is chained.
- `walk_chain` reads the lines by listing, `line_days`: the as-of day must be a listed day or the walk refuses — an as-of past the head and an absent as-of line are this one refusal; from the as-of line down, each line is paired with the listed line before it, its `day` that line's day plus one — a gap in the listed days, a missing line among them, refuses, naming the line after the gap — and its `prev` the sha256 of that line's bytes; the walk ends at the base line, the first listed, whose `prev` is null. `head(root)` is the newest line whose listed files are all present, its chain then walked; a broken link at or below it refuses, never read past. A listed file absent is a `RollingError` naming it, never a bare `OSError`.
- `verify(root, as_of)` walks the chain to `as_of` and runs `verify_line` on every line from the base up, so a changed byte in any file the set holds at that day refuses, naming the file; its `files=<n>` counts every file those lines list, the base's twelve and each day's.
- `read_rolling` walks the chain to `as_of`, opens the pair's base file and each of its day files, hashes each file's bytes against its listing before reading it, selects the columns by name into `FRAME_SCHEMA`'s order, concatenates, derives 60, 240 and 1440 by `derive_bars` and selects `FRAME_SCHEMA`'s order again, since `derive_bars` returns tape order (`cli/tick/materialize.py:71`), returns 15 as it is, refusing any other interval, and applies `window` to the result. A day whose line names the pair under `holes` and whose span meets the window refuses, naming the pair and the day, unless `accept_holes`, when it is returned in `holes`. A `pair` the base line does not name is a `RollingError` naming it and the set's pairs, before any file is opened: the seed reads every absent series of `BASKET` (Task 7), which a basket widening can carry outside the set.

The fixture helper, `write_chain(root: Path, *, pairs=("BTC/EUR", "ETH/BTC"), days: int = 3, holes: dict[date, set[str]] | None = None, closed: dict[date, set[str]] | None = None, skip: date | None = None, bar: Callable[[str, date], dict[str, float]] | None = None) -> list[str]`, writes the base files in `FRAME_SCHEMA`'s order (96 bars on 2026-09-30), the day files in `ticks_to_bars`' order (96 bars a day from 2026-10-01) and every line in the canonical form, each `prev` the sha256 of the line before it — with `skip`, that day's line and files are left out and the next line chained to the one before the gap, every `prev` valid; with `closed`, each pair named for a day is written under that day's `holes` and its line's `notes` carry `closed <PAIR>`, as a close in force writes it (Task 2); with `bar`, the `close`, `vwap` and `volume` it returns for a pair and a day, the base day among them, are set on every one of that day's 96 bars, so a test prices one pair's days apart (Task 8) — and returns the lines' relpaths, the base line's first.

- [ ] **Step 1: Read** spec 00125 D1 (the trees, the columns), D2 (the lines, the pin, the proof) and D6 (the hole refusal); `cli/tick/materialize.py:52-72`; `cli/ohlc/dataset.py:10-57`; `cli/data/command.py:1-30`.
- [ ] **Step 2: Write the failing tests** in `tests/test_rolling_reader.py`, every tree built by `write_chain` under `tmp_path`: `test_the_read_returns_the_base_and_the_days_up_to_the_as_of_day`; `test_the_read_returns_frame_schema_columns_from_tape_order_day_files`, parametrised over 15, 60, 240 and 1440; `test_a_coarse_grid_is_derived_across_the_seam_as_bars_computed_by_hand` (1440 over the base day and two extension days, against three bars written out in the test); `test_an_edited_line_breaks_the_chain` (one hex digit of the first day line's `prev` changed, the line still parsing: the read at the third day refuses naming that line); `test_a_skipped_day_breaks_the_chain` (`write_chain(..., skip=<the second day>)`, every `prev` valid: the read at the third day refuses naming the gap); `test_two_day_files_swapped_between_pairs_are_refused`; `test_a_listed_file_absent_is_refused`; `test_an_as_of_past_the_head_is_refused`; `test_a_line_naming_a_pair_outside_the_base_is_refused`; `test_a_pair_outside_the_set_is_refused` (a read of a pair the base line does not name: refused naming that pair and each of the set's pairs); `test_a_hole_inside_the_window_is_refused_without_accept_holes`; `test_an_accepted_hole_is_reported_and_its_day_left_out`; `test_a_hole_outside_the_window_is_not_a_refusal`; `test_the_head_is_the_newest_line_whose_files_are_present` (the newest line's day file removed: the head is the line before it); `test_verify_prints_the_as_of_lines_sha256_and_exits_0`, `test_verify_names_the_first_broken_link_and_exits_1`, `test_verify_refuses_a_flipped_byte_in_an_earlier_days_file` (one byte of the first day's file flipped: `verify` at the third day exits 1 naming that file) and `test_verify_refuses_an_os_error_in_one_line` (the `verify` the command calls replaced, by `monkeypatch`, with one raising an `OSError` naming a path: exit 1, `result.exception` a `SystemExit`, the output naming that path), through `typer.testing.CliRunner` over `cli.__main__.app`; `test_the_cli_loads_where_no_data_root_is_configured` (`[sys.executable, "-m", "cli", "data", "rolling", "verify", "--help"]` run with `cwd=tmp_path`, which holds no `zcrypto.toml`: exit 0).
- [ ] **Step 3: Run them and read the failure**

```bash
uv run pytest tests/test_rolling_reader.py -q -p no:cacheprovider
```

Expected: the file fails to collect, one error, on the missing module `cli.data.rolling`.

- [ ] **Step 4: Implement** `cli/data/rolling.py`'s reader half and the `verify` command per the decisions above: `verify` prints `<as-of> <sha256> files=<n>` and exits 0, or logs a `RollingError` or an `OSError` — a read of the set it could not make, a listed file absent being the `RollingError` above — as one line and exits 1; its `--root` is `typer.Option(None, ...)`, resolved inside the command body to `resolve_data_dir(load_config()) / ROLLING_SET`, a `ConfigError` its one-line refusal, as `fetch` resolves its root (`cli/data/command.py:35-40`) — a default computed where the option is declared runs when `cli/__main__.py` imports this module, for every subcommand, and raises wherever no `zcrypto.toml` configures a data root; its help text one operator-readable sentence with no internal term.
- [ ] **Step 5: Run the tests** — Step 3's command; Expected: `22 passed`.
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

- [ ] **Step 9: Prove the guards**, `--file cli/data/rolling.py`, `TESTS=tests/test_rolling_reader.py`: the `prev` comparison made always equal, against `-k test_an_edited_line_breaks_the_chain`; the day-contiguity check dropped, against `-k test_a_skipped_day_breaks_the_chain`; the per-file byte hash before the read dropped, against `-k test_two_day_files_swapped_between_pairs_are_refused`; the absent-file refusal made a skip, against `-k test_a_listed_file_absent_is_refused`; the as-of line's presence check dropped, the walk starting from the newest listed line at or before the as-of day, against `-k test_an_as_of_past_the_head_is_refused`; the pair-set check of a line dropped, against `-k test_a_line_naming_a_pair_outside_the_base_is_refused`; `read_rolling`'s check of the pair against the set's pairs dropped, against `-k test_a_pair_outside_the_set_is_refused`; the hole refusal's `accept_holes` test inverted, against `-k test_a_hole_inside_the_window_is_refused_without_accept_holes`; the window test of a hole made always true, against `-k test_a_hole_outside_the_window_is_not_a_refusal`; the select into `FRAME_SCHEMA`'s order before the concatenation dropped, and, separately, the select after `derive_bars` dropped, each against `-k test_the_read_returns_frame_schema_columns_from_tape_order_day_files`; `derive_bars` replaced by the 15-minute frame unchanged, against `-k test_a_coarse_grid_is_derived_across_the_seam_as_bars_computed_by_hand`; `head`'s present-files test dropped, against `-k test_the_head_is_the_newest_line_whose_files_are_present`; `verify`'s per-line `verify_line` dropped, against `-k test_verify_refuses_a_flipped_byte_in_an_earlier_days_file`; and, `--file cli/data/command.py`, `verify`'s refusal exit made 0, against `-k test_verify_names_the_first_broken_link_and_exits_1`; `OSError` dropped from `verify`'s arm, against `-k test_verify_refuses_an_os_error_in_one_line`; and `--root`'s default made `resolve_data_dir(load_config()) / "ohlc-rolling"` where the option is declared — the literal, because `ROLLING_SET` imported inside the command body would make the mutation a `NameError` in pytest's own process, a collection error, before the test's subprocess meets the missing data root — against `-k test_the_cli_loads_where_no_data_root_is_configured` — each `KILLED`; then the message-only amend.
- [ ] **Step 10: The tree is clean** — `git status --porcelain`; Expected: empty.

---

### Task 2: The writer — the base staged once and the days extended from tape-bars' finals

**Files:**
- Modify: `cli/data/rolling.py` (the writer half), `cli/data/command.py` (`rolling base`, `rolling extend`), `tests/test_data_gated_run.py` (`_DATA_ABSENT_REASONS`, :114-139, gains the two skip reasons below)
- Create: `tests/test_rolling_extend.py`

**Interfaces:**
- Consumes: Task 1's line format and `walk_chain`; `cli.tick.materialize.RESCAN_DAYS` (:79) and `_watermark` (:157-168), imported so the extender's hole bound reads the materializer's window and its newest-final reading rather than a copy of either; tape-bars' layout and sidecar (`cli/tick/materialize.py:116-141`, `<digest>  <name>\n`); `cli.data.manifest.read_manifest` for the source's attestations.
- Produces, for Tasks 5 and 9 and the Rollout: `Q3_15M_SHA256`, the table below as a `dict` from pair to sha256; `stage_base(source, out, staging) -> Line`; `Close`, a frozen dataclass of `pairs: tuple[str, ...]`, `from_day: date`, `word: str`, `word_date: date`; `extend(tape_root, out, staging, *, close: Close | None = None) -> ExtendResult` (`days_written: int`, `holes: int`, `head: Line`, `ended: bool`); `is_ended(root, line) -> bool`, true when `line`'s `notes` carry `closed <PAIR>` for each of `pairs(root)`, the one reading of an ended set the extension's stop and the daily pass's head row share; `zcrypto data rolling base --source DIR --out DIR --staging DIR`, printing `base <sha256> files=<n>`; `zcrypto data rolling extend --tape-root DIR --out DIR --staging DIR [--close-pair PAIR ... --from YYYY-MM-DD --owner-word TEXT --owner-date YYYY-MM-DD]`, printing `head=<YYYY-MM-DD> days_written=<n> holes=<n>`, followed by a space and `ended` when the head line `is_ended`; both exit 1 on a `RollingError` or an `OSError`, logged as one line.

**What this task decides, where the spec leaves it open:**
- Every file is written to a temporary name under `staging`, its data fsynced, then `os.replace`d into `out`, the destination directory fsynced, as `publish_day` does; `staging` and `out` must share a filesystem, the replace refusing otherwise. A day's files land before its line, and no line is written while its predecessor's is absent.
- No existing file is rewritten: a destination present with the bytes the write would give is accepted, so a run stopped between a day's files and its line, or between the base's twelve files and its line, completes the day or the base on the next run; present with other bytes, it refuses.
- Every directory the writer creates is mode `0o2775` and every file `0o664`, set explicitly whatever the umask, so the research user who stages the base and the ops container that extends it can both add to the tree through the outbox's group. A directory present before the call — `staging`, `out`'s ancestors, and every directory an earlier run created, the other user's among them — is never chmod-ed: changing the mode of a directory another user owns is refused (`EPERM`), so a helper that chmods every directory on a path fails the first run that crosses the other user's tree. `extend` creates nothing before it has read a base line.
- `stage_base` copies each `<BASE>/<QUOTE>/15.parquet` of `source` to a temporary under `staging` and refuses — before its first rename into `out`, every temporary removed — a source whose pairs are not `Q3_15M_SHA256`'s twelve, a temporary whose sha256 is not `Q3_15M_SHA256`'s value for its pair, or a file whose frame's `dataset_hash` is not the value the source's conformant manifest attests for that path; it then renames the twelve in and writes the base line, `day` 2026-09-30, whose `notes` are `seam` (`2026-10-01T00:00:00+00:00`), `base_from` (the source directory's name), `base_identity_digest` (the source manifest's identity digest) and `vwap` (the dump's close-weighted proxy before the seam, the tape's tick-weighted mean from it); a run over a base already present takes the rule above, each destination byte-equal to its write accepted and the line written if absent, any other refused. `Q3_15M_SHA256` is what binds the base to the Q3 frame before anything reaches the outbox, whose next pull is final: any 15-minute sibling with the same twelve paths, the frozen `ohlc-15m` among them, has a conformant manifest of its own, so the manifest check alone admits a wrong base.
- `extend` refuses an `out` with no base line, its `RollingError` reading `<out> holds no base line`, before it reads the head or creates anything — a text `head`'s own refusals do not carry. From the day after the head: when each of the set's pairs has a final in `tape_root` whose bytes hash to its sidecar, it writes the day; when some pair has none, and each such pair's newest final under `tape_root`, read by `_watermark`, is dated `RESCAN_DAYS` + 1 days or more after the day, it writes the day with each such pair under `holes` as `"no tape-bars final past the re-scan window"` — only once every pair without a final is past the window, one still inside it holding the day for all; a pair under a close in force takes its hole at once (below); otherwise it stops, however late the clock. The bound is the materializer's own: its candidate floor for a pair is `min(newest settled − RESCAN_DAYS, newest final + 1)` (`cli/tick/materialize.py:199`), its newest settled day is never before its newest final, and neither term ever falls, so a final `RESCAN_DAYS` + 1 days past D puts D below the floor for good at the runner's default re-scan — D is then a `days_gap` the runner's sweep never publishes, spec D6 naming the hand-widened re-scan that still can, into tape-bars alone — while a pair whose newest final is before D, its healer stalled or its capture stopped, is still retried by the materializer and holds the head, which the daily pass's head row reports. The rule reads no clock, so `extend` takes none. A head line that `is_ended` ends the set (spec D6): the run writes no line after it, a final reappearing for a pair included, and returns, its result's `ended` true, its summary line followed by `ended` and its exit 0, an ended set being the owner's closes read back, never the run's failure — so a run whose close leaves no pair open writes that close's line and stops there. Without this stop the run would write an all-hole line for each day after an all-closed line, a closed pair without a final taking its hole at once, without end where no final reappears; every other line it writes has some pair's final dated on or after its day, so with it the run ends. Only each final's bytes and the day's line are written; no sidecar. A final present without its sidecar, or disagreeing with it, refuses and writes nothing of that day.
- A close is the owner's act alone and the code never makes one: `--close-pair <PAIR>` (once per pair closed from the same day, so two pairs stopping together cannot each block the other's close) `--from <day> --owner-word <text> --owner-date <day>`, the four given together or none — the command refusing a partial set, exit 1, its one line naming the options missing, before it calls `extend` — the runner passing none. It refuses, writing nothing: a closed pair that is not one of the set's pairs exactly as the base line spells them, naming that pair and the set's pairs, read before any closed pair is split on `/` or looked up under `tape_root` — a line naming another pair is one Task 1's shape rule refuses for every reader, on a hub that never rewrites; a closed pair with a final under `tape_root` for `from_day` itself; and a run that cannot write `from_day`'s line, the first to carry the close — a close no line records would end with the command. A final dated after `from_day` never refuses it, for the reason spec D6 gives: that later final is copied when its day comes and ends the close there, as below, unless the set has ended before it (above), and the pair's next day without a final takes the rule above or a further close. In that line and each later one up to the set's end, a closed pair without a final for the day takes its hole at once, as `"closed on the owner's word"`, and the line's `notes` carry `closed <PAIR>`: `from <from_day>, the owner's word of <word_date>: <word>`, each run copying its predecessor line's close notes forward, which is how the close outlives the command; a final that reappears for the pair is copied as any final is, its line carries no close note for the pair, and the pair is back under the rule above. Spec D6 states why the code never cuts a pair on its own.
- Every failure of `base` and `extend` reaches the operator as the command's one-line refusal, exit 1, never a traceback; its members: a `--close-pair` spelled without its `/`, refused as a pair outside the set before any pair is split (above); a `TickError` from `_watermark`, a path under a pair's tape directory that is not `<YYYY>/<MM>/<DD>.parquet` (`cli/tick/materialize.py:165-168`), re-raised by `extend` as a `RollingError` naming it; a `ManifestError` from the source's manifest, re-raised by `stage_base` as one naming the manifest; and an `OSError` — a replace across filesystems (`EXDEV`), a directory the run cannot write, a file it cannot read — which each command's arm takes beside `RollingError`, logging its text, which names the path, as `verify`'s does (Task 1).

`Q3_15M_SHA256`, in `cli/data/rolling.py` and imported by the data-gated byte test, is this table — the bytes of `ohlc-15m-20261007`'s files as read on 2026-10-09 (`sha256sum */*/15.parquet` in it, the hub's copy hashing the same); the two data-gated tests read the main checkout's set once the Rollout has fetched it:

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

`Q3_COARSE_IDENTITY`, the derivation test's literal, is `cli.ohlc.dataset.dataset_hash` over the columns `ts, open, high, low, close, count` of each of `ohlc-full-20261007`'s 36 files, read on 2026-10-09 in the main checkout's copy, where `derive_bars` over the pair's `ohlc-15m-20261007` file, its columns in `FRAME_SCHEMA`'s order, gives the same 36 values; committed so this check too outlives that sibling's retirement:

| Pair | 60 | 240 | 1440 |
| --- | --- | --- | --- |
| ADA/EUR | `4aa8c7415e74b3f3533b737c196bbd832765a2fb0e16d8780b00373fe9328d05` | `9f1d43e614f84c4ff41df15400642251425b65805c7e376f19b18bd2488b1c17` | `3bde97837b0713986c863a7607952684079dc7bc6e8333925aabc04424361b4a` |
| AVAX/EUR | `45f5bb236e58347c66bf53aa117ef3089830f54daadef6fc372b4302e4fe9cc8` | `b76742f54b1f88aeec7160e4316be39a7fe0f6a5662f9947be33564bbd4a36ce` | `baf79ba33a23d444f7dc9995b78e51fa57fb29b593df465d18ffd33e546d0199` |
| BTC/EUR | `8de3b163c16efdcedda516d72e10b2d8057a82955ab6908ef8f98e43ab81d39e` | `e7345b65a39c4c1144a13252b42a139de011e074102496016976d3c98f569649` | `d7df07ba52d788c879e1e362cc70d39bbce55db5be14aec4b9a027b1622e3328` |
| DOGE/EUR | `0186967c78cd806626c8d2475b2df453bb084659ca03a00e409e2387c93767ba` | `cad5590ebfd403f482143496acf72dfb80cdc6180c343499857c8eb63a349e80` | `717605594e7df07b488ff1093cd496340755fddc8ee82eead3605ae45f502561` |
| DOT/EUR | `00973ad27478169fc6049200ab47e7700aec8fbbc8019d2974019158567a3d32` | `30987cc17987caa2b7482629435f23942a9b5d78eb420df0add10f32f0b3e9b2` | `6abc6d78db49dc68e048a662ffb60cf116a7dff4b9e93153e9445cc5d7a8389c` |
| ETH/BTC | `0555619676a8ed7e24335a0c0b67ca9fef3ed78478f29822b3536f1f916395c6` | `5898792fd3437371515b68441e5701e6268e11bdb66b4cb5da7826e17bff3911` | `53b3081460b728ed5a6855f5f4517e28e9e203b30723475cf79350dd760a4070` |
| ETH/EUR | `3f762502336894481f2fe7d52d079b72b12ba86160a960678a4a9097ab015f43` | `f86a1780c95fd2cbb11df2931a01f1d4c1c50a5cea48c5552364fd18ba737dea` | `52e4160a9a9622240fae7f88bcb5e869d4d4d960c3fe55771b873a7d3d959bca` |
| LINK/EUR | `5fbc1dd565b8e62f7cf6b507acc1e7302d8138167c2063fd7be0d341b3e104b4` | `463babc098296071468b1ccbcc118fa464517c8870d8a5994dee61c9b6151eac` | `f34b6f5df5dc97980766c44a9177fd5c475e35d73137f5fea4e58daeeb4dfa71` |
| LTC/EUR | `6a2d7ab71292f5f957f6dab6c6815420ea498f48d5fed06b0150f157e4b8dc70` | `a71a2ae703e476fef9e02c51d7d9faec6de822dfc5d2fd6b85e0fdf4675bd8e6` | `92737571f0cc6c08941d07dab62ea6beb1853365c81b3e2748d43def1b980638` |
| SOL/BTC | `4da1b35b90ddf8efdbc10629041a28a2235e6c2c5def0c3f403f85d2ec4966ae` | `1822fa2c798811be5d13ebc0e54b35f1d5ecad5670746f24cb635cbb87b0f2d7` | `6f85440cda658edcad829c0abeece384af62353545c909ceaf1441cf025bf0f0` |
| SOL/EUR | `6f62c26e90bf0f30634f3baa885f9a7c4ffbf561716ddd1467f9ea8b675a6abc` | `b0b362e6bc1842592772076ebfe1c04f18f46b91b61b060c3cd098673b98637e` | `468a7adb2f4610eab5df9a3bc31f043f46e9d4019cc7e4b99fbfbb5a15bf2147` |
| XRP/EUR | `a21afb27c5f900f05a63d5a9189c645260ac536c934b222020f3451c12d9b728` | `06b0ae87eb745e695d1c644b06b507bb708a8ad9378ee7ffb3bfee4887b376d4` | `fe5bbf99b8d72a6ce463444e248880932b9e2bb0c9318ab53f11ab7f63155f52` |

- [ ] **Step 1: Read** spec 00125 D1, D3 (the outbox, the staging, the order) and D6 (the hole); `cli/tick/materialize.py:116-219`; `cli/data/manifest.py:116-189`; `tests/test_data_gated_run.py:108-139`.
- [ ] **Step 2: Write the failing tests** in `tests/test_rolling_extend.py`, every tree under `tmp_path` — a tape-bars tree written in its own layout with sidecars, a source set of `Q3_15M_SHA256`'s twelve pairs with a conformant manifest, `cli.data.rolling.Q3_15M_SHA256` replaced by `monkeypatch.setattr` with a new dict of that source's file hashes inside each unit test that stages a base but the one refusing a source for its bytes (never an autouse fixture and never `setitem` on the module's own dict: the two data-gated tests import that dict and read it as committed), each base refusal's fixture failing that refusal's check alone — the module carrying `pytestmark = pytest.mark.data`, since its two data-gated reasons read as data absences (`tests/test_data_gated_marker.py`): `test_the_base_copies_the_source_byte_for_byte_and_writes_the_base_line`; `test_the_base_refuses_a_source_whose_bytes_are_not_the_q3_frame` (the twelve-pair source, the literal as committed: refused naming a pair's file, nothing under `out`); `test_the_base_refuses_a_source_file_its_manifest_does_not_attest` (the source's files untouched and the literal patched to their bytes, the manifest attesting another frame hash for one path: refused naming that path, nothing under `out`); `test_the_base_refuses_a_source_missing_one_of_the_twelve_pairs` (the literal patched to twelve pairs' bytes, the source holding eleven of them under a manifest attesting those eleven: refused naming the missing pair, nothing under `out`); `test_a_days_line_is_written_only_after_its_files` (`os.replace` patched to raise on the line: the day's files are present and no line); `test_a_rerun_after_a_stop_between_files_and_line_completes_the_day`; `test_a_rerun_after_a_stop_between_the_base_files_and_its_line_completes_the_base` (`os.replace` patched to raise on the base line: the twelve files present and no line; a rerun writes the line, every file's bytes unchanged); `test_a_final_disagreeing_with_its_sidecar_is_refused_and_nothing_of_that_day_written`; `test_a_final_without_its_sidecar_is_refused_and_nothing_of_that_day_written` (one pair's sidecar for D removed); `test_no_existing_file_is_rewritten` (the line for the day after the base already present in canonical form, its `prev` the base line's sha256 and its listed files absent from `out` with sha256 values other than the finals', so the line parses, the head is the base line and the bytes differ from the run's: the run writes that day's files and refuses the line, its bytes unchanged); `test_day_d_plus_one_waits_while_d_is_pending` (one pair's final for D absent, every pair's D+1 present: the head stays D−1); `test_a_hole_is_written_only_past_the_rescan_window` (the same tree with that pair's finals added through D + `RESCAN_DAYS`: the head still D−1; then its D + `RESCAN_DAYS` + 1 final added: D written with the pair under `holes`, then each later day); `test_a_day_missing_two_pairs_is_a_hole_only_once_both_are_past_the_window` (two pairs' finals for D absent, every other pair's present through D + `RESCAN_DAYS` + 1, ADA/EUR, which sorts first, with its finals through D + `RESCAN_DAYS` + 1 save D, XRP/EUR with its finals through D + 2 save D, so its newest final lies after D and inside the window and no other rule holds the day: the head stays D−1, which a reading of the first pair alone would not hold; then XRP/EUR's finals added through D + `RESCAN_DAYS` + 1 save D: D written naming both under `holes`); `test_a_pair_whose_newest_final_is_before_the_day_holds_the_head` (that pair's finals ending at D−1 while every other pair's run to D + 8: no line after D−1); `test_prev_is_the_sha256_of_the_predecessors_bytes` (at a day whose predecessor is a day line); `test_only_finished_names_appear_under_the_outbox` (the outbox listed from inside a patched `os.replace`: no temporary name); `test_the_outbox_holds_exactly_the_lines_and_the_files_they_list_each_renamed_in` (every `os.replace` destination recorded across the base and two extended days: the files under `out` are exactly those destinations, and exactly every line's `files` and the lines' own relpaths — no sidecar, no file put at its final path but by a rename from `staging`); `test_every_directory_the_writer_creates_is_group_writable_and_setgid` (`os.umask(0o022)` around the run; `staging` and `out`'s parent made beforehand at `0o2770`, and the base's directories set to `0o2770` before the extension; `os.chmod` patched to raise `PermissionError` on any path present before the call: after `stage_base` and after `extend`, every directory the call created `0o2775`, every file `0o664`, every directory present before it at its `0o2770`); `test_extend_refuses_an_outbox_without_a_base_line` (refused with `holds no base line`, and nothing created under `out` or `staging`); `test_a_tape_pair_outside_the_base_is_neither_copied_nor_listed` (the tape tree carrying a thirteenth pair's sidecar-valid finals beside the set's: each written line lists the base's pairs alone, and no file of the thirteenth pair is under `out`); `test_a_closed_pairs_later_lines_carry_the_hole` (through `CliRunner`, two pairs' finals ending at D−1, every other pair's running on, a close of both from D, `--close-pair` given once per pair, with the owner's word and its date: D's line and each later one name both under `holes` and carry both closes in `notes`, and a later run given no close keeps carrying them); `test_a_final_reappearing_after_the_close_is_copied_and_ends_the_hole` (that pair's finals ending at D−1 save one for D+1, every other pair's running on, a close from D given while that D+1 final is present: taken; D's line names the pair under `holes` with the close in `notes`, D+1's line lists its final and carries no close note, and D+2, without a final, waits under the ordinary rule); `test_a_final_reappearing_in_a_run_given_no_close_ends_the_close` (that pair's finals ending at D−1, every other pair's running to D+2, a close from D: D to D+2 written with the pair under `holes`; then the pair's final for D+3 and every other pair's through D+4 added and a run given no close: D+3's line lists the pair's final and carries no close note for it, and D+4, without it, waits under the ordinary rule); `test_a_close_on_a_pair_with_a_final_for_its_day_is_refused` (a close of ADA/EUR and XRP/EUR from D, given in that order, which is also their sorted order, XRP/EUR's final for D present: refused, nothing written); `test_a_close_whose_first_line_cannot_be_written_is_refused` (another pair's final for D absent: refused, nothing written); `test_a_line_closing_every_pair_ends_the_set` (through `CliRunner`, every pair's finals ending at D−1 save XRP/EUR's, which sorts last and runs to D+1, and a close from D of the other eleven, ADA/EUR, which sorts first, among them, `--close-pair` given once per pair: D's and D+1's lines written, each naming the eleven under `holes` and listing XRP/EUR's final, the run waiting at D+2 and its summary not followed by `ended` — a stop reading any closed pair, or the first pair alone, would end at D; then a close of XRP/EUR from D+2, given alone: D+2's line names every pair under `holes` with its close in `notes`, no line follows it, and the summary is followed by `ended`, exit 0; then every pair's sidecar-valid final for D+3 added and a run given no close: nothing written, the head D+2, the summary followed by `ended`, exit 0); `test_a_close_without_the_owners_word_and_date_is_refused` (through `CliRunner`, `--close-pair` and `--from` alone: exit 1, `result.exception` a `SystemExit`, the output naming `--owner-word` and `--owner-date`, nothing written under `out` or `staging`); `test_a_close_of_a_pair_outside_the_set_is_refused`, parametrised over `LNIK/EUR` and `DOTEUR` (through `CliRunner`, DOT/EUR's finals ending at D−1 and every other pair's final for D present, a close of DOT/EUR and the mistyped pair, given in that order, which is also their sorted order, so a reading of the first pair alone takes the close: exit 1, `result.exception` a `SystemExit`, the output naming the mistyped pair and each of the set's pairs, no line for D and nothing under `staging`); `test_a_tape_path_that_is_not_a_day_is_a_one_line_refusal` (through `CliRunner`, a `.parquet` under DOT/EUR's tape directory at a path that is not `<YYYY>/<MM>/<DD>`, sorting after its finals, DOT/EUR's final for D absent and every other pair's present, so its newest final is read: exit 1, `result.exception` a `SystemExit`, the output naming that path, no line for D); `test_a_base_whose_rename_fails_is_a_one_line_refusal` and `test_an_extension_whose_rename_fails_is_a_one_line_refusal` (each through `CliRunner`, `os.replace` patched to raise the `OSError` a replace across filesystems raises, `EXDEV` with its two paths: exit 1, `result.exception` a `SystemExit`, the output naming the destination); `test_the_base_refuses_a_source_whose_manifest_is_not_conformant` (through `CliRunner`, the literal patched to the source's bytes and its manifest without `schema_version`: exit 1, `result.exception` a `SystemExit`, the output naming the manifest, nothing under `out`); `test_the_extend_summary_line_names_the_head_the_days_and_the_holes` (through `CliRunner`). Data-gated, each skipping with its reason where the set is absent: `test_the_staged_base_is_the_q3_15m_frame_byte_for_byte` (the twelve base files' sha256 equal `Q3_15M_SHA256`; reason `data/ohlc-rolling absent — the staged base is on the data-bearing workstation only`) and `test_the_grids_derived_from_the_staged_base_equal_the_q3_coarse_frames` (`read_rolling` at the base line for 60, 240 and 1440, each frame's `dataset_hash` over `ts, open, high, low, close, count` equal to `Q3_COARSE_IDENTITY`; reason `data/ohlc-rolling absent — the base's derivation is checked on the data-bearing workstation only`). The two reasons join `_DATA_ABSENT_REASONS`.
- [ ] **Step 3: Run them and read the failure**

```bash
uv run pytest tests/test_rolling_extend.py -q -p no:cacheprovider
```

Expected: the file fails to collect, one error, on the import of `stage_base` and `extend` from `cli.data.rolling`.

- [ ] **Step 4: Implement** the writer half and the two commands per the decisions above, the commands' help text operator-readable with no internal term.
- [ ] **Step 5: Run the tests** — Step 3's command; Expected: `34 passed, 2 skipped`, the two data-gated cases skipping with their reasons in a worktree, whose `data/` is empty.
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

- [ ] **Step 9: Prove the guards**, `--file cli/data/rolling.py`, `TESTS=tests/test_rolling_extend.py`: the line's write moved ahead of the day's files, against `-k test_a_days_line_is_written_only_after_its_files`; the sidecar comparison made always equal, against `-k test_a_final_disagreeing_with_its_sidecar_is_refused_and_nothing_of_that_day_written`; the comparison skipped when the sidecar is absent, against `-k test_a_final_without_its_sidecar_is_refused_and_nothing_of_that_day_written`; the existing-destination refusal made an overwrite, against `-k test_no_existing_file_is_rewritten`; the byte-equal acceptance of an existing destination dropped, against `-k test_a_rerun_after_a_stop_between_files_and_line_completes_the_day`, and, separately, from the base's writes, against `-k test_a_rerun_after_a_stop_between_the_base_files_and_its_line_completes_the_base`; the pending stop made a hole, against `-k test_day_d_plus_one_waits_while_d_is_pending`, its command `timeout 60 uv run pytest …` in place of the bare form, since in its fixture, no pair closed, that stop is the rule's one exit and a run without it does not return, the timeout's rc 124 its `KILLED`; `RESCAN_DAYS` dropped from the hole's bound, against `-k test_a_hole_is_written_only_past_the_rescan_window`; the hole condition made true when any pair without a final is past the window, against `-k test_a_day_missing_two_pairs_is_a_hole_only_once_both_are_past_the_window`; the pair's own newest final replaced by the newest final of any pair, against `-k test_a_pair_whose_newest_final_is_before_the_day_holds_the_head`; `prev` taken as the predecessor's own `prev` in place of the sha256 of its bytes, against `-k test_prev_is_the_sha256_of_the_predecessors_bytes`; the temporary name put under `out` in place of `staging`, against `-k test_only_finished_names_appear_under_the_outbox`; a day file copied straight to its final path, and, separately, each final's sidecar copied beside it, each against `-k test_the_outbox_holds_exactly_the_lines_and_the_files_they_list_each_renamed_in`; the explicit `0o2775` dropped from the directory creation, and, separately, every directory on the path chmod-ed, each against `-k test_every_directory_the_writer_creates_is_group_writable_and_setgid`; the no-base refusal dropped, against `-k test_extend_refuses_an_outbox_without_a_base_line`; the day's pair list read from `tape_root`'s directories in place of the base line's `files`, against `-k test_a_tape_pair_outside_the_base_is_neither_copied_nor_listed`; the close's carry from the predecessor line's `notes` dropped, against `-k test_a_closed_pairs_later_lines_carry_the_hole`; a closed pair's reappearing final taken as a hole in the run given the close, against `-k test_a_final_reappearing_after_the_close_is_copied_and_ends_the_hole`, and, separately, in a run given no close, the close read from its predecessor line's `notes`, against `-k test_a_final_reappearing_in_a_run_given_no_close_ends_the_close`; the close's check of a final for its day dropped, against `-k test_a_close_on_a_pair_with_a_final_for_its_day_is_refused`; that check widened to a final at or after its day, against `-k test_a_final_reappearing_after_the_close_is_copied_and_ends_the_hole`; the close's first-line check dropped, against `-k test_a_close_whose_first_line_cannot_be_written_is_refused`; the ended stop dropped, against `-k test_a_line_closing_every_pair_ends_the_set`, under `timeout 60` as the pending stop's — these two the probes whose mutant leaves its fixture's run no exit; `is_ended` made true when any pair of the line is closed, and, separately, when the set's first pair is, each against `-k test_a_line_closing_every_pair_ends_the_set`; the `Q3_15M_SHA256` comparison dropped, against `-k test_the_base_refuses_a_source_whose_bytes_are_not_the_q3_frame`; the manifest attestation of a base file dropped, against `-k test_the_base_refuses_a_source_file_its_manifest_does_not_attest`; the pair-set check made a subset test, the source's pairs within `Q3_15M_SHA256`'s, against `-k test_the_base_refuses_a_source_missing_one_of_the_twelve_pairs`; the close's check of its pairs against the set's dropped, against `-k test_a_close_of_a_pair_outside_the_set_is_refused`; the `TickError`'s re-raise as a `RollingError` dropped, against `-k test_a_tape_path_that_is_not_a_day_is_a_one_line_refusal`; the `ManifestError`'s re-raise dropped, against `-k test_the_base_refuses_a_source_whose_manifest_is_not_conformant`; and, `--file cli/data/command.py`, the four-together check of the close options dropped, against `-k test_a_close_without_the_owners_word_and_date_is_refused`, and `OSError` dropped from `base`'s arm, against `-k test_a_base_whose_rename_fails_is_a_one_line_refusal`, and, separately, from `extend`'s, against `-k test_an_extension_whose_rename_fails_is_a_one_line_refusal`, and the `ended` after the summary dropped, against `-k test_a_line_closing_every_pair_ends_the_set` — each `KILLED`; then the message-only amend.
- [ ] **Step 10: The tree is clean** — `git status --porcelain`; Expected: empty.

---

### Task 3: The fetch attests the rolling canonical by its index

**Files:**
- Modify: `cli/data/sync.py` (`_verify_new_files`, :199-219, gains the chained arm), `cli/data/command.py` (the `--no-verify` help, :32, which names the manifest alone)
- Test: `tests/test_data_sync.py`

**Interfaces:**
- Consumes: Task 1's `is_chained`, `line_days`, `read_line`, `head`; `_verify_new_files`' per-set loop.
- Produces: a fetch that refuses a chained set's file whose bytes disagree with the line naming it, refuses a fetched chain whose head does not walk, reports a day file no line names yet as pending, unread, and compares that file when a later fetch brings its line, reports a line whose file has not arrived as pending and compares that file when a later fetch brings it, and refuses only as a `DataSyncError`.

**What this task decides, where the spec leaves it open:**
- For a set whose hub directory `is_chained`, a fetch that brings any new file of it, a line included, takes the chained arm — the per-set loop today admits only a set with a new parquet (`cli/data/sync.py:199-204`), which a fetch bringing a line alone is not. The attestation is the union of every hub line's `files`, path to the sha256 of the bytes, each hub line parsed by `read_line` and never walked — the identity grade, never the manifests' frame-content grade, which is why the index stays out of `_attestations_for_set`, whose hashes `_attestation_failure` compares as `dataset_hash` (`:153-166`) — and each new parquet of the local copy is compared by its bytes; the manifest and vouched-sidecar arm is not consulted for it. Each line new in this fetch is then parsed from the local copy by `read_line`, its link not walked, and each file it lists that is present locally is compared by its bytes to the listing, so a file that arrived ahead of its line is compared when its line arrives; a listed file not yet present — a hub pull having copied the line before it, which the next pull completes — is logged as pending with its path and compared by the union above when a later fetch brings it, never refused as lost. Then `head` over the local copy must walk, or the fetch refuses naming the link — the arm's one walk, every other read of a line a parse alone. A new parquet no line names is logged as pending with its path and left in place, since no reader reaches a file but through a line.
- Every refusal of the arm is a `DataSyncError`, the one dialect `data fetch` catches (`cli/data/command.py:42-45`): a `RollingError` from `read_line` or `head` is re-raised as one naming its text. `--no-verify` skips the chained arm with the manifest one, both inside `_verify_new_files` (`cli/data/sync.py:230-234`), and its help becomes `Skip hash verification of newly fetched files against their manifest or index.`

- [ ] **Step 1: Read** spec 00125 D3 (the fetch); `cli/data/sync.py:109-236`; `tests/test_data_sync.py:1-40` and `:116-200`.
- [ ] **Step 2: Write the failing tests**, the hub tree built by `write_chain` under `tmp_path` and fetched through `fetch_hot` with the real `rsync`: `test_fetch_admits_a_rolling_day_file_matching_its_line`; `test_fetch_refuses_a_rolling_day_file_disagreeing_with_its_line` (one day file's byte flipped on the hub after its line was written); `test_fetch_leaves_a_rolling_day_file_no_line_names_pending` (a day file without its line: the fetch succeeds and the log names the file); `test_fetch_refuses_a_fetched_chain_whose_link_is_broken` (the hub's second day line's `prev` replaced by another 64-hex value, every line still parsing); `test_fetch_compares_a_pending_file_when_its_line_arrives` (a day file pending at one fetch, its line on the hub before the next, the file's local bytes flipped in between: the second fetch refuses naming the file); `test_fetch_admits_a_line_ahead_of_its_file_as_pending` (a day's line on the hub without one of its files: the fetch succeeds and the log names that file pending; the file then put on the hub: the next fetch succeeds); `test_fetch_refuses_a_file_arriving_after_its_line_whose_bytes_disagree` (the same line fetched first without its file, the file then put on the hub with one byte flipped: the second fetch, which brings no new line, refuses naming the file). Every refusal case asserts `pytest.raises(DataSyncError)` and the file or link it names.
- [ ] **Step 3: Run them and read the failure**

```bash
uv run pytest tests/test_data_sync.py -q -p no:cacheprovider -k "test_fetch_admits_a_rolling_day_file_matching_its_line or test_fetch_refuses_a_rolling_day_file_disagreeing_with_its_line or test_fetch_leaves_a_rolling_day_file_no_line_names_pending or test_fetch_refuses_a_fetched_chain_whose_link_is_broken or test_fetch_compares_a_pending_file_when_its_line_arrives or test_fetch_admits_a_line_ahead_of_its_file_as_pending or test_fetch_refuses_a_file_arriving_after_its_line_whose_bytes_disagree"
```

Expected: every case fails at its first fetch, which brings the set's parquet, on `attested by neither its manifest nor` — a case expecting a refusal there gets one of that text rather than the chain's.

- [ ] **Step 4: Implement** the arm per the decision above.
- [ ] **Step 5: Run the tests** — `uv run pytest tests/test_data_sync.py -q -p no:cacheprovider`; Expected: no failure.
- [ ] **Step 6: The consumers**

```bash
uv run pytest $(infra/scripts/consumers.sh cli/data/sync.py cli/data/command.py | grep -E '^tests/test_[^ ]*\.py$' | sort -u) tests/test_cli_help_hygiene.py tests/test_internal_terms_not_operator_visible.py -q -p no:cacheprovider
```

Expected: no failure.

- [ ] **Step 7: The commit gate**

```bash
git add cli/data/sync.py cli/data/command.py tests/test_data_sync.py && uv run pre-commit run -a
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

- [ ] **Step 9: Prove the guards**, `--file cli/data/sync.py`, `TESTS=tests/test_data_sync.py`: the byte comparison made always equal, against `-k test_fetch_refuses_a_file_arriving_after_its_line_whose_bytes_disagree`, the fixture where no other check reads the file; the head walk after the checks dropped, and, separately, the `RollingError`'s re-raise as a `DataSyncError` dropped, each against `-k test_fetch_refuses_a_fetched_chain_whose_link_is_broken`; the pending arm made a refusal, against `-k test_fetch_leaves_a_rolling_day_file_no_line_names_pending`; the pending arm for a new line's absent file made a refusal, against `-k test_fetch_admits_a_line_ahead_of_its_file_as_pending`; the chained arm's `is_chained` test made false, against `-k test_fetch_admits_a_rolling_day_file_matching_its_line`; the comparison of a new line's present files dropped, against `-k test_fetch_compares_a_pending_file_when_its_line_arrives` — each `KILLED`; then the message-only amend.
- [ ] **Step 10: The tree is clean** — `git status --porcelain`; Expected: empty.

---

### Task 4: The registry records the as-of line, and the conformance pass walks the chain from it

**Files:**
- Modify: `cli/registry/observed.py` (`read_rolling` beside `read_series`, :72-127; `vouched_status`, :66-70, its rolling case; the module docstring, :1-4, and `_attestations`' docstring, :46-50, re-trued for a set the index attests; `block`, :129-139, unchanged), `tests/test_registry_conformance.py` (`conformance`, :59-87)
- Test: `tests/test_registry_observed.py`, `tests/test_registry_conformance.py`

**Interfaces:**
- Consumes: Task 1's `read_rolling`, `verify`, `line_relpath`; the registry's `compute_hash` (`cli/registry/record.py:35-36`), untouched.
- Produces, for Task 6: `ObservedReader.read_rolling(dataset: str, pair: str, interval: int, as_of: str, window: tuple[str, str] | None = None, accept_holes: bool = False) -> pl.DataFrame` and `ObservedReader.holes() -> dict[str, list[str]]`, the holes each dataset's reads accepted, each `"<pair> <YYYY-MM-DD>"`.

**What this task decides, where the spec leaves it open:**
- A rolling read records, for its dataset, `files` exactly `{line.relpath: line.sha256}` of the as-of line, whatever pairs and grids it read, and accumulates `rows` and `span` once per `(pair, interval)`: a pair's first read at a grid adds its returned frame's height to `rows` and widens `span` to cover it, a repeat with the same window adds nothing, and one with another window is refused — the discipline `read_series` keeps once per `(dataset, relpath)` (:73-77, :120-126), whose key a rolling read cannot reuse, every read of one dataset recording the same line; it parses `as_of` as `YYYY-MM-DD` and `window` as `read_series` does (:98-117), refusing the same malformed bounds, and refuses a windowed frame of zero rows before recording it, as `read_series` does (:118-119). A second rolling read of the same dataset at another as-of day is refused, and so is a `read_series` of a dataset already read as rolling, or the reverse. The manifest cross-check is not run for a rolling read: the chain attests every file at the identity grade. A `RollingError` is raised as a `RegistryError` naming it, the dialect `research eval` catches (`cli/research/command.py:97`). `vouched_status` gives a dataset read through `read_rolling` `chained (as of <day>, line <first twelve hex>)` and never consults `_attestations_for_set`, which holds no hash for a set with no manifest and would print `inert (0 vouched hashes)` for a read the chain verified file by file.
- In the conformance pass, a cited relpath under `index/` whose bytes re-hash as recorded is then `verify`'d to its day; a `RollingError` is a finding with its text.

- [ ] **Step 1: Read** spec 00125 D2 (the registry, the proof); `cli/registry/observed.py`; `tests/test_registry_conformance.py:59-160`; `tests/test_registry_observed.py:1-60`.
- [ ] **Step 2: Write the failing tests** — in `tests/test_registry_observed.py`: `test_a_rolling_read_records_the_as_of_line_alone`; `test_a_rolling_pin_reproduces_one_block_read_twice` (two readers over one `write_chain` tree give equal blocks and equal `compute_hash`); `test_a_second_as_of_on_one_rolling_set_is_refused`; `test_a_rolling_read_honours_the_window_in_rows_and_span`; `test_an_accepted_rolling_hole_is_listed_by_pair_and_day`; `test_a_rolling_dataset_reads_as_chained_not_inert`; `test_rolling_reads_of_two_pairs_at_two_grids_accumulate_rows_and_span` (one reader over a `write_chain` tree reading both pairs at 1440 and at 240: `rows` the four frames' heights summed and `span` their union; a repeated read with the same window changes neither; one with another window refused); `test_a_series_read_of_a_rolling_dataset_is_refused` (after a rolling read, a `read_series` of the same dataset's base file refused; on a fresh reader, the two in the other order refused); `test_a_rolling_read_of_zero_rows_is_refused` (a window over a day before the base's: a `RegistryError` naming zero rows). In `tests/test_registry_conformance.py`: `test_a_record_citing_a_line_walks_the_chain_and_a_broken_link_is_a_finding` (a record appended through `TrialRegistry.append` whose block names a `write_chain` tree's third day line and its sha256, written by hand as `_fabricated` writes its block; the pass rederives it; one byte of an earlier line flipped, the pass reads a finding naming that line; on a fresh tree, one byte of an earlier day's file flipped, the pass reads a finding naming that file).
- [ ] **Step 3: Run them and read the failure**

```bash
uv run pytest tests/test_registry_observed.py tests/test_registry_conformance.py -q -p no:cacheprovider -k "test_a_rolling_read_records_the_as_of_line_alone or test_a_rolling_pin_reproduces_one_block_read_twice or test_a_second_as_of_on_one_rolling_set_is_refused or test_a_rolling_read_honours_the_window_in_rows_and_span or test_an_accepted_rolling_hole_is_listed_by_pair_and_day or test_a_rolling_dataset_reads_as_chained_not_inert or test_rolling_reads_of_two_pairs_at_two_grids_accumulate_rows_and_span or test_a_series_read_of_a_rolling_dataset_is_refused or test_a_rolling_read_of_zero_rows_is_refused or test_a_record_citing_a_line_walks_the_chain_and_a_broken_link_is_a_finding"
```

Expected: the nine observed cases fail on `ObservedReader` having no `read_rolling`; the conformance case fails at its broken-link half, the pass reading `rederived`.

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

- [ ] **Step 9: Prove the guards**: in `cli/registry/observed.py`, `TESTS=tests/test_registry_observed.py`, the recorded `files` made every file the read opened, against `-k test_a_rolling_read_records_the_as_of_line_alone`; the second-as-of refusal dropped, against `-k test_a_second_as_of_on_one_rolling_set_is_refused`; the window dropped from the rolling read, against `-k test_a_rolling_read_honours_the_window_in_rows_and_span`; the rolling case dropped from `vouched_status`, against `-k test_a_rolling_dataset_reads_as_chained_not_inert`; the accumulation keyed on the dataset alone, and, separately, the other-window refusal of a repeated pair and grid dropped, each against `-k test_rolling_reads_of_two_pairs_at_two_grids_accumulate_rows_and_span`; the refusal between a series read and a rolling read of one dataset dropped, against `-k test_a_series_read_of_a_rolling_dataset_is_refused`; the zero-row refusal dropped from the rolling read, against `-k test_a_rolling_read_of_zero_rows_is_refused`; in `tests/test_registry_conformance.py`, `TESTS` the same file, the `verify` call dropped from `conformance`, against `-k test_a_record_citing_a_line_walks_the_chain_and_a_broken_link_is_a_finding` — each `KILLED`; then the message-only amend.
- [ ] **Step 10: The tree is clean** — `git status --porcelain`; Expected: empty.

---

### Task 5: The daily pass reads the rolling canonical's head on the hub

**Files:**
- Modify: `infra/scripts/ops_daily.py` (`ROLLING_CHECK`, `ROLLING_HUB`, `ROLLING_STALE_AFTER_DAYS` and `read_rolling_head` after `read_soak_verdict`, :968; `main`'s appends, :1314-1316, gain the row after the soak row; the classifier's first-stage shapes, `_FIRST_STAGE_SHAPES`, :1439-1596, gain `zcrypto data rolling verify`; `ROLLING_TAPE` and `ROLLING_ESCALATE_AFTER_DAYS` beside `ROLLING_HUB`)
- Test: `tests/test_ops_daily.py` (its `_DESTRUCTIVE`, :716-747, gains the set's writers), `tests/test_ops_daily_soak.py` (its `test_ops_daily` import, :17-25, gains the rolling stub beside `live_soak_run`)

**Interfaces:**
- Consumes: Task 1's `line_days`, `walk_chain` and `verify_line` and Task 2's `is_ended`, imported inside the reader as `derive_soak_store` imports the engine's (:900-903); `Check` (:531).
- Produces: `ROLLING_CHECK = "rolling canonical head"`, `ROLLING_HUB = Path("/mnt/zhao-crypto/hot/ohlc-rolling")`, `ROLLING_STALE_AFTER_DAYS = 3`, `ROLLING_TAPE = Path("/var/lib/zcrypto-ops/tape-bars")`, `ROLLING_ESCALATE_AFTER_DAYS = 14`, `read_rolling_head(*, now: datetime, root: Path, tape_root: Path) -> Check`, keyword-only with no default, `main` passing `root=ROLLING_HUB, tape_root=ROLLING_TAPE`.

**What this task decides, where the spec leaves it open:**
- `ok` is the newest line — read by `line_days`, never by `head`, which steps past a line whose files are absent — dated at or after `now`'s UTC date less three days, its chain walked from it, its own files re-hashed by `verify_line`, and not the ended state below; the value names the head's day, its age in days and the first twelve hex of its line's sha256, or why it failed. A root with no `index/` or an `OSError` on the mount is `unreadable: …` with `ok` false, never a pass; a `RollingError` over a readable index — a `prev` that disagrees, a listed file absent or changed — is a FAIL whose value names the line or the file, never `unreadable:`, since that prefix files the row under the sources the pass could not read and makes the pass exit 2 (`Report.unreadable`, `Report.exit_code`), the reading of an outage, not of a hub whose bytes disagree with its index.
- A head older than the threshold is the held state: the value names D, the day after the head, and each of the set's pairs with no final for D under `tape_root` — tape-bars' tree, local to the host the pass runs on, read by listing — save a pair the newest line's `notes` record as `closed <PAIR>`, whose missing finals the owner has already decided, or says none lacks one, the extension or the hub's pull then being behind. D's finals are nominally published at D + 2 (spec D3); once `now`'s UTC date is `ROLLING_ESCALATE_AFTER_DAYS` days or more past D + 2 and the held state names some pair, the value becomes the attention line: each pair it names, the day, and the owner's decision — close the pair from that day, or wait — naming no command, since the close's command carries the outbox's host paths and the owner's word and its date, which Task 11's runbook section spells. A newest line that `is_ended` (Task 2), its chain walked and its files verified, is the ended state whatever its age, read before the age test: the value names `ended`, the line's day and that no line follows it, and neither the held state nor the attention line is read. No upper bound on the newest line's day is read: every line the extension writes but an ended one, which the state above reads whatever its day, has some pair's final dated on or after its day (Task 2). The three states are `ok` false; an `OSError` on the tape tree is `unreadable:` as on the hub.
- The classifier gains `zcrypto data rolling verify` with `--root` a path and `--as-of` a day, a read-only instrument as `continuity.py` is (:1562), so the runbook's diagnostic for a failing row is one the pass runs on its own.
- `_DESTRUCTIVE` gains `data rolling extend` and `data rolling base`, the set's two writers, a close being an `extend`: the guard that no runbook command carrying a destructive token is ever autonomous then sees them, and the runbook ratio counts no write to the hub as a read-only diagnostic; `data rolling verify` carries neither.
- An autouse fixture in `tests/test_ops_daily.py`, `passing_rolling_head`, replaces `ops_daily.read_rolling_head` with one answering an ok `Check` and returns the real reader, which the reader cases take as their argument, as `live_soak_run` does for `soak_run`; `tests/test_ops_daily_soak.py` imports it beside `live_soak_run`, so every existing case driving `main(["report"])` keeps its exit code with no hub mounted.

- [ ] **Step 1: Read** spec 00125 D3 (the daily pass) and D7 (the check, its fixtures, its threshold); `infra/scripts/ops_daily.py:523-545`, `:720-830` and `:1264-1330`; `tests/test_ops_daily.py:3252-3330`.
- [ ] **Step 2: Write the failing tests**, the hub a `write_chain` tree and the tape a tape-bars tree in its own layout, both under `tmp_path`: `test_the_rolling_head_is_ok_three_days_back`; `test_a_rolling_head_four_days_back_fails`; `test_a_rolling_head_whose_prev_disagrees_fails`; `test_a_rolling_head_naming_an_absent_file_fails`; `test_a_rolling_head_file_with_a_flipped_byte_fails` — these three asserting a value that does not start with `unreadable:`; `test_an_unreadable_rolling_hub_is_unreadable_not_ok`; `test_the_rolling_row_reaches_the_verdict_the_pass_prints` (`main(["report"])` over the stubs `tests/test_ops_daily_soak.py::test_the_soak_row_reaches_the_verdict_the_pass_prints` uses, the reader stubbed: an ok row prints `- PASS rolling canonical head` and exits 0, a failing one `- FAIL rolling canonical head` and exits 1, an unreadable one `rolling canonical head could not be read` and exits 2); `test_the_rolling_verify_is_an_autonomous_read_on_ops` (`uv run zcrypto data rolling verify --root /mnt/zhao-crypto/hot/ohlc-rolling --as-of 2026-10-07` classifies autonomous on `ops`); `test_a_day_held_thirteen_days_past_its_publication_reads_as_held` (one pair's final for D absent from the tape, `now` 13 days past D + 2: not ok, the held state naming the pair, no attention line); `test_a_day_held_fourteen_days_past_its_publication_is_an_attention_line_naming_the_pair` (the same at 14 days: the attention line naming the pair, the day and the close); `test_a_closed_pair_is_never_named_by_the_held_state_or_the_attention_line` (the hub's newest line, by `write_chain(..., closed=...)`, recording one pair closed, that pair's finals absent from the tape and every other pair's D final present, `now` 14 days past D + 2: not ok, the held state saying none lacks one, no attention line; then two other pairs' D finals removed as well: the attention line naming those two, never the closed one); `test_an_ended_set_reads_as_its_own_state` (the hub's newest line, by `write_chain(..., closed=...)`, recording each of the tree's pairs closed, `now` one day past it, where its age alone reads ok: not ok, the value naming `ended` and the line's day; then a tree whose newest line records the first of its pairs in sorted order alone closed: ok); `test_the_rolling_writers_carry_a_destructive_token` (`_destructive` true for the close as R-close spells it and for R4's `rolling base`, false for the verify above).
- [ ] **Step 3: Run them and read the failure**

```bash
uv run pytest tests/test_ops_daily.py -q -p no:cacheprovider -k "test_the_rolling_head_is_ok_three_days_back or test_a_rolling_head_four_days_back_fails or test_a_rolling_head_whose_prev_disagrees_fails or test_a_rolling_head_naming_an_absent_file_fails or test_a_rolling_head_file_with_a_flipped_byte_fails or test_an_unreadable_rolling_hub_is_unreadable_not_ok or test_the_rolling_row_reaches_the_verdict_the_pass_prints or test_the_rolling_verify_is_an_autonomous_read_on_ops or test_a_day_held_thirteen_days_past_its_publication_reads_as_held or test_a_day_held_fourteen_days_past_its_publication_is_an_attention_line_naming_the_pair or test_a_closed_pair_is_never_named_by_the_held_state_or_the_attention_line or test_an_ended_set_reads_as_its_own_state or test_the_rolling_writers_carry_a_destructive_token"
```

Expected: every case errors at the autouse fixture's setup, `ops_daily` having no `read_rolling_head`.

- [ ] **Step 4: Implement** per the decision above, its strings carrying no internal term.
- [ ] **Step 5: Run the tests** — `uv run pytest tests/test_ops_daily.py tests/test_ops_daily_soak.py -q -p no:cacheprovider`; Expected: no failure.
- [ ] **Step 6: The consumers**

```bash
uv run pytest $(infra/scripts/consumers.sh infra/scripts/ops_daily.py | grep -E '^tests/test_[^ ]*\.py$' | sort -u) tests/test_internal_terms_not_operator_visible.py -q -p no:cacheprovider
```

Expected: no failure.

- [ ] **Step 7: The commit gate**

```bash
git add infra/scripts/ops_daily.py tests/test_ops_daily.py tests/test_ops_daily_soak.py && uv run pre-commit run -a
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

- [ ] **Step 9: Prove the guards**, `--file infra/scripts/ops_daily.py`, `TESTS=tests/test_ops_daily.py`: `ROLLING_STALE_AFTER_DAYS` made 4, against `-k test_a_rolling_head_four_days_back_fails`; the chain walk from the newest line dropped, against `-k test_a_rolling_head_whose_prev_disagrees_fails`; `verify_line` dropped, against `-k test_a_rolling_head_file_with_a_flipped_byte_fails` and `-k test_a_rolling_head_naming_an_absent_file_fails`; the unreadable arm's `ok=False` made `ok=True`, against `-k test_an_unreadable_rolling_hub_is_unreadable_not_ok`; the `unreadable: ` prefix put on the `RollingError` arm's value, against `-k test_a_rolling_head_whose_prev_disagrees_fails`; the row's append in `main` dropped, against `-k test_the_rolling_row_reaches_the_verdict_the_pass_prints`; the `zcrypto data rolling verify` shape dropped, against `-k test_the_rolling_verify_is_an_autonomous_read_on_ops`; `ROLLING_ESCALATE_AFTER_DAYS` made 15, against `-k test_a_day_held_fourteen_days_past_its_publication_is_an_attention_line_naming_the_pair`; the escalation's comparison made one day early, against `-k test_a_day_held_thirteen_days_past_its_publication_reads_as_held`; the closed-pair exclusion dropped, against `-k test_a_closed_pair_is_never_named_by_the_held_state_or_the_attention_line`; the ended state dropped, against `-k test_an_ended_set_reads_as_its_own_state`, and, `--file cli/data/rolling.py` with `TESTS` still `tests/test_ops_daily.py`, `is_ended` made true when any pair of the line is closed, against the same name; and, `--file tests/test_ops_daily.py`, `TESTS` the same file, the `data rolling extend` entry dropped from `_DESTRUCTIVE`, and, separately, the `data rolling base` entry, each against `-k test_the_rolling_writers_carry_a_destructive_token` — each `KILLED`; then the message-only amend.
- [ ] **Step 10: The tree is clean** — `git status --porcelain`; Expected: empty.

---

### Task 6: `research eval` reads the rolling canonical at a required as-of day

**Files:**
- Modify: `cli/research/command.py` (`--as-of`, `--accept-holes`; the series check, :87-90; the report, :100-103; the app help, :37, the `--dataset` help, :53, and the `eval` docstring, :74-75, each naming a frozen dataset and its freeze record alone), `cli/research/subjects.py` (`Subject.build`'s signature, :22-27; `_capturing_union`, :34-40; the two builds, :43-67), `cli/portfolio/record44_legs.py` (`load_union`'s docstring, :49-51, naming `ObservedReader.read_series` as the capturing adapter and the bytes the function opens as the run's identity — re-trued to name either adapter, the rolling set's identity being its as-of line)
- Test: `tests/test_research_command.py`

**Interfaces:**
- Consumes: Task 1's `is_chained` and `pairs`; Task 4's `ObservedReader.read_rolling` and `holes`.
- Produces: `zcrypto research eval --dataset ohlc-rolling --as-of YYYY-MM-DD [--accept-holes]`; `Subject.build(reader, dataset, window, as_of=None, accept_holes=False)`.

**What this task decides, where the spec leaves it open:**
- A chained dataset requires `--as-of`, and an unchained one refuses `--as-of` and `--accept-holes`, each before the fit. For a chained set the series check reads `pairs` inside a `RollingError` arm, a base line it cannot read the command's one-line refusal — a required asset's `<asset>/EUR` absent from the set is refused, naming every one — and `_capturing_union` hands each path `load_union` composes to `read_rolling` as the pair its first two parts name and the interval its stem names. The report prints `as of: <day>` under `window:` and each accepted hole as `hole: <pair> <day>`.

- [ ] **Step 1: Read** spec 00125 D4 (the searches); `cli/research/command.py`; `cli/research/subjects.py`; `cli/portfolio/record44_legs.py:48-60` (`load_union`); `tests/test_research_command.py:1-100` and `:196-260`.
- [ ] **Step 2: Write the failing tests**, the set a `write_chain` tree over the ten `/EUR` assets `load_union` reads, the subject a stub registered as `_stub_subject` registers its own (`tests/test_research_command.py:57-65`), over those ten assets, its `build` reading 1440 through `_capturing_union` and returning fixed metrics, so no fit's minimum history applies to a four-day chain: `test_eval_on_a_chained_set_requires_as_of`; `test_eval_on_an_unchained_set_refuses_as_of`; `test_eval_on_the_rolling_set_records_the_as_of_line` (with `--register` into a `tmp_path` registry: the record's `datasets` is the line alone and its `dataset_hash` derives from it; the printed `vouched` carries no `inert`); `test_eval_refuses_a_hole_and_reads_across_it_with_accept_holes` (the second run printing `hole: <pair> <day>`); `test_a_chained_set_missing_a_required_pair_is_refused_naming_it` (the set lacking two of the ten pairs: the refusal names both and none of the eight the set holds); `test_eval_refuses_a_chained_set_whose_base_line_cannot_be_read` (a `write_chain` tree whose base line's bytes are replaced by `{}`: exit 1, the refusal naming the line, `result.exception` a `SystemExit`); `test_the_window_reaches_the_rolling_reads`.
- [ ] **Step 3: Run them and read the failure**

```bash
uv run pytest tests/test_research_command.py -q -p no:cacheprovider -k "test_eval_on_a_chained_set_requires_as_of or test_eval_on_an_unchained_set_refuses_as_of or test_eval_on_the_rolling_set_records_the_as_of_line or test_eval_refuses_a_hole_and_reads_across_it_with_accept_holes or test_a_chained_set_missing_a_required_pair_is_refused_naming_it or test_eval_refuses_a_chained_set_whose_base_line_cannot_be_read or test_the_window_reaches_the_rolling_reads"
```

Expected: every case fails on `No such option: --as-of` or on the missing-series refusal of `<asset>/EUR/<interval>.parquet`.

- [ ] **Step 4: Implement** per the decision above; the two options' help text operator-readable with no internal term.
- [ ] **Step 5: Run the tests** — `uv run pytest tests/test_research_command.py tests/test_research_control.py -q -p no:cacheprovider`; Expected: no failure, the control skipping in a worktree.
- [ ] **Step 6: The consumers**

```bash
uv run pytest $(infra/scripts/consumers.sh cli/research/command.py cli/research/subjects.py cli/portfolio/record44_legs.py | grep -E '^tests/test_[^ ]*\.py$' | sort -u) tests/test_cli_help_hygiene.py tests/test_internal_terms_not_operator_visible.py -q -p no:cacheprovider
```

Expected: no failure.

- [ ] **Step 7: The commit gate**

```bash
git add cli/research/command.py cli/research/subjects.py cli/portfolio/record44_legs.py tests/test_research_command.py && uv run pre-commit run -a
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

- [ ] **Step 9: Prove the guards**: in `cli/research/command.py`, `TESTS=tests/test_research_command.py`, the as-of requirement dropped, against `-k test_eval_on_a_chained_set_requires_as_of`; the unchained refusal dropped, against `-k test_eval_on_an_unchained_set_refuses_as_of`; the chained series check made the file check, against `-k test_a_chained_set_missing_a_required_pair_is_refused_naming_it`; `--accept-holes` not handed to the build, and, separately, the `hole:` line's print dropped, each against `-k test_eval_refuses_a_hole_and_reads_across_it_with_accept_holes`; the series check's `RollingError` arm dropped, against `-k test_eval_refuses_a_chained_set_whose_base_line_cannot_be_read`; in `cli/research/subjects.py`, the window dropped from the rolling read, against `-k test_the_window_reaches_the_rolling_reads`, and the rolling read's `accept_holes` made `True`, against `-k test_eval_refuses_a_hole_and_reads_across_it_with_accept_holes` — each `KILLED`; then the message-only amend.
- [ ] **Step 10: The tree is clean** — `git status --porcelain`; Expected: empty.

---

### Task 7: `engine seed` copies an absent store file from the rolling canonical at its head

**Files:**
- Modify: `cli/engine/command.py` (`seed`, :374-418, and its help, :376-379; the `CANONICAL_DIR` comment, :82-85, whose second sentence names the frozen sibling the seed no longer reads), `cli/engine/store.py` (the module docstring, :1-2; `_STORE_RECOVERY`, :154-159, `_REBUILD_THE_SET`, :160-163, which `_CANONICAL_RECOVERY`, `_FIRST_SEED_REBUILD` and the absent-store hint embed, and `_DISJOINT_CANONICAL_DUMP`, :192 — each naming an ingest, a frozen sibling's rebuild or the quarterly dump as the seed's source)
- Test: `tests/test_engine_command.py` (the seed tests, :160-283), `tests/test_engine_store.py` (every name, docstring, comment and assertion naming those texts' dump, ingest or frozen-sibling rebuild: `test_seed_store_window_shortfall_names_ohlcvt_dump`, :159, its docstring, :160-164, and its pins, :176 and :178; the seam-holes docstring's dump sentence, :196, and its negative pin, :214; the pins of "rebuild the set", :218, :245, :290 and :981, and of its absence, :249 and :342; the pins of `data rebuild ohlc-full --no-push`, :243, :439 and :809, and of "the data pipeline's to republish", :440 and :808, and the docstring naming "the data pipeline's recovery", :795; `test_seed_store_disjoint_reseed_names_store_file_recovery_not_the_dump`, :296, its docstring, :297-299, and its comment and pin, :312; the empty-fetch docstring's dump sentence, :320-324, and its negative pin, :336; the negative pin at :361 — each positive pin re-pointed at the re-trued text, each negative pin at the re-trued words of the remedy it keeps out of its arm, so it still tells that arm from the one whose remedy it names)

**Interfaces:**
- Consumes: Task 1's `head` and `read_rolling`; `seed_store(store_dir, canonical_dir)` (`cli/engine/store.py:341-407`), its logic unchanged; `BASKET` and `GRID_INTERVALS` (`cli/engine/store.py:24-43`).
- Produces: a seed whose canonical, for an absent store file, is the rolling set under the configured data root at its local head; `zcrypto engine seed [--accept-holes]`.

**What this task decides, where the spec leaves it open:**
- `seed_store` keeps its directory argument and its logic: the seed writes, for each absent store series alone, `read_rolling`'s frame at the head into a temporary store-shaped directory, `<scratch>/<BASE>/<QUOTE>/<interval>.parquet`, and hands it over — `seed_store` opens the canonical for an absent store file only (`cli/engine/store.py:360-365`). Its summary names `canonical ohlc-rolling as of <day> (<first twelve hex>)`; a `RollingError` or a missing set is the seed's refusal with its existing prefix (:396-401). A seed over a complete store reads no rolling set, as it reads no canonical today.
- A hole in a series the seed reads refuses, naming the pair and the day, unless `--accept-holes`, when the frame is copied without that day and the summary prints each `hole: <pair> <day>`: a hole is permanent, so a refusal with no accept path would close the store's repair path for that pair for good, and the store's frame check takes a frame missing a day as it takes the dump's omitted no-trade bars. Without the flag the seed refuses, never accepting a hole in silence: it delivers the engine's live store, whose own check is a seam check at the tail, not an interior-gap check, and whose REST fill reaches only its window, so no later step would name the missing day.
- The store's recovery texts are re-trued to the rolling set: a canonical tail the REST window no longer reaches is cured by `zcrypto data fetch` bringing the hub's newer head, and a canonical frame the store refuses is the owner's question, the set being written once on the hub with its bytes pinned by its index — never a rebuild of `ohlc-full`, an ingest or the quarterly dump, none of which the seed reads any more.

- [ ] **Step 1: Read** spec 00125 D4 (the seed) and D6 (the hole); `cli/engine/command.py:80-90` and `:374-418`; `cli/engine/store.py:1-2`, `:150-195` and `:341-407`; `tests/test_engine_command.py:160-283`; `tests/test_engine_store.py:155-362`, `:432-441`, `:790-811` and `:970-982`.
- [ ] **Step 2: Write the failing tests** — `test_seed_copies_absent_series_from_the_rolling_set_at_its_head` (a `write_chain` tree over the twelve `BASKET` pairs as the configured data root's `ohlc-rolling`, two store files absent, of two pairs; `seed_store` stubbed to record the directory it was handed and the frames under it: the two absent series alone, each equal to `read_rolling` at the head, its columns `FRAME_SCHEMA`'s, and each giving `[]` from `cli.engine.store._frame_differences` for its interval — the check `seed_store` runs over a canonical before it copies, which the stub would otherwise keep the frames from meeting); `test_seed_refuses_a_hole_and_copies_across_it_with_accept_holes` (a hole in the absent series' pair: refused naming the pair and the day; with `--accept-holes`, the handed-over frame lacks that day and the summary prints `hole: <pair> <day>`); `test_seed_refuses_naming_the_rolling_set_when_it_cannot_be_read` (replacing `test_seed_refuses_when_no_whole_frozen_set_resolves`); `test_seed_prints_per_pair_overlap_summary`, `test_seed_engine_error_is_a_clean_exit_1`, `test_seed_refuses_without_a_configured_data_dir` and `test_seed_reads_no_canonical_when_every_store_file_is_present` re-pointed from `resolve_canonical_root` to the rolling set; in `tests/test_engine_store.py`, the pins of the re-trued texts assert the rolling set's remedies, and `test_seed_store_window_shortfall_names_ohlcvt_dump` and `test_seed_store_disjoint_reseed_names_store_file_recovery_not_the_dump` are renamed for the remedies they now pin.
- [ ] **Step 3: Run them and read the failure**

```bash
uv run pytest tests/test_engine_command.py -q -p no:cacheprovider -k "test_seed_copies_absent_series_from_the_rolling_set_at_its_head or test_seed_refuses_a_hole_and_copies_across_it_with_accept_holes or test_seed_refuses_naming_the_rolling_set_when_it_cannot_be_read"
```

Expected: all three fail, the seed resolving a frozen sibling and taking no `--accept-holes`.

- [ ] **Step 4: Implement** per the decisions above and re-true the comment, the seed's help and the store's texts.
- [ ] **Step 5: Run the tests** — `uv run pytest tests/test_engine_command.py tests/test_engine_store.py -q -p no:cacheprovider`; Expected: no failure.
- [ ] **Step 6: The consumers**

```bash
uv run pytest $(infra/scripts/consumers.sh cli/engine/command.py cli/engine/store.py | grep -E '^tests/test_[^ ]*\.py$' | sort -u) tests/test_cli_help_hygiene.py tests/test_internal_terms_not_operator_visible.py -q -p no:cacheprovider
```

Expected: no failure.

- [ ] **Step 7: The commit gate**

```bash
git add cli/engine/command.py cli/engine/store.py tests/test_engine_command.py tests/test_engine_store.py && uv run pre-commit run -a
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

- [ ] **Step 9: Prove the guards**, `--file cli/engine/command.py`, `TESTS=tests/test_engine_command.py`: the head replaced by the base line, against `-k test_seed_copies_absent_series_from_the_rolling_set_at_its_head`; the `RollingError` arm dropped, against `-k test_seed_refuses_naming_the_rolling_set_when_it_cannot_be_read`; the absent-only gate on the rolling read dropped, against `-k test_seed_reads_no_canonical_when_every_store_file_is_present`; `--accept-holes` not handed to the read, and, separately, the read's `accept_holes` made `True`, each against `-k test_seed_refuses_a_hole_and_copies_across_it_with_accept_holes` — each `KILLED`; then the message-only amend.
- [ ] **Step 10: The tree is clean** — `git status --porcelain`; Expected: empty.

---

### Task 8: The universe rebuild reads the rolling canonical; the reach round and the frozen-sibling resolvers retire

**Files:**
- Modify: `cli/data/rebuild.py` (`_refresh_universe`, :184-287, on the rolling set; `_rebuild_ohlc_reach`, :77-90, its import, :27, and its `REBUILDABLE` entry, :293, deleted; `_STAMPED_REACH`, `_STAMPED_FULL`, `_basket_legs`, `_missing_from_whole_set`, `resolve_canonical_root` and `resolve_ohlc_source`, :126-181, deleted; `_require_fresh_ohlc`'s refusal text, :117-123, naming the rolling set; `BUILDER_REFUSALS`, :301-310, gaining `RollingError`, so a hole or a chain the universe's read refuses reaches the operator as `data rebuild`'s one-line refusal), `cli/data/command.py` (the `rebuild` help, :72), `zcrypto.toml` (`ohlc-reach` out of `authored_sets`, :12), `cli/engine/store.py` (:104 and :314, each naming `cli/ohlc/reach.py` as a sibling), `cli/ohlc/dataset.py` (:13-14), `cli/ohlc/seam.py` (:1)
- Delete: `cli/ohlc/reach.py`, `tests/test_ohlc_reach.py`
- Test: `tests/test_data_rebuild.py` (the universe tests, :162-530, re-pointed; the resolver tests, :465-484 and :521-581, the reach tests, :584-670, and the `cli.ohlc.reach` import, :15, deleted), `tests/test_data_command.py` (`test_rebuild_ohlc_reach_aborts_naming_a_canonical_file_it_cannot_join`, :185-219, deleted; `_BUILDER_REFUSALS`, :129-138, gaining `cli.data.rolling.RollingError`, which `test_every_builder_refusal_has_its_case_and_every_case_its_refusal` requires and `test_rebuild_turns_a_builders_own_refusal_into_an_abort_not_a_traceback` drives through the command); `tests/test_data_rebuild.py::test_every_rebuildable_dataset_is_an_authored_set` (:673), unchanged, holds `REBUILDABLE`'s names inside `authored_sets`, so `ohlc-reach` leaves both in this commit; `tests/test_data_manifest.py` (`_PRODUCERS`, :436-443, its reach case, :452-453, and `_drive_reach`, :362-380, lose `cli/ohlc/reach.py`); `tests/test_universe_provenance.py` (`test_the_universe_doc_cites_a_hash_that_reproduces_from_the_set_it_names`, :48-72, learns the chained set; its :61-62 comment names `resolve_ohlc_source`)

**Interfaces:**
- Consumes: Task 1's `head`, `pairs`, `read_rolling`, `ROLLING_SET`.
- Produces: a universe file whose provenance is `snapshot_sha256`, `ohlc_dataset_hash` (the head line's sha256), `ohlc_dataset_dir` (`ohlc-rolling`), `ohlc_as_of` (the head's day), `ohlc_stalest_daily_bar` and `ohlc_closed_pairs` (the pairs left out as closed, sorted, empty when none is).

**What this task decides, where the spec leaves it open:**
- The universe reads each candidate symbol's 1440 frame by `read_rolling` at the head with a `window` spanning the `_UNIVERSE_VOLUME_WINDOW_DAYS` daily bars that end at the head day, the rows its median and its freshness check read (`cli/universe/volume.py:8-31`, `cli/data/rebuild.py:200-214`): a hole inside that window refuses, a hole before it is never read — a hole is permanent, and a whole-history read would refuse every later rebuild on one hole; a pair the head line's `notes` record as `closed <PAIR>` is left out of `symbols` (:187), the candidate list the snapshot (:190), the derivation (:191), the dailies' reads (:201) and the spreads (:222) take, for as long as the close runs, and `ohlc_closed_pairs` names it, as spec D6 rules; the missing-leg refusal (:194), which iterates `CANDIDATE_SYMBOLS`, reads `pairs`, where a closed pair stays; a closed pair the selection rule's own mandatory test names — `_is_mandatory` over `MANDATORY` (`cli/universe/rules.py:18`, :37-40), never a second copy of that rule, handed the notes key's `<BASE>/<QUOTE>` split on `/` as an object carrying `base` and `quote`, since it reads `pair.base` and `pair.quote` (:40) and a notes key is a string, so BTC/EUR or ETH/EUR and never ETH/BTC — refuses the rebuild with a `DataSyncError` naming the pair, before anything is fetched or written, as spec D6 rules; BTC/EUR, the `/BTC` legs' EUR rate (:200, :210), stays read for them, a rebuild going on only while it is open; the manifest identity block (:239-270) goes, the head line being the identity. `data rebuild ohlc-reach` becomes an unknown set, refused by the existing arm. `cli/ohlc/fetch.py` and `cli/ohlc/seam.py` stay, the engine's store importing both.
- The provenance test learns the chained set: where the set the universe doc names holds `index/`, the cited sha256 must be the sha256 of one of its index lines' bytes and `verify` to that line's day must pass; the manifest arm stays for a set that carries one; the skip fires only when neither `<set>/manifest.json` nor `<set>/index` is under `data/`. The comparison moves into a helper the live test calls, so a `write_chain` tree drives the chained arm, which the doc reaches only at the next universe rebuild.

- [ ] **Step 1: Read** spec 00125 D4 (the universe, the resolvers), D5 and D6 (the hole); `cli/data/rebuild.py`; `tests/test_data_rebuild.py:140-670`; `tests/test_data_command.py:180-225`; `tests/test_data_manifest.py:360-460`; `tests/test_universe_provenance.py`.
- [ ] **Step 2: Write the failing tests** — `test_refresh_universe_reads_the_rolling_set_at_its_head` (and, the newest line's day file of one pair removed, as a fetch that brought a line ahead of its file leaves it, at the line before — `days` 30 or more, the line before carrying one daily bar fewer than the head's); `test_refresh_universe_provenance_names_the_set_the_as_of_and_the_line`; `test_refresh_universe_refuses_a_rolling_set_whose_chain_does_not_walk` (replacing the two manifest refusals, :244-296; its refusal is `read_rolling`'s walk, Task 1's guard, so it carries no probe of its own); `test_rebuild_refuses_ohlc_reach_as_an_unknown_set`; `test_refresh_universe_reads_past_a_hole_older_than_its_volume_window` (a hole on 2026-10-01 under a head 31 days later: the rebuild succeeds; the hole moved inside the window: refused naming the pair and the day); `test_refresh_universe_leaves_a_closed_pair_out_and_names_it` (two `/EUR` pairs other than BTC/EUR and ETH/EUR closed by `write_chain(..., closed=...)` from a day inside the 30 to the head: the rebuild completes, both absent from the file's entries and `selected`, `ohlc_closed_pairs` naming both, sorted; the same days written as those pairs' plain `holes`, both open: refused naming one of them and the day); `test_refresh_universe_refuses_a_closed_mandatory_pair`, parametrised over BTC/EUR and ETH/EUR (that pair and ADA/EUR, which sorts before it, closed by `write_chain(..., closed=...)` from a day inside the 30 to the head: refused with a `DataSyncError` naming that pair and not ADA/EUR, never the `RollingError` a read of a closed BTC/EUR's holes as the `/BTC` legs' rate would raise, no universe file written); `test_refresh_universe_leaves_a_closed_eth_btc_out_though_eth_is_mandatory` (ETH/BTC closed the same way, alone: the rebuild completes, ETH/BTC absent from the file's entries and `selected`, `ohlc_closed_pairs` naming it — `MANDATORY` names a base's EUR leg, never the base alone); in `tests/test_universe_provenance.py`, `test_a_doc_naming_a_chained_set_cites_one_of_its_lines` (the helper over a `write_chain` tree named `ohlc-rolling` and a doc text naming `data/ohlc-rolling/`: citing a line's sha256 passes, citing any other 64-hex value fails); in `tests/test_data_command.py`, `_BUILDER_REFUSALS` gaining `cli.data.rolling.RollingError`; the remaining universe tests of `tests/test_data_rebuild.py`, the thirteen in :162-530 beside the resolver tests Files deletes, built by `write_chain` in place of a manifest-bearing `ohlc-full` or reach sibling, with at least 30 daily bars per pair — `days` 29 or more — since `median_quote_volume` refuses fewer (`cli/universe/volume.py:10-11`), save the one case whose short set is its subject, below. A chained set ends each pair at its one head, a pair the tape stops carrying being a hole or a held head, never a shorter frame, so no fixture makes one pair staler than another; the thirteen go thus. `test_refresh_universe_actually_applies_the_spread_cap`, `test_refresh_universe_accepts_an_ohlc_set_inside_the_staleness_budget` and `test_a_source_missing_a_candidate_leg_refuses_and_names_it` (the base line without ETH/BTC) keep their assertions; `test_refresh_universe_refuses_a_stale_ohlc_set` and `test_refresh_universe_diagnoses_staleness_before_the_row_count` keep theirs, the day each refusal names the chain's head, the second's set shorter than the 30 daily bars as before; `test_refresh_universe_requires_live_ohlc_full`, renamed for the rolling set, refuses where no `ohlc-rolling` is, naming it; `test_refresh_universe_reads_the_resolved_source_not_the_hardcoded_ohlc_full`, renamed the same way, keeps its stale manifest-bearing `ohlc-full` beside a `write_chain` set and asserts the provenance names `ohlc-rolling` and its head line; `test_refresh_universe_medians_over_the_window_its_params_declare` keeps its assertions through `write_chain`'s `bar` (Task 1) — `days` 39, BTC/EUR's `vwap` one value on its first 30 daily bars and twice it on the last 10, so the medians over 30 and over 20 differ — and `test_a_symbol_the_floor_rejects_is_NOT_a_missing_source` keeps its own, SOL/BTC's `volume` 0.001 through `bar`; `test_refresh_universe_writes_point_in_time_universe_json` keeps its assertions, its `ohlc_dataset_hash` and `ohlc_dataset_dir` then the head line's sha256 and `ohlc-rolling`, and its different-frontier `ohlc_stalest_daily_bar` the head's day; three go — `test_refresh_universe_refuses_a_basket_where_only_some_symbols_are_fresh`, whose stale pair no chained set can hold, so no case is left telling the freshness check's min from its max, which a chained set never distinguishes, and the two manifest refusals, :244-296, replaced above.
- [ ] **Step 3: Run them and read the failure**

```bash
uv run pytest tests/test_data_rebuild.py tests/test_universe_provenance.py tests/test_data_command.py -q -p no:cacheprovider -k "test_refresh_universe_reads_the_rolling_set_at_its_head or test_refresh_universe_provenance_names_the_set_the_as_of_and_the_line or test_refresh_universe_refuses_a_rolling_set_whose_chain_does_not_walk or test_rebuild_refuses_ohlc_reach_as_an_unknown_set or test_refresh_universe_reads_past_a_hole_older_than_its_volume_window or test_refresh_universe_leaves_a_closed_pair_out_and_names_it or test_refresh_universe_refuses_a_closed_mandatory_pair or test_refresh_universe_leaves_a_closed_eth_btc_out_though_eth_is_mandatory or test_a_doc_naming_a_chained_set_cites_one_of_its_lines or test_every_builder_refusal_has_its_case_and_every_case_its_refusal or RollingError"
```

Expected: the nine new tests fail, ten cases with the mandatory refusal's two pairs, the universe reading `resolve_ohlc_source`'s source, `ohlc-reach` rebuilding and the provenance helper absent, and the two builder-refusal cases fail on `RollingError` absent from `BUILDER_REFUSALS`.

- [ ] **Step 4: Implement** the universe's source; write the provenance helper Step 2's chained case calls, the live test's comparison moved into it beside its new chained arm; delete the two files Files names with `rm`, not `git rm`, so Step 7's `git add` stages their deletion; re-true the four comments the Files entry names; then confirm nothing names the deleted code:

```bash
git grep -n -E 'reach_round|cli\.ohlc\.reach|cli/ohlc/reach\.py|resolve_canonical_root|resolve_ohlc_source|_STAMPED_(REACH|FULL)' -- cli tests infra .claude zcrypto.toml ':!*vault.yml' ':!*.vault' ':!*.sops.*' ':!*vault-password*' ':!infra/ansible/files/*_ed25519'
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
git add cli/data/rebuild.py cli/data/command.py zcrypto.toml cli/engine/store.py cli/ohlc/dataset.py cli/ohlc/seam.py cli/ohlc/reach.py tests/test_ohlc_reach.py tests/test_data_rebuild.py tests/test_data_command.py tests/test_data_manifest.py tests/test_universe_provenance.py && uv run pre-commit run -a
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

- [ ] **Step 9: Prove the guards**, `--file cli/data/rebuild.py`, `TESTS=tests/test_data_rebuild.py`: the head replaced by the base line, against `-k test_refresh_universe_reads_the_rolling_set_at_its_head`; `ohlc_as_of` dropped from the provenance, against `-k test_refresh_universe_provenance_names_the_set_the_as_of_and_the_line`; the head read made the newest listed line, its files unchecked, against `-k test_refresh_universe_reads_the_rolling_set_at_its_head`; `"ohlc-reach": _refresh_universe` added to `REBUILDABLE`, against `-k test_rebuild_refuses_ohlc_reach_as_an_unknown_set`; the window dropped from the universe's read, and, separately, the read's `accept_holes` made `True`, each against `-k test_refresh_universe_reads_past_a_hole_older_than_its_volume_window`; the closed-pair skip dropped, and, separately, `ohlc_closed_pairs` written empty, each against `-k test_refresh_universe_leaves_a_closed_pair_out_and_names_it`; the mandatory refusal dropped, and, separately, the refusal read from the first closed pair alone, each against `-k test_refresh_universe_refuses_a_closed_mandatory_pair`; the mandatory test made the base alone against `MANDATORY`, against `-k test_refresh_universe_leaves_a_closed_eth_btc_out_though_eth_is_mandatory`; `RollingError` dropped from `BUILDER_REFUSALS`, `TESTS=tests/test_data_command.py`, against `-k "test_rebuild_turns_a_builders_own_refusal_into_an_abort_not_a_traceback and RollingError"`; in `tests/test_universe_provenance.py`, `TESTS` the same file, the chained arm's line-hash comparison made always equal, against `-k test_a_doc_naming_a_chained_set_cites_one_of_its_lines` — each `KILLED`; then the message-only amend.
- [ ] **Step 10: The tree is clean** — `git status --porcelain`; Expected: empty.

---

### Task 9: The tape-bars runner extends the rolling canonical after each sweep

**Files:**
- Modify: `infra/ansible/roles/ops/templates/tape-bars.sh.j2` (the extension after the gauge export, :97-126, before `exit "$rc"`, :128; the comment at :9-10, which claims a NAS pull of tape-bars' output that no channel makes), `infra/ansible/roles/ops/defaults/main.yml` (`ops_rolling_staging_subdir: hot-out-staging` after `ops_hot_out_subdir`, :33; the comment on `ops_hot_group`, :47, naming `zhaow` alone as writing into the outbox), `infra/ansible/roles/ops/tasks/main.yml` (a staging-directory task after the outbox's, :245-251; the outbox group's gid looked up beside the data user's uid and gid, :339-347), `infra/ops/README.md` (:14, the outbox's writers, which the runner's extension joins as `zcrypto-data`; :175, hot sets carrying `manifest.json`, which the rolling set does not), `infra/nas/README.md` (:108, the `HOT_SOURCE` row's hot sets carrying `manifest.json`, the NAS side of :175)
- Test: `tests/test_infra_tape_bars_template.py` (`CONTEXT`, :22-35, gains `ops_hot_out_subdir`, `ops_rolling_staging_subdir` and `ops_hot_gid`), `tests/test_infra_converge_guards.py`, `tests/test_infra_shell_templates_render.py` (`RUNTIME_FACTS`, :19-31, gains `"ops_hot_gid": "1002"`, a converge-time fact the role defaults do not carry)

**Interfaces:**
- Consumes: Task 2's `zcrypto data rolling extend` and its summary line.
- Produces: the unit that, after each sweep, runs the extension in the same pinned image and exits with the sweep's code when the sweep failed, else the extension's.

**What this task decides, where the spec leaves it open:**
- The extension is a second `docker run --rm --pull never --name zcrypto-rolling-extend --user "{{ ops_uid }}:{{ ops_gid }}" --group-add "{{ ops_hot_gid }}" --entrypoint zcrypto` — the entrypoint as every ops runner passes it, the image's own resetting the arguments and starting `zcrypto capture` (`infra/docker/Dockerfile:66`) —, its image `"{{ ops_image }}@{{ ops_image_digest }}"`, the materialize step's own operand, so the extension runs the image the sweep ran, mounting `{{ ops_data_dir }}:/data` and `{{ ops_data_dir }}/{{ ops_tape_bars_subdir }}:/data/{{ ops_tape_bars_subdir }}:ro` and nothing else, running `data rolling extend --tape-root "/data/{{ ops_tape_bars_subdir }}" --out "/data/{{ ops_hot_out_subdir }}/ohlc-rolling" --staging "/data/{{ ops_rolling_staging_subdir }}"`: the outbox and the staging directory sit on one mount, so the writer's rename stays on one filesystem, and the tape tree is read-only to it. It runs after the gauge export, so its outcome never rewrites the sweep's gauges; its output is replayed to the journal as the sweep's is.
- `--group-add` is load-bearing: `--user` with a numeric uid and gid gives the container no supplementary group, and the base's directories, created by the research user, are writable to the outbox's group alone, `zcrypto-hot` (gid 1002 on `zcrypto-ops`, `zcrypto-data` a member — `getent group zcrypto-hot`). `ops_hot_gid` is set from an `ansible.builtin.getent` of `{{ ops_hot_group }}` beside the uid and gid derivation, so every digest-gated block can read it, as `ansible_facts['getent_group'][ops_hot_group][1]`: a group record's fields after its name are password, gid and members, so its gid is index 1, where the passwd record's gid beside it, `ops_gid`, is index 2 (`infra/ansible/roles/ops/tasks/main.yml:347`), and as `ops_journal_gid` reads `systemd-journal`'s (`:860`).
- The staging directory is the outbox's sibling, `{{ ops_data_dir }}/{{ ops_rolling_staging_subdir }}`, owner `{{ ops_data_user }}`, group `{{ ops_hot_group }}`, mode `"2775"`, ungated as the outbox is: the NAS pull pins `hot-out` alone, so nothing under the staging directory is ever pulled.

- [ ] **Step 1: Read** spec 00125 D3; `infra/ansible/roles/ops/templates/tape-bars.sh.j2`; `infra/ansible/roles/ops/tasks/main.yml:238-252`; `tests/test_infra_tape_bars_template.py`; `tests/test_infra_converge_guards.py:20-80` and `:2150-2170`.
- [ ] **Step 2: Write the failing tests** — in `tests/test_infra_tape_bars_template.py`, a helper slicing the second `docker run` up to its redirection: `test_the_extend_step_hands_the_cli_the_tape_the_outbox_and_the_staging` (the CLI's own option names read through `get_command(app)`, as the materialize case reads its positionals, `--entrypoint` followed by `zcrypto`, and the image, the token before `data rolling extend`, equal to the first `docker run`'s); `test_the_extend_step_mounts_the_data_dir_once_and_the_tape_read_only` (the mounts exactly the two); `test_the_extend_step_runs_as_the_data_user_in_the_outbox_group` (`--user 998:998` and `--group-add` with `CONTEXT`'s `ops_hot_gid`); `test_the_extend_step_runs_after_the_gauges_are_written` (its `docker run` after `mv "$tmp" "$PROM"`); `test_a_failed_extend_fails_the_unit_and_a_failed_sweep_keeps_its_own_rc` (the tail from the extension to `exit` run in `bash` with `docker` a shell function answering a given code: sweep 0 and extension 1 exit 1, sweep 2 and extension 0 exit 2, sweep 2 and extension 1 exit 2, both 0 exit 0). In `tests/test_infra_converge_guards.py`: `test_the_rolling_staging_dir_is_the_outboxs_sibling_with_its_owner_group_and_mode` (the task named `ensure the rolling canonical's staging directory exists` by `find_task(load_tasks(OPS_TASKS), …)`: its path, owner, group and mode as above, no `when`, after the outbox's task by `task_index`); `test_the_outbox_groups_gid_is_derived_beside_the_data_users` (an `ansible.builtin.getent` of `{{ ops_hot_group }}` in the group database and a `set_fact` of `ops_hot_gid` from it, both before the first digest-gated block, the `set_fact` rendered through the Templar over `{"ansible_facts": {"getent_group": {"zcrypto-hot": ["x", "1002", "zcrypto-data,zhaow"]}}, "ops_hot_group": "zcrypto-hot"}` giving `"1002"`).
- [ ] **Step 3: Run them and read the failure**

```bash
uv run pytest tests/test_infra_tape_bars_template.py tests/test_infra_converge_guards.py -q -p no:cacheprovider -k "test_the_extend_step_hands_the_cli_the_tape_the_outbox_and_the_staging or test_the_extend_step_mounts_the_data_dir_once_and_the_tape_read_only or test_the_extend_step_runs_as_the_data_user_in_the_outbox_group or test_the_extend_step_runs_after_the_gauges_are_written or test_a_failed_extend_fails_the_unit_and_a_failed_sweep_keeps_its_own_rc or test_the_rolling_staging_dir_is_the_outboxs_sibling_with_its_owner_group_and_mode or test_the_outbox_groups_gid_is_derived_beside_the_data_users"
```

Expected: the five template cases fail on the absent second `docker run`; the two guard cases on the absent tasks.

- [ ] **Step 4: Implement** per the decisions above; correct the :9-10 comment to say the tree stays on the ops host and the rolling set's day files reach the NAS through the outbox; in `infra/ops/README.md`, :14's "(`zcrypto-data` owns + serves it, `zhaow` writes into it)" becomes "(`zcrypto-data` owns + serves it and writes the rolling canonical's daily extension into it from the tape-bars runner, `zhaow` writes into it)", and :175's "carry `manifest.json`, not" becomes "carry `manifest.json` — `ohlc-rolling` its chained index instead — not"; in `infra/nas/README.md`, :108's "hot sets carry `manifest.json`, not sidecars" becomes "hot sets carry `manifest.json` — `ohlc-rolling` its chained index instead — not sidecars"; in the role defaults, :47's "zcrypto-data owns + serves; zhaow authors into it." becomes "zcrypto-data owns + serves, and writes the rolling canonical's daily extension from the tape-bars runner through `--group-add`; zhaow authors into it."
- [ ] **Step 5: Run the tests**

```bash
uv run pytest tests/test_infra_tape_bars_template.py tests/test_infra_converge_guards.py tests/test_infra_shell_templates_render.py -q -p no:cacheprovider
```

Expected: no failure.

- [ ] **Step 6: The consumers**

```bash
uv run pytest $(infra/scripts/consumers.sh infra/ansible/roles/ops/templates/tape-bars.sh.j2 infra/ansible/roles/ops/defaults/main.yml infra/ansible/roles/ops/tasks/main.yml infra/ops/README.md infra/nas/README.md | grep -E '^tests/test_[^ ]*\.py$' | sort -u) tests/test_internal_terms_not_operator_visible.py -q -p no:cacheprovider
```

Expected: no failure.

- [ ] **Step 7: The commit gate**

```bash
git add infra/ansible/roles/ops/templates/tape-bars.sh.j2 infra/ansible/roles/ops/defaults/main.yml infra/ansible/roles/ops/tasks/main.yml infra/ops/README.md infra/nas/README.md tests/test_infra_tape_bars_template.py tests/test_infra_converge_guards.py tests/test_infra_shell_templates_render.py && uv run pre-commit run -a
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

- [ ] **Step 9: Prove the guards**: in `tape-bars.sh.j2`, `TESTS=tests/test_infra_tape_bars_template.py`, the extension's `--staging` pointed under the outbox, and, separately, the extension's `--entrypoint zcrypto` dropped, and, separately, `@{{ ops_image_digest }}` dropped from the extension's image, each against `-k test_the_extend_step_hands_the_cli_the_tape_the_outbox_and_the_staging`; the `:ro` dropped from the tape mount, against `-k test_the_extend_step_mounts_the_data_dir_once_and_the_tape_read_only`; the `--group-add` line dropped, against `-k test_the_extend_step_runs_as_the_data_user_in_the_outbox_group`; the extension moved above the gauge export (a range move written against the committed text), against `-k test_the_extend_step_runs_after_the_gauges_are_written`; the rc combination made `rc=$extend_rc`, against `-k test_a_failed_extend_fails_the_unit_and_a_failed_sweep_keeps_its_own_rc`; in `tasks/main.yml`, `TESTS=tests/test_infra_converge_guards.py`, the staging task's mode made `"0755"`, against `-k test_the_rolling_staging_dir_is_the_outboxs_sibling_with_its_owner_group_and_mode`; the gid lookup's `database: group` made `database: passwd`, and, separately, the gid's subscript `[1]` made `[2]`, each against `-k test_the_outbox_groups_gid_is_derived_beside_the_data_users` — each `KILLED`; then the message-only amend.
- [ ] **Step 10: The tree is clean** — `git status --porcelain`; Expected: empty.

---

### Task 10: The catalog, the fleet reference and the README name the rolling canonical

**Files:**
- Modify: `docs/reference/data-catalog-full.md` (a `### ohlc-rolling` section in `## hot` before `### ohlc-full`; `ohlc-full`'s :13 and `ohlc-15m`'s :67, which still name the retired Q2 siblings; `ohlc-reach`'s :69-80; tape-bars' consumers line, :142; the `engine-store` bullet, :154), `docs/reference/fleet.md` (:66's `hot/` list), `docs/universe/point-in-time-universe.md` (:84 and :100, which name `resolve_ohlc_source` and the reach round, both retired by Task 8, as the page's source's resolver and producer), `README.md` (the `data` section's reach paragraphs and rebuild list, :328-337, and its universe-source clause, :340; the `research eval` table, :352-368; the `engine seed` row, :112)

- [ ] **Step 1: Read** spec 00125 D8, whose sentences these edits carry out, and the spec's measured basis, from which every figure the catalog states is copied; each page's lines above.
- [ ] **Step 2: The catalog and the fleet reference** — the new section states the set, its three trees, its seam at 2026-10-01, its vwap change, its index and its holes, its author and channel, and how a search names it; `ohlc-full` and `ohlc-15m` are frozen pins for the records citing them, new work reading `ohlc-rolling`, and drop the Q2 names; `ohlc-reach` says its producer retired, records the REST disagreement of D5 and names the two sets the hub keeps and why. The lines naming `ohlc-full-20261007` (:13), `ohlc-15m-20261007` (:67) and `ohlc-reach-20261007` (:80) say each is on `hot/` until the owner retires it (spec D5) and then off `hot/`, in the NAS backup directory the owner chooses, naming no directory — so no line goes false at the owner's move, wherever the set goes. New paragraphs one line each; a universal word in a new list item of `fleet.md` carries its `(set: …; count: …)` or `(no count command: …)`. The universe page's two sentences, each quoted text becoming the text after the arrow, nothing else on its line moving: `docs/universe/point-in-time-universe.md:84`, "`resolve_ohlc_source` as the newest stamped" → "`resolve_ohlc_source`, retired since, as the newest stamped"; `:100`, "`_refresh_universe` resolves the newest stamped reach sibling, and the reach round now mints all twelve" → "`_refresh_universe` resolved the newest stamped reach sibling, and the reach round then minted all twelve".

```bash
uv run python infra/scripts/guidance-guard.py --uncounted docs/reference/fleet.md
```

Expected: no output.

- [ ] **Step 3: The README** — the `data` section gains the `rolling` group's three commands with their options, loses the reach paragraphs and `ohlc-reach` from the rebuild list, and names the rolling set as the universe's source; `research eval` gains `--as-of` and `--accept-holes`; `engine seed`'s row names the rolling set at its head and its `--accept-holes`; no internal term enters. Each sentence the earlier tasks made false is re-trued, the text after the arrow its new reading:
- `README.md:298`: "fetches the same small `hot/` working set from the NAS hub and pushes back only what it authored;" → "fetches the same small `hot/` working set from the NAS hub and pushes back only what it authored, save the rolling canonical, which the ops node writes into its outbox and the NAS pulls;".
- `README.md:300`: "verifying newly fetched files against their manifest's `sha256` by default" → "verifying newly fetched files by default — a set's parquet against its manifest, the rolling canonical's against its index lines, a day file no line names yet, or a line whose file has not arrived, left pending until the other arrives".
- `README.md:308`, the `--no-verify` row: "Skip manifest hash verification of newly fetched files." → Task 3's help text, "Skip hash verification of newly fetched files against their manifest or index."
- `README.md:322`: "the ops node is pull-only and only consumes frozen baskets via `fetch`." → "the ops node authors one set, the rolling canonical, through its outbox, which the NAS pulls, and otherwise consumes frozen baskets via `fetch`."
- `README.md:340`: "a `universe` rebuild whose resolved OHLC source (the newest `ohlc-reach-<stamp>` sibling, else `ohlc-full`) is staler than the 7-day budget, is missing any candidate leg, or whose `manifest.json` is missing/unreadable — the set then cannot identify itself, so no artifact is written" → "a `universe` rebuild whose source, the rolling canonical at its local head, is staler than the 7-day budget, is missing any candidate leg, has an index chain that does not walk, holds a hole of a candidate pair in the 30 days its volume median reads (a pair the owner has closed is left out of the candidates), or records a mandatory pair, BTC/EUR or ETH/EUR, as closed — no artifact is then written".
- `README.md:346`: "Evaluates a committed system over a frozen dataset" → "Evaluates a committed system over a frozen dataset, or over the rolling canonical at an as-of day,".
- `README.md:355`, the `--dataset` row: "Frozen dataset directory name under the repo's `data/` root, e.g. `ohlc-full`." → "Dataset directory name under the repo's `data/` root: a frozen set, e.g. `ohlc-full`, or the rolling canonical `ohlc-rolling`, which requires `--as-of`."
- `README.md:368`: "(a dataset with no `manifest.json` reports as inert — nothing cross-checked the bytes)" → "(a dataset with no `manifest.json` reports as inert — nothing cross-checked the bytes — save the rolling canonical, which reports `chained` with its as-of day and line, every file the run read checked against its index)".
- [ ] **Step 4: The consumers**

```bash
uv run pytest $(infra/scripts/consumers.sh docs/reference/data-catalog-full.md docs/reference/fleet.md docs/universe/point-in-time-universe.md README.md | grep -E '^tests/test_[^ ]*\.py$' | sort -u) tests/test_internal_terms_not_operator_visible.py -q -p no:cacheprovider
```

Expected: no failure.

- [ ] **Step 5: The commit gate and the two commits** — the reference pages first, then the README, each staged by path and gated:

```bash
git add docs/reference/data-catalog-full.md docs/reference/fleet.md docs/universe/point-in-time-universe.md && uv run pre-commit run -a && git commit -F - <<'EOF'
docs(reference): the catalog and the fleet reference name the rolling canonical, the reach round retires, and the universe page's resolver sentences read in the past

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

### Task 11: The ops runbook's section for the head check, and the engine runbook's seed source

**Files:**
- Modify: `infra/runbooks/ops.md` (a section after `## zcrypto-ops-tapebars-not-advancing — ALERT`, :134; the permanent-gap section's step 2, :122), `infra/runbooks/engine.md` (the store repair's clause at :335 naming the newest frozen sibling and the next quarterly ingest as the seed's source)

- [ ] **Step 1: Load `zcrypto-refine-rules`** and measure before: the runbook-read ratio as `tests/test_ops_daily.py::test_most_read_only_diagnostics_are_autonomous_on_ops` computes it against its 0.70 floor:

```bash
uv run python -c 'import tests.test_ops_daily as t; r=[c for c in t._runbook_commands() if not t._destructive(c)]; a=[c for c in r if t.ops_daily.classify_action(chr(96)+c+chr(96), host="ops", resolve=t._identity) is t.ops_daily.Tier.AUTONOMOUS]; print(f"{len(a)}/{len(r)}")'
```

Expected: one `<autonomous>/<read-only>` reading, recorded for the pull request body.

- [ ] **Step 2: The section** — `<a name="rolling-canonical-head"></a>` above `## rolling-canonical-head — PROCEDURE: reading a failing row`: a PROCEDURE, `infra/runbooks/README.md`'s kind whose trigger is the intent its heading states, since the pass names no runbook anchor (`tests/test_ops_daily.py::test_every_runbook_citation_the_instrument_itself_prints_resolves` would hold one it did), and Task 12's skill paragraph names it by file and anchor. Its four parts in the README's order: *What you are seeing*, the row's value; *What it means*, its four failing shapes — a newest line older than three days, a broken link, an absent or changed file, and the ended state, a newest line on which the owner has closed each of the set's pairs, which no line follows, whatever its age — the first including a head held by a pending hole — four days past the day's nominal publication when the pair's later days publish, for as long as the materializer retries the day otherwise — read as held and, at 14 days past the day's nominal publication, as the attention line naming the pair and the day, neither state naming a pair the owner has closed, and the third including a hub pull that copied a day's line before one of its files, which the next pull, an hour on, completes; *What to do*, for each shape the read-only commands that tell them apart — `uv run zcrypto data rolling verify --root <the hub or the outbox> --as-of <day>`, the tape-bars unit's journal as `sudo journalctl -u zcrypto-tape-bars.service --since -24h --no-pager`, the listing of a pair's month, `ls /var/lib/zcrypto-ops/tape-bars/<BASE>/<QUOTE>/<YYYY>/<MM>/`, which shows a day without a final whatever its cause, beside `zcrypto_tapebars_days_unhealed`, which counts a day whose trades are still being healed and no other, and for an absent file a re-read after the next pull before it is read as lost; for the attention line, the owner's decision, which the pass hands over — close the pair, from the main checkout, with `uv run zcrypto data rolling extend --tape-root /var/lib/zcrypto-ops/tape-bars --out /var/lib/zcrypto-ops/hot-out/ohlc-rolling --staging /var/lib/zcrypto-ops/hot-out-staging --close-pair <PAIR> --from <day> --owner-word <text> --owner-date <day>` — the host paths R-close uses, not the runner's container paths — run right after a `:52` tape-bars run has finished, `<PAIR>` spelled as the attention line names it, since a pair the set does not hold is refused, a later final of the pair ending the close at its own day while a pair of the set stays open, and the universe rebuild leaving the pair out of its candidates while the close runs — save a mandatory pair, BTC/EUR or ETH/EUR, whose close refuses each universe rebuild while it runs, naming the pair, since the universe's selection rule keeps both mandatory legs selected in each universe it publishes (a closed BTC/EUR would leave ETH/BTC and SOL/BTC unpriced in EUR as well), which the owner weighs before closing it; closing the last pair the set still carries ends the set, so no line follows that close's line, a reappearing final included, the row reads the ended state from then on, and the series goes on as a new set the owner starts — or wait; for the ended state, no host action, the row reading back the owner's own closes; *Retire when*, `ROLLING_CHECK` is no longer in `infra/scripts/ops_daily.py`; no internal term; each read-only command, its placeholders filled, one the daily pass's classifier reads as autonomous — the verify's `--root` an absolute path and its `--as-of` a `YYYY-MM-DD` day, by the shape Task 5 adds, the listing's path a pair's month — the page keeping the placeholders; the close, a write to the hub, carries the `data rolling extend` token Task 5 adds to `_DESTRUCTIVE`.
- The engine runbook's clause at `infra/runbooks/engine.md:335` — a series moved aside is re-copied "while the newest frozen sibling's last stamp lies inside the 4h REST window of about 120 days, else the next quarterly ingest is minted first" — names the seed's source as the rolling set at its local head, its tail days from the present, `zcrypto data fetch` bringing a newer head, and an absent store file whose pair holds a hole copied by `zcrypto engine seed --accept-holes` and refused without it.
- The permanent-gap section's step 2, `infra/runbooks/ops.md:122`, whose heal and widened `--rescan-days` publish a lost day into tape-bars, gains that the rolling canonical names a day a hole once the pair's newest final carries it past the sweep's default re-scan window — so by the time the alert fires the hole may already be written — and that the hole stays, so the heal restores the day in tape-bars alone.

```bash
uv run python infra/scripts/guidance-guard.py --uncounted infra/runbooks/ops.md infra/runbooks/engine.md
```

Expected: no output, which needs each list item on either page to carry, outside a code span, none of the words `UNIVERSAL` matches in `infra/scripts/guidance-guard.py` — `read-only` matches as `only` — unless it carries its count or its `(no count command: …)`.

- [ ] **Step 3: Measure after** — Step 1's command; Expected: at or above 0.70, the reading recorded beside Step 1's.
- [ ] **Step 4: The consumers**

```bash
uv run pytest $(infra/scripts/consumers.sh infra/runbooks/ops.md infra/runbooks/engine.md | grep -E '^tests/test_[^ ]*\.py$' | sort -u) tests/test_internal_terms_not_operator_visible.py tests/test_runbook_internal_tokens.py tests/test_runbook_triggers.py tests/test_guidance_guard.py tests/test_guidance_refs_resolve.py -q -p no:cacheprovider
```

Expected: no failure.

- [ ] **Step 5: The commit gate and commit**

```bash
git add infra/runbooks/ops.md infra/runbooks/engine.md && uv run pre-commit run -a && git commit -F - <<'EOF'
docs(runbooks): the ops runbook reads the rolling canonical head row, and the engine runbook's seed reads the rolling set

Co-Authored-By: Claude <actual executing model> <noreply@anthropic.com>
EOF
```

Expected: the commit made, its hooks `Passed` or `Skipped`.

- [ ] **Step 6: The tree is clean** — `git status --porcelain`; Expected: empty.

---

### Task 12: The daily-ops skill reads the row

**Files:**
- Modify: `.claude/skills/zcrypto-daily-ops/SKILL.md` (a paragraph after the `soak verdict` row's, :58), `.claude/skills/zcrypto-rollout-image/SKILL.md` (:123, *Canonical cannot always seed a new leg*)

- [ ] **Step 1: Load `zcrypto-refine-rules`**; read `.claude/skills/zcrypto-daily-ops/SKILL.md:40-70` and `.claude/skills/zcrypto-rollout-image/SKILL.md:118-124`.
- [ ] **Step 2: The paragraph** — the `rolling canonical head` row is the rolling canonical's freshness and chain on the hub; a failing row is read by `infra/runbooks/ops.md#rolling-canonical-head`, Task 11's section, its anchor read back after the edit (`grep -c '<a name="rolling-canonical-head"></a>' infra/runbooks/ops.md` → `1`), and none of its states is a host action the pass takes — its attention line at 14 days is the owner's decision, a close or waiting, which the pass hands over, and its ended state reads back the owner's closes of each of the set's pairs, after which no line is written. The rollout skill's :123, which names `data/ohlc-full` frozen at its last quarterly dump as the seed's canonical, is re-trued to the rolling canonical at its local head, which holds the twelve base pairs alone, so a new leg outside them has no canonical and is seeded REST-only, as the bullet already says. Neither skill's name nor description changes, so the commit carries no `Ambient grows by` line.
- [ ] **Step 3: The consumers**

```bash
uv run pytest $(infra/scripts/consumers.sh .claude/skills/zcrypto-daily-ops/SKILL.md .claude/skills/zcrypto-rollout-image/SKILL.md | grep -E '^tests/test_[^ ]*\.py$' | sort -u) tests/test_guidance_refs_resolve.py -q -p no:cacheprovider
```

Expected: no failure.

- [ ] **Step 4: The commit gate and commit**

```bash
git add .claude/skills/zcrypto-daily-ops/SKILL.md .claude/skills/zcrypto-rollout-image/SKILL.md && uv run pre-commit run -a && git commit -F - <<'EOF'
claude(skills): the daily-ops skill reads the rolling canonical head row, and the rollout skill's seed note names the rolling set

Co-Authored-By: Claude <actual executing model> <noreply@anthropic.com>
EOF
```

Expected: the commit made, `claude-kind files not mixed with other kinds` `Passed`.

- [ ] **Step 5: The tree is clean** — `git status --porcelain`; Expected: empty.

---

### Task 13: The master plan's rider, the sweep and the body

**Files:**
- Modify: `docs/research/00.master-plan.md` (the eight lines below), a rider on the owner's word of 2026-10-09, "accept all twelve, master plan as a rider" (spec 00125's ruling 12); a research document, not an operator-read surface, so an internal term may stand there, each sentence keeping the master plan's own register.

- [ ] **Step 1: The rider** — on each line the quoted text becomes the text after the arrow, nothing else on the line moving:
- `docs/research/00.master-plan.md:57`: "Kraken's own free full-history OHLCVT ZIPs (1m…1d) + full tick history via the Trades endpoint" → "Kraken's own free full-history OHLCVT ZIPs (1m…1d) through Q3 2026 — from 2026-10-01 the capture daemon's tape carries the canonical on, as `ohlc-rolling` (spec 00125) — + full tick history via the Trades endpoint".
- `docs/research/00.master-plan.md:77`: "plus **quarterly incremental ZIPs**;" → "plus **quarterly incremental ZIPs**, research's source through Q3 2026 only — from 2026-10-01 the canonical grows daily from the captured tape (`ohlc-rolling`, spec 00125, the owner's decision of 2026-10-09);".
- `docs/research/00.master-plan.md:190`, the row's first cell: "OHLCVT 15m/1h/4h/1d full history" → "OHLCVT 15m full history through 2026-09-30 + the captured tape's daily 15m finals after it (`ohlc-rolling`; 1h/4h/1d derived on read)".
- `docs/research/00.master-plan.md:191`, the row's first cell: "OHLCVT 1m full history" → "OHLCVT 1m full history (dumps through Q3 2026; no later ingest feeds research)".
- `docs/research/00.master-plan.md:227`, the row's third cell: "Primary research dataset; **retain every quarterly ZIP forever** (survivorship mitigation)" → "The research canonical's base through 2026-09-30, the captured tape carrying it on (`ohlc-rolling`, spec 00125); **retain every quarterly ZIP forever** (survivorship mitigation)".
- `docs/research/00.master-plan.md:339`: "ingest OHLCVT ZIPs → canonical Parquet (all intervals, empty-interval reconstruction);" → "ingest OHLCVT ZIPs → canonical Parquet (all intervals, empty-interval reconstruction; from 2026-10-01 the canonical is extended daily from the captured tape instead, spec 00125);".
- `docs/research/00.master-plan.md:418`: "Quarterly: OHLCVT increment ingestion, universe review, decay tests (CUSUM on live-vs-expected P&L)." → "Quarterly: universe review, decay tests (CUSUM on live-vs-expected P&L); OHLCVT increment ingestion is no longer a research input, the canonical growing daily from the captured tape (spec 00125, the owner's decision of 2026-10-09)."
- `docs/research/00.master-plan.md:438`: "OHLCVT downloadable history + quarterly increments — support article 360047124832;" → "OHLCVT downloadable history + quarterly increments (research's source through Q3 2026) — support article 360047124832;".

```bash
git grep -n 'OHLCVT' -- docs/research/00.master-plan.md | cut -d: -f1-2
```

Expected: the same eight `path:line` pairs, each line read back carrying its new text.

- [ ] **Step 2: The consumers**

```bash
uv run pytest $(infra/scripts/consumers.sh docs/research/00.master-plan.md | grep -E '^tests/test_[^ ]*\.py$' | sort -u) -q -p no:cacheprovider
```

Expected: no failure.

- [ ] **Step 3: The commit gate and commit**

```bash
git add docs/research/00.master-plan.md && uv run pre-commit run -a && git commit -F - <<'EOF'
docs(research): the master plan's eight OHLCVT lines read the rolling canonical, a rider on the owner's word of 2026-10-09

Co-Authored-By: Claude <actual executing model> <noreply@anthropic.com>
EOF
```

Expected: the commit made, its hooks `Passed` or `Skipped`.

- [ ] **Step 4: The gate and the counts**

```bash
uv run pre-commit run -a && infra/scripts/count-list.sh probe-verdicts-without-the-script prose-only-commits-without-the-prover
```

Expected: every hook `Passed` or `Skipped`; `prose-only-commits-without-the-prover` `0`; `probe-verdicts-without-the-script` what it read at this branch's base, `1` at `f70be7dae` — develop's `65997b3bd`, a plan commit before this branch — so the branch's own commits add none.

- [ ] **Step 5: The branch's own tests together**

```bash
uv run pytest tests/test_rolling_reader.py tests/test_rolling_extend.py tests/test_data_sync.py tests/test_registry_observed.py tests/test_registry_conformance.py tests/test_ops_daily.py tests/test_ops_daily_soak.py tests/test_research_command.py tests/test_engine_command.py tests/test_engine_store.py tests/test_data_rebuild.py tests/test_data_command.py tests/test_data_manifest.py tests/test_universe_provenance.py tests/test_infra_tape_bars_template.py tests/test_infra_converge_guards.py tests/test_infra_shell_templates_render.py tests/test_data_gated_run.py tests/test_data_gated_marker.py tests/test_cli_help_hygiene.py tests/test_internal_terms_not_operator_visible.py -q -p no:cacheprovider
```

Expected: no failure; the two data-gated cases of `tests/test_rolling_extend.py` skipped in the worktree, their run the Rollout's R6.

- [ ] **Step 6: The pull request body, drafted for R1** in `open-pr`'s shape: `## Spec / Plan` names 00125; the probes; `## Changes` from the diff, the master plan's rider named as the owner's word; Task 11's runbook-read ratio, before and after — without the read line and its `Fable floor substituted by Opus: <reason>` line, which name a read not yet taken and are R1's.

---

## Rollout (attended)

**Operator steps.** Nothing below is an executor step: each reaches the ops host's live trees, the NAS, the hub or the fleet. `W$` is a shell on this workstation, `zcrypto-ops`, at the main checkout's root on merged `develop`. `KRAKEN` is the whole-feed read, `curl -fsS https://status.kraken.com/api/v2/scheduled-maintenances.json | jq .`, read entire and judged by `.claude/rules/fleet-deploys.md`'s test, at planning and again immediately before the converge. `OUTBOX` is `/var/lib/zcrypto-ops/hot-out/ohlc-rolling`, `STAGING` is `/var/lib/zcrypto-ops/hot-out-staging`, `HUB` is `/mnt/zhao-crypto/hot/ohlc-rolling`.

**Stop conditions.** A converge preview naming a file outside the ops role's runner scripts, units, defaults-driven directories and its compose files holds the rollout until the owner has read it. A `RollingError` from `base`, `extend` or `verify`, a fetch refusal, or a head row that does not read ok at R7 stops the rollout for the owner; no file under `OUTBOX` or `HUB` is edited or deleted by hand to get past it — the outbox and the hub never rewrite, so a wrong file is the owner's question, never an operator's fix.

**R1. The pull request** (after Task 13). Through `open-pr`, a draft carrying Task 13 Step 6's body; the `pre-review` workflow over the range's prose and messages, then `review` once the branch is complete, `re-review` over a fix range at most twice, every reviewer on Opus; at the undraft, once the review has read the branch, the read line naming that reader and the tip it read, and the `Fable floor substituted by Opus: <reason>` line where the gate asks it (`uv run python infra/scripts/merge-gate.py --fable-paths`).

**R2. The merge.** `merge-pr`, then `W$ git switch develop && git pull --ff-only && git status --porcelain`, reading empty. From here until R6, an engine seed over an absent store file and a universe rebuild refuse, the local rolling set not yet fetched, the daily pass's `rolling canonical head` row reads unreadable, and the nightly data-gated run reads the two data-gated cases of `tests/test_rolling_extend.py` as skipped for want of data, so not ok; a seed over a complete store runs as before.

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

Expected: `base <sha256> files=12` — the command refusing before its first rename unless each file's bytes are `Q3_15M_SHA256`'s — and the verify printing `2026-09-30`, the same sha256 and `files=12`; a `base` stopped before it prints is run again at once, the same command completing the base by Task 2's byte-equal rule; `[[ROLLOUT: the base line's sha256]]`.

**R5. The first extension** (immediately after R4, before the next `:52`, so the manual start is the first extension and the journal's last ten minutes hold its lines).

```bash
sudo systemctl start zcrypto-tape-bars.service && sudo journalctl -u zcrypto-tape-bars.service --since '-10 min' --no-pager | grep -E 'days_written=|head='
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

Expected: the hub's verify printing R5's sha256 at `HEAD_DAY`; the fetch with no refusal, its `new=` counting the set's files and every other hub set the local root lacks — `derivatives-oi`'s 11 files and `ohlc-reach`'s 31 as read on 2026-10-09; the two data-gated tests `2 passed`, neither skipped; `[[ROLLOUT: the fetch's new-file count and the two data-gated readings]]`.

**R7. The head read by value.**

```bash
uv run python infra/scripts/ops-daily.py report --since 24h; echo "report exit $?"
```

Expected: the `rolling canonical head` row ok, naming the R5 head, its age and its line's first twelve hex; `[[ROLLOUT: the first rolling canonical head row]]`.

**R8. The retirements the owner takes.** By the owner's hand on the NAS, as the Q2 siblings went to `/volume1/ZhaoCrypto/backup-ohlc-squash-2026-10-09/`: `ohlc-reach-20261007` off `hot/` from R2 on, and `ohlc-full-20261007` and `ohlc-15m-20261007` once R6's data-gated tests have passed; each local copy under the main checkout's `data/` the owner removes too, after copying it aside per `CLAUDE.md`'s data rule. No step of this plan moves or deletes a set; `[[ROLLOUT: each retirement's instant and destination]]`.

**R-close. Closing a pair the tape stopped carrying** — only on the owner's explicit word, after the head row's attention line has named the pair and the day; never part of this rollout's own run, and taken whenever that word comes. Right after a `:52` tape-bars run has finished, so no extension runs beside it, the values replaced by the attention line's pair and day and the owner's words and their date:

```bash
PAIR=DOT/EUR
FROM_DAY=2026-11-14
OWNER_WORD="close DOT/EUR from 2026-11-14"
OWNER_DATE=2026-11-30
uv run zcrypto data rolling extend --tape-root /var/lib/zcrypto-ops/tape-bars --out /var/lib/zcrypto-ops/hot-out/ohlc-rolling --staging /var/lib/zcrypto-ops/hot-out-staging --close-pair "$PAIR" --from "$FROM_DAY" --owner-word "$OWNER_WORD" --owner-date "$OWNER_DATE"
```

Expected: `head=<FROM_DAY or later> days_written=<n> holes=<n>`, followed by `ended` when the close leaves no pair of the set open, which ends the set as Task 11's section tells the owner before the word is given, the line for `FROM_DAY` naming the pair under `holes` and carrying the close in its `notes`; a refusal writes nothing and goes back to the owner, a `PAIR` the set does not hold — one spelled otherwise than the attention line names it — among the refusals.

**R-records.** A records pull request after R7: the converge's deploy-log row and the ops pin row of `docs/reference/fleet-pins.md`; the slots' readings in its message, each retirement R8 has seen by then among them. The catalog's lines naming the sets R8 retires read true before and after each move (Task 10), so a retirement after this pull request owes the tree no edit; the slot below records only the retirements R8 has seen by then, a later one's instant and destination being the owner's to keep.

## Resolution

This plan delivers spec 00125: the rolling canonical's reader, writer and record; its daily extension on the ops host through the outbox; the fetch's attestation and the daily pass's head row; the searches, the universe rebuild and the engine seed on it; and the reach round's retirement; and, a rider on the owner's word, the master plan's eight lines naming the OHLCVT archive as research's source. It moves no set off the hub — the retirements are the owner's — and it touches neither tape-bars' gate and layout nor what `soak-check`, record 44's legs and the legacy pins read, which stays `ohlc-full` and `ohlc-15m` (Task 6 re-trues `load_union`'s docstring alone).

## Slots the rollout fills

- `[[ROLLOUT: the ops image digest the converge lands]]` (R3) — into the records' pin row.
- `[[ROLLOUT: the base line's sha256]]` (R4) — the pin of the base alone, the as-of 2026-09-30.
- `[[ROLLOUT: the first extension's summary line and its head line's sha256]]` (R5).
- `[[ROLLOUT: the fetch's new-file count and the two data-gated readings]]` (R6).
- `[[ROLLOUT: the first rolling canonical head row]]` (R7).
- `[[ROLLOUT: each retirement's instant and destination]]` (R8) — the owner's acts, in R-records' message for those taken before it.
