# Incremental verify-replay Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `verify-replay` certifies the whole archive nightly while replaying only stale hours, making runtime `(new hours) + (fixed budget)` and journal output flat — spec `00078`, closing [[T0114]].

**Architecture:** A parquet checkpoint (`cli/archive/checkpoint.py`) caches each hour's **raw** replay facts keyed by byte-hash + `VERIFIER_VERSION`; an incremental orchestrator in `cli/archive/replay.py` partitions hours into mandatory-new / budget-drained / cache-reused, re-replays a K=25 random audit sample, refolds `_chain_anchor` over the full sequence every run, and refuses destructive evictions. The CLI gains `--state-dir`/`--reverify-all`; the ops runner gains a `:rw` state mount, census parsing, four new metrics; one new warning alert watches the drain backlog.

**Tech Stack:** Python 3.14 (uv), polars, typer, pytest + CliRunner, Jinja2-rendered bash runner (tested by rendering), Grafana provisioned alerts.

## Global Constraints

- **The summary surfaces are byte-frozen** (spec `00078` D11): the `typer.echo` line `replayed {n} hour(s): {ok} ok, {failed} failed`, the logfmt line `verify-replay complete hours=%d ok=%d failed=%d`, and the per-failing-hour line format must not change — `00077`'s parse and alert semantics depend on them.
- **Raw facts only in the checkpoint** (D1): `anchored` as cached is `opens_with_snapshot`, never the chain verdict. The chain is refolded every run.
- **Failures are never trusted from cache** (D3): any cached row with `error != None` or any check false is always re-replayed.
- **Operator-facing text** (`.claude/rules/operator-facing-text.md`): no `T0114`/`spec 00078`/`D<N>` tokens in `--help`, metric HELP lines, or the alert summary; the alert summary must be self-contained (no "the rule above").
- Python 3.14 / PEP 758: unparenthesized `except A, B:` is valid — do not "fix" it.
- Run everything through `uv run`; commit gate is `uv run pre-commit run -a`; stage by explicit path.
- Every commit ends with `Co-Authored-By: <your actual model> <noreply@anthropic.com>` (verify your model; never copy a hardcoded name).
- Constants (verbatim): `VERIFIER_VERSION = 1`, `CHECKPOINT_SCHEMA_VERSION = 1`, drain budget default `7200.0` s, audit `K = 25`, flush every `250` replayed hours, eviction refusal above `0.10` of checkpoint rows, state path `/var/lib/zcrypto-ops/verify-replay-state`, container mount `/state`.

---

### Task 1: Checkpoint store (`cli/archive/checkpoint.py`)

**Files:**
- Create: `cli/archive/checkpoint.py`
- Test: `tests/test_archive_checkpoint.py`

**Interfaces:**
- Consumes: nothing project-internal beyond `polars`.
- Produces (Tasks 2–4 rely on these exact names):

```python
CHECKPOINT_SCHEMA_VERSION = 1

@dataclass(frozen=True)
class CheckpointRow:
    pair: str
    hour: datetime          # tz-aware UTC
    byte_hash: str          # sha256 hex of the bytes replayed
    verifier_version: int
    opens_with_snapshot: bool
    ts_ordered: bool
    checksum_present: bool
    replay_ok: bool
    error: str | None
    rows: int
    messages: int
    polars_version: str     # recorded, NOT an invalidation key (D5)
    depth: int              # recorded, NOT an invalidation key (D5)
    verified_at: datetime

class CheckpointWriteError(Exception): ...

def load_checkpoint(state_dir: Path) -> dict[tuple[str, datetime], CheckpointRow] | None
def save_checkpoint(state_dir: Path, rows: Iterable[CheckpointRow]) -> None
```

- [ ] **Step 1: Write the failing tests** — round-trip; absent dir → `None`; corrupt file → `None`; wrong `schema_version` → `None`; atomicity; write failure raises.

```python
import polars as pl
import pytest
from cli.archive.checkpoint import (
    CHECKPOINT_SCHEMA_VERSION, CheckpointRow, CheckpointWriteError, load_checkpoint, save_checkpoint,
)

def _row(pair="BTC/EUR", hour=None, **kw):
    from datetime import UTC, datetime
    base = dict(
        pair=pair, hour=hour or datetime(2026, 8, 1, 3, tzinfo=UTC), byte_hash="ab" * 32,
        verifier_version=1, opens_with_snapshot=True, ts_ordered=True, checksum_present=True,
        replay_ok=True, error=None, rows=10, messages=3, polars_version=pl.__version__,
        depth=10, verified_at=datetime(2026, 8, 1, 4, tzinfo=UTC),
    )
    base.update(kw)
    return CheckpointRow(**base)

def test_round_trip_preserves_every_field(tmp_path):
    rows = [_row(), _row(pair="ETH/EUR", error="EIO", replay_ok=False)]
    save_checkpoint(tmp_path, rows)
    loaded = load_checkpoint(tmp_path)
    assert loaded is not None and len(loaded) == 2
    assert loaded[("BTC/EUR", rows[0].hour)] == rows[0]
    assert loaded[("ETH/EUR", rows[1].hour)] == rows[1]  # error survives as a string, None stays None

def test_absent_state_dir_loads_none(tmp_path):
    assert load_checkpoint(tmp_path / "never-created") is None

def test_corrupt_file_loads_none_not_raise(tmp_path):
    save_checkpoint(tmp_path, [_row()])
    (tmp_path / "checkpoint.parquet").write_bytes(b"not parquet")
    assert load_checkpoint(tmp_path) is None

def test_wrong_schema_version_loads_none(tmp_path):
    save_checkpoint(tmp_path, [_row()])
    frame = pl.read_parquet(tmp_path / "checkpoint.parquet")
    frame = frame.with_columns(pl.lit(CHECKPOINT_SCHEMA_VERSION + 1).alias("schema_version"))
    frame.write_parquet(tmp_path / "checkpoint.parquet")
    assert load_checkpoint(tmp_path) is None

def test_save_is_atomic_no_tmp_left_behind(tmp_path):
    save_checkpoint(tmp_path, [_row()])
    save_checkpoint(tmp_path, [_row(), _row(pair="ETH/EUR")])
    assert [p.name for p in tmp_path.iterdir()] == ["checkpoint.parquet"]

def test_unwritable_dir_raises_checkpoint_write_error(tmp_path):
    state = tmp_path / "ro"; state.mkdir(); state.chmod(0o500)
    try:
        with pytest.raises(CheckpointWriteError):
            save_checkpoint(state, [_row()])
    finally:
        state.chmod(0o700)
```

- [ ] **Step 2: Run to verify they fail** — `uv run pytest tests/test_archive_checkpoint.py -q` → import error.
- [ ] **Step 3: Implement.** Parquet with a `schema_version` literal column; `save_checkpoint` writes `checkpoint.parquet.tmp` then `os.replace` (the mint pattern), wrapping every OS/IO error in `CheckpointWriteError`; `load_checkpoint` returns `None` on absent/unreadable/wrong-schema (never raises — the caller announces the rebuild). `error=None` round-trips as parquet null. Hours stored as UTC timestamps, loaded back tz-aware.
- [ ] **Step 4: Run to verify green**, then `uv run pre-commit run -a` until clean.
- [ ] **Step 5: Commit** — `feat(archive): checkpoint store for incremental verify-replay` (stage the two files explicitly).

### Task 2: Incremental orchestrator core (`verify_replay_incremental`)

**Files:**
- Modify: `cli/archive/replay.py` (append; do not touch `replay_segment`/`_chain_anchor`/`verify_replay`)
- Test: `tests/test_archive_replay_incremental.py`

**Interfaces:**
- Consumes: Task 1's store; existing `replay_segment`, `_chain_anchor`, `canonical_segments`, `ReplayResult`.
- Produces:

```python
VERIFIER_VERSION = 1

@dataclass(frozen=True)
class Census:
    replayed: int
    reused: int
    audited: int
    audit_mismatches: tuple[str, ...]   # "PAIR YYYY-MM-DD HH:00" labels
    pending: int
    evicted: int
    duration_s: float

class EvictionRefusedError(Exception): ...

def verify_replay_incremental(
    primary_root: Path, reconciled_root: Path | None, *, state_dir: Path, depth: int,
    drain_budget_s: float = 7200.0, audit_k: int = 25, reverify_all: bool = False,
    rng: random.Random | None = None,
) -> tuple[list[ReplayResult], Census]
```

Behavioral contract (each clause is a test below): raw-facts caching; staleness = new ∪ hash-changed ∪ version-changed ∪ cached-failure ∪ `reverify_all`; new hours mandatory, older stale hours drained oldest-first (sorted by `(hour, pair)`) within `drain_budget_s`; sidecar read (`path.with_name(path.name + ".sha256")`, first whitespace token) is the cheap staleness probe; a replayed hour's `byte_hash` is `hashlib.sha256(path.read_bytes()).hexdigest()` computed before the replay, and a mismatch against the sidecar token (or a missing/empty sidecar) rewrites the result to a failure (`error="manifest mismatch: …"` / `"no manifest sidecar"`); refold `_chain_anchor` over cached+fresh in `(pair, hour)` order; empty enumeration returns `([], Census(0,0,0,(),0,0,~0))` **without touching the checkpoint**; eviction of >10% of a nonempty checkpoint raises `EvictionRefusedError` before any replay; the checkpoint is flushed every 250 replayed hours and at the end (fresh rows carry current `VERIFIER_VERSION`; pending rows keep their old ones; evicted keys dropped). **A *cached failure* is `error != None` or any of `ts_ordered`/`checksum_present`/`replay_ok` false — `opens_with_snapshot` is excluded** (a raw fact, not a failure; including it re-replays ~96% of the archive nightly). **The sidecar probe and the pre-replay `read_bytes()` hash both isolate `OSError` into that hour's failure** (`error=…`, run continues) — they sit outside `replay_segment`'s never-raises contract, and a transient NFS EIO must stay one failing hour, not a whole-run crash.

- [ ] **Step 1: Build the synthetic-tree helper.** Reuse the fixture idiom from `tests/test_archive_replay.py` (it already builds parquet book hours; read it first). Helper `make_tree(tmp_path, pairs, hours, *, snapshot_first_hour=True)` writes canonical layout + a correct `.sha256` sidecar per final (`hashlib.sha256(final.read_bytes()).hexdigest()` + `"  " + name`, matching `verify_manifest`'s token format).
- [ ] **Step 2: Write the failing tests:**

```python
def test_equivalence_full_vs_warm_incremental(tmp_path):
    """Spec D1: a warm no-change incremental run equals the full replay field-for-field."""
    tree = make_tree(tmp_path, pairs=["BTC/EUR", "ETH/EUR"], hours=6)
    full = verify_replay(tree.primary, None, depth=10)
    state = tmp_path / "state"
    first, c1 = verify_replay_incremental(tree.primary, None, state_dir=state, depth=10)
    assert first == full and c1.replayed == 12 and c1.reused == 0
    second, c2 = verify_replay_incremental(tree.primary, None, state_dir=state, depth=10, audit_k=0)
    assert second == full and c2.replayed == 0 and c2.reused == 12

def test_d1_sequence_chain_verdict_is_never_cached(tmp_path):
    """The review's breaking sequence: H chained through good H-1; H-1 rewritten to fail; H must flip."""
    tree = make_tree(tmp_path, pairs=["BTC/EUR"], hours=3)  # hour0 snapshot; hours 1,2 chained
    state = tmp_path / "state"
    first, _ = verify_replay_incremental(tree.primary, None, state_dir=state, depth=10, audit_k=0)
    assert all(r.anchored for r in first)
    tree.corrupt_hour("BTC/EUR", 1)          # rewrite hour1 final+sidecar to unreadable garbage
    second, census = verify_replay_incremental(tree.primary, None, state_dir=state, depth=10, audit_k=0)
    by_hour = {r.hour.hour: r for r in second}
    assert by_hour[1].error is not None       # replayed (hash changed), fails
    assert not by_hour[2].anchored            # NOT re-replayed, but the refold must flip it

def test_new_hours_are_mandatory_even_at_zero_budget(tmp_path): ...
    # warm checkpoint; add hour; drain_budget_s=0 -> census.replayed == 1, hours_total grows

def test_version_bump_drains_oldest_first_within_budget(tmp_path, monkeypatch): ...
    # warm checkpoint; monkeypatch VERIFIER_VERSION+1; budget sized (monkeypatched clock) for ~half ->
    # census.pending > 0, the replayed set is the OLDEST hours, pending rows keep the old version

def test_cached_failure_is_always_replayed_and_heals(tmp_path): ...
    # corrupt hour -> run (fails, cached as failure) -> restore good final+sidecar with ORIGINAL bytes
    # (hash matches cache) -> next run must re-replay it anyway and report healthy (spec D3)

def test_sidecar_missing_or_mismatched_is_a_failure_and_never_trusted(tmp_path): ...
    # delete one sidecar -> hour reported failing (error mentions manifest), replayed on EVERY run;
    # separately: rewrite final without updating sidecar -> failure naming the mismatch

def test_empty_enumeration_leaves_checkpoint_untouched(tmp_path): ...
    # warm checkpoint; point at an EMPTY primary root -> ([], census); checkpoint bytes identical

def test_eviction_over_ten_percent_refuses_before_replaying(tmp_path): ...
    # warm 20-hour checkpoint; delete 3 hours from the tree -> EvictionRefusedError; checkpoint intact

def test_eviction_under_ten_percent_proceeds_and_evicts(tmp_path): ...
    # warm 20-hour checkpoint (2 pairs x 10h); delete ONE hour's final+sidecar (5%) -> run succeeds,
    # census.evicted == 1, reloaded checkpoint lacks exactly that key, results carry 19 hours

def test_flush_every_250_survives_a_kill(tmp_path, monkeypatch): ...
    # monkeypatch the flush interval to 3 and replay_segment to raise SystemExit on the 5th call;
    # rerun -> census.replayed strictly less than the tree size (progress survived)

def test_transient_read_error_is_isolated_to_the_hour(tmp_path, monkeypatch): ...
    # monkeypatch Path.read_bytes to raise OSError for ONE final only -> run completes,
    # that hour fails (error set), census emitted, every other hour verdicted (spec D3/F5)

def test_recorded_environment_never_invalidates(tmp_path): ...
    # doctor polars_version and depth in a cached row -> hour still REUSED (census.reused counts it).
    # Constructed proof of spec D5's NON-invalidation: accidentally adding these to the stale
    # predicate passes every other test and ships the permanent-mid-drain pathology.
```

- [ ] **Step 3: Run to verify they fail**, then implement. Orchestration order (spec D7): enumerate → empty-guard → load checkpoint (`None` → empty dict; every hour becomes stale) → eviction guard → partition → replay mandatory (in `(pair, hour)` order) → drain oldest-first under `time.monotonic()` budget → assemble raw list (fresh where replayed, cached otherwise, converting `CheckpointRow` → `ReplayResult` with `anchored=opens_with_snapshot`) → `_chain_anchor` → final `save_checkpoint`. Keep the audit out — Task 3 adds it (pass `audit_k=0` through a parameter that Task 3 implements; until then accept and ignore it).
- [ ] **Step 4: Green + `uv run pre-commit run -a`.**
- [ ] **Step 5: Commit** — `feat(archive): incremental verify-replay with raw-fact checkpointing`.

### Task 3: The sampled audit (D6)

**Files:**
- Modify: `cli/archive/replay.py` (the `audit_k` path inside `verify_replay_incremental`)
- Test: `tests/test_archive_replay_incremental.py` (append)

**Interfaces:** `Census.audited` / `Census.audit_mismatches` become live; `rng` (default `random.Random()`) drives `rng.sample` over the **reused keys ONLY** — never pending, whose rows are known-stale by construction and would mismatch with certainty through every legitimate drain (spec D6/F1) — `min(audit_k, len(reused))` of them.

- [ ] **Step 1: Failing tests:**

```python
def test_audit_trips_on_a_doctored_fact(tmp_path):
    """Plant a lie in the checkpoint; the audit must catch it (guard proven by construction)."""
    tree = make_tree(tmp_path, pairs=["BTC/EUR"], hours=4)
    state = tmp_path / "state"
    verify_replay_incremental(tree.primary, None, state_dir=state, depth=10, audit_k=0)
    doctor_checkpoint(state, ("BTC/EUR", hour(2)), ts_ordered=False)   # helper: rewrite one row
    _, census = verify_replay_incremental(
        tree.primary, None, state_dir=state, depth=10, audit_k=4, rng=random.Random(7))
    assert census.audit_mismatches and "BTC/EUR" in census.audit_mismatches[0]

def test_audit_trips_on_a_doctored_byte_hash(tmp_path): ...
    # doctor byte_hash only -> mismatch (covers overlay bit rot the NAS instrument cannot see)

def test_audit_k_larger_than_cache_degrades_to_all(tmp_path): ...
def test_audit_zero_disables_cleanly(tmp_path): ...
def test_audited_fresh_result_replaces_cached_row(tmp_path): ...
    # after an audit pass, the audited rows' verified_at advanced in the saved checkpoint

def test_audit_never_samples_pending_rows(tmp_path, monkeypatch): ...
    # warm checkpoint; bump VERIFIER_VERSION and set a budget forcing spillover (pending > 0);
    # audit_k > 0 -> a clean drain night reports ZERO mismatches (spec D6/F1: sampling pending
    # would fail every night of a legitimate 74-night drain)
```

- [ ] **Step 2: Fail → implement.** Audit runs after the drain: sample, re-replay + re-hash each, compare the full raw tuple `(byte_hash, opens_with_snapshot, ts_ordered, checksum_present, replay_ok, error, rows, messages)`; mismatches → `census.audit_mismatches` labels; fresh results replace the cached rows in both the result list (before the refold) and the saved checkpoint — the checkpoint is still written (self-healing), the **CLI** decides loud failure (Task 4).
- [ ] **Step 3: Green + gate. Commit** — `feat(archive): nightly sampled audit of cache-trusted verify-replay verdicts`.

### Task 4: CLI wiring

**Files:**
- Modify: `cli/archive/command.py` (the `verify_replay` command)
- Modify: `README.md` (Usage — same change, per `readme-usage.md`)
- Test: `tests/test_archive_replay.py` (append CliRunner tests)

**Interfaces:** new options `--state-dir Path`, `--reverify-all` flag, `--drain-budget-seconds float = 7200.0`, `--audit-sample int = 25`. Help text plain-operator ("cache verified hours here and replay only changed ones on later runs" — no spec/topic tokens).

Behavioral contract: **an empty result list takes the existing `no canonical book hours found` early return BEFORE any census or summary emission** — printing `hours=0` would make the runner read an unmounted NAS as healthy (`run_ok=1`), re-opening the blind spot `00077` D2 closed. Without `--state-dir` the command is **byte-identical to today** (full replay, per-hour lines — the ad-hoc path). With it: refuse `--pair`/`--since` (`typer.BadParameter`); refuse `--reverify-all` without `--state-dir`; call the incremental path; print one line per **currently-failing** hour (existing line format), the census logfmt line, then the frozen echo+logfmt summaries; `EvictionRefusedError`/`CheckpointWriteError` → error line, **no summary**, `raise typer.Exit(2)`; nonempty `audit_mismatches` → per-mismatch line + error line, **no summary** (checkpoint already self-healed), `Exit(2)`; failed hours → summary printed then `Exit(1)` (unchanged).

- [ ] **Step 1: Failing tests** (follow `tests/test_archive_replay.py`'s existing CliRunner idiom, incl. the `caplog`-handler attachment lesson):

```python
def test_state_dir_with_pair_is_refused(): ...          # exit != 0, message names the conflict
def test_reverify_all_requires_state_dir(): ...
def test_census_line_and_frozen_summary_both_emitted(tmp_path): ...
    # 'verify-replay census replayed=' in output AND the exact 'verify-replay complete hours=' logfmt
def test_audit_mismatch_withholds_summary_and_exits_2(tmp_path, monkeypatch): ...
    # monkeypatch verify_replay_incremental to return a census with audit_mismatches ->
    # no 'verify-replay complete' line in output, exit_code == 2
def test_eviction_refusal_withholds_summary_and_exits_2(tmp_path, monkeypatch): ...
def test_currently_failing_cached_hour_is_still_printed(tmp_path): ...
    # a cached-failure hour appears as a line even though this run replayed it from the drain
def test_without_state_dir_output_is_unchanged(tmp_path): ...  # per-hour lines still present
def test_empty_tree_with_state_dir_emits_no_census_and_no_summary(tmp_path): ...
    # empty primary root + --state-dir -> exit 0, 'no canonical book hours found', NO 'census',
    # NO 'verify-replay complete' line (spec D7/F3)
def test_state_dir_with_since_is_refused(): ...
def test_checkpoint_write_error_withholds_summary_and_exits_2(tmp_path, monkeypatch): ...
```

- [ ] **Step 2: Fail → implement → green.** Census via `typer.echo` **and** `logger.info("verify-replay census replayed=%d reused=%d audited=%d pending=%d evicted=%d duration_s=%d", ...)` (the runner parses the log; both surfaces carry it).
- [ ] **Step 3: Update `README.md` Usage** for the four new options, same commit.
- [ ] **Step 4: Gate. Commit** — `feat(archive): --state-dir incremental mode for verify-replay`.

### Task 5: Runner template + role

**Files:**
- Modify: `infra/ansible/roles/ops/templates/verify-replay.sh.j2`
- Modify: `infra/ansible/roles/ops/tasks/main.yml` (state-dir creation, near the existing textfile-dir task)
- Modify: `infra/ansible/roles/ops/defaults/main.yml` (`ops_verify_replay_state_subdir: verify-replay-state`)
- Test: `tests/test_infra_verify_replay_template.py` (append)
- Test: `tests/test_infra_alloy_series.py` (pin the four new series in `OPS_REQUIRED` — the `00077` precedent: a narrowed keep-wildcard must fail here rather than silently NoData the backlog rule)

Template changes: add `-v "{{ ops_data_dir }}/{{ ops_verify_replay_state_subdir }}:/state:rw"` and pass `--state-dir /state` (both on the `docker run`; `/data` stays `:ro` — assert that in a test); parse the census with the established sed idiom (`replayed=`, `reused=`, `pending=`, `duration_s=` — each `'s/.*<field>=\([0-9][0-9]*\).*/\1/p' | tail -1`); publish `ops_verify_replay_replayed_hours`, `ops_verify_replay_reused_hours`, `ops_verify_replay_pending_hours`, `ops_verify_replay_duration_seconds` — **carried forward on a broken run exactly like `failed_hours`** (same `prev_` idiom, same D3 reasoning); `run_ok` gating and all existing series unchanged. Role: create the state dir `owner/group zcrypto-data, mode 0750` (the container runs as that uid/gid — spec `00057`).

- [ ] **Step 1: Failing tests.** Extend the existing render-harness file, reusing its `_render`/stub machinery: census-parse test runs **every** new sed over the CLI's real census line — both hardcoded and via the live `caplog` record, all fields asserted by value (the `00077` `hours=` lesson: covering one field silently dropped the other); executed-block test stubs `docker` to (a) census+summary, (b) census only, (c) nothing, asserting carry-forward + `run_ok` per path; a `/data:ro` + `/state:rw` mount assertion; a bash `-n` syntax check (existing).
- [ ] **Step 2: Fail → implement → green.** Prove one census mutation by construction: change the CLI's `reused=` to `cached=` in a scratch probe → the parse test must fail naming the field; revert, clear `cli/**/__pycache__` before and after.
- [ ] **Step 3: Gate. Commit** — `feat(infra): verify-replay runner mounts checkpoint state and publishes census metrics`.

### Task 6: The backlog-stuck alert + runbook

**Files:**
- Modify: `infra/grafana/alerts.yaml` (one rule, uid `zcrypto-ops-verify-replay-backlog-stuck`, beside the two `00077` rules)
- Modify: `infra/runbooks/README.md` (entry anchored like the `00077` pair, cross-linked from the rule's annotation)
- Test: `tests/test_infra_alert_rules.py` (follow the `00077` rules' test shape — the pinning idiom `test_the_permanent_loss_page_outlives_a_single_evaluation_hour` lives here)

Rule (spec D12): warning; query A `ops_verify_replay_pending_hours`, query B `delta(ops_verify_replay_pending_hours[26h])`, math `$A > 0 && $B >= 0`, **`for: 27h`**, `relativeTimeRange from: 93600` — the 26 h window spans exactly the last two runs, and `for` must **strictly exceed `max(24 h, window)` = 26 h** because `pending` is a persistent gauge: the condition goes true at the bump night's publish and cannot go false until the window's left edge passes it, so a *healthy* drain holds it true for a full 26 h regardless of night two's progress. `for: 25h` therefore fires an hour after night two, identically to a stuck backlog, and `for: 26h` trips on the 26 h true run — 27 h leaves an hour of margin. A 49 h window is wrong for the separate reason that it drags a third night into the same difference, so `delta`'s sign stops meaning "did the last run make progress" (spec D12/F2). `noDataState: OK`, `execErrState: Alerting`. Summary, self-contained, operator-plain: `The nightly archive re-verification backlog is not shrinking. The sweep still runs, but hours queued for re-verification have not decreased across two nightly runs — the drain budget may be zero, the state directory lost, or the drain broken. Runbook: <anchor>` (no trailing period — a dot is swallowed by Slack's link autodetection, and every existing summary ends at the anchor). The runbook entry also carries the eviction-refusal operator path (spec D7): after a deliberate mass archive shrink, delete the checkpoint dir and accept the announced rebuild.

- [ ] **Step 1: Failing tests:** uid present ≤40 chars; expr/window/`for`/states pinned (the repo has the exact idiom — `test_the_permanent_loss_page_outlives_a_single_evaluation_hour`); the `for > max(24 h, window)` invariant asserted as arithmetic, plus a **timeline simulation** replaying four nightly-gauge histories (steady / healthy drain / stuck flat / growing) through the rule's own window and `for` and asserting quiet/quiet/fires/fires — reading the rule is not enough, this is the assertion that catches a wrong `for`; the **firing direction** pinned (`condition` names the math-fed threshold node, evaluator `gt 0` — a `lt` evaluator can never fire, since the math node emits only 0 or 1); summary passes the internal-vocabulary guard (it runs automatically; still assert the rule is *covered* by it); runbook anchor resolves character-for-character (nothing mechanical checks links — assert both sides literally, per the `00077` addendum).
- [ ] **Step 2: Fail → implement → green → gate. Commit** — `feat(infra): page when the verify-replay re-verification backlog stops draining`.

### Task 7: Closeout (branch end — verify against the full branch log first)

**Files:**
- Modify: `docs/open-topics/T0114-verify-replay-rescans-the-whole-archive-every-night.md` → `docs/open-topics/archive/` (via `git mv`)
- Modify: `docs/open-topics/README.md` (index move to `### Resolved`, link to archived path)
- Modify: `docs/iterations-history-phase6.md` (+ its index only if a new file were needed — it is not)
- Modify: `docs/specs/00078-incremental-verify-replay-design.md` (only if drift emerged during implementation — record what changed, in place)

- [ ] **Step 1: Load the `topic-ops` and `iteration-closeout` skills** (orchestrator does this task's dispatching with them loaded; the implementer gets their mechanics in the brief).
- [ ] **Step 2: Resolve T0114.** All three sub-items close: checkpointing (this branch), windowing re-evaluation (D13 — decided never, with the reasoning), duration/hour-count metrics (D11). `## Resolution` names the spec, the commits, and the D1 near-miss (the cold review's post-chain-anchored finding). Delete `ripe_when:`; move to `archive/`; index bullet moves to `### Resolved` with the archived link.
- [ ] **Step 3: Iterations-history entry** (phase 6 file), written fresh at branch end against the actual log — never pre-written. It must state: what shipped, the D1 silent-false-pass caught at design review (before a line of code — contrast with `00076` D7 which shipped and reverted same-day), the D5 sustainability reversal (polars out of the invalidation key, and why), and the deploy tail owed.
- [ ] **Step 4: The attended tail is NOT run by this branch** — the entry and the memo (orchestrator, Edit tool under the read-guard, never a subagent) record it per spec `00078` Deploy: image rebuild → pin recorded → converge `--limit zcrypto-ops` (no `ops_alloy_digest`; liquidations decision, prefer rolling) → push rules (additive, no prune) → verify by value at the first tick (census present, `reused ≈ 0` night one, `pending` draining, `failed_hours` unchanged). **Rollback is digest + template together** — the prior image rejects `--state-dir`, so a digest-only rollback yields `run_ok=0` nightly and a dark dead-man (spec Rollback/F6).
- [ ] **Step 5: Full gate** (`uv run pytest` complete, `uv run pre-commit run -a`), stage by kind, commit — `docs(ops): iter closeout — verify-replay goes incremental (spec 00078, resolves T0114)`.
