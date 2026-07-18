# OPS-6 Loop (spec 00056, T0033, iter-103) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make research runnable on either the ops node or the workstation: the `custody`/`hot`/`private` dataset topology, the `zcrypto data` fetch/push/rebuild exchange through the NAS `hot/` hub, git-tracked running decisions logs, the catalog rewrite, dead-config removal, and the workstation payload retirement (spec 00056 D1–D9).

**Architecture:** Tasks 1–6 are code/docs (subagent-executable, TDD). Tasks 7–9 are **attended, orchestrator-only** (NAS/ops converges, seeding, systemd retirement — they touch live infrastructure). Task 10 is closeout. The transport is plain rsync with `--ignore-existing` and never `--delete` — the append-only contract enforced structurally (spec D1c).

**Tech Stack:** Python 3.14 (uv-locked), Typer, subprocess+rsync, polars (manifest verify), Ansible (nas/ops roles), pytest.

## Global Constraints

- Branch `feat/ops6-loop` in `/home/zhaow/Projects/zcrypto-kraken` (already cut; spec committed). One commit per task; plain blocking commands; never end a turn before the commit exists.
- **Security (binding, every task):** NEVER run `ansible-inventory --host`/`--list` (prints every secret incl. the live Kraken trade key — use `--graph`/`--list-tags`). Never decrypt/print/echo a vault value. Playbooks only via `infra/ansible/scripts/run.sh`, preview with `--check --diff`. The ops node never joins `engine_host`. L2 capture is unbackfillable.
- **Transport invariants (spec D1c/D2):** rsync always `--archive --ignore-existing`, never `--delete`; the workstation push never goes through the rw+soft NFS mount (ssh only); ops never pushes.
- Python 3.14 / PEP 758: `except ValueError, IndexError:` without `as` is valid — never "fix" it.
- Commit gate: `uv run pre-commit run -a` until clean; a run that rewrites files leaves them unstaged — re-run, restage everything, commit. Never `--no-verify`.
- Commit messages: `<type>(<scope>): <subject>`, no iter-N tags in subjects, ending with a blank line + `Co-Authored-By: <your ACTUAL model name> <noreply@anthropic.com>`. Every subagent commit gets a `Reviewed-by:` trailer amended after its review passes (while local).
- Decisions-log running files are **verbatim** — no formatter may restructure them (Task 5 extends the mdformat exclusion BEFORE the files land; keep that ordering inside the task).
- README `## Usage` must document the new `data` group in the same change that completes it (Task 4).

______________________________________________________________________

### Task 1: Remove the dead config surface (spec D5)

**Files:**

- Modify: `cli/config.py`, `zcrypto.toml`, `tests/test_config.py`

**Interfaces:**

- Produces: `AppConfig` without `backup_dir`; `FetchConfig` without `backfill_right_edge_grace_days`/`rename_synth_warn_days`; `resolve_backup_dir` gone. (Verified this session: zero non-declaration consumers for all three.)

- [ ] **Step 1: Write the failing test change.** In `tests/test_config.py`: remove `resolve_backup_dir` from the import list (line 11); delete the `backup_dir`-assert lines 26, 40, 47 and the whole test around lines 188–189 (`resolve_backup_dir(None, cfg) == Path("cfg_bk")`); drop `backup_dir = "../zcrypto-data"` from the TOML literal at line 36; drop `backup_dir=None` from the two `AppConfig(...)` constructions at lines 203 and 211. Add one new test pinning the removal:

```python
def test_removed_keys_are_rejected(tmp_path):
    with pytest.raises(ConfigError, match="unknown key"):
        load_config(_write(tmp_path, '[zcrypto.fetch]\nbackfill_right_edge_grace_days = 7\n'))
```

(`[zcrypto.fetch]` unknown keys already raise via `_build_fetch`'s allowlist — this pins that the removed field is now unknown. Note: a top-level `backup_dir` key is silently ignored by `load_config` (it only `.get`s known keys) — that is acceptable and needs no guard; do NOT add one.)

- [ ] **Step 2: Run to verify failure.** `uv run pytest tests/test_config.py -v` — expect ImportError/AttributeError failures against the still-present fields, and the new test failing (the key is currently known).
- [ ] **Step 3: Implement.** In `cli/config.py`: delete `backfill_right_edge_grace_days: int = 7` and `rename_synth_warn_days: int = 7` (lines 25–26); delete `backup_dir: Path | None` from `AppConfig` (line 44); delete `backup_dir=None` from the no-config return (line 121) and `backup_dir=_read_path(...)` (line 131); delete `resolve_backup_dir` (lines 150–151). In `zcrypto.toml`: delete the `backup_dir` line and its comment (`# Durable backup root holding raw/ ...`).
- [ ] **Step 4: Verify.** `uv run pytest tests/test_config.py -q` — all pass. Then `grep -rn "backup_dir\|right_edge\|rename_synth" cli/ tests/ zcrypto.toml` — expect zero hits.
- [ ] **Step 5: Commit.** `fix(config): remove dead backup_dir + two never-wired fetch fields (spec 00056 D5)`

______________________________________________________________________

### Task 2: The `[zcrypto.data]` config table (spec D3)

**Files:**

- Modify: `cli/config.py`, `zcrypto.toml`, `tests/test_config.py`

**Interfaces:**

- Produces (later tasks consume verbatim):

```python
@dataclass(frozen=True)
class DataConfig:
    """The hot-cluster exchange (spec 00056): where to fetch the replicated working set from,
    where this node pushes what it authors, and which sets it authors."""

    hot_dir: Path | None = None        # the mounted NAS hot/ (fetch source; NFS read path)
    push_dest: str | None = None       # rsync destination for push (ssh alias or path; rrsync-pinned)
    authored_sets: tuple[str, ...] = ()  # set names this node may push

def resolve_hot_dir(flag_value: Path | None, cfg: AppConfig) -> Path      # _resolve-style, name="data.hot_dir", flag="--hot-dir"
def resolve_push_dest(cfg: AppConfig) -> str                              # raises ConfigError when unset
```

`AppConfig` gains `data: DataConfig`; `load_config` builds it via a new `_build_data(table, config_path)` following `_build_engine`'s shape: unknown-key rejection over `fields(DataConfig)`; `hot_dir` via the non-empty-string check (as `_read_path` does) → `Path`; `push_dest` a non-empty string; `authored_sets` a list of non-empty strings → tuple.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_config.py`):

```python
def test_data_config_defaults_when_absent(tmp_path):
    cfg = load_config(_write(tmp_path, "[zcrypto]\n"))
    assert cfg.data == DataConfig()


def test_data_config_parses_all_keys(tmp_path):
    cfg = load_config(
        _write(
            tmp_path,
            '[zcrypto.data]\nhot_dir = "../zcrypto-kraken-data/hot"\npush_dest = "nas-hot:"\n'
            'authored_sets = ["ohlc-full", "snapshots"]\n',
        )
    )
    assert cfg.data.hot_dir == Path("../zcrypto-kraken-data/hot")
    assert cfg.data.push_dest == "nas-hot:"
    assert cfg.data.authored_sets == ("ohlc-full", "snapshots")


def test_data_config_unknown_key_raises(tmp_path):
    with pytest.raises(ConfigError, match="unknown key"):
        load_config(_write(tmp_path, '[zcrypto.data]\nhot_root = "x"\n'))


def test_data_config_rejects_bad_types(tmp_path):
    with pytest.raises(ConfigError):
        load_config(_write(tmp_path, '[zcrypto.data]\nauthored_sets = "ohlc-full"\n'))
    with pytest.raises(ConfigError):
        load_config(_write(tmp_path, '[zcrypto.data]\nhot_dir = ""\n'))


def test_resolve_hot_dir_flag_beats_config_and_errors_when_absent(tmp_path):
    cfg = load_config(_write(tmp_path, '[zcrypto.data]\nhot_dir = "cfg_hot"\n'))
    assert resolve_hot_dir(Path("flag_hot"), cfg) == Path("flag_hot")
    assert resolve_hot_dir(None, cfg) == Path("cfg_hot")
    empty = load_config(_write(tmp_path, "[zcrypto]\n"))
    with pytest.raises(ConfigError):
        resolve_hot_dir(None, empty)
```

Extend the test file's `from cli.config import (...)` with `DataConfig, resolve_hot_dir` (and `resolve_push_dest` if you add a direct test for it — do: unset raises, set returns). Update the two bare `AppConfig(...)` constructions (post-Task-1 lines ~203/211) to pass `data=DataConfig()`.

- [ ] **Step 2: Run to verify failure.** `uv run pytest tests/test_config.py -k data -v` — ImportError.
- [ ] **Step 3: Implement** per the Interfaces block: dataclass after `EngineConfig`; `_build_data` after `_build_engine`; `data=_build_data(table, config_path)` in both `load_config` returns; the two resolvers beside the existing ones. In `zcrypto.toml` add (documented, workstation values):

```toml
# The hot-cluster exchange (spec 00056): fetch source (NFS read path), push destination
# (ssh alias pinned by the NAS rrsync forced command -- NEVER the rw NFS mount), authored sets.
[zcrypto.data]
hot_dir = "../zcrypto-kraken-data/hot"
push_dest = "nas-hot:"
authored_sets = ["ohlc-full", "ohlc-15m", "ohlc-holdout-2026-07-10", "derivatives-funding", "snapshots", "universe"]
```

- [ ] **Step 4: Verify.** `uv run pytest tests/test_config.py -q` all green.
- [ ] **Step 5: Commit.** `feat(config): [zcrypto.data] table — hot_dir, push_dest, authored_sets (spec 00056 D3)`

______________________________________________________________________

### Task 3: `cli/data` — sync library + `zcrypto data fetch` / `push`

**Files:**

- Create: `cli/data/__init__.py`, `cli/data/errors.py`, `cli/data/sync.py`, `cli/data/command.py`
- Modify: `cli/__main__.py` (register `data_app`)
- Test: `tests/test_data_sync.py`, `tests/test_data_command.py`

**Interfaces:**

- Consumes: `DataConfig`/`resolve_hot_dir`/`resolve_push_dest` (Task 2); `cli.logging.get_logger`; `cli.ohlc.dataset.read_parquet`, `dataset_hash`.
- Produces:

```python
# cli/data/errors.py
class DataSyncError(Exception):
    """A hot-cluster sync step failed (rsync error, manifest mismatch, missing set)."""

# cli/data/sync.py
@dataclass(frozen=True)
class SyncReport:
    new_files: tuple[str, ...]   # relative paths rsync actually created
    skipped_existing: int        # files present on both sides (never transmitted)

def fetch_hot(hot_dir: Path, data_root: Path, *, verify: bool = True, runner=subprocess.run) -> SyncReport
def push_hot(data_root: Path, authored_sets: Sequence[str], dest: str, *, runner=subprocess.run) -> SyncReport
```

Mechanics: both build `["rsync", "--archive", "--ignore-existing", "--itemize-changes", "--out-format=%i %n", src, dst]` — no `--delete` anywhere, enforced by construction. `fetch_hot` runs one rsync `hot_dir/` → `data_root/`; missing/unmountable `hot_dir` → `DataSyncError` (fail loud, never silently no-op). `push_hot` runs one rsync **per authored set** `data_root/<set>/` → `dest + <set>/` (a set dir missing locally → `DataSyncError` naming it, before any transfer). New files are parsed from the itemized output (lines whose itemize flags start with `>f+` or `cd+`); `skipped_existing` = files present in src but not itemized as created (compute by walking src and subtracting). Non-zero rsync exit → `DataSyncError` with stderr. `verify=True` on fetch: for each set dir that received new files and has a `manifest.json` with a `series` list carrying `sha256` entries, recompute `dataset_hash(read_parquet(file))` for each **newly fetched** parquet the manifest names; mismatch → `DataSyncError`; files the manifest doesn't name → log a WARNING, never fail (liquidations/panel-style trees are custody-side and never fetched here, but future authored sets may carry different manifest shapes).

- [ ] **Step 1: Write the failing sync tests** (`tests/test_data_sync.py`; real `rsync` against `tmp_path` dirs — local-to-local paths exercise the exact flag semantics):

```python
import subprocess
from pathlib import Path

import pytest

from cli.data.errors import DataSyncError
from cli.data.sync import fetch_hot, push_hot


def _mk(root: Path, rel: str, content: bytes) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(content)
    return p


def test_fetch_is_additive_and_idempotent(tmp_path):
    hot, data = tmp_path / "hot", tmp_path / "data"
    _mk(hot, "ohlc-full/BTC/EUR/1440.parquet", b"remote")
    r1 = fetch_hot(hot, data, verify=False)
    assert r1.new_files == ("ohlc-full/BTC/EUR/1440.parquet",)
    r2 = fetch_hot(hot, data, verify=False)
    assert r2.new_files == () and r2.skipped_existing == 1


def test_fetch_never_overwrites_a_changed_file(tmp_path):
    # The D1c contract: a content-changed remote file is structurally untransmittable.
    hot, data = tmp_path / "hot", tmp_path / "data"
    _mk(hot, "ohlc-full/x.parquet", b"remote-v2")
    local = _mk(data, "ohlc-full/x.parquet", b"local-v1")
    fetch_hot(hot, data, verify=False)
    assert local.read_bytes() == b"local-v1"


def test_fetch_missing_hot_dir_raises(tmp_path):
    with pytest.raises(DataSyncError, match="hot"):
        fetch_hot(tmp_path / "absent", tmp_path / "data", verify=False)


def test_push_only_allowlisted_sets_and_additive(tmp_path):
    data, dest = tmp_path / "data", tmp_path / "dest"
    _mk(data, "ohlc-full/a.parquet", b"A")
    _mk(data, "engine-store/secret.parquet", b"NO")
    dest.mkdir()
    push_hot(data, ["ohlc-full"], str(dest) + "/")
    assert (dest / "ohlc-full/a.parquet").read_bytes() == b"A"
    assert not (dest / "engine-store").exists()


def test_push_refuses_missing_authored_set(tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "dest").mkdir()
    with pytest.raises(DataSyncError, match="universe"):
        push_hot(tmp_path / "data", ["universe"], str(tmp_path / "dest") + "/")


def test_push_never_overwrites_dest(tmp_path):
    data, dest = tmp_path / "data", tmp_path / "dest"
    _mk(data, "snapshots/s.json", b"local-new")
    kept = _mk(dest, "snapshots/s.json", b"dest-old")
    push_hot(data, ["snapshots"], str(dest) + "/")
    assert kept.read_bytes() == b"dest-old"
```

Plus the verify pair — the matching rule is **path-keyed and only path-keyed**: a manifest `series` entry with a `path` (relative to its set dir) is verified when that file was newly fetched; entries without `path` are logged as a WARNING and skipped:

```python
def test_fetch_verifies_manifest_and_fails_on_corruption(tmp_path):
    import json

    import polars as pl

    from cli.ohlc.dataset import dataset_hash

    hot, data = tmp_path / "hot", tmp_path / "data"
    f = hot / "ohlc-test/BTC/EUR/1440.parquet"
    f.parent.mkdir(parents=True)
    good = pl.DataFrame({"ts": [1, 2], "close": [1.0, 2.0]})
    good.write_parquet(f)
    manifest = {"series": [{"path": "BTC/EUR/1440.parquet", "sha256": dataset_hash(good)}]}
    (hot / "ohlc-test/manifest.json").write_text(json.dumps(manifest))
    r = fetch_hot(hot, data)  # verify=True is the default
    assert "ohlc-test/BTC/EUR/1440.parquet" in r.new_files

    bad = hot / "ohlc-bad/x.parquet"
    bad.parent.mkdir(parents=True)
    pl.DataFrame({"ts": [9]}).write_parquet(bad)
    (hot / "ohlc-bad/manifest.json").write_text(json.dumps({"series": [{"path": "x.parquet", "sha256": "0" * 64}]}))
    with pytest.raises(DataSyncError, match="manifest"):
        fetch_hot(hot, data)
```

(`dataset_hash` hashes any frame's canonical CSV bytes — no OHLC schema required, so plain frames keep the test hermetic.)

- [ ] **Step 2: Run to verify failure.** `uv run pytest tests/test_data_sync.py -v` — ImportError.
- [ ] **Step 3: Implement `cli/data/sync.py` + `errors.py`** per Interfaces. Loggers `get_logger("data.sync")`.
- [ ] **Step 4: Command layer + registration.** `cli/data/command.py`: `data_app = typer.Typer(help="Hot-cluster dataset exchange: fetch the shared working set, push what this node authored, rebuild frozen sets.")` — **spec D10 binds every help string and command docstring in this package: no iter-N / spec-serial / OPS-N / phase-N / T-NNNN tracker ids in user-facing help; put such references in code comments only.** `@data_app.command() fetch(hot_dir: Optional[Path] --hot-dir, no_verify: bool --no-verify)` and `push(hot_dir-independent; uses resolve_push_dest + cfg.data.authored_sets)`; each loads config, resolves, calls the library, logs a one-line summary (`data fetch: new=%d skipped=%d` / `data push: ...`), exits non-zero on `DataSyncError` (log via `get_logger("data.command").error`, `raise typer.Exit(1)`). In `cli/__main__.py`: `from cli.data.command import data_app` (alphabetical between capture and engine imports) + `app.add_typer(data_app, name="data")` after the `archive` line.
- [ ] **Step 5: Command tests** (`tests/test_data_command.py`, `CliRunner` + `monkeypatch.chdir(tmp_path)` with a written `zcrypto.toml` pointing hot_dir/push_dest at tmp dirs): `zcrypto data fetch` happy path prints/logs the summary and exits 0; missing hot_dir exits 1; `data push` respects the allowlist. Follow `tests/test_liquidations_coinalyze.py`'s CliRunner idiom (`runner.invoke(app, ["data", "fetch"])`, assert `result.exit_code`).
- [ ] **Step 6: Verify.** `uv run pytest tests/test_data_sync.py tests/test_data_command.py -q` green; then the fast suite `uv run pytest -q` (data-dependent tests run on this workstation — expect the full ~7 min once; all green).
- [ ] **Step 7: Commit.** `feat(data): zcrypto data fetch/push — the hot-cluster exchange (spec 00056 D2/D3)`

______________________________________________________________________

### Task 4: `zcrypto data rebuild` + README Usage

**Files:**

- Create: `cli/data/rebuild.py`
- Modify: `cli/data/command.py`, `README.md`
- Test: `tests/test_data_rebuild.py`

**Interfaces:**

- Consumes: `resolve_ohlcvt_source_dir` (gains its first production consumer), `cli.backfill.backfill_basket`, `cli.backfill.substrate15m.build_15m_substrate`, `cli.derivatives.funding.build_funding_substrate`, `cli.snapshot` (`fetch_public`, `derive_universe`, `CANDIDATE_SYMBOLS`), `push_hot`.
- Produces:

```python
# cli/data/rebuild.py
REBUILDABLE: dict[str, Callable[[RebuildContext, Path], None]] = {
    "ohlc-full": _rebuild_ohlc_full,       # backfill_basket(source_dir, symbols, ["1440","240","60"], out_root, fetched_at)
    "ohlc-15m": _rebuild_ohlc_15m,         # build_15m_substrate(source_dir, symbols, out_root, fetched_at=...)
    "derivatives-funding": _refresh_funding,
    "snapshots": _refresh_snapshots,
    "universe": _refresh_universe,
}

def rebuild_sets(sets: Sequence[str], ctx: RebuildContext) -> list[Path]:
    """For each named set: mint the sibling dir data_root/f"{name}-{ctx.stamp}" (DataSyncError if it
    already exists or the name is unknown), call its builder with out_root=<sibling>, and return the
    minted dirs. NEVER writes into the live set dir — the sibling is the whole contract (spec D1c/D3)."""
```

`RebuildContext` (frozen dataclass): `data_root: Path`, `ohlcvt_source_dir: Path | None`, `stamp: str` (UTC `%Y%m%d`, injected — never computed inside the library, so tests pin it). The two dump-driven builders raise `DataSyncError` when `ohlcvt_source_dir` is None. **Builder wiring note for the implementer:** `backfill_basket` and `build_15m_substrate` signatures are verified above; for `build_funding_substrate` and the snapshot/universe writers, read the actual signatures in `cli/derivatives/funding.py:181` and `cli/snapshot/` first, wire with `out_root=<sibling>` semantics (the builders all take output-location arguments), and paste each actual signature into your report. If a builder writes files rather than taking a dir, wrap it minimally inside the `_refresh_*` — never modify the builder itself.

- [ ] **Step 1: Failing tests** (`tests/test_data_rebuild.py`) — stub the builders so tests are hermetic:

```python
def test_rebuild_mints_sibling_and_dispatches(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setitem(rebuild.REBUILDABLE, "ohlc-full", lambda ctx, out: calls.append(out) or (out / "ok").write_text("x"))
    ctx = rebuild.RebuildContext(data_root=tmp_path, ohlcvt_source_dir=tmp_path, stamp="20260718")
    minted = rebuild.rebuild_sets(["ohlc-full"], ctx)
    assert minted == [tmp_path / "ohlc-full-20260718"] == calls
    assert (tmp_path / "ohlc-full-20260718/ok").exists()


def test_rebuild_refuses_existing_sibling(tmp_path, monkeypatch):
    (tmp_path / "ohlc-full-20260718").mkdir()
    ctx = rebuild.RebuildContext(data_root=tmp_path, ohlcvt_source_dir=tmp_path, stamp="20260718")
    with pytest.raises(DataSyncError, match="already exists"):
        rebuild.rebuild_sets(["ohlc-full"], ctx)


def test_rebuild_never_touches_live_dir(tmp_path, monkeypatch):
    live = tmp_path / "ohlc-full"; live.mkdir(); (live / "keep.parquet").write_bytes(b"K")
    monkeypatch.setitem(rebuild.REBUILDABLE, "ohlc-full", lambda ctx, out: (out / "new").write_text("x"))
    rebuild.rebuild_sets(["ohlc-full"], rebuild.RebuildContext(tmp_path, tmp_path, "20260718"))
    assert sorted(p.name for p in live.iterdir()) == ["keep.parquet"]


def test_rebuild_unknown_set_raises(tmp_path):
    with pytest.raises(DataSyncError, match="unknown"):
        rebuild.rebuild_sets(["ohlc"], rebuild.RebuildContext(tmp_path, None, "20260718"))
```

- [ ] **Step 2: verify failure; Step 3: implement** `rebuild.py` + the `data rebuild [SETS...] --push/--no-push` command (default `--push` per spec D3). The minted sibling names are NOT in `authored_sets`, so `push_hot` gains a keyword extension `push_hot(data_root, authored_sets, dest, *, extra_sets=())` — `extra_sets` names are pushed exactly like authored ones. Test (add to `tests/test_data_sync.py`):

```python
def test_push_extra_sets_pushes_minted_siblings(tmp_path):
    data, dest = tmp_path / "data", tmp_path / "dest"
    _mk(data, "ohlc-full-20260718/a.parquet", b"A")
    dest.mkdir()
    push_hot(data, [], str(dest) + "/", extra_sets=["ohlc-full-20260718"])
    assert (dest / "ohlc-full-20260718/a.parquet").read_bytes() == b"A"
```

Command computes `stamp` from `datetime.now(UTC)` and passes it in.
- [ ] **Step 4: README Usage** — add the `data` group section after the `panel` section, matching the house style: fetch (mirror hot/ additively; verify manifests), push (authored allowlist, ssh channel, never the NFS mount), rebuild (sibling-minting re-freeze/refresh; workstation-owned by convention; `--no-push` for inspection), plus one paragraph on the custody/hot/private topology pointing at spec 00056. (README is docs — spec/topic references are fine THERE; D10 covers only `--help` output.)
- [ ] **Step 5: Help-hygiene sweep (spec D10).** Enumerate every existing offender: `grep -rnE "iter-[0-9]+|spec [0-9]{5}|OPS-[0-9]|phase[- ][0-9]|T[0-9]{4}" cli/ --include="*.py"` and, of the hits, fix ONLY those inside Typer `help=` strings or **command-function docstrings** (Typer renders those in `--help`; module docstrings and `#` comments are exempt — leave them). Known offenders to fix (current text verbatim in `cli/archive/command.py`): the `--min-gap-seconds` help ("validated cross-host (T0039, resolved 2026-07-17): 2.48x…") → `"Primary book silence longer than this, with the secondary alive inside it, is a gap. The default 30 s is validated from a 66h/217-window two-host soak: 2.48x the worst coalescing artifact, 2.8x below the smallest real outage on record."`; the `--mint` help → `"DEFAULT is --detect-only: ledger what WOULD be spliced and mint nothing. The deployed reconciler runs --mint; ad-hoc runs stay detect-only."`; the `reconcile` docstring's "(T0039, resolved 2026-07-17)" clause → drop the parenthetical, keep the figures. Rewrite any further hits the grep surfaces the same way: keep the substance, drop the tracker id; list every changed string in your report.
- [ ] **Step 6: The regression test** (`tests/test_cli_help_hygiene.py`) — walks the whole command tree so no future help string regresses:

```python
import re

import click
import typer
from typer.testing import CliRunner

from cli.__main__ import app

_INTERNAL = re.compile(r"iter-\d+|spec\s*`?\d{5}|OPS-\d|phase[- ]\d|T\d{4}", re.IGNORECASE)
runner = CliRunner()


def _all_paths():
    stack = [([], typer.main.get_command(app))]
    while stack:
        path, cmd = stack.pop()
        yield path
        if isinstance(cmd, click.Group):
            for name, sub in cmd.commands.items():
                stack.append(([*path, name], sub))


def test_no_internal_tracker_terms_in_any_help():
    offenders = []
    for path in _all_paths():
        result = runner.invoke(app, [*path, "--help"])
        assert result.exit_code == 0, path
        match = _INTERNAL.search(result.output)
        if match:
            offenders.append((path, match.group(0)))
    assert offenders == []
```

Run it BEFORE the Step-5 fixes to watch it fail on the known offenders (the TDD order: test first, then scrub until green — the failure list IS the sweep's checklist), then after the fixes: green. Mutation-check: temporarily re-add "T0039" to one help string, watch the test name it, revert.

- [ ] **Step 7: Verify** (`uv run pytest tests/test_data_rebuild.py tests/test_data_command.py tests/test_cli_help_hygiene.py -q`, then `uv run pre-commit run -a`).
- [ ] **Step 8: Commit.** `feat(data): zcrypto data rebuild + CLI help-hygiene sweep and regression test (spec 00056 D3/D10)`

______________________________________________________________________

### Task 5: Decisions-log continuity — git-tracked running files (spec D7)

**Files:**

- Modify: `.pre-commit-config.yaml`, `.claude/rules/decisions-log.md`, `.claude/skills/research-loop/SKILL.md`
- Create: `docs/research/decisions-running-phase1.md`, `-phase4.md`, `-phase5.md`, `-phase6.md` (migrated verbatim from `.tmp/`)
- Modify: the four `.tmp/decisions-phase<N>.md` (truncate to a pointer line)

**Ordering inside this task is load-bearing:** extend the mdformat exclusion FIRST, then create the files, then run the gate — otherwise mdformat rewrites the verbatim option lists on first commit.

- [ ] **Step 1: mdformat exclusion.** In `.pre-commit-config.yaml`, the mdformat `files:` verbose-regex line for docs/research (currently `docs/research/(?!.*-(cont-decisions-\d+|decisions)\.md$).*\.md`) becomes:

```
docs/research/(?!(.*-(cont-decisions-\d+|decisions)|decisions-running-phase\d+)\.md$).*\.md
```

and the comment above it gains: `# ...and the git-tracked running logs decisions-running-phase<N>.md (spec 00056 D7).` Prove it: `uv run python -c "import re; pat=re.compile(r'''<the full files regex, (?x) form>'''); assert not pat.match('docs/research/decisions-running-phase1.md'); assert pat.match('docs/research/99.some-report.md')"` (adapt to test the whole alternation verbatim from the file).

- [ ] **Step 2: Migrate.** For each N in 1,4,5,6: create `docs/research/decisions-running-phase<N>.md` opening with exactly two lines — `# Running decisions log — phase <N> (git-tracked since 2026-07-18, spec 00056 D7)` and a blank line — then the **verbatim** current content of `.tmp/decisions-phase<N>.md` (13/20/12/16 entries respectively; byte-verify with `diff <(tail -n +3 docs/research/decisions-running-phase<N>.md) .tmp/decisions-phase<N>.md`). Then truncate each `.tmp` file to the single line: `Migrated to docs/research/decisions-running-phase<N>.md (spec 00056 D7, 2026-07-18) — do not append here.`
- [ ] **Step 3: Rule edit.** `.claude/rules/decisions-log.md`: line 3's location becomes the git-tracked path; the *Phase persistence* section is rewritten: running files live at `docs/research/decisions-running-phase<N>.md`, **appended and committed as part of each iteration's closing commit** (the changelog's own mechanism; git is the cross-host baton, never-parallel precludes concurrent appends); close-out drain unchanged in semantics — copy verbatim into the serial-numbered file, truncate the running file, one commit (`mv` now allowed since both are tracked? NO — keep copy-then-truncate so the running file always exists for the next append; state that). Drop the "gitignored"/"must survive" phrasing accordingly; keep the fan-out, routing, and verbatim rules intact.
- [ ] **Step 4: Skill edit.** `.claude/skills/research-loop/SKILL.md`: update every `.tmp/decisions` reference (the log step, the phase-close-out constraint, the stop-note location) to the new running-file paths; the close-out constraint's "copy `.tmp/decisions.md` verbatim to ..." becomes the tracked-file drain.
- [ ] **Step 5: Verify + commit.** `uv run pre-commit run -a` (mdformat must NOT touch the four new files — check `git diff --name-only` after the run); `claude(config): decisions-log running files move into git — multi-host continuity (spec 00056 D7)`. (Type `claude` — this commit's substance is `.claude/` rules/skills; the docs/research files ride it.)

______________________________________________________________________

### Task 6: The catalog rewrite (spec D8)

**Files:**

- Modify: `docs/reference/data-catalog-full.md`, `docs/reference/data-catalog.md`

- [ ] **Step 1: Restructure `data-catalog-full.md`** into the D1 taxonomy. Required content (compose in the file's existing voice; every figure below is session-verified — do not invent new ones):
  - An intro paragraph defining the three clusters (custody / hot / private, one-liners from spec 00056 D1) and stating provenance is a per-set attribute, not the structure.
  - **hot** section: the existing frozen-basket table (unchanged figures) + new entries for `ohlc-15m` (producer `cli/backfill/substrate15m.py` iter-085, basket `0fed24a6…`, 12 pairs ~3.12M bars, consumer trials 45-46), `derivatives-funding` (producer `cli/derivatives/funding.py` iter-090, basket `e08ea1a9…`, staged for B2), `ohlc-holdout-2026-07-10` (the out-of-time holdout pull, manifest `4e251df2…`, look budget spent — see `13.phase5-holdout-ledger.md`), `snapshots` + `universe` (venue point-in-time snapshots + the derived universe). Note the append-only/sibling-minting contract and the `zcrypto data` exchange.
  - **custody** section: the existing "Live-accruing operational datasets" content with the **producer corrections**: canonical trades' producer line becomes the ops-node overlay writer (`zcrypto archive reconcile` + `backfill-trades`, spec `00054`, reading NAS custody over NFS per T0058; the NAS pulls the overlay back) — the "daily on the NAS beside the reconciler" claim is stale; the "OPS-6 migrates the research loop" sentence becomes the ratified replication model (both nodes hold the hot working set; NAS is the custody hub). Add the dumps (`kraken-ohlcvt-updates` 13G, `kraken-trades` 15G) as custody members read in place.
  - **private** section (new, three lines): `engine-store` (rebuildable, `engine seed`), `engine-journal` (per-host, unreproducible, VPS journal pulled to custody), never synced.
- [ ] **Step 2 (deliberately deferred):** the v0 `data-catalog.md` deletion note is **NOT written here** — the deletion happens in Task 8 (attended), and completed-work docs are authored when the work is real (`iterations-history.md` closeout discipline). Task 10 writes it.
- [ ] **Step 3: Verify + commit.** Facts cross-check against `docs/specs/00056-ops6-loop-design.md` + the registry/holdout serials named above; `uv run pre-commit run -a`; `docs(config): rewrite the dataset catalog by the custody/hot/private topology (spec 00056 D8)`

______________________________________________________________________

### Task 7 (ATTENDED, orchestrator-only): NAS `hot/` + the push channel + the ops outbox pull

**Files:** `infra/ansible/roles/nas/` (+ `host_vars/nas`), `infra/ansible/roles/ops/tasks/main.yml`, `infra/nas/` (vendored rrsync + pull-entrypoint extension), vault additions.

- [ ] **Step 1: Design the channel pieces on the branch (code-reviewable before any converge):**
  - Vendor OpenSSH's `rrsync` into `infra/nas/rrsync` (the NAS has no rrsync; it has rsync + python — T0056 facts).
  - NAS role: create `/volume1/ZhaoCrypto/hot` (owner zhaow, 0775); deploy `rrsync` to the NAS payload dir; add the **push key**'s public half to the NAS user's `authorized_keys` with forced command `<payload>/rrsync /volume1/ZhaoCrypto/hot` (write-capable, root pinned to hot/ — the whole point), `no-agent-forwarding,no-port-forwarding,no-pty,no-X11-forwarding`.
  - Ops role: create `/var/lib/zcrypto-ops/hot-out` (deploy-owned) — the ops outbox the existing D9 `rrsync -ro` export already covers (verify the export root includes it; if the forced command pins a narrower root, extend it read-only).
  - NAS pull side: extend the NAS's ops-pull (`infra/nas/pull-entrypoint.sh`) with an additive `rsync --archive --ignore-existing` of ops `hot-out/` → `/volume1/ZhaoCrypto/hot/` (same guard style as the existing PANEL/RECONCILED channels; optional-when-unset).
  - Keys: generate the ed25519 push keypair; private stays on the workstation (`~/.ssh/zcrypto-hot-push_ed25519` + a `Host nas-hot` ssh-config block using it); vault a backup copy beside the other deploy keys (`ansible-vault encrypt --output ... -` from stdin, never a plaintext file); public half into the role.
- [ ] **Step 2: Subagent review of the channel code, then commit** (`feat(infra): NAS hot/ hub — push channel, ops outbox, pull extension (spec 00056 D2/D4)`).
- [ ] **Step 3: Converge (attended):** `run.sh site.yml --limit nas --tags nas --check --diff` → review → converge; same for `--limit zcrypto-ops --tags ops` (re-render only — the ops role never restarts payloads on converge). Verify by outcome: `ssh nas-hot` refuses a shell but accepts rsync into hot/ (probe with a throwaway file, then remove it); the ops outbox exists; a NAS pull cycle logs the new channel as skipped-or-empty, not failed.

______________________________________________________________________

### Task 8 (ATTENDED, orchestrator-only): Seed, fetch, acceptance

- [ ] **Step 1: Seed.** On the workstation: `uv run zcrypto data push` → seeds all six authored sets (~281 MB) into `hot/`. Verify: NAS-side listing matches the local tree file-for-file; spot-verify two `sha256`s.
- [ ] **Step 2: Delete the dead sets.** Workstation: `rm -rf data/ohlc data/engine-journal-vps` (v0 dead — spec D4; the VPS-journal pull copy — spec D6; both verified consumer-free). Confirm the fast suite still passes.
- [ ] **Step 3: Ops acceptance.** On ops (repo checkout, `git pull`, `uv sync`): configure `[zcrypto.data] hot_dir = "/mnt/zhao-crypto/hot"` (ops pushes nothing — no `push_dest`, empty `authored_sets`); `uv run zcrypto data fetch`; then the **sharpest acceptance test**: `uv run pytest tests/test_crossfreq_system.py tests/test_portfolio_builder.py -q` — the data-dependent regression tests must **RUN (not skip) and pass on ops**. Record runtimes.
- [ ] **Step 4: Round-trip.** Push a tiny sibling-minted test set from the workstation, fetch it on ops byte-identical, verify manifest; attempt a content-changed re-push of the same file and confirm rsync transmits nothing (the D1c proof, live). Remove the test set from `hot/` (attended NAS-side `rm` — the one sanctioned deletion, it never entered any registry).

______________________________________________________________________

### Task 9 (ATTENDED, orchestrator-only): Retire the workstation payloads (spec D6)

- [ ] **Step 1:** `systemctl --user disable --now zcrypto-engine-gateops.timer zcrypto-engine-shadow.service`; remove the unit files README names + `~/.ssh/zcrypto-sync_ed25519`; `systemctl --user daemon-reload`. Verify: `systemctl --user list-units 'zcrypto*'` empty; no new writes to `data/engine-journal` after a full day boundary.
- [ ] **Step 2:** README truth-up: the gateops "retired" claim now carries the actual removal date; the shadow-soak section marked concluded (superseded by the VPS deployment, T0018). Commit `docs(config): workstation payloads actually retired (spec 00056 D6)` (fold into the branch; subagent review per the rules — attended execution, reviewed docs).

______________________________________________________________________

### Task 10: Closeout

- [ ] **Step 1:** [[T0033]] → `resolved` + archive + index sync (OPS-6 was its final increment; verify no live deferred sub-item remains in its next-steps — everything either landed here or lives in T0065/T0066). Also NOW write the v0 `data-catalog.md` deletion note deferred from Task 6 (the `rm` happened in Task 8): dated, spec 00056 D4, catalog retained as the iter-004 historical record.
- [ ] **Step 2:** Append the `iter-103` entry to `docs/iterations-history-phase1.md` (under the continuation divider if present): the topology (D1) + the exchange tool + seeding/acceptance evidence (ops regression-tests-pass figure from Task 8) + D7 continuity + the catalog rewrite + dead-config/payload removals — every figure from the executed tasks' reports.
- [ ] **Step 3:** Final whole-branch review (most capable model), `Reviewed-by:` trailers amended, push once, PR into `develop`: `feat(data): iter-103 — OPS-6 Loop: dataset topology + zcrypto data exchange (spec 00056)` with body per `pull-requests.md` (Follow-ups may reference only registered topics: T0065, T0066).
- [ ] **Step 4:** Commit `docs(config): closeout — T0033 resolved, changelog, catalog verified (spec 00056)`.

______________________________________________________________________

## Execution notes (orchestrator)

- Tasks 1→6 sequential (shared files: config.py in 1–2, command.py in 3–4). Tasks 7–9 are attended and interleave with the owner present; Task 10 last.
- Task 8's ops steps assume the ops checkout exists (the research-loop premise); creating it is part of Task 8 if absent (git clone + uv sync — record what was done).
- The `.tmp` migration (Task 5) must land before any future research iteration appends a decision — do not reorder Task 5 after 7–9 if a research iteration might run in between.
