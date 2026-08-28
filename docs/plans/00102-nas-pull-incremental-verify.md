# Spec 00102 — bound the NAS pull's verify cost: implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship spec `00102` — the NAS pull publishes its per-cycle verify cost as a per-channel gauge, and can hash only what rsync transferred plus a stateless 1/24 rotating slice, with the traversal (and therefore the pull-lag and prune semantics) left whole — closing [[T0028]] once the two attended converges have measured it.

**Architecture:** `_run_rsync` gains an output contract (rsync's `--out-format='%i %n'` parsed into the set of received `*.parquet` names). `verify_tree` gains a `hash_only` scope that skips `verify_manifest` for finals neither transferred nor in the cycle's slice (`--slice`), while walking every final exactly as today. The `pull` command gains `--hash-scope full|incremental` (default `full`), `--textfile` + `--channel` (one gauge file per channel), and its log line gains `hashed=` and `verify_s=` with `failed=` untouched. The NAS entrypoint passes all three per channel from an ansible-rendered `.env` whose committed source is one `host_vars` variable — so one image serves both deploy legs and the flip is a config-only converge.

**Tech Stack:** Python 3.14 via `uv`; typer; `hashlib`; rsync's itemize format; Prometheus textfile collector via the NAS's Alloy; pytest with `CliRunner`; `infra/scripts/mutate-probe.sh` for guard proofs.

## Global Constraints

- **`verify_tree`'s traversal is never narrowed** — only the call to `verify_manifest` is skipped. `newest_ts` (→ `pull_lag_seconds`) and `checked` derive from the walk — spec D1. A test pins that a zero-transfer, off-slice cycle still reports the tree's newest hour.
- The skip test is exactly: an itemize line whose flags begin `>f` and whose name ends `.parquet` — spec D2. Attribute-only touches (`.f...p.....`, this pull's `--chmod` on every run), directories, deletions and sidecars are not transfers.
- The slice is `int(sha256(<root-relative posix name>).hexdigest()[:8], 16) % 24`, hashed when equal to the `--slice` the caller passes — the NAS entrypoint's cycle counter modulo 24, **never the clock**: a clock-keyed slice starves fixed slices whenever the loop period divides 24 h — spec D3. `--slice` is required with `incremental`. The modulus carries spec `00062`'s `<= 24` assert.
- Metric names, exactly: `zcrypto_archive_pull_verify_seconds`, `zcrypto_archive_pull_files_hashed`, `zcrypto_archive_pull_files_walked`, each with one `channel` label — spec D4. One file per channel. HELP text carries no `T<NNNN>`/`spec`/`iter` tokens (`operator-facing-text.md`).
- The `pull complete ...` log line keeps ` failed=%d ` verbatim — spec D5; the dead-man rule matches `failed=0`.
- `--hash-scope` defaults to `full`; a pull invoked as today behaves as today — spec D7. `--textfile` and `--channel` are both optional and go together.
- **Never touch `cli/config.py` or `cli/__init__.py`** — they are inside the gate-export replay-fingerprint closure; `cli/archive/` is not, and that is what keeps both converges out of the cold replay.
- The keep-regex edit, the `NAS_REQUIRED` pin and the two dashboard panels land in ONE commit — spec D8; the suite fails on any subset.
- `README.md` `## Usage` documents the four new options in the same change — `readme-usage.md`.
- Every guard is proven on a fixture where defect and fix differ, and the suite keeps a true positive — `agent-ops.md`. `infra/scripts/mutate-probe.sh` refuses a dirty worktree, so every proof runs after its commit.
- No new `T<NNNN>` topics. Residuals go to [[T0028]]'s body.
- Model ceiling for implementers and task reviewers: **Opus**. **Fable** for the cold spec+plan review and the final whole-branch review — the NAS mirror is the durable copy of the unbackfillable capture path.
- Every commit carries `Co-Authored-By:` and, after its review, `Reviewed-by:` — `commit-messages.md`. Stage by explicit path.
- Branch: `feat/t0028-nas-pull-incremental-verify`, cut from `e2a6e2f9` on `deploy/rollout-eb6a503a`. It stays local until that rollout closes, then rebases onto `develop` and opens its PR there.

### The rsync itemize lines this plan parses, verbatim

| Meaning | `%i %n` line | transfer? |
| --- | --- | --- |
| new file received | `>f+++++++++ BTC/book/2026/07/12/03.parquet` | yes |
| existing file re-sent (size/time changed) | `>f.st...... BTC/book/2026/07/12/02.parquet` | yes |
| attribute-only touch (`--chmod`) | `.f...p..... BTC/book/2026/07/12/01.parquet` | no |
| directory created/touched | `cd+++++++++ BTC/book/2026/07/12/` | no |
| deletion (never passed here, parsed anyway) | `*deleting   BTC/book/2026/07/01/00.parquet` | no |
| a sidecar | `>f+++++++++ BTC/book/2026/07/12/03.parquet.sha256` | not a segment |

`%n` is the destination-relative name whether or not the source spec ends in `/` (rsync prefixes the basename otherwise, and the file lands under that same prefix), so `dest / name` is the file in both cases — the parser keeps names relative and `verify_tree` compares `p.relative_to(root).as_posix()`.

---

### Task 1: `_run_rsync` reports what it transferred

**Files:**
- Modify: `cli/archive/pull.py` (add `RsyncOutcome`, `transferred_parquets`)
- Modify: `cli/archive/command.py::_run_rsync`
- Test: `tests/test_archive_pull.py`

**Interfaces:**
- Produces: `RsyncOutcome(returncode: int, transferred: frozenset[str])` (frozen dataclass, `cli/archive/pull.py`); `transferred_parquets(itemized: str) -> frozenset[str]`; `_run_rsync(source, dest) -> RsyncOutcome`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_archive_pull.py` (extend the existing import: `from cli.archive.pull import RsyncOutcome, pull_lag_seconds, transferred_parquets, verify_tree`; add `import subprocess` and `from cli.archive import command`):

```python
def test_transferred_parquets_reads_only_received_segment_files() -> None:
    """The skip test is rsync's own itemization: a received regular file begins `>f`. Attribute-only
    touches (this pull's --chmod on every run), directories, deletions and sidecars are not transfers."""
    itemized = "\n".join(
        [
            ">f+++++++++ BTC/book/2026/07/12/03.parquet",
            ">f.st...... BTC/book/2026/07/12/02.parquet",
            ">f+++++++++ BTC/book/2026/07/12/03.parquet.sha256",
            ".f...p..... BTC/book/2026/07/12/01.parquet",
            "cd+++++++++ BTC/book/2026/07/12/",
            "*deleting   BTC/book/2026/07/01/00.parquet",
            ">f+++++++++ BTC/book/2026/07/12/03.part0001.parquet",
        ]
    )
    assert transferred_parquets(itemized) == frozenset(
        {
            "BTC/book/2026/07/12/03.parquet",
            "BTC/book/2026/07/12/02.parquet",
            "BTC/book/2026/07/12/03.part0001.parquet",  # verify_tree skips parts itself; the parser stays dumb
        }
    )
    assert transferred_parquets("") == frozenset()


def test_run_rsync_itemizes_and_returns_the_transfers(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ARCHIVE_SSH_KEY", "/keys/k")
    seen: dict = {}

    def fake_run(argv, **kwargs):
        seen["argv"], seen["kwargs"] = argv, kwargs
        return subprocess.CompletedProcess(argv, 0, stdout=">f+++++++++ BTC/book/2026/07/12/03.parquet\n")

    monkeypatch.setattr(command.subprocess, "run", fake_run)
    assert command._run_rsync("h:/src/", tmp_path) == RsyncOutcome(0, frozenset({"BTC/book/2026/07/12/03.parquet"}))
    assert "--out-format=%i %n" in seen["argv"]
    assert seen["kwargs"]["stdout"] is subprocess.PIPE and seen["kwargs"]["text"] is True


def test_run_rsync_without_a_key_is_a_transport_failure_with_no_transfers(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("ARCHIVE_SSH_KEY", raising=False)
    assert command._run_rsync("h:/src/", tmp_path) == RsyncOutcome(2, frozenset())
```

Update the four existing stubs so the type matches: `lambda source, d: 0` → `lambda source, d: RsyncOutcome(0, frozenset())` in `test_pull_ok_exits_zero`, `test_pull_mismatch_exits_one`, `test_pull_no_verify_skips_verification`; `lambda source, d: 23` → `lambda source, d: RsyncOutcome(23, frozenset())` in `test_pull_transport_failure_exits_two`.

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/test_archive_pull.py -q`
Expected: FAIL — `ImportError: cannot import name 'RsyncOutcome'`.

- [ ] **Step 3: Implement**

In `cli/archive/pull.py`, after `VerifyResult`:

```python
@dataclass(frozen=True)
class RsyncOutcome:
    returncode: int
    transferred: frozenset[str]  # dest-relative names of the *.parquet files rsync received this run


def transferred_parquets(itemized: str) -> frozenset[str]:
    """The dest-relative `*.parquet` names in rsync's `--out-format='%i %n'` output.

    `%i` is the 11-character itemize string; a received regular file begins `>f` (`>f+++++++++` new,
    `>f.st......` re-sent). Nothing else is a transfer: `.f...p.....` is an attribute-only touch (this
    pull's --chmod, every run), `cd+++++++++` a directory, `*deleting` a deletion. Only `>f` files are
    worth a hash -- an unchanged file's bytes are the bytes the last hash already covered.
    """
    names: set[str] = set()
    for line in itemized.splitlines():
        flags, _, name = line.partition(" ")
        if flags.startswith(">f") and name.endswith(".parquet"):
            names.add(name)
    return frozenset(names)
```

In `cli/archive/command.py`: import `RsyncOutcome, transferred_parquets` from `cli.archive.pull`; change `_run_rsync`'s signature to `-> RsyncOutcome`, its no-key early return to `return RsyncOutcome(2, frozenset())`, and its tail to:

```python
    # --out-format lists every file rsync UPDATED (received, re-sent), one per line, and nothing else
    # -- so this is O(changed), never O(files), and it is the whole skip test for verify_tree's
    # incremental scope (spec 00102 D2). stderr stays attached: rsync's own errors keep reaching the
    # container log unchanged.
    argv = ["rsync", "-a", "--chmod=D0775,F0664", "--out-format=%i %n", "-e", ssh_command, source, str(dest)]
    proc = subprocess.run(argv, stdout=subprocess.PIPE, text=True)
    return RsyncOutcome(proc.returncode, transferred_parquets(proc.stdout))
```

In `pull()`, rename the local: `outcome = _run_rsync(source, dest)` / `if outcome.returncode != 0:` / log `outcome.returncode`. Nothing else in `pull()` changes in this task.

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/test_archive_pull.py tests/test_error_paths_are_logged.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add cli/archive/pull.py cli/archive/command.py tests/test_archive_pull.py
git commit -m "feat(archive): rsync reports which segments it transferred"
```

---

### Task 2: `verify_tree` narrows the hash, never the walk

**Files:**
- Modify: `cli/archive/pull.py` (`_ROTATION_SLICES`, `slice_of`, `verify_tree`, `VerifyResult.hashed`)
- Test: `tests/test_archive_pull.py`

**Interfaces:**
- Consumes: nothing new from Task 1 (the scope is passed by the caller in Task 3).
- Produces: `verify_tree(root, *, now, hash_only: frozenset[str] | None = None) -> VerifyResult`; `VerifyResult.hashed: int`; `slice_of(rel_name: str) -> int`; `_ROTATION_SLICES = 24`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_archive_pull.py` (extend the import with `_ROTATION_SLICES, slice_of`):

```python
def _rel(pair: str, kind: str, hour: str) -> str:
    return f"{pair}/{kind}/2026/07/12/{hour}.parquet"


NOW = datetime(2026, 7, 12, 5, tzinfo=UTC)


def _off_slice(*names: str) -> int:
    """A rotation index holding NONE of `names` -- so a "not hashed" assertion cannot go green because
    a fixture path happened to land in the slice under test."""
    taken = {slice_of(n) for n in names}
    return next(i for i in range(24) if i not in taken)


def test_every_rotation_slice_is_reachable_from_a_cycle_counter() -> None:
    assert _ROTATION_SLICES == 24
    assert {slice_of(f"x/y/2026/07/12/{i}.parquet") for i in range(2000)} == set(range(24))


def test_full_scope_hashes_every_final(tmp_path: Path) -> None:
    _seg(tmp_path, "BTC", "book", "00")
    _seg(tmp_path, "BTC", "book", "01")
    r = verify_tree(tmp_path, now=datetime(2026, 7, 12, 5, tzinfo=UTC))
    assert (r.checked, r.hashed, r.ok) == (2, 2, 2)


def test_incremental_scope_hashes_the_transfer_but_walks_the_whole_tree(tmp_path: Path) -> None:
    """The defect this guards: narrowing the WALK. Then `checked` would read 1 and `newest_ts` would be
    the transferred hour (01) instead of the tree's newest (03), and the pull-lag figure the entrypoint
    calls its dead-man signal would go blank on a quiet cycle (spec 00102 D1)."""
    for h in ("00", "01", "02", "03"):
        _seg(tmp_path, "BTC", "book", h)
    names = [_rel("BTC", "book", h) for h in ("00", "01", "02", "03")]
    r = verify_tree(tmp_path, now=NOW, hash_only=frozenset({_rel("BTC", "book", "01")}), rotation_slice=_off_slice(*names))
    assert (r.checked, r.hashed, r.ok, r.failed) == (4, 1, 1, ())
    assert r.newest_ts == datetime(2026, 7, 12, 3, tzinfo=UTC)
    assert r.verified == (str(tmp_path / "BTC/book/2026/07/12/01.parquet"),)


def test_the_rotation_slice_catches_a_corrupt_final_nothing_transferred(tmp_path: Path) -> None:
    """Both halves on one fixture: in its slice the corrupt final is hashed and fails; off-slice with
    nothing transferred, nothing is hashed, nothing fails, and the walk still reports the newest hour."""
    _seg(tmp_path, "BTC", "book", "00")
    _seg(tmp_path, "BTC", "book", "01", corrupt=True)
    bad = _rel("BTC", "book", "01")
    r = verify_tree(tmp_path, now=NOW, hash_only=frozenset(), rotation_slice=slice_of(bad))
    assert r.hashed >= 1 and r.failed == (str(tmp_path / "BTC/book/2026/07/12/01.parquet"),)
    r2 = verify_tree(tmp_path, now=NOW, hash_only=frozenset(), rotation_slice=_off_slice(_rel("BTC", "book", "00"), bad))
    assert (r2.hashed, r2.failed, r2.checked) == (0, (), 2)
    assert r2.newest_ts == datetime(2026, 7, 12, 1, tzinfo=UTC)


def test_a_narrowed_scope_without_a_slice_is_refused(tmp_path: Path) -> None:
    """An incremental pull with no slice is the narrowed hash with no safety net -- never a silent default."""
    _seg(tmp_path, "BTC", "book", "00")
    with pytest.raises(ValueError, match="rotation slice"):
        verify_tree(tmp_path, now=NOW, hash_only=frozenset())
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/test_archive_pull.py -q -k "rotation or scope"`
Expected: FAIL — `ImportError` on `slice_of`, then `TypeError: verify_tree() got an unexpected keyword argument 'hash_only'`.

- [ ] **Step 3: Implement**

In `cli/archive/pull.py` add `import hashlib`, then above `verify_tree`:

```python
# Spec 00102 D3. A final is re-hashed in the cycle whose rotation index equals its slice, so every
# final is re-hashed every 24 cycles with no state -- a pure function of the name and the CALLER'S
# counter, never the clock: the NAS loop's period is 3600 + work, so `now.hour` drifts every cycle
# and, when the period divides 24 h, fixed slices are never visited at all (measured in the spec).
# The assert is spec 00062's: a counter modulo 24 can only produce [0, 23], so a larger modulus would
# leave high slices permanently unreachable and their finals silently never re-hashed.
_ROTATION_SLICES = 24
assert _ROTATION_SLICES <= 24, "_ROTATION_SLICES > 24 would leave high slices unreachable from a counter modulo 24"


def slice_of(rel_name: str) -> int:
    """The re-verification slice of a final, in [0, _ROTATION_SLICES), from its root-relative posix name."""
    return int(hashlib.sha256(rel_name.encode()).hexdigest()[:8], 16) % _ROTATION_SLICES
```

Add `hashed: int = 0` to `VerifyResult` (after `verified`, defaulted — `command.py`'s reconcile path constructs one without it). Replace `verify_tree` with:

```python
def verify_tree(
    root: Path, *, now: datetime, hash_only: frozenset[str] | None = None, rotation_slice: int | None = None
) -> VerifyResult:
    """Walk every final under `root`; hash each against its sidecar, or only a subset.

    `hash_only=None` hashes every final -- the whole-archive sweep. A set of root-relative names hashes
    those plus the finals whose `slice_of` equals `rotation_slice` -- required with a set: the caller's
    cycle counter modulo 24, never the clock (spec 00102 D3) -- and STILL WALKS EVERY FINAL: `checked` and
    `newest_ts` -- and through it the pull-lag figure the NAS entrypoint reads as its dead-man signal --
    come from the walk, not the hash, so a cycle that transferred nothing keeps reporting freshness
    (spec 00102 D1). `verified` lists only the finals hashed AND ok, so under a narrowed scope
    `prune_stale_parts` reaches a final's parts on its arrival cycle (a transfer in a clean cycle is always hashed) or
    within 24 cycles (its slice), never later.
    """
    checked = ok = hashed = 0
    failed: list[str] = []
    verified: list[str] = []
    newest: datetime | None = None
    if hash_only is not None and rotation_slice is None:
        raise ValueError("a narrowed hash scope needs a rotation slice")
    for p in sorted(root.rglob("*.parquet")):
        if ".part" in p.name or ".held" in p.name:  # in-progress part / quarantined held-spill, no manifest
            continue
        checked += 1
        ts = _hour_ts(p)
        if ts is not None and (newest is None or ts > newest):
            newest = ts
        rel = p.relative_to(root).as_posix()
        if hash_only is not None and rel not in hash_only and slice_of(rel) != rotation_slice:
            continue
        hashed += 1
        try:
            is_ok = verify_manifest(p)
        except CaptureError, IndexError:
            failed.append(str(p))
        else:
            if is_ok:
                ok += 1
                verified.append(str(p))
            else:
                failed.append(str(p))
    return VerifyResult(
        checked=checked, ok=ok, failed=tuple(failed), newest_ts=newest, verified=tuple(verified), hashed=hashed
    )
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/test_archive_pull.py tests/test_archive_reconcile_command.py -q`
Expected: PASS (the reconcile command still constructs `VerifyResult` without `hashed`).

- [ ] **Step 5: Commit**

```bash
git add cli/archive/pull.py tests/test_archive_pull.py
git commit -m "feat(archive): verify_tree can narrow the hash to a scope, and never narrows the walk"
```

- [ ] **Step 6: Prove the guards bite (after the commit — the probe refuses a dirty tree)**

```bash
infra/scripts/mutate-probe.sh --file cli/archive/pull.py \
  --control 's/checked += 1/checked += 2/' \
  --mutation 's/ and slice_of(rel) != rotation_slice//' \
  -- uv run pytest tests/test_archive_pull.py -q -k "rotation_slice or incremental_scope"
infra/scripts/mutate-probe.sh --file cli/archive/pull.py \
  --control 's/checked += 1/checked += 2/' \
  --mutation 's/rel not in hash_only and/True and/' \
  -- uv run pytest tests/test_archive_pull.py -q -k "rotation_slice or incremental_scope"
```

Expected: control FAILS the probe (proving the harness), both mutations KILLED. The first drops the slice — the corrupt in-slice final goes unhashed; the second drops the transfer — the transferred final goes unhashed. Run `--collect-only` with the same `-k` first and confirm both tests are selected.

---

### Task 3: the `pull` command — scope, cost, and the gauge file

**Files:**
- Modify: `cli/archive/command.py::pull` (+ `_write_pull_textfile`, `HashScope`)
- Modify: `README.md` (`## Usage`, the `zcrypto archive pull` entry)
- Test: `tests/test_archive_pull.py`

**Interfaces:**
- Consumes: `RsyncOutcome.transferred` (Task 1), `verify_tree(..., hash_only=)` and `VerifyResult.hashed` (Task 2).
- Produces: `zcrypto archive pull [--hash-scope full|incremental --slice 0-23] [--textfile PATH --channel NAME] SOURCE DEST`; the log line `pull complete source=%s checked=%d hashed=%d ok=%d failed=%d verify_s=%.1f lag_s=%s pruned_parts=%d pruned_hours=%d`; the textfile shape below.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_archive_pull.py` (add `import re`):

```python
def _pull(args: list[str], monkeypatch, *, transferred: frozenset[str] = frozenset(), now: datetime, lines: list[str]):
    monkeypatch.setattr(command, "_run_rsync", lambda source, d: RsyncOutcome(0, transferred))
    monkeypatch.setattr(command, "_utc_now", lambda: now)
    monkeypatch.setattr(command.logger, "info", lambda msg, *a: lines.append(msg % a))
    return CliRunner().invoke(app, ["archive", "pull", "src", *args])


def test_pull_default_scope_is_full_and_the_line_keeps_the_dead_mans_token(tmp_path: Path, monkeypatch) -> None:
    """`failed=0` is what `NAS · archive-pull stalled (dead-man)` matches -- the rule lives in Grafana, so
    the suite carries the claim. `hashed == checked` with nothing transferred proves the default is full."""
    _seg(tmp_path, "BTC", "book", "00")
    _seg(tmp_path, "BTC", "book", "01")
    lines: list[str] = []
    r = _pull([str(tmp_path)], monkeypatch, now=NOW, lines=lines)
    assert r.exit_code == 0, r.output
    line = next(m for m in lines if m.startswith("pull complete"))
    assert " checked=2 hashed=2 ok=2 failed=0 verify_s=" in line


def test_pull_textfile_publishes_three_gauges_labelled_by_channel(tmp_path: Path, monkeypatch) -> None:
    dest = tmp_path / "dest"
    _seg(dest, "BTC", "book", "00")
    _seg(dest, "BTC", "book", "01")
    prom = tmp_path / "textfile" / "archive-pull-capture.prom"
    prom.parent.mkdir()
    off = str(_off_slice(_rel("BTC", "book", "00"), _rel("BTC", "book", "01")))
    r = _pull(
        [str(dest), "--hash-scope", "incremental", "--slice", off, "--textfile", str(prom), "--channel", "capture"],
        monkeypatch, transferred=frozenset({_rel("BTC", "book", "01")}), now=NOW, lines=[],
    )
    assert r.exit_code == 0, r.output
    body = prom.read_text()
    assert 'zcrypto_archive_pull_files_walked{channel="capture"} 2\n' in body
    assert 'zcrypto_archive_pull_files_hashed{channel="capture"} 1\n' in body
    assert re.search(r'^zcrypto_archive_pull_verify_seconds\{channel="capture"\} \d+\.\d+$', body, re.M)
    assert body.count("# HELP zcrypto_archive_pull_") == 3
    assert not prom.with_name(prom.name + ".tmp").exists()


def test_pull_publishes_the_cost_even_when_a_hash_fails(tmp_path: Path, monkeypatch) -> None:
    dest = tmp_path / "dest"
    _seg(dest, "BTC", "book", "00", corrupt=True)
    prom = tmp_path / "p.prom"
    r = _pull([str(dest), "--textfile", str(prom), "--channel", "capture"], monkeypatch,
              now=datetime(2026, 7, 12, 0, tzinfo=UTC), lines=[])
    assert r.exit_code == 1
    assert 'zcrypto_archive_pull_files_hashed{channel="capture"} 1\n' in prom.read_text()


def test_pull_textfile_without_channel_is_a_usage_error(tmp_path: Path, monkeypatch) -> None:
    r = _pull([str(tmp_path), "--textfile", str(tmp_path / "p.prom")], monkeypatch,
              now=datetime(2026, 7, 12, 0, tzinfo=UTC), lines=[])
    assert r.exit_code == 2 and "--channel" in r.output


def test_pull_incremental_without_slice_is_a_usage_error(tmp_path: Path, monkeypatch) -> None:
    r = _pull([str(tmp_path), "--hash-scope", "incremental"], monkeypatch, now=NOW, lines=[])
    assert r.exit_code == 2 and "--slice" in r.output


def test_pull_without_textfile_writes_no_prom_file(tmp_path: Path, monkeypatch) -> None:
    _seg(tmp_path, "BTC", "book", "00")
    r = _pull([str(tmp_path)], monkeypatch, now=datetime(2026, 7, 12, 0, tzinfo=UTC), lines=[])
    assert r.exit_code == 0 and list(tmp_path.rglob("*.prom")) == []
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/test_archive_pull.py -q -k "pull_"`
Expected: FAIL — `No such option: --hash-scope` / `--slice`, and the default-scope test fails on the missing `hashed=` token.

- [ ] **Step 3: Implement**

In `cli/archive/command.py`, add `from enum import Enum` and above `pull`:

```python
class HashScope(str, Enum):
    full = "full"
    incremental = "incremental"


def _write_pull_textfile(path: Path, *, channel: str, result: VerifyResult, verify_seconds: float) -> None:
    """This run's verify cost as textfile-collector gauges, one FILE per channel (spec 00102 D4): five
    pulls share the collector directory on the NAS, and a shared file would carry whichever ran last.
    tmp + os.replace, the gate export's idiom, so a scrape never reads a partial file. `files_walked` is
    `checked` -- the denominator that makes `files_hashed` readable, and the series that grows."""
    label = f'{{channel="{channel}"}}'
    lines = [
        "# HELP zcrypto_archive_pull_verify_seconds wall time spent hashing pulled segments against their sidecars this cycle",
        f"zcrypto_archive_pull_verify_seconds{label} {verify_seconds:.3f}",
        "# HELP zcrypto_archive_pull_files_hashed segments whose bytes were re-hashed this cycle",
        f"zcrypto_archive_pull_files_hashed{label} {result.hashed}",
        "# HELP zcrypto_archive_pull_files_walked segments present in the destination tree this cycle",
        f"zcrypto_archive_pull_files_walked{label} {result.checked}",
    ]
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text("\n".join(lines) + "\n")
    os.replace(tmp_path, path)
```

Extend `pull`'s signature (after `verify`):

```python
    hash_scope: HashScope = typer.Option(
        HashScope.full,
        "--hash-scope",
        help="full: re-hash every segment under DEST. incremental: hash only the segments rsync transferred "
        "this run plus the rotating 1/24 slice named by --slice, so every segment is still re-hashed every 24 cycles.",
    ),
    textfile: Optional[Path] = typer.Option(
        None, "--textfile", help="Write this run's verify cost as Prometheus textfile-collector gauges here. Needs --channel."
    ),
    channel: Optional[str] = typer.Option(None, "--channel", help="The `channel` label on the --textfile gauges, e.g. capture."),
    slice_: Optional[int] = typer.Option(
        None, "--slice", min=0, max=23,
        help="The rotation index for --hash-scope incremental: the caller's cycle counter modulo 24. Required with incremental.",
    ),
```

and its body, from the rsync call on:

```python
    if (textfile is None) != (channel is None):
        raise typer.BadParameter("--textfile and --channel go together")
    if hash_scope is HashScope.incremental and slice_ is None:
        raise typer.BadParameter("--hash-scope incremental needs --slice")
    outcome = _run_rsync(source, dest)
    if outcome.returncode != 0:
        logger.error("archive pull: rsync failed source=%s dest=%s returncode=%s", source, dest, outcome.returncode)
        raise typer.Exit(2)

    if not verify:
        logger.info("archive pull complete (no verify) source=%s dest=%s", source, dest)
        return

    hash_only = outcome.transferred if hash_scope is HashScope.incremental else None
    started = time.monotonic()
    result = verify_tree(dest, now=_utc_now(), hash_only=hash_only, rotation_slice=slice_)
    verify_seconds = time.monotonic() - started
    lag_s = pull_lag_seconds(result, now=_utc_now())
    # (existing T0038 prune comment stays)
    pruned_hours, pruned_parts = prune_stale_parts(result.verified)
    # `failed=%d` keeps its spelling and its place: `NAS · archive-pull stalled (dead-man)` matches
    # `failed=0` on this line (spec 00102 D5). The cost fields are here as well as in the textfile
    # because this line is the only record when the process is killed before it can publish.
    logger.info(
        "pull complete source=%s checked=%d hashed=%d ok=%d failed=%d verify_s=%.1f lag_s=%s pruned_parts=%d pruned_hours=%d",
        source, result.checked, result.hashed, result.ok, len(result.failed), verify_seconds, lag_s, pruned_parts, pruned_hours,
    )
    if textfile is not None:
        _write_pull_textfile(textfile, channel=channel, result=result, verify_seconds=verify_seconds)
    if result.failed:
        for path in result.failed:
            logger.error("archive pull: verify failed path=%s", path)
        raise typer.Exit(1)
```

Update the docstring's first sentence to mention the scope. In `README.md` `## Usage`, extend the `zcrypto archive pull` entry with the four options and one sentence each, matching the surrounding entries' style.

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/test_archive_pull.py tests/test_internal_terms_not_operator_visible.py tests/test_dashboards_cover_metrics.py -q`
Expected: `test_archive_pull.py` and the internal-terms guard PASS; **`test_every_published_app_family_is_charted` FAILS** on the three new families — expected, Task 4 charts them. Do not silence it.

- [ ] **Step 5: Commit**

```bash
git add cli/archive/command.py tests/test_archive_pull.py README.md
git commit -m "feat(archive): the pull takes a hash scope and publishes its verify cost per channel"
```

---

### Task 4: the operating surfaces — entrypoint, env, keep-regex, dashboard

**Files:**
- Modify: `infra/nas/pull-entrypoint.sh` (five `zcrypto archive pull` call sites)
- Modify: `infra/nas/compose.yaml` (archive-pull `environment`)
- Modify: `infra/ansible/roles/nas/templates/env.j2`, `infra/ansible/host_vars/nas/vars.yml`
- Modify: `infra/nas/config.alloy` (keep regex)
- Modify: `infra/grafana/data-integrity-dashboard.json` (two panels)
- Test: `tests/test_infra_alloy_series.py` (`NAS_REQUIRED`), `tests/test_dashboards_cover_metrics.py` (derives; must pass)

**Interfaces:**
- Consumes: the CLI options from Task 3.
- Produces: `ARCHIVE_PULL_HASH_SCOPE` (container env, default `full`), committed as `nas_archive_pull_hash_scope` in `host_vars/nas/vars.yml`; textfiles `/textfile/archive-pull-<channel>.prom` for `capture`, `capture_red`, `liquidations`, `panel`, `reconciled`.

- [ ] **Step 1: Pin the keep-regex (failing test first)**

In `tests/test_infra_alloy_series.py`, add `"zcrypto_archive_pull_files_walked",` to `NAS_REQUIRED` after `"zcrypto_gate_streak_days",`.

Run: `uv run pytest tests/test_infra_alloy_series.py -q`
Expected: FAIL — the NAS keep regex does not admit it.

- [ ] **Step 2: Admit the family**

In `infra/nas/config.alloy`, in the single `action = "keep"` block's `regex`, append `|zcrypto_archive_pull_.*|node_textfile_mtime_seconds` immediately after `zcrypto_trade_backfill_.*` — the second is the collector's per-file mtime, the series spec D4 names as the stale-file reader; it is not admitted today. Add one comment line above the block: `// zcrypto_archive_pull_*: the pull's per-channel verify cost (spec 00102) -- written by the archive-pull container into the same textfile dir as gate.prom.`

Run: `uv run pytest tests/test_infra_alloy_series.py -q` — PASS.

- [ ] **Step 3: Chart the family**

In `infra/grafana/data-integrity-dashboard.json`, add two `timeseries` panels, cloning the JSON shape (datasource, `fieldConfig`, `gridPos` width, `id` annotation convention) of the existing panel whose `expr` contains `zcrypto_gate_export_duration_seconds`; place them in the same row area, new `id`s one above the file's highest:

- title `NAS pull · verify seconds per channel`; one target `expr: zcrypto_archive_pull_verify_seconds{host="nas"}`, `legendFormat: {{channel}}`, unit `s`.
- title `NAS pull · segments hashed vs walked`; two targets: `sum(zcrypto_archive_pull_files_hashed{host="nas"})` legend `hashed`, and `sum(zcrypto_archive_pull_files_walked{host="nas"})` legend `walked`.

Run: `uv run pytest tests/test_dashboards_cover_metrics.py -q`
Expected: PASS — every published family charted, panel ids well-formed.

- [ ] **Step 4: Wire the entrypoint and its env**

`infra/nas/pull-entrypoint.sh` — declare `cycle=0` immediately before `while true; do`, and make `cycle=$((cycle + 1))` the loop's first statement (the rotation index, spec D3 — a counter, never the clock). Each of the five verified pulls gains the same four options; the capture one becomes:

```sh
	# Spec 00102: the verify cost is published per channel (one .prom each -- five pulls share
	# /textfile), and ARCHIVE_PULL_HASH_SCOPE decides whether every segment is re-hashed (full) or
	# only rsync's transfers plus a 1/24 slice keyed on this loop's cycle counter (incremental). The value is rendered into
	# .env from nas_archive_pull_hash_scope, so flipping it is a config-only converge on the running
	# image -- and the rollback is the same flip.
	if ! ARCHIVE_SSH_KEY="$CAPTURE_SSH_KEY" zcrypto archive pull \
			--hash-scope "${ARCHIVE_PULL_HASH_SCOPE:-full}" --slice $((cycle % 24)) \
			--textfile /textfile/archive-pull-capture.prom --channel capture \
			"$CAPTURE_SOURCE" "$CAPTURE_DEST"; then
```

Likewise `capture_red` (the `CAPTURE_RED_*` block), `liquidations`, `panel`, `reconciled` — the `--textfile` basename and `--channel` value use the channel's name; the journal (`--no-verify`) and hot (raw rsync) blocks are untouched.

`infra/nas/compose.yaml` — in the archive-pull service's `environment`, beside `GATE_TEXTFILE`: `ARCHIVE_PULL_HASH_SCOPE: ${ARCHIVE_PULL_HASH_SCOPE:-full}`.

`infra/ansible/roles/nas/templates/env.j2` — append `ARCHIVE_PULL_HASH_SCOPE={{ nas_archive_pull_hash_scope }}`.

`infra/nas/README.md` — its Env-var contract table states that every rendered `.env` row is listed there: add the `ARCHIVE_PULL_HASH_SCOPE` row (meaning: `full` re-hashes every segment each cycle, `incremental` hashes rsync's transfers plus the cycle-keyed 1/24 slice; the `Set where` cell mirrors the `JOURNAL_SOURCE` row's form, naming `nas_archive_pull_hash_scope`).

`infra/ansible/roles/nas/tasks/main.yml` — immediately before the task that renders `env.j2`, a guard (spec Deploy sequence: a value the CLI rejects stops all five pulls with the exit code the ops gate books as a not-clean capture pull):

```yaml
- name: refuse an archive-pull hash scope the CLI would reject
  ansible.builtin.assert:
    that: nas_archive_pull_hash_scope in ['full', 'incremental']
    fail_msg: "nas_archive_pull_hash_scope must be full or incremental, got '{{ nas_archive_pull_hash_scope }}'"
```

and in `tests/test_infra_converge_guards.py`, using its existing `load_tasks` / `find_task` / `assert_that` / `truthy` helpers, the proof that it bites both ways:

```python
NAS = ANSIBLE / "roles" / "nas" / "tasks" / "main.yml"


# "" is refused as AMBIGUOUS, not as CLI-rejected: env.j2 renders it as an empty assignment and both
# compose and the entrypoint substitute `full` for it -- a committed empty value must say what it means.
@pytest.mark.parametrize("value, expected", [("full", True), ("incremental", True), ("bogus", False), ("", False)])
def test_nas_hash_scope_guard_refuses_what_the_cli_would(value, expected):
    task = find_task(load_tasks(NAS), "refuse an archive-pull hash scope the CLI would reject")
    assert all(truthy(c, {"nas_archive_pull_hash_scope": value}) for c in assert_that(task)) is expected
```

The `name:` and `fail_msg:` are operator-visible — no internal tokens.

`infra/ansible/host_vars/nas/vars.yml` — add, beside `nas_capture_image`:

```yaml
# Spec 00102 D7: `full` re-hashes every segment each cycle; `incremental` hashes rsync's transfers plus
# a rotating 1/24 slice. Flipping this is a config-only converge on the running digest (under
# -e nas_apply_compose=true), and so is the rollback. Leg A converges at `full` for the baseline; leg B
# flips it. The entrypoint that reads this needs an image that knows --hash-scope: it lands with that
# image pin in one applied converge, never render-only against an older image.
nas_archive_pull_hash_scope: full
```

- [ ] **Step 5: Run the reachable tests and the gate**

Run: `uv run pytest tests/test_error_paths_are_logged.py tests/test_infra_alloy_series.py tests/test_dashboards_cover_metrics.py tests/test_infra_compose_templates.py tests/test_infra_converge_guards.py tests/test_internal_terms_not_operator_visible.py -q && uv run pre-commit run -a`
Expected: PASS; gate clean (yamllint, ansible-lint cover the yaml/j2).

- [ ] **Step 6: Commit**

```bash
git add infra/nas/pull-entrypoint.sh infra/nas/compose.yaml infra/nas/README.md infra/ansible/roles/nas/templates/env.j2 \
  infra/ansible/host_vars/nas/vars.yml infra/ansible/roles/nas/tasks/main.yml infra/nas/config.alloy \
  infra/grafana/data-integrity-dashboard.json tests/test_infra_alloy_series.py tests/test_infra_converge_guards.py
git commit -m "feat(nas): the pull publishes its verify cost, and its hash scope is a deployed setting"
```

---

### Task 5: closeout in this PR — T0028 partial, the history entry

**Files:**
- Modify: `docs/open-topics/T0028-nas-pull-incremental-verify.md`, `docs/open-topics/README.md`
- Modify: `docs/iterations-history-phase1.md`

- [ ] **Step 1: T0028 → `partial`** (load `topic-ops`): flip `status: partial`; insert `## Done so far` after `## Findings so far`, naming spec `00102`, this branch's four `feat` commits, the three families, the `--hash-scope` default and where its NAS value lives; trim `## Suggested next steps` to the remainder — leg A (baseline at `full`), leg B (flip to `incremental`, measure the drop, resolve with the measured horizon). Move the index bullet from `### Open` to the end of `### Partially done` under Research and development; refresh its description to say the code landed and the two converges remain. Verify the heading set before and after.

- [ ] **Step 2: the history entry** (load `iteration-closeout`): append `## 2026-MM-DD — iter-<N>: spec 00102 — the NAS pull's verify cost, bounded and observable` to `docs/iterations-history-phase1.md` (Role A's home; iter-101 is there). If the file's tail already carries a `**Continuation — …**` divider after rebasing, append below it; otherwise add one. One bullet per: the itemized skip test; the walk-not-hash invariant and why; the slice; the three gauges and the per-channel file; the deployed setting and the two-leg sequence it enables; what is NOT yet true (no converge has run, no baseline exists). Name classes, not counts.

- [ ] **Step 3: Gate and commit**

```bash
uv run pre-commit run -a
git add docs/open-topics/T0028-nas-pull-incremental-verify.md docs/open-topics/README.md docs/iterations-history-phase1.md
git commit -m "docs(archive): T0028 partial -- the pull's cost is measurable and its hash narrowable, unmeasured until the converges"
```

Then the final whole-branch review at the **Fable** floor, trailers, and the branch waits — local — for the rollout to close, rebases onto `develop`, and opens its PR on the user's word.

---

### Task 6: Leg A — the baseline (ATTENDED, main loop, after the PR merges)

**Not a subagent task.** Every step here touches a host; the permission gate blocks ssh/sudo in a dispatched agent. Each irreversible step takes the user's word with the blocker sweep beside it (`agent-ops.md`). Skill: `fleet-deploys.md` § NAS converges.

- [ ] **Step 1:** After the PR merges into `develop`, take the `-compat` digest from `capture-image.yml`'s run. On the NAS: pull it, and prove `runtime=compat` by **running** polars in the pulled image (`docker run --rm --entrypoint python <image> -c 'import polars; print(polars.__version__)'`) — never by reading the label.
- [ ] **Step 2:** Re-pin `nas_capture_image` in `infra/ansible/host_vars/nas/vars.yml` (committed); `nas_archive_pull_hash_scope` stays `full`. Confirm the previous digest is still resident on the NAS (`docker image ls --digests`) — it is the rollback operand.
- [ ] **Step 3:** `infra/ansible/scripts/converge.sh site.yml --limit nas -e nas_apply_compose=true` — preview, then the user's typed confirm. **The apply flag is not optional**: without it the nas role renders files and restarts nothing, and Step 4 then reads the old image's silence. This pass lands the image pin AND the new entrypoint together — a render-only converge of this entrypoint against the old image is never run (the old image rejects `--hash-scope` with exit 2, which the ops gate books as a not-clean capture pull). `converge.sh` appends the machine line to `docs/reference/deploy-log.jsonl`.
- [ ] **Step 4:** Wait one full pull cycle (the entrypoint's `ARCHIVE_PULL_INTERVAL`, 3600 s, plus the cycle's own work). Then, by value:

```bash
uv run python infra/scripts/grafana-query.py \
  'zcrypto_archive_pull_verify_seconds{host="nas"}' \
  'zcrypto_archive_pull_files_hashed{host="nas"}' \
  'zcrypto_archive_pull_files_walked{host="nas"}'
```

Expected: five `channel` instances per family, `files_hashed == files_walked` on every channel (the scope is `full`). `(no series)` is FAIL — the keep regex or the Alloy restart did not take; do not proceed to leg B.

- [ ] **Step 5:** Re-true the NAS row in `docs/reference/fleet-pins.md` from the deploy-log line. The commit message carries every value read in Step 4, per channel, and the literal token `archive_pull baseline` — leg B's gate greps for it AND reads those values back.

---

### Task 7: Leg B — the cut (ATTENDED, main loop)

- [ ] **Step 1 — the gate:** on the rollout branch, `git log HEAD --grep='archive_pull baseline' --format=%h -- docs/reference/fleet-pins.md` must print a commit (it cannot be on `develop` yet — the rollout PR merges after this leg). Empty → leg A's baseline was never recorded on the pins row; stop. Then `git show -s <hash>` and copy A's per-channel `verify_seconds` / `files_hashed` / `files_walked` into this session — Step 4 compares against THOSE, not against memory.
- [ ] **Step 2:** Flip `nas_archive_pull_hash_scope: incremental` in `host_vars/nas/vars.yml` (committed). `nas_capture_image` unchanged.
- [ ] **Step 3:** `infra/ansible/scripts/converge.sh site.yml --limit nas -e nas_apply_compose=true` — config-only, the running digest; the apply flag is what recreates the container with the new `.env` value. Without it the file is rendered and the running container never re-reads it.
- [ ] **Step 4:** Wait one full pull cycle, run the same three-family query. Against the values copied in Step 1: `files_walked` unchanged from leg A within the hour's growth; `files_hashed` ≈ transfers + `files_walked / 24`; `verify_seconds` down by the same ratio. Quote every value.
- [ ] **Step 5:** Pins row re-trued; the commit message carries the before/after per channel. **Resolve [[T0028]]** (`topic-ops`: `status: resolved`, `## Resolution` with the measured drop and the measured horizon the new curve implies, `git mv` to `archive/`, index bullet to `### Resolved`). Then prune the NAS's superseded image — `uv run python infra/scripts/prune-host-images.py nas`, then `--apply` — after the row is written, never before.
- [ ] **Step 6 — rollback, if `files_hashed` did not drop or any channel's `failed` went non-zero on a clean tree:** flip the variable back to `full` and converge again; no image changes hands. Then stop and report — a rollback is a finding, not a retry license.
