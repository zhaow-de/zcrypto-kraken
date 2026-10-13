# Every trial re-derivable — the invocation, the CI check, the computed verdict, the replay, the hub pass, the readings ledger and record 47's identity

**Spec:** `docs/specs/00129-trial-provenance-design.md` — binding; every shape, floor and enumeration below is the spec's, repeated only where a task needs it in front of it. **Branch:** `docs/00129-trial-provenance`, worktree `.claude/worktrees/trial-provenance`. **Ruling:** the owner's of 2026-10-13T10:37:59Z, quoted in the spec's header.

**Goal:** a record past 47 and a reading carry the invocation that produced them, written only by `zcrypto research eval` from a clean tree at a commit; CI holds each to its subject, its spec, its rule and its comparator; every one replays at HEAD nightly; the hub's `hot/` is checked for every byte a record cites; B2 trial 1's stop is kept as reading 1 and the decisions logs are tied to ids; record 47's identity is a committed test.

**Architecture:** the store (`cli/registry/`) gains schema 5's `invocation` and a floor at 47, form only — no git, no import of `cli/research`; the subjects (`cli/research/subjects.py`) declare their spec, keys, seeds, rule and incumbent and pin the costs they read; the command (`cli/research/command.py`) is the one writer and the one place git runs, against `_REPO_ROOT`; the checks are tests — ungated over the committed files (`tests/test_trial_registry_provenance.py`, `tests/test_decisions_log_ties.py`), data-gated where bytes are read (`tests/test_registry_replay.py`, `tests/test_registry_conformance.py`, `tests/test_record47_identity.py`). Nothing under `cli/engine/` changes.

**Tech stack:** Python 3.14; `subprocess` for git in the command and the tests; `cli.registry` (`TrialRegistry`, `compute_hash`, the new `ReadingLedger`), `cli.registry.observed` (`ObservedReader`), `cli.research.subjects` (`SUBJECTS`, `Subject`, `_capturing_union`, `_b2_inputs`, `_b2_arm_a_bar`), `cli.portfolio.crossfreq_system` (`CrossfreqSystemConfig`, `build_crossfreq_system_fast`), `cli.portfolio.builder` (`CombinedSystemConfig`, `build_combined_system`), `cli.engine.cycle` (`select_model_inputs`, `_expand_to_basket`) and `cli.engine.store` (`read_store_series`, `PAIR_KEYS`, `BASKET`) read only, `cli.config` (`load_config`, `resolve_hot_source`), `cli.data.rolling` (`verify`), `tests.skip_gates` (`mount_absent`).

## Global constraints

- TDD per task: the failing test first, the implementation second, the test green third. Every guard is proven with `infra/scripts/mutate-probe.sh` after the task's commit (it refuses a dirty tree), its verdict line in the PR body naming the script. Each probe's sed names its site — a line address, or a pattern only that line holds, `grep -c` of it reading 1 before the run — and each `--control` renames the def of a function the probe's test module imports (`s/^def <name>(/def <name>_gone(/`, its `grep -c` reading 1), never a variant of the mutation.
- Nothing under `cli/engine/` is written, by a task or by a probe: Task 8 reads it, and its probes mutate the subject side and `cli/portfolio/record44_legs.py`.
- No arm-B return of the B2 trial is computed on real data. The real-data runs on this branch are the legacy subjects, `b2-arm-a-bar` (reading 1, Task 7), the replay of reading 1, record 47's identity test and the two conformance passes. No trial is registered on this branch; the one write to a committed record file is reading 1's line.
- Datasets reach the worktree as one link per set — `ln -s /home/zhaow/Projects/zcrypto-kraken/data/<set> /home/zhaow/Projects/zcrypto-kraken/.claude/worktrees/trial-provenance/data/<set>` for `ohlc-full`, `ohlc-rolling`, `derivatives-funding` — never the `data/` root, never an `ohlc-holdout-*` set; each link is removed with `rm` before `git worktree remove` (Task 9).
- String literals under `cli/` and `infra/scripts/` — refusals, help texts, the stop text — and the README rows carry no `Phase <N>`, `T<NNNN>`, `iter-<N>`, `spec <NNNNN>` or `D<N>`: `tests/test_internal_terms_not_operator_visible.py` scans every non-docstring literal there.
- A data-gated test file carries `pytestmark = pytest.mark.data`; its gate is one of the admitted forms — the path form `not _CANONICAL.is_dir()` over a literal-rooted `_CANONICAL = Path(__file__).resolve().parents[1] / "data" / "ohlc-full"`, or `mount_absent("hot")` from `tests.skip_gates` — with a reason in the runner's vocabulary (`data/`, `hub`, `mount`); `tests/test_data_gated_marker.py` and `tests/test_live_venue_opt_in.py` hold both. The data-gated files this branch touches run locally before the first push (`uv run pytest -m data <files>`), the skip count read.
- Before each commit, every consumer of a changed module runs: `git grep -l -E "<changed module or helper>" -- tests infra/scripts .claude ':!*vault.yml' ':!*.vault' ':!*.sops.*' ':!*vault-password*' ':!infra/ansible/files/*_ed25519'` and those files under `uv run pytest`; never the full suite, which is CI's.
- Commits by kind — `feat(registry)`, `feat(research)`, `test(research)`, `docs(research)` — each task its own commit (Task 7 two), no amend; `uv run pre-commit run -a` is the gate, re-run until clean.
- Reads, as CLAUDE.md orders them: `pre-review` over each range's prose and messages before each read, `review` once the branch is complete, `re-review` over a fix range at most twice; Task 7's records commit takes its own `pre-review`; the PR's read line on Opus with the Fable line unless the owner names a difficulty.

## Task 1 — develop in, the premises re-read

**Files:** none (a merge commit).

1. `git -C <worktree> fetch origin develop`, then `git -C <worktree> log --first-parent --merges --format=%h --grep 'fix/research-subject-refusals' origin/develop` prints one hash. None: stop and tell the owner — the fix edits `cli/research/command.py`, `cli/research/subjects.py`, `tests/test_research_command.py` and `README.md`, every one of which Tasks 3, 4, 5 and 7 edit.
2. `git -C <worktree> merge --no-edit origin/develop` (a merge commit, never a rebase).
3. Re-run the spec's measured-basis commands that read code the fix touched or this branch will — the subjects and their fields, the `CrossfreqSystemConfig()` reads in `subjects.py`, `_B2_METRIC_KEYS`, the registry's line count and schemas, the five `append` call sites, the highest spec serial (`00129` now) — and compare each output with the spec's. A difference that moves a decision goes to the owner before Task 2; one that moves only a line number is carried into the task that edits that line.
4. `uv run pytest tests/test_research_command.py tests/test_trial_registry_provenance.py tests/test_registry_store.py tests/test_registry_conformance.py tests/test_research_control.py -q` passes, the skips read (the data-gated ones skip until the links exist).

**Commit:** the merge commit.

## Task 2 — schema 5: the invocation, the floor at 47

**Files:** `cli/registry/record.py`, `cli/registry/store.py`, `cli/research/command.py`, `tests/test_registry_record.py`, `tests/test_registry_store.py`, `tests/test_registry_conformance.py`, `tests/test_research_control.py`, `tests/test_research_command.py`.

1. `record.py`: `SCHEMA_VERSION = 5`; `_LOADABLE_SCHEMA_VERSIONS = {2, 3, 4, 5}`; `_EXPECTED_STORED_KEYS[5] = _EXPECTED_STORED_KEYS[4] | {"invocation"}`; `validate_stored_record` requires and checks `invocation` at version 5; `TrialRecord` gains `invocation: dict | None = None`. The validator, form only:

   ```python
   _INVOCATION_KEYS = frozenset({"subject", "dataset", "window", "as_of", "accept_holes", "comparator_trial", "commit"})
   _COMMIT = re.compile(r"[0-9a-f]{40}")
   _DAY = re.compile(r"\d{4}-\d{2}-\d{2}")

   def validate_invocation(inv, datasets: dict, own_trial_id: int | None, where: str) -> None:
       """own_trial_id None: a reading, whose comparator is a trial id from another sequence."""
   ```

   It refuses: not a dict, or a key set other than `_INVOCATION_KEYS`; `subject` not a non-empty str; `dataset` not a key of `datasets`; `window` neither None nor a list of exactly two str; `as_of` neither None nor a str `_DAY` fullmatches; `accept_holes` whose `type` is not `bool`; `comparator_trial` neither None nor an int (`type` is `int`, so not a bool) at least 1 and, for a trial, below `own_trial_id`; `commit` not a str `_COMMIT` fullmatches. Each as `RegistryCorruptionError` naming `where` and the key.
2. `store.py`: `_INVOCATION_FLOOR_TRIAL_ID = 47` beside `_LEGACY_UNPROVENANCED_MAX_TRIAL_ID`; `_assert_cross_record` refuses a record past 47 below schema 5, naming the trial and the floor; `append(..., invocation: dict)` — a required keyword, stored in the record before `validate_stored_record` runs, so a missing or ill-shaped invocation is refused before the write.
3. `command.py`: `_tree_state(root: Path) -> tuple[str, str]`, the one place git runs:

   ```python
   def _tree_state(root: Path) -> tuple[str, str]:
       def git(*args: str) -> subprocess.CompletedProcess:
           return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True)
       head = git("rev-parse", "HEAD")
       if head.returncode != 0:
           raise _abort(f"{root} is not a git checkout, and a record names its code by commit")
       return head.stdout.strip(), git("status", "--porcelain").stdout
   ```

   The register path passes `invocation={"subject": subject, "dataset": dataset, "window": None if bounds is None else list(bounds), "as_of": as_of, "accept_holes": accept_holes, "comparator_trial": None, "commit": _tree_state(_REPO_ROOT)[0]}`; the refusals come in Task 4.
4. Migrate the four test call sites to pass an invocation over their own `datasets`: `tests/test_registry_store.py`'s `_append` helper (`:148-161`) and `:485`, `tests/test_registry_conformance.py`'s `_append` (`:138`), `tests/test_research_control.py:83`. `tests/test_research_command.py` gains an autouse fixture stubbing `research_command._tree_state` to `("a" * 40, "")`. The four assertions that a new record is schema 4 move to 5 — `tests/test_registry_record.py:50`, `tests/test_registry_store.py:521`, `tests/test_research_command.py:152`, `tests/test_research_control.py:98` (`git grep -n -E "schema_version.{0,6}== ?4|SCHEMA_VERSION == 4" -- tests/` lists them).
5. Tests, `tests/test_registry_store.py` unless named:
   - a record appended with an invocation reloads schema 5 with it, `TrialRecord.invocation` equal to what was passed;
   - `append` without `invocation` raises `TypeError`;
   - each refusal by its own case, parametrised: a missing key; an extra key; `subject` `""`; `dataset` not in `datasets`; `window` of one str, and of a str and an int; `as_of` `"2026-1-1"`; `accept_holes` `1`; `comparator_trial` `0`, `True`, and equal to the record's own id; `commit` of 39 hex, and of 40 uppercase hex;
   - the floor, on the real file read-only, as `test_a_record_past_the_legacy_floor_must_declare_schema_four` (`:615`) builds trial 48 — a test this task must migrate, since its passing line is schema 4: that line becomes schema 5 with an invocation and the file loads 48 records; the same line at schema 4 is refused naming trial 48 and schema 5; its schema-3 case stays refused;
   - `tests/test_research_command.py`: a register run writes schema 5 whose `invocation` equals the run's subject, dataset, window, as-of and holes flag, `comparator_trial` None and the stubbed commit;
   - `test_live_registry_file_loads_clean` still passes over the committed file.
6. Probes, each expect KILLED: the floor at schema 4 (`s/schema_version"\] < 5/schema_version"] < 4/`, its `grep -c` 1) against the schema-4 trial-48 case; the dataset membership dropped against its case; `_COMMIT` widened to `[0-9a-fA-F]{40}` against the uppercase case; the `accept_holes` test made `isinstance(…, int)` against the `1` case.

**Commit:** `feat(registry): schema 5 — a record past 47 carries the invocation that produced it`.

## Task 3 — the subjects declare themselves, and CI holds every record past 47 to them

**Files:** `cli/research/subjects.py`, `tests/test_trial_registry_provenance.py`, `tests/test_research_command.py`.

1. `Subject` gains the spec D2's keyword fields with defaults — `spec`, `metric_keys`, `seeds`, `verdict`, `no_verdict`, `incumbent` — the code block there, verbatim.
2. Declarations: `record44-crossfreq` — `spec="docs/specs/00038-cross-frequency-combination-design.md"`, `metric_keys` its six (`ann_sharpe_noc`, `per_period_sharpe_4h`, `ann_sharpe_ungoverned`, `cap_breach_bars`, `governor_engaged_bars`, `n_periods`); `record33-combined` — `spec="docs/specs/00035-combination-trial-design.md"`, its five; `b2-funding-derisk` — `spec="docs/specs/00128-b2-family-opening-design.md"`, `metric_keys=_B2_METRIC_KEYS` (a module frozenset of spec 00128 D7's 40 keys), `seeds=(42, 7, 1234)`, `verdict=_b2_verdict` (the spec D4's block, verbatim), `no_verdict` the stop text — e.g. "instrument finding: arm A fails the bar this window sets, or the overlay engages at no stamp; no verdict, the trial unspent" — with no internal term.
3. `LEGACY_INCUMBENTS: dict[int, str] = {33: "record33-combined", 44: "record44-crossfreq", 47: "record44-crossfreq"}` in `subjects.py`.
4. `tests/test_trial_registry_provenance.py`: `_findings(entry: dict, kind: str, *, subjects: dict, legacy: dict, trials: dict[int, dict], is_ancestor: Callable[[str], bool], spec_sha256: Callable[[str], str]) -> list[str]` — the spec D2's (i)–(vi), each finding naming the entry and what failed; (v) for a trial is `entry["verdict"] == subject.verdict(entry["metrics"])` with a rule present (a ruleless subject named by a trial is a finding); (vi) is the spec D3's: `comparator_trial` set exactly when the subject declares an incumbent, and N accepted when `trials[N]` carries an invocation whose subject is the incumbent (on the committed file, exactly the records past 47) or `legacy[N]` is the incumbent. `_is_ancestor(c)` is `git -C REPO merge-base --is-ancestor c HEAD` exiting 0; `spec_sha256(p)` the sha256 of `REPO / p`. The live test runs `_findings` over every committed record with `trial_id > 47` and expects none.
5. Tests:
   - constructive, in `tests/test_trial_registry_provenance.py`, over one synthetic schema-5 trial for `b2-funding-derisk` that yields no finding — its 40 keys with values the rule maps to `reject` (`passes` 0, `arm_a_passes` 1, a non-zero `engaged_per_year`), `commit` the current HEAD, `spec_hash` the sha256 of spec 00128, `verdict` `"reject"` — then one change per case, each case asserting exactly one finding: an unknown subject; a key added and, apart, a key removed; `commit` `"f" * 40`; `spec_hash` of spec 00035; `verdict` `"adopt"`; a trial naming `record33-combined`, which has no rule; with a synthetic `subjects` holding a stub that declares `incumbent="record44-crossfreq"`: no `comparator_trial`; `comparator_trial` on the B2 subject, which declares none; N = 44 accepted through the map; N = 33, mapped to another subject; N = 45, in no map and carrying no invocation; N a synthetic schema-5 trial whose subject is not the incumbent;
   - `LEGACY_INCUMBENTS` equals the literal `{33: "record33-combined", 44: "record44-crossfreq", 47: "record44-crossfreq"}`, every value a key of `SUBJECTS`, every key a committed record at or below 47 — the failure message naming the growth rule: a legacy id joins with its subject and a data-gated proof in one PR;
   - in `tests/test_research_command.py`: every subject's `spec` is tracked (`git ls-files --error-unmatch`), its `metric_keys` non-empty, `verdict` set exactly when `no_verdict` is, `incumbent` None or a key of `SUBJECTS`, `seeds` a tuple of int; `SUBJECTS["b2-funding-derisk"].metric_keys == _B2_METRIC_KEYS` (the test's literal) and the two legacy key sets equal their literals;
   - `_b2_verdict`, parametrised: `arm_a_passes` 0 with every other input adopting → None; every `engaged_per_year` value 0 → None; `passes` 0 → `reject`; mean outperformance 0.001, p 0.01, reduction 5.0 → `adopt`; p exactly 0.05 → `park`; mean exactly 0.0 → `reject`; reduction exactly 1e-6 → `reject`; reduction 2e-6, mean positive, p 0.2 → `park`; mean negative → `reject`.
6. Probes, each expect KILLED: each of `_findings`' six conditions made always-clean, a run each against its constructive case; `< 0.05` → `<= 0.05`, `> 1e-6` → `>= 1e-6`, `["head_to_head_mean_outperf_2021"] > 0` → `>= 0`, the arm-A clause removed, the dead-knob clause removed, each against its rule case; the map's 47 value changed against the literal test.

**Commit:** `feat(research): subjects declare spec, keys, seeds, rule and incumbent; CI holds every record past 47 to them`.

## Task 4 — the command, the only writer

**Files:** `cli/research/command.py`, `tests/test_research_command.py`, `README.md` (the `research eval` options table and the paragraph under it).

1. The register path, in this order: the subject known; `--register` refused for a subject with no rule, and when the subject declares an incumbent without `--comparator-trial N`, or does not and the flag is given; N resolved against the target registry and `LEGACY_INCUMBENTS` as Task 3's (vi) reads it; the caller fields present (`--iteration`, `--family`, `--n-trials`); `before = _tree_state(_REPO_ROOT)`, refused when its status is non-empty, the refusal listing the paths — all before any read. Then the spec's sha256 from `_REPO_ROOT / subject.spec`, refused when a typed `--spec-hash` differs; the dataset checks as today; the fit; the build's key set against `metric_keys`, refused on any difference; the report printed, with the rule's verdict when the subject has one. Then `after = _tree_state(_REPO_ROOT)`, refused when `after != before` — HEAD moved or the tree changed during the fit. Then `verdict = subject.verdict(metrics)`: refused when a typed `--verdict` differs from it (a None included); a None is refused here naming the subject's `no_verdict` — "no verdict: … no trial spent" — and Task 7 turns it into a reading; otherwise the append with `verdict`, `spec_hash`, `seeds=list(subject.seeds)` and the invocation, `comparator_trial` N.
2. `--seed` is removed; `--verdict` and `--spec-hash` become optional; `--comparator-trial N` is added.
3. Tests, the stubbed `_tree_state` overridden per case:
   - `_tree_state` unstubbed over a real repository: a `tmp_path` repository with one commit, called while the cwd (`monkeypatch.chdir`) is a second repository with another HEAD, returns the first one's HEAD; an untracked file in the first appears in its status; a directory that is no repository is refused;
   - dirty before the fit: exit 1, the path listed, the stub build never called, no registry file;
   - HEAD moved during the fit (the stub returns `("a" * 40, "")` then `("b" * 40, "")`): exit 1, no line; the tree dirty after the fit: exit 1, no line;
   - an evaluate-only subject under `--register`: exit 1 before the fit;
   - a stub subject whose rule returns `park`: the record's verdict `park` with no `--verdict`; typed `--verdict adopt`: exit 1, no line; typed `--verdict park`: recorded; a rule returning None: exit 1 naming its `no_verdict`, no line;
   - `spec_hash` recorded as the sha256 of the stub's tracked spec; a typed different `--spec-hash`: exit 1; `seeds` recorded as the subject's; `--seed 1`: a usage error;
   - a build returning one key more than `metric_keys`: exit 1, no line;
   - the comparator: a stub declaring `incumbent="record44-crossfreq"` without the flag: exit 1; the B2 subject with the flag: exit 1; N = 44: recorded as `invocation.comparator_trial`; N = 33 and N = 45: exit 1; N a schema-5 record of a `tmp_path` registry, registered first through the command by a ruled stub that a second stub names as its incumbent: recorded, and the same N under a stub naming another incumbent: exit 1;
   - the B2 register test migrated: no `--spec-hash`, no `--verdict`; its first parametrisation (B passes at the headline, arm A's sentinel the opposite) now stops — exit 1 naming the stop, its assertions read off the printed report through `_block_and_metrics`; its second (B fails, arm A passes) registers `reject`, asserted on the record as today.
4. README: the rows for `--register` (records a trial whose verdict is the subject's rule; refused for a subject with none, and from a tree with uncommitted changes), `--verdict` and `--spec-hash` (optional; each must equal what the command computes), `--comparator-trial`; the `--seed` row removed.
5. Probes, each expect KILLED: `"-C", str(root),` dropped from `_tree_state` against the two-repository case; the after-fit comparison made `after = before` against the moved-HEAD case; the verdict comparison removed against the `--verdict adopt` case; the key-set comparison removed against the extra-key case; the spec-hash comparison removed against its case; the incumbent equality in N's resolution removed against the wrong-subject case.

**Commit:** `feat(research): the command is the one writer — a clean tree at a commit, the spec hash and the verdict computed, the comparator resolved`.

## Task 5 — the subjects pin what they inherit; every record replays at HEAD

**Files:** `cli/research/subjects.py`, `tests/test_research_command.py`, `tests/test_registry_replay.py` (new, module-marked `data`).

1. The literals: `_B2_COST_PER_SIDE = 0.006` at the two B2 cost sites (`:239`, `:278` at d1d56c741); `_B2_A2_ARMS = (((20, 50, 100), 0.12), ((60, 120, 240), 0.10), ((60, 120, 240), 0.12))` for `CrossfreqSystemConfig().a2_arms` (`:195`); `_B2_LOOKBACK = 180` for `_A2_LOOKBACK` and the module's `PPY_4H` for `_PPY_4H` in `_b2_inputs`; `_RECORD44_CONFIG = CrossfreqSystemConfig(fee_per_side=0.0040, spread_per_side=0.0020)` passed by `_build_crossfreq` (`:110`); `_RECORD33_CONFIG = CombinedSystemConfig(spot_fee_per_side=0.006)` passed to `build_combined_system`.
2. `tests/test_registry_replay.py`:
   - `replay(entry: dict, kind: str, data_root: Path) -> list[str]`: a fresh `ObservedReader(data_root)`; `SUBJECTS[inv["subject"]].build(reader, inv["dataset"], None if inv["window"] is None else tuple(inv["window"]), as_of=inv["as_of"], accept_holes=inv["accept_holes"])`; a finding when `reader.block() != entry["datasets"]`, one naming each metric key whose value differs or that one side lacks, and one when the rule's verdict differs from a trial's `verdict` (a reading's `outcome`, from Task 7). An exception from the build propagates: a cited set that is absent fails the case.
   - `_tracked_dirt(root: Path) -> str`: `git -C root status --porcelain --untracked-files=no`'s output.
   - `_behind(head_text: str, develop_text: str, id_key: str) -> set[int]`: the ids the second file's lines hold and the first's do not.
   - `REPLAY_MOVED: dict[str, str] = {}`.
   - The live test, gated `@pytest.mark.skipif(not _CANONICAL.is_dir(), reason="data/ohlc-full absent — the replay runs on the data host only")` and parametrised over `trial-<id>` for every committed record past 47 (Task 7 adds `reading-<id>`), a `REPLAY_MOVED` label taking `pytest.mark.xfail(strict=True, reason=…)`: it fails first when `_tracked_dirt(REPO)` is non-empty, naming the paths, then asserts `replay(...) == []`.
   - The staleness test, the same gate: `git -C REPO rev-parse --verify origin/develop` exits 0, or the test fails saying so; for the registry (and, from Task 7, the ledger), `git -C REPO show origin/develop:<path>` — a path develop does not yet hold reads as empty — and `_behind(<HEAD's file>, <that>, <id key>)` is empty, or the test fails naming the ids and the pull of the checkout it needs.
3. Tests, ungated:
   - every subject's metrics are unchanged when the shared defaults move: each subject's build runs on the module's synthetic sets — the B2 register fixture, and a ten-asset set at 1440 and 240 for the two legacy subjects — once as is and once with `subjects.CrossfreqSystemConfig` replaced by a subclass whose fee, spread and `a2_arms` defaults differ and `build_combined_system.__kwdefaults__["config"]` replaced by a config with another fee; and the literals equal spec 00128's values (`_B2_COST_PER_SIDE == 0.006`, `_B2_A2_ARMS` the three arms as written);
   - a ruled stub subject — a tracked spec, its declared keys — registered into a `tmp_path` registry through the command (the stubbed clean tree), then `replay(record, "trial", tmp_data_root) == []`; the same record with one metric moved by one ulp (`math.nextafter`) gives a finding naming the key; with the cited file's bytes rewritten, a finding naming the block; with the stored verdict changed, a finding naming the verdict;
   - `_tracked_dirt` over a `tmp_path` repository: a tracked modification is listed, an untracked file is not;
   - `_behind` over synthetic texts: develop holding ids 1–3 and HEAD 1–2 gives `{3}`; HEAD holding more than develop gives the empty set;
   - `REPLAY_MOVED` is empty or `infra/scripts/replay-at-commit.py` exists, and every key names a committed record's label.
4. Probes, each expect KILLED: the two B2 cost sites reverted to `CrossfreqSystemConfig().cost_per_side` and the arms site to `CrossfreqSystemConfig().a2_arms`, a run each by line address, against the defaults-move test; `_build_crossfreq`'s `config=_RECORD44_CONFIG` made `config=CrossfreqSystemConfig()` and `config=_RECORD33_CONFIG` dropped from `_build_combined`, each against the same test — call-time reads the patched defaults reach, where a module-level revert would not (the lookback and periods-a-year literals are held by the value assertion alone: their shared counterparts are constants no default change moves); the metric comparison removed against the ulp case; the block comparison removed against the bytes case; the verdict comparison removed against its case; `--untracked-files=no` dropped against the untracked-file case; `_behind`'s difference reversed against the synthetic case.

**Commit:** `feat(research): subjects pin the costs they inherit, and every record past 47 replays at HEAD`.

## Task 6 — the hub keeps what records cite

**Files:** `tests/test_registry_conformance.py`.

1. `conformance(cited: list[tuple[str, dict]], data_root: Path, absent_ok: frozenset[str]) -> list[Verdict]`, `Verdict.label` (`"trial 47"`) in place of `trial_id`; `_cited(trials)` builds the pairs from every trial at schema 4 or later (Task 7 adds readings); the existing tests migrate to the labels.
2. `_hub_root() -> Path` returns `resolve_hot_source(load_config())`.
3. The hub test, gated `@pytest.mark.skipif(mount_absent("hot"), reason="hub mount absent — the hub pass reads hot/ where the NAS is mounted")`: `conformance(_cited(...), _hub_root(), frozenset())` holds no finding, the message naming each record and set and saying that a set a record cites changed or left the hub's `hot/`.
4. Tests, ungated: `_hub_root() == Path(load_config().nfs_mount_dir) / "hot"`; on `tmp_path` roots, a node and a hub — a cited frozen file whose hub copy holds other bytes is `rederived` on the node and a finding on the hub; a cited index line whose day files were moved off the hub with the lines kept (`tests.rolling_fixtures.write_chain`, then the day parquets moved aside) is `rederived` before the move and a finding naming the absent day file after it.
5. Probes, each expect KILLED: `_hub_root` returning `_DATA_ROOT` against its test; the `verify(...)` call in `conformance` removed against the moved-day-files case.

**Commit:** `test(research): the hub's hot/ still holds every byte a record cites, its chains verified there`.

## Task 7 — the readings ledger, the decisions-log tie, reading 1

**Files (code):** `cli/registry/record.py`, `cli/registry/store.py`, `cli/registry/__init__.py`, `cli/research/command.py`, `cli/research/subjects.py`, `README.md`, `tests/test_registry_store.py`, `tests/test_research_command.py`, `tests/test_trial_registry_provenance.py`, `tests/test_registry_replay.py`, `tests/test_registry_conformance.py`, `tests/test_decisions_log_ties.py` (new). **Files (records):** `docs/reference/reading-ledger.jsonl` (new), `docs/research/10.phase4-decisions.md`.

1. `record.py`: `validate_stored_reading(rec, where)` — the spec D7's thirteen keys exactly; `schema_version` 1; `record_hash` and `dataset_hash` derived as for a trial; `datasets` by `_validate_datasets_shape`; `invocation` by `validate_invocation(…, own_trial_id=None, …)`; `metrics` a non-empty dict through `_assert_finite`; `iteration` and `spec_hash` non-empty str; `outcome` None or a non-empty str; `notes` a str. `ReadingRecord`, frozen.
2. `store.py`: the healing read and the locked, re-read-under-lock append factored into private functions both classes call, each with its own validator and cross-record check; `ReadingLedger(path)` with `records` and `append(*, iteration, spec_hash, invocation, datasets, metrics, outcome, notes="") -> ReadingRecord`; its cross-record check: `reading_id` contiguous from 1 and the `prev_hash` chain. `cli/registry/__init__.py` exports it.
3. `subjects.py`: `b2-arm-a-bar` — `Subject("b2-arm-a-bar", (240,), _ASSETS, _build_b2_arm_a_bar, spec="docs/specs/00128-b2-family-opening-design.md", metric_keys=<the spec D7's ten>, seeds=(42,))`, its build `_b2_inputs` then `_b2_arm_a_bar`, the ten keys taken from the bar's result with each flag as `int`, wrapped in the B2 build's `SubjectError` translation.
4. `command.py`: `--reading` (needs `--iteration`; refused with `--register`; refused for a subject with a rule) and `--ledger PATH` (default `docs/reference/reading-ledger.jsonl`, anchored on `_REPO_ROOT` as `_REGISTRY` is); both write paths take Task 4's checks before and after the fit; `--register` whose rule returns None appends a reading with `outcome=subject.no_verdict`, prints "no verdict — <outcome>: recorded reading <N>; no trial spent", and exits 0, replacing Task 4's refusal. The module's tests gain an autouse fixture moving `_LEDGER` off the committed file, as `_REGISTRY`'s does.
5. CI and the passes: `_findings(…, kind="reading")` over every committed reading — (i)–(iv) and (vi), and in place of (v) the outcome's consistency (a ruleless subject: None; a ruled one: its `no_verdict`, and its rule None on the stored metrics); the replay's parametrisation and staleness test take the ledger (`reading-<id>`, `reading_id`); `_cited` takes every reading (`"reading 1"`).
6. `tests/test_decisions_log_ties.py`, ungated, over `git ls-files 'docs/research/*decisions*'`:

   ```python
   _ENTRY = re.compile(r"^\[iter-(\d+)\] ")
   _TIE = re.compile(r"\((registry trial|reading) (\d+)\b")
   _VERDICT = re.compile(r"\b(ADOPT|PARK|REJECT)(?:ED|S)?\b")
   _TRIAL_WORD = re.compile(r"\btrial\b", re.IGNORECASE)
   _TIE_FLOOR_ITER = 175

   def _header(line: str) -> str:
       cut = line.find(". ")
       return line if cut < 0 else line[:cut]
   ```

   `tie_findings(entries: list[tuple[int, str]], trials: dict[int, str], readings: set[int]) -> list[str]` over `(iter, header)` pairs, the spec D7's (a)–(c): (a) each tie token names an existing id, and for `registry trial N` the distinct verdict tokens before the token, if exactly one, equal N's verdict upper-cased, two or more being a finding; (b) an entry past `_TIE_FLOOR_ITER` whose header holds a verdict token and `_TRIAL_WORD` holds a tie token; (c) every trial past 47 and every reading is named by some tie token.
7. README: the rows for `--reading` and `--ledger`, and the sentence that a run whose rule gives no verdict is kept as a reading and spends no trial.
8. Tests:
   - `tests/test_registry_store.py`: a reading round-trips; two readings chain with contiguous ids across a reopen; a torn trailing line heals in the ledger as in the registry; refusals: `outcome` `""`, `outcome` `1`, a missing `invocation`, a `metrics` NaN;
   - `tests/test_research_command.py`: `--reading` on a ruleless stub writes one reading with outcome None and no registry line; `--reading` on a ruled subject: exit 1; `--reading` with `--register`: exit 1; `--register` whose rule gives None: exit 0, one reading whose outcome is the `no_verdict`, no registry line; the migrated B2 test's first parametrisation asserts that reading — metrics equal to the printed ones, outcome the B2 stop text; `b2-arm-a-bar` declares the ten keys, returns them as ints and floats on the B2 register fixture, and never calls `subjects.scale_positions` (a recording stub counts zero calls), so arm B is never built;
   - `tests/test_trial_registry_provenance.py`: the reading cases of `_findings` — a ruleless subject's reading with a non-null outcome; a ruled subject's reading whose rule gives a verdict on its metrics; a clean reading;
   - `tests/test_decisions_log_ties.py`: the committed logs give no finding; constructive, one finding each: an unknown trial id; `REJECT` before `(registry trial N` whose record is `adopt`; an unknown reading; a past-floor header with `REJECT`, "trial" and no tie; a record past 47 named by no header; a reading named by none — and none for the same header at iter-175, nor for a past-floor `ADOPTED` header without the word "trial".
9. Probes, each expect KILLED: the ledger's contiguity check removed against the reopen case; the outcome-consistency clause made always-clean against its case; the `--reading` refusal for a ruled subject removed against its case; the rule-None path made to append a trial against its case; `iter_n > _TIE_FLOOR_ITER` → `>=` against the iter-175 case; (a)'s verdict equality removed against the `REJECT`-over-`adopt` case; (c) removed against the unnamed-record case; `REJECT` dropped from `_VERDICT` against the past-floor case.

**Commit (code):** `feat(research): the readings ledger — what decides without registering is kept, and the decisions logs are tied to ids`.

10. Reading 1, on the code commit with a clean tree (`git status --porcelain` empty) and `ohlc-rolling` and `derivatives-funding` linked: `uv run zcrypto research eval --subject b2-arm-a-bar --dataset ohlc-rolling --as-of 2026-10-10 --window "2020-09-22 00:00:00+00:00" "2026-06-30 23:59:59+00:00" --accept-holes --reading --iteration iter-175 --notes "B2 trial 1's pre-flight: arm A's headline bar over the trial's window, as of 2026-10-10, holes accepted; arm A fails it, so the trial stopped as an instrument finding, unspent"` (about 92 s; no arm-B return).
11. Read back: `reading_id` 1; `dataset_hash` `500b55ea53eee9f4601f8d0f8dda6c1197dd048fdac5975ef4cb4c2e220be1b0`; `dsr` `0.8784909571584375`, `spa_p_value` `0.3843078460769615`, `spa_p_value_full` `0.09395302348825588`, `dsr_pass` 0, `spa_pass` 0, `cost_stress_pass` 1, `worst_slice_pass` 1, `passes` 0 — the spec's measured basis; `invocation.commit` the code commit; `spec_hash` `56baf5834a2b…` in full. Any difference: stop, tell the owner, nothing committed.
12. The decisions-log entry, written with `iteration-closeout` loaded, appended to `docs/research/10.phase4-decisions.md`: an `[iter-175]` entry whose header — the text before its first `. ` — holds `(reading 1` and no `ADOPT`, `PARK` or `REJECT`, naming `b2-arm-a-bar` and the block hash; its options and `(Decision: N)` as the skill lays them out.
13. `uv run pytest tests/test_decisions_log_ties.py tests/test_trial_registry_provenance.py tests/test_registry_store.py` passes; the records commit; then, on the clean tree, `uv run pytest tests/test_registry_replay.py -k reading-1` and `uv run pytest tests/test_registry_conformance.py` pass — the replay and both conformance passes over reading 1. The records commit takes its own `pre-review`.

**Commit (records):** `docs(research): B2 trial 1's pre-flight stop kept as reading 1`.

## Task 8 — record 47's identity

**Files:** `cli/research/subjects.py`, `tests/test_record47_identity.py` (new, module-marked `data`).

1. `_crossfreq_book(reader, dataset, window, as_of=None, accept_holes=False) -> CrossfreqSystemResult`: the two `_capturing_union` calls and `build_crossfreq_system_fast(…, config=_RECORD44_CONFIG)`, factored out of `_build_crossfreq`, which returns its six metrics over it unchanged.
2. The test, gated `@pytest.mark.skipif(not _CANONICAL.is_dir(), reason="data/ohlc-full absent — record 47's identity runs on the data host only")`: the engine side `raw = {(s, iv): read_store_series(_CANONICAL, s, iv) for s in PAIR_KEYS for iv in (1440, 240)}`, `select_model_inputs` per grid over the twelve, `build_crossfreq_system_fast(…, config=subjects._RECORD44_CONFIG)`, `_expand_to_basket` on every row; the subject side `subjects._crossfreq_book(ObservedReader(_DATA_ROOT), "ohlc-full", None)`. Asserted with `==`: the daily and 4h stamp lists and price panels; `governed_net` and `ungoverned_net`; for every row of `final_targets`, each `<base>/EUR` equal to the subject's `<base>` and every `BASKET` symbol ending `/BTC` exactly 0.0; `cap_breach_bars == 1318` and `governor_engaged_bars == 7302` on both; `{f"{s}/{iv}.parquet": <sha256 of _CANONICAL/s/iv.parquet>}` equal to record 47's `datasets["ohlc-full"]["files"]`, read from the committed registry; `subjects._RECORD44_CONFIG.cost_per_side == 0.006`. Lengths are asserted before the comparisons — 4,582 daily stamps, 27,338 4h stamps and target rows, 27,337 bars of net — so an empty side cannot pass.
3. Probes, each expect KILLED, none touching `cli/engine/`: `_crossfreq_book`'s 4h union read at 1440 (by line address), and `load_union`'s calendar in `cli/portfolio/record44_legs.py` made the legs' intersection (`s/set().union(\*\[/set.intersection(*[/`) — the subject side moves, the engine side does not — each against the test.

**Commit:** `test(research): record 47's identity — the twelve-leg engine path is record44-crossfreq's book on the ten EUR legs`.

## Task 9 — closeout

1. `git -C <worktree> diff --quiet "$(git -C <worktree> merge-base origin/develop HEAD)" HEAD -- cli/engine` exits 0.
2. With the three sets linked: `uv run pytest -m data tests/test_registry_replay.py tests/test_registry_conformance.py tests/test_record47_identity.py tests/test_research_control.py tests/test_research_b2_basis.py` passes, its skip count read — 0 on the workstation, where the hub is mounted.
3. Every consumer: the files `git grep -l -E "cli\.registry|cli\.research|test_registry_conformance" -- tests infra/scripts .claude` (the vault excludes) lists, run.
4. The reads (Global constraints), then the PR through `open-pr` — `feat(research): 00129 — every trial re-derivable from the tree and the hub`, its body naming reading 1, the mutate-probe verdict lines and the read line — and the change-index row it writes; merge on the owner's word through `merge-pr`.
5. Before `merge-pr` runs: `rm` the three links under the worktree's `data/`, then `ls -la /home/zhaow/Projects/zcrypto-kraken/data` reads the canonical sets still there.
