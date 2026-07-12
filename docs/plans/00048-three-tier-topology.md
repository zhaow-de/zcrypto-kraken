# Three-tier topology — Increment 1: Role A (always-on NAS pull + archive) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the always-on NAS pull/archive tier (Role A of spec `00048`): a scheduled NAS container pulls the VPS capture segments + engine journal, hash-verifies each segment, and archives to `/volume1/ZhaoCrypto` — decoupling data durability from the intermittent workstation.

**Architecture:** A new `zcrypto archive` CLI group (runs on the NAS in the *same* `ghcr.io/zhaow-de/zcrypto-capture` x86 image) does `rsync`-over-`ssh` pulls against the VPS's read-only `rrsync` forced-command channels, then verifies each `*.parquet` against its `.sha256` sidecar (reusing `cli.capture.verify_manifest`) and reports pull-lag. A NAS compose stack runs it hourly under Container Manager's restart policy (no systemd, `--user 1000:1000`, `umask 0002`). The VPS side adds one new `rrsync -ro` channel for the capture segments (the engine-journal channel already exists) and moves the unattended-reboot window to 02:00 UTC.

**Tech Stack:** Python 3.14 + Typer (CLI), `rsync`/`ssh` (transport), `polars` (already a dep; not needed here beyond the existing verify helper), Ansible (VPS convergence), Synology Container Manager (NAS runtime).

## Global Constraints

- **Never disturb the running capture daemon** — the VPS capture container must not be restarted or interrupted (L2 gaps are unbackfillable). All VPS changes are additive (a new authorized_key channel, a defaults value) and converge without touching the `capture` container. Deploy is attended (Task 6).
- **Canonical data is immutable** — the pull is read-only from the VPS; the NAS never deletes on the VPS. Archived segments are written under `/volume1/ZhaoCrypto`; never overwrite a verified segment in place.
- **NAS runtime touches zero NAS-OS config** — everything runs in containers under Container Manager (`restart: unless-stopped`); no systemd units, no DSM Task Scheduler entries. Containers run `--user 1000:1000` with `umask 0002` so archived files are `0664`/`0775` group `zcrypto` (see `infra/nas/normalize-archive-perms.sh`).
- **Secrets** — the NAS→VPS pull uses vaulted ed25519 keys (the existing `sync` key for the journal; a **new** `sync_capture` key for the segments). No key material is printed or committed unencrypted; the NAS mounts the key file `0600`.
- **Reversible-first** — Tasks 1–5 are code/config on the branch (subagent-buildable, no production contact). Task 6 (deploy) is attended and is the only task that touches the live NAS/VPS.

______________________________________________________________________

## File Structure

- Create `cli/archive/__init__.py`, `cli/archive/command.py` — the `zcrypto archive` Typer group with the `pull` command (pull + verify + pull-lag).
- Create `cli/archive/pull.py` — the pull/verify core logic (rsync runner injection point, manifest verification sweep, pull-lag), kept separate from the Typer wiring so it is unit-testable without a CLI runner.
- Modify `cli/__main__.py` — register the `archive` sub-app.
- Create `tests/test_archive_pull.py` — unit tests for the verify sweep + pull-lag + mismatch handling, and a `CliRunner` smoke test.
- Create `infra/nas/compose.yaml` — the NAS pull container (image, `user: "1000:1000"`, `restart: unless-stopped`, mounts, env).
- Create `infra/nas/pull-entrypoint.sh` — the in-container scheduler loop (`umask 0002`; run `zcrypto archive pull …` for each source; sleep the interval; survive a failed pull).
- Create `infra/nas/README.md` — how to deploy/operate the NAS stack (build-less: it uses the published image), and the key-mount contract.
- Modify `infra/ansible/roles/capture/tasks/main.yml` (+ `defaults`/`vars` as needed) — add the read-only `rrsync` channel for `capture_data_dir` keyed by the new `sync_capture_authorized_key`.
- Modify `infra/ansible/group_vars/capture_host/vault.yml` — add `sync_capture_authorized_key` (public key; the private key is deployed to the NAS out-of-band). *(Vault edit is done at deploy time, Task 6 — not in the code tasks.)*
- Modify `infra/ansible/roles/base/defaults/main.yml` — `base_unattended_upgrades_reboot_time: "04:00"` → `"02:00"`.
- Append to `docs/iterations-history-phase6.md` — the closeout entry (Task 7).

______________________________________________________________________

## Task 1: `archive pull` core — manifest-verify sweep + pull-lag

**Files:**

- Create: `cli/archive/__init__.py`, `cli/archive/pull.py`
- Test: `tests/test_archive_pull.py`

**Interfaces:**

- Consumes: `cli.capture.verify_manifest(path: Path) -> bool` (recompute sha256, compare to `<path>.sha256`; raises `CaptureError` if the sidecar is missing).
- Produces:
  - `@dataclass(frozen=True) VerifyResult(checked: int, ok: int, failed: tuple[str, ...], newest_ts: datetime | None)`
  - `verify_tree(root: Path, *, now: datetime) -> VerifyResult` — walk `root` for `*.parquet` (skip `*.part*.parquet`), call `verify_manifest` on each, collect failures (path strings), and track the newest segment's manifest hour from its path (`<pair>/<kind>/<YYYY>/<MM>/<DD>/<HH>.parquet` → aware-UTC), so `pull_lag = now - newest_ts`.
  - `pull_lag_seconds(result: VerifyResult, *, now: datetime) -> float | None`

**Step 1: Write the failing test** (`tests/test_archive_pull.py`)

```python
from datetime import UTC, datetime
from pathlib import Path
import hashlib
import polars as pl
from cli.archive.pull import verify_tree, pull_lag_seconds

def _seg(root: Path, pair: str, kind: str, hour: str, *, corrupt: bool = False) -> None:
    d = root / pair / kind / "2026" / "07" / "12"
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{hour}.parquet"
    pl.DataFrame({"x": [1, 2, 3]}).write_parquet(p)
    digest = hashlib.sha256(p.read_bytes()).hexdigest()
    if corrupt:
        digest = "0" * 64
    (d / f"{hour}.parquet.sha256").write_text(f"{digest}  {p.name}\n")

def test_verify_tree_all_ok(tmp_path):
    _seg(tmp_path, "BTC/EUR", "book", "10")
    _seg(tmp_path, "BTC/EUR", "trades", "11")
    now = datetime(2026, 7, 12, 13, 0, tzinfo=UTC)
    r = verify_tree(tmp_path, now=now)
    assert r.checked == 2 and r.ok == 2 and r.failed == ()
    # newest hour is 11:00 UTC -> lag = 2h
    assert pull_lag_seconds(r, now=now) == 2 * 3600

def test_verify_tree_flags_mismatch(tmp_path):
    _seg(tmp_path, "ETH/EUR", "book", "09", corrupt=True)
    r = verify_tree(tmp_path, now=datetime(2026, 7, 12, 13, 0, tzinfo=UTC))
    assert r.checked == 1 and r.ok == 0
    assert any("ETH/EUR/book/2026/07/12/09.parquet" in f for f in r.failed)

def test_verify_tree_skips_partfiles(tmp_path):
    d = tmp_path / "BTC/EUR/book/2026/07/12"
    d.mkdir(parents=True)
    (d / "12.part0000.parquet").write_bytes(b"partial")  # current-hour part, no manifest
    r = verify_tree(tmp_path, now=datetime(2026, 7, 12, 13, 0, tzinfo=UTC))
    assert r.checked == 0
```

**Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_archive_pull.py -q`
Expected: FAIL (`ModuleNotFoundError: cli.archive.pull`).

**Step 3: Write the minimal implementation** (`cli/archive/pull.py`)

```python
from __future__ import annotations
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from cli.capture.segment_writer import verify_manifest

@dataclass(frozen=True)
class VerifyResult:
    checked: int
    ok: int
    failed: tuple[str, ...]
    newest_ts: datetime | None

def _hour_ts(path: Path) -> datetime | None:
    # .../<YYYY>/<MM>/<DD>/<HH>.parquet
    try:
        hh = path.stem
        d, m, y = path.parent.name, path.parent.parent.name, path.parent.parent.parent.name
        return datetime(int(y), int(m), int(d), int(hh), tzinfo=UTC)
    except (ValueError, IndexError):
        return None

def verify_tree(root: Path, *, now: datetime) -> VerifyResult:
    checked = ok = 0
    failed: list[str] = []
    newest: datetime | None = None
    for p in sorted(root.rglob("*.parquet")):
        if ".part" in p.name:  # in-progress current-hour part, no manifest yet
            continue
        checked += 1
        if verify_manifest(p):
            ok += 1
        else:
            failed.append(str(p))
        ts = _hour_ts(p)
        if ts is not None and (newest is None or ts > newest):
            newest = ts
    return VerifyResult(checked=checked, ok=ok, failed=tuple(failed), newest_ts=newest)

def pull_lag_seconds(result: VerifyResult, *, now: datetime) -> float | None:
    if result.newest_ts is None:
        return None
    return (now - result.newest_ts).total_seconds()
```

**Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/test_archive_pull.py -q`
Expected: PASS (3 tests).

**Step 5: Commit**

```bash
git add cli/archive/__init__.py cli/archive/pull.py tests/test_archive_pull.py
git commit -m "feat(archive): manifest-verify sweep + pull-lag for the NAS pull"
```

______________________________________________________________________

## Task 2: `zcrypto archive pull` command — rsync + verify wiring

**Files:**

- Create: `cli/archive/command.py`
- Modify: `cli/__main__.py`
- Test: `tests/test_archive_pull.py` (add a `CliRunner` test + an injected-runner test)

**Interfaces:**

- Consumes: `cli.archive.pull.verify_tree`, `pull_lag_seconds`; `cli.logging.get_logger("archive.command")`.
- Produces: `archive_app: typer.Typer`; `pull(source: str, dest: Path, *, rsync_runner: Callable[[str, Path], int] = _run_rsync)` where `source` is an `rsync` spec (e.g. `deploy@host:/var/lib/zcrypto-capture/segments/`) and `_run_rsync` shells out to `rsync -a --delete-excluded=false -e "ssh -i $ARCHIVE_SSH_KEY -p $ARCHIVE_SSH_PORT -o StrictHostKeyChecking=accept-new" <source> <dest>` and returns its exit code. The runner is injectable so tests never touch the network.

**Behavior (exact):**

- `pull` runs the rsync runner; if it returns non-zero, log an error and exit 2 (transport failure — do NOT verify a partial pull as authoritative).
- On rsync success, call `verify_tree(dest, now=_utc_now())`; log `pull complete source=… checked=N ok=N failed=N lag_s=…`.
- If `result.failed` is non-empty, log each failed path at ERROR and exit 1 (a hash mismatch is a first-class finding, never silently archived-as-good).
- Else exit 0.
- `_utc_now()` is a module function so tests can monkeypatch it (mirrors `cli/engine`).

**Step 1: Write the failing tests**

```python
from typer.testing import CliRunner
from cli.__main__ import app
# ... build a good tree in tmp_path/dest, inject a runner that returns 0
def test_pull_ok_exits_zero(tmp_path, monkeypatch):
    dest = tmp_path / "arch"; dest.mkdir()
    _seg(dest, "BTC/EUR", "book", "10")
    from cli.archive import command
    monkeypatch.setattr(command, "_run_rsync", lambda source, d: 0)
    res = CliRunner().invoke(app, ["archive", "pull", "deploy@h:/src/", str(dest)])
    assert res.exit_code == 0

def test_pull_mismatch_exits_one(tmp_path, monkeypatch):
    dest = tmp_path / "arch"; dest.mkdir()
    _seg(dest, "BTC/EUR", "book", "10", corrupt=True)
    from cli.archive import command
    monkeypatch.setattr(command, "_run_rsync", lambda source, d: 0)
    res = CliRunner().invoke(app, ["archive", "pull", "deploy@h:/src/", str(dest)])
    assert res.exit_code == 1

def test_pull_transport_failure_exits_two(tmp_path, monkeypatch):
    from cli.archive import command
    monkeypatch.setattr(command, "_run_rsync", lambda source, d: 23)
    res = CliRunner().invoke(app, ["archive", "pull", "deploy@h:/src/", str(tmp_path)])
    assert res.exit_code == 2
```

**Step 2: Run to verify fail** — `uv run pytest tests/test_archive_pull.py -q` → FAIL.

**Step 3: Implement** `cli/archive/command.py` (Typer group + `pull` per the behavior above; `_run_rsync` builds the argv from `ARCHIVE_SSH_KEY`/`ARCHIVE_SSH_PORT` env, default port `10022`), and register in `cli/__main__.py`:

```python
from cli.archive.command import archive_app
app.add_typer(archive_app, name="archive")
```

**Step 4: Run to verify pass** — `uv run pytest tests/test_archive_pull.py -q` → PASS. Also `uv run zcrypto archive --help`.

**Step 5: Update `README.md`** `## Usage` — document `zcrypto archive pull <source> <dest>` (per `readme-usage.md`).

**Step 6: Commit** — `feat(archive): zcrypto archive pull command (rsync + verify + exit codes)`.

______________________________________________________________________

## Task 3: NAS pull container + in-container scheduler

**Files:**

- Create: `infra/nas/compose.yaml`, `infra/nas/pull-entrypoint.sh`, `infra/nas/README.md`

**Details:**

- `pull-entrypoint.sh`: `#!/usr/bin/env sh` + `set -eu`; `umask 0002`; a loop that, every `${ARCHIVE_PULL_INTERVAL:-3600}`s, runs `zcrypto archive pull "$CAPTURE_SOURCE" "$CAPTURE_DEST"` then `zcrypto archive pull "$JOURNAL_SOURCE" "$JOURNAL_DEST"`, logging failures but never exiting on a single failed pull (the loop is the availability guarantee; the pull-lag metric is the dead-man). Trap `SIGTERM` to exit cleanly.
- `compose.yaml`: service `archive-pull` using `image: ghcr.io/zhaow-de/zcrypto-capture@<digest>` (pinned; the same image the VPS runs — it already contains the `zcrypto` CLI), `entrypoint: ["/opt/pull-entrypoint.sh"]`, `user: "1000:1000"`, `restart: unless-stopped`, `environment` (`CAPTURE_SOURCE`, `CAPTURE_DEST=/archive/derivatives-...`, `JOURNAL_SOURCE`, `JOURNAL_DEST`, `ARCHIVE_SSH_KEY=/keys/sync_capture`, `ARCHIVE_SSH_PORT`, `ARCHIVE_PULL_INTERVAL`), volumes (`/volume1/ZhaoCrypto:/archive`, the entrypoint script `:ro`, the SSH key dir `:ro`), `logging` json-file caps. **No `container_name` clash with the VPS**; this stack only ever runs on the NAS.
- `README.md`: exact deploy steps (place the compose + entrypoint under `/volume1/docker/zcrypto-archive/`, drop the `0600` `sync_capture` key, `docker compose up -d` via the full `/usr/local/bin/docker` path), the archive-path contract, and how to read pull-lag from the logs.

*(No unit tests — this is container config; it is exercised by the Task 6 deploy. Validate `sh -n pull-entrypoint.sh` and `docker compose config` in the review.)*

**Commit** — `feat(nas): archive-pull container + in-container scheduler`.

______________________________________________________________________

## Task 4: VPS capture-segments `rrsync` pull channel (ansible)

**Files:**

- Modify: `infra/ansible/roles/capture/tasks/main.yml`, `infra/ansible/roles/capture/defaults/main.yml` (if a var is needed)

**Details:** mirror the engine-journal channel (`infra/ansible/roles/engine/tasks/main.yml`): ensure `rsync` present; install `sync_capture_authorized_key` as a forced-command entry on the `deploy` user — `key_options: 'command="/usr/bin/rrsync -ro {{ capture_data_dir }}",restrict'`; ensure `deploy` can traverse the capture data dir (group membership if the dir is group-restricted; capture writes as its own uid — confirm the mode). Use `exclusive: false` so it coexists with the existing deploy + engine-journal keys. First-run check-mode guards per the engine role's pattern.

*(No unit tests — ansible config; validated by `ansible-playbook --check` + `--syntax-check` in review, and the Task 6 converge.)*

**Commit** — `feat(capture): read-only rrsync channel for the NAS segment pull`.

______________________________________________________________________

## Task 5: Move the unattended-reboot window to 02:00 UTC

**Files:**

- Modify: `infra/ansible/roles/base/defaults/main.yml`

**Step 1:** change `base_unattended_upgrades_reboot_time: "04:00"` → `"02:00"`.
**Step 2:** grep the repo for any doc referencing the `04:00` reboot and update to `02:00` (e.g. `T0027`, spec `00048` already says 02:00).
**Commit** — `feat(base): move unattended-upgrades reboot window 04:00 -> 02:00 UTC`.

______________________________________________________________________

## Task 6: (ATTENDED) Deploy + end-to-end verification

**Not subagent-run — the orchestrator performs this with the human, and it is the only task that touches production.** Preconditions: Tasks 1–5 merged (or on the branch), the `sync_capture` keypair generated.

- [ ] Generate the `sync_capture` ed25519 keypair; vault the **public** key as `sync_capture_authorized_key` (scripted vault append, values never printed); place the **private** key `0600` on the NAS under the archive stack's key dir.
- [ ] Converge the VPS **without touching the capture container**: `run.sh site.yml --tags capture,base --check` first (confirm only the authorized_key + reboot-time change), then apply. Verify `Automatic-Reboot-Time 02:00` on the host and the new `deploy` authorized_key line present; `docker ps` shows the capture container **unchanged** (same id, same uptime).
- [ ] Deploy the NAS stack (`docker compose up -d`); confirm the container is `Up`, runs as `1000:1000`.
- [ ] **End-to-end:** within one pull interval, a recent VPS segment appears under `/volume1/ZhaoCrypto/…` hash-verified; `zcrypto archive pull` logs `failed=0` and a plausible `lag_s`; files are `0664` group `zcrypto`. Inject a deliberately corrupted `.sha256` in a scratch dir and confirm `pull` exits 1 + logs the path (then remove it).
- [ ] Confirm the workstation sees the pulled data through the mount.

______________________________________________________________________

## Task 7: Closeout — iterations-history entry

- [ ] Append a `## <date> — Three-tier Role A: NAS pull/archive` section to `docs/iterations-history-phase6.md`: the `zcrypto archive` CLI, the NAS pull container, the VPS capture rrsync channel, the 02:00 reboot move, and that it supersedes T0003's workstation-pull. (Authored at closeout, when the work is real — per `iterations-history.md`.)

______________________________________________________________________

## Increment roadmap (context — not built here)

- **Increment 2 — Role B (always-on gate verification):** a NAS container runs `zcrypto engine report`/`replay` daily against the pulled journal; alerts + reports pull-lag/gate-status into Grafana Cloud (spec §Role B, §Observability).
- **Increment 3 — Role C (redundant NAS capture + dual-L2 reconciliation):** a second capture container on the NAS + the canonical-VPS/gap-fill-NAS reconciler (trades by `trade_id`, book by time-window) (spec §Role C).

## Self-Review

- **Spec coverage:** Role A (pull + hash-verify + archive), the NAS runtime (1000:1000, umask 0002, no-systemd, restart policy), the VPS rrsync channel, the reboot-window change, and the pull-lag signal are all covered. Role B/C and the Grafana hook are explicitly deferred to increments 2/3 (spec's A+B+C scope, built incrementally).
- **Placeholder scan:** none — every code task carries its test + implementation; config tasks name exact files/values.
- **Type consistency:** `verify_tree`/`VerifyResult`/`pull_lag_seconds` signatures match across Tasks 1–2; `_run_rsync`/`_utc_now` are the named monkeypatch points.
