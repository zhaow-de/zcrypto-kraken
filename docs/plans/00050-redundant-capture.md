# Role C — redundant capture + reconciliation: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up a second capture host and an hourly reconciler so a primary outage no longer punches a permanent hole in the unbackfillable L2 archive, healed by whole-window book splice + trade-id union, provenance-tagged and auditable.

**Architecture:** Zero changes to `cli/capture/` — the secondary runs the identical deployed image. All new code is archive-side: a `zcrypto archive reconcile` Typer command in `cli/archive/`, a canonical-read helper, and an overlay mode for the continuity instrument. The NAS gains a second pull channel and runs the reconciler at the end of its existing hourly loop. Reconciliation is an **overlay**: raw mirrors stay immutable and canonical-by-default; only healed hours are minted.

**Tech Stack:** Python 3.14, Typer, polars, pytest; Ansible (devsec hardening roles); Docker Compose on Synology DSM; Grafana Cloud + Alloy.

## Global Constraints

Copied verbatim from spec `00050`. Every task's requirements implicitly include these.

- **Never interleave rows from two book streams.** Kraken coalesces book updates per WS connection: two healthy hosts record *different* message streams for the same pair (different counts, both 100% CRC-valid). Cross-host row-diffing measures coalescing, not loss. Book redundancy operates **only at whole-window granularity** — splice the secondary's window as a **block**.
- **Never sort rows by `ts`.** L2 rows carry **absolute quantities** and are order-sensitive; concatenate blocks in source order only. (`SegmentWriter._write_merging` holds the same rule.)
- **Trades may be unioned row-level** — `trade_id` is globally unique and identical across hosts.
- **A minted final is never overwritten.** `<HH>.parquet` on disk means "committed and complete" (the T0036 invariant). Write path: temp → fsync → rename (`_replace_durably`), sidecar minted from the final's bytes **before** the rename.
- **Exit-bar isolation:** the T0003 gap measurement runs on the **raw primary mirror only**. The overlay gets a *separate* report and is **never** an input to the Phase-1 exit bar (an overlay heals gaps by design, so measuring the bar on it would let a raw-capture regression bank a clean run).
- **`--min-gap-seconds` default is 30** — 2× the measured 14.78 s maximum natural quiescence. It is **not yet validated**; the reconciler runs **detect-only** through the soak and the final value is pinned from cross-host data (T0039). Never mint before that soak.
- **Never delete data to resolve an ambiguity** — quarantine, never unlink.
- Deploy embargo: no primary capture-image re-pin until the ≥7-day clean-run gate banks. All future re-pins follow the canary rule (`.claude/rules/capture-deploys.md`).

## Facts the implementer needs (verified against the tree, 2026-07-14)

- `cli/archive/` today = `__init__.py` (empty), `command.py` (`archive_app`, one command `pull`), `pull.py` (`VerifyResult`, `_hour_ts`, `verify_tree`, `pull_lag_seconds`). Tests: `tests/test_archive_pull.py`.
- Typer wiring: `cli/__main__.py` does `from cli.archive.command import archive_app; app.add_typer(archive_app, name="archive")`. Commands are declared `@archive_app.command()` (function name = command name).
- `verify_tree(root: Path, *, now: datetime) -> VerifyResult`; `VerifyResult(checked:int, ok:int, failed:tuple[str,...], newest_ts:datetime|None)`. It **skips** any path whose name contains `.part` or `.held`.
- Manifest sidecar bytes: `f"{sha256_hexdigest}  {final.name}\n"` (two spaces). `verify_manifest(path) -> bool` raises `CaptureError` on a missing/empty sidecar. Import: `from cli.capture.segment_writer import verify_manifest`.
- Durability helper: `_replace_durably(tmp_path: Path, dest: Path) -> None` in `cli/capture/segment_writer.py` (module-private; import it explicitly and note the coupling in a comment).
- Schemas: `from cli.capture.segment_writer import BOOK_SCHEMA, TRADE_SCHEMA`.
- Segment layout: `<root>/<BASE>/<QUOTE>/<kind>/<YYYY>/<MM>/<DD>/<HH>.parquet` (+ `.sha256`). Pair spans **two** path levels.
- Error type: `CaptureError` (`cli/capture/errors.py`). `archive pull` exit codes: 2 = transport, 1 = hash mismatch, 0 = ok.
- **`zcrypto_capture_*` Prometheus metrics do not exist** — `cli/capture/` emits none. The spec's `|zcrypto_capture_.*` keep-regex addition is inert future-proofing; do not claim it makes series appear.
- NAS loop (`infra/nas/pull-entrypoint.sh`) is POSIX `sh`, `set -eu`, best-effort per step: `if ! <cmd>; then echo "pull-entrypoint: <step> failed (…), continuing" >&2; fi` — never `exit`.
- Existing NAS env vars: `CAPTURE_SOURCE`, `CAPTURE_DEST`, `CAPTURE_SSH_KEY`, `JOURNAL_*`, `ARCHIVE_SSH_KNOWN_HOSTS`, `ARCHIVE_SSH_PORT`, `ARCHIVE_PULL_INTERVAL`, `GATE_TEXTFILE`, `GATE_HEALTHCHECK_URL`. Textfile dir: host `/volume1/docker/zcrypto-archive/textfile` → `/textfile` (RW in `archive-pull`, RO in `alloy`).
- Alloy keep-regex is at `infra/nas/config.alloy` inside `prometheus.remote_write "grafana"`, ending `…|zcrypto_gate_.*`. **It silently drops every unknown series** — extending it is mandatory or no new metric ever leaves the NAS.
- Ansible: `inventory/hosts.yml` now has `capture_host` (zcrypto) + `engine_host` (zcrypto) + `workstation`. **No `host_vars/` directory exists.** No `sync_capture_red` keypair. No `capture_retention_days` / prune timer. Run playbooks via `infra/ansible/scripts/run.sh` (loads the vaulted deploy key into a throwaway agent). **Never run `ansible-inventory --host/--list`** — it prints the whole vault in cleartext.
- `capture` role defaults: `capture_cpu_limit: "1.5"`, `capture_memory_limit: "2g"`, `capture_healthcheck_url: ""`, `capture_image_digest: ""` (must be passed `-e`).
- Deployed capture digest (both hosts must run ≥ this): `sha256:63708539c3f9683608b0d5ad396ea213717d6a38c0291233bbf0d5af220b3676`.

## File structure

| File | Responsibility |
|---|---|
| `cli/archive/reconcile.py` (new) | Pure logic: settle rule, gap detection, block splice, trade union, provenance/ledger records. No I/O policy, no Typer. |
| `cli/archive/mint.py` (new) | Write path: atomic mint of a reconciled final + sidecar + provenance, append to ledger. Reuses `_replace_durably`. |
| `cli/archive/reader.py` (new) | `canonical_segments()` — reconciled-first resolution with a strict `<HH>.parquet` final-name match (also closes T0038's glob trap for consumers). |
| `cli/archive/command.py` (modify) | Add `@archive_app.command()` `reconcile` — wiring + exporter + exit codes only. |
| `infra/scripts/continuity.py` (modify) | Add `--overlay <reconciled-root>` as a **separate mode**; default stays raw-only (exit-bar isolation). |
| `infra/ansible/host_vars/zcrypto-red/{vars,vault}.yml` (new) | Secondary overrides: reboot 22:25, 1g/0.9 limits, own healthcheck, own rrsync key. |
| `infra/ansible/roles/capture/` (modify) | `capture_retention_days` + `zcrypto-capture-prune` systemd timer. |
| `infra/nas/{compose.yaml,pull-entrypoint.sh,config.alloy,README.md}` (modify) | Second pull channel, reconcile step, keep-regex, env-var contract. |
| `infra/grafana/{alerts.yaml,zcrypto-dashboard.json}` (modify) | Role C row + 4 rules. |
| `tests/test_archive_reconcile.py`, `tests/test_archive_reader.py` (new) | TDD for the above. |

---

## Task 1: Converge the primary VPS (attended, config-only)

**Files:** none (applies already-merged config). **Interfaces:** none.

Applies the re-slotted reboot window + key-only root SSH to the live primary. The `engine_host` split, the §8-gate widening and the `ttyS0` preservation are already on this branch; a check-mode run has been done and is clean.

- [ ] **Step 1: Re-run the dry run and confirm the change set is exactly as expected**

```bash
cd infra/ansible && ./scripts/run.sh site.yml \
  -e capture_image_digest=sha256:63708539c3f9683608b0d5ad396ea213717d6a38c0291233bbf0d5af220b3676 \
  -e engine_image_digest=sha256:8574aff805c0ab6a22d82b3a6dd942c90f194f79d552412b0be6c15e1971a8ad \
  --check --diff
```
Expected: `ok=205 changed=6 failed=0`. The changed tasks must be exactly: unattended-upgrades (`02:00`→`21:25`), securetty (blank-line only — **`ttyS0` must remain**), sshd_config (`PermitRootLogin prohibit-password`, `AllowUsers deploy root`), nftables (comments only), chrony flush_handlers ×2. **If any `capture`-role task appears, STOP** — the capture daemon must not restart.

- [ ] **Step 2: Record the pre-converge capture state (so a regression is provable, not assumed)**

```bash
ssh zcrypto 'docker inspect zcrypto-capture-capture-1 --format "{{.State.StartedAt}} restarts={{.RestartCount}}"'
```

- [ ] **Step 3: Converge**

```bash
cd infra/ansible && ./scripts/run.sh site.yml \
  -e capture_image_digest=sha256:63708539c3f9683608b0d5ad396ea213717d6a38c0291233bbf0d5af220b3676 \
  -e engine_image_digest=sha256:8574aff805c0ab6a22d82b3a6dd942c90f194f79d552412b0be6c15e1971a8ad
```

- [ ] **Step 4: Verify by outcome (not by "it said ok")**

```bash
ssh zcrypto 'grep Automatic-Reboot-Time /etc/apt/apt.conf.d/50unattended-upgrades; \
  sudo sshd -T | grep -E "^(permitrootlogin|passwordauthentication|allowusers)"; \
  grep -c ttyS0 /etc/securetty; \
  docker inspect zcrypto-capture-capture-1 --format "{{.State.StartedAt}} restarts={{.RestartCount}}"'
ssh zcrypto 'systemctl is-active zcrypto-capture zcrypto-engine'
```
Expected: `"21:25"`; `permitrootlogin prohibit-password` / `passwordauthentication no` / `allowusers deploy root`; `ttyS0` count `1`; **`StartedAt` and `RestartCount` unchanged from Step 2** (capture did NOT restart); both services `active`.

- [ ] **Step 5: Prove root break-glass actually works (the whole point of the change)**

```bash
ssh -p 10022 -i ~/.ssh/zhaow-master-2018 root@zcrypto.zhaow.me 'id'
```
Expected: `uid=0(root)`. If this fails the change is cosmetic — investigate before proceeding.

- [ ] **Step 6: Commit nothing** — this task applies config, it does not change the repo. Record the outcome in the task ledger.

---

## Task 2: Reconciler — gap detection (TDD, pure logic)

**Files:** Create `cli/archive/reconcile.py`; Test `tests/test_archive_reconcile.py`.

**Interfaces — Produces (later tasks rely on these exact names):**
```python
@dataclass(frozen=True)
class Gap:
    start: datetime      # t1: last primary row before the silence
    end: datetime        # t2: first primary row after it
    seconds: float

def find_book_gaps(primary: pl.DataFrame, secondary: pl.DataFrame, *, min_gap_seconds: float) -> list[Gap]
def secondary_covers(secondary: pl.DataFrame, gap: Gap) -> bool
```

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_archive_reconcile.py
from datetime import UTC, datetime, timedelta
import polars as pl
import pytest
from cli.archive.reconcile import Gap, find_book_gaps, secondary_covers

H = datetime(2026, 7, 16, 9, tzinfo=UTC)

def _book(rows: list[tuple[float, str]]) -> pl.DataFrame:
    """rows = [(offset_seconds, type)]; one wire message per row."""
    return pl.DataFrame(
        {
            "ts": [H + timedelta(seconds=o) for o, _ in rows],
            "symbol": ["BTC/EUR"] * len(rows),
            "type": [t for _, t in rows],
            "side": ["bid"] * len(rows),
            "price": [1.0] * len(rows),
            "qty": [1.0] * len(rows),
            "checksum": [0] * len(rows),
        }
    )

def test_a_quiet_primary_with_no_secondary_activity_is_not_a_gap():
    # 60 s of primary silence, but the secondary is equally quiet -> the market was quiet.
    primary = _book([(0, "update"), (60, "update")])
    secondary = _book([(0, "update"), (60, "update")])
    assert find_book_gaps(primary, secondary, min_gap_seconds=30) == []

def test_primary_silence_with_secondary_updates_inside_is_a_gap():
    primary = _book([(0, "update"), (120, "update")])
    secondary = _book([(0, "update"), (40, "update"), (80, "update"), (120, "update")])
    gaps = find_book_gaps(primary, secondary, min_gap_seconds=30)
    assert len(gaps) == 1
    assert gaps[0].start == H
    assert gaps[0].end == H + timedelta(seconds=120)
    assert gaps[0].seconds == pytest.approx(120.0)

def test_a_secondary_resubscribe_snapshot_alone_never_fabricates_a_gap():
    # THE pinned spec case: a snapshot is full state, not market activity. If the only secondary
    # rows inside the window are snapshot rows, nothing was lost -> no gap, no heal.
    primary = _book([(0, "update"), (120, "update")])
    secondary = _book([(0, "update"), (60, "snapshot"), (120, "update")])
    assert find_book_gaps(primary, secondary, min_gap_seconds=30) == []

def test_silence_below_the_threshold_is_not_a_gap():
    primary = _book([(0, "update"), (20, "update")])
    secondary = _book([(0, "update"), (10, "update"), (20, "update")])
    assert find_book_gaps(primary, secondary, min_gap_seconds=30) == []

def test_multiple_gaps_in_one_hour_are_all_found():
    primary = _book([(0, "update"), (100, "update"), (200, "update"), (400, "update")])
    secondary = _book([(0, "update"), (50, "update"), (100, "update"), (150, "update"),
                       (200, "update"), (300, "update"), (400, "update")])
    gaps = find_book_gaps(primary, secondary, min_gap_seconds=30)
    assert [(g.start, g.end) for g in gaps] == [
        (H, H + timedelta(seconds=100)),
        (H + timedelta(seconds=100), H + timedelta(seconds=200)),
        (H + timedelta(seconds=200), H + timedelta(seconds=400)),
    ]

def test_an_empty_primary_hour_is_one_whole_hour_gap():
    primary = _book([])
    secondary = _book([(1, "update"), (3599, "update")])
    gaps = find_book_gaps(primary, secondary, min_gap_seconds=30)
    assert len(gaps) == 1

def test_secondary_covers_requires_an_update_row_strictly_inside():
    gap = Gap(start=H, end=H + timedelta(seconds=120), seconds=120.0)
    assert secondary_covers(_book([(60, "update")]), gap) is True
    assert secondary_covers(_book([(60, "snapshot")]), gap) is False
    assert secondary_covers(_book([]), gap) is False
    # boundary rows are NOT inside (strict inequalities keep same-ts wire messages intact)
    assert secondary_covers(_book([(0, "update"), (120, "update")]), gap) is False
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/test_archive_reconcile.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cli.archive.reconcile'`

- [ ] **Step 3: Implement**

```python
# cli/archive/reconcile.py
"""Pure reconciliation logic for spec 00050: cross-stream book-gap detection.

No I/O and no Typer here — `mint.py` owns the write path and `command.py` the wiring, so the rules
below are testable on plain DataFrames.

Load-bearing constraints (spec 00050, constraints 1 + 2):
  * Kraken coalesces book updates PER CONNECTION, so two healthy hosts record different message
    sequences for the same pair. A gap is therefore only ever detected — never repaired — by
    comparing row-level content across hosts; repair is whole-window block substitution.
  * A secondary *snapshot* row is full state, not market activity. It must never, on its own,
    testify that the primary lost something: after any reconnect the secondary re-snapshots, and a
    quiet market would otherwise be "healed" for a window in which nothing happened.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import polars as pl


@dataclass(frozen=True)
class Gap:
    """A window in which the primary stream was silent and the secondary was demonstrably alive."""

    start: datetime
    end: datetime
    seconds: float


def _message_ts(df: pl.DataFrame) -> list[datetime]:
    """One entry per wire message: many rows share a `ts` (one row per book level)."""
    if df.height == 0:
        return []
    return df.select(pl.col("ts").unique(maintain_order=True)).to_series().to_list()


def secondary_covers(secondary: pl.DataFrame, gap: Gap) -> bool:
    """True iff the secondary has at least one **update** row strictly inside `gap`.

    Strict inequalities: a row exactly at a boundary belongs to the wire message that defines the
    boundary, and splitting a message across blocks would tear one book update in half.
    """
    if secondary.height == 0:
        return False
    inside = secondary.filter(
        (pl.col("ts") > gap.start) & (pl.col("ts") < gap.end) & (pl.col("type") == "update")
    )
    return inside.height > 0


def find_book_gaps(
    primary: pl.DataFrame, secondary: pl.DataFrame, *, min_gap_seconds: float
) -> list[Gap]:
    """Windows where the primary was silent > `min_gap_seconds` AND the secondary was alive inside.

    A wholly-absent primary hour degenerates to one window spanning the secondary's own extent.
    """
    sec_ts = _message_ts(secondary)
    if not sec_ts:
        return []

    pri_ts = _message_ts(primary)
    if not pri_ts:
        gap = Gap(start=sec_ts[0], end=sec_ts[-1], seconds=(sec_ts[-1] - sec_ts[0]).total_seconds())
        return [gap] if secondary_covers(secondary, gap) else []

    gaps: list[Gap] = []
    for a, b in zip(pri_ts, pri_ts[1:], strict=False):
        seconds = (b - a).total_seconds()
        if seconds <= min_gap_seconds:
            continue
        gap = Gap(start=a, end=b, seconds=seconds)
        if secondary_covers(secondary, gap):
            gaps.append(gap)
    return gaps
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run pytest tests/test_archive_reconcile.py -v`
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add cli/archive/reconcile.py tests/test_archive_reconcile.py
git commit -m "feat(archive): detect cross-stream book gaps (spec 00050)

A gap is primary silence > --min-gap-seconds with a secondary UPDATE row strictly
inside it. A secondary resubscribe snapshot alone never testifies to a loss —
it is full state, not market activity, so a quiet market can never be 'healed'.

Co-Authored-By: <model> <noreply@anthropic.com>"
```

---

## Task 3: Reconciler — book block splice (TDD, pure logic)

**Files:** Modify `cli/archive/reconcile.py`; Test `tests/test_archive_reconcile.py`.

**Interfaces — Consumes:** `Gap`, `find_book_gaps` (Task 2). **Produces:**
```python
@dataclass(frozen=True)
class Block:
    source: str          # "primary" | "secondary"
    frame: pl.DataFrame
    from_ts: datetime | None
    to_ts: datetime | None

def splice_book(primary: pl.DataFrame, secondary: pl.DataFrame, gaps: list[Gap]) -> list[Block]
```

- [ ] **Step 1: Write the failing tests**

```python
def test_splice_orders_blocks_primary_secondary_primary_and_never_sorts():
    primary = _book([(0, "update"), (120, "update")])
    secondary = _book([(0, "update"), (40, "update"), (80, "update"), (120, "update")])
    gaps = find_book_gaps(primary, secondary, min_gap_seconds=30)
    blocks = splice_book(primary, secondary, gaps)
    assert [b.source for b in blocks] == ["primary", "secondary", "primary"]
    out = pl.concat([b.frame for b in blocks])
    # every primary row survives, the secondary fills only the window, nothing is reordered
    assert out["ts"].to_list() == [
        H, H + timedelta(seconds=40), H + timedelta(seconds=80), H + timedelta(seconds=120)
    ]

def test_a_shared_ts_wire_message_is_never_split_across_blocks():
    # two rows share ts=0 (one message, two levels). The primary block must keep BOTH.
    primary = pl.concat([_book([(0, "update"), (0, "update")]), _book([(120, "update")])])
    secondary = _book([(0, "update"), (60, "update"), (120, "update")])
    gaps = find_book_gaps(primary, secondary, min_gap_seconds=30)
    blocks = splice_book(primary, secondary, gaps)
    assert blocks[0].frame.height == 2               # both level-rows of the ts=0 message
    assert blocks[1].source == "secondary"
    assert blocks[1].frame["ts"].to_list() == [H + timedelta(seconds=60)]

def test_a_missing_primary_hour_becomes_one_full_secondary_block():
    primary = _book([])
    secondary = _book([(1, "update"), (3599, "update")])
    gaps = find_book_gaps(primary, secondary, min_gap_seconds=30)
    blocks = splice_book(primary, secondary, gaps)
    assert [b.source for b in blocks] == ["secondary"]
    assert blocks[0].frame.height == 2
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/test_archive_reconcile.py -k splice -v`
Expected: FAIL — `ImportError: cannot import name 'splice_book'`

- [ ] **Step 3: Implement (append to `cli/archive/reconcile.py`)**

```python
@dataclass(frozen=True)
class Block:
    """One contiguous run of rows from one source. Blocks concatenate in list order — never sorted."""

    source: str
    frame: pl.DataFrame
    from_ts: datetime | None
    to_ts: datetime | None


def _span(frame: pl.DataFrame) -> tuple[datetime | None, datetime | None]:
    if frame.height == 0:
        return None, None
    return frame["ts"].min(), frame["ts"].max()


def _block(source: str, frame: pl.DataFrame) -> Block:
    lo, hi = _span(frame)
    return Block(source=source, frame=frame, from_ts=lo, to_ts=hi)


def splice_book(primary: pl.DataFrame, secondary: pl.DataFrame, gaps: list[Gap]) -> list[Block]:
    """Mint the hour as ordered blocks: primary up to each gap, secondary inside it, primary after.

    Boundaries are **strict** on the secondary side (`start < ts < end`) and **inclusive** on the
    primary side (`ts <= start`, `ts >= end`), so the rows of one wire message — which all share a
    `ts` — always stay together in the same block. Rows are concatenated in source order and NEVER
    sorted: L2 updates carry absolute quantities, so reordering within a `ts` changes the book.
    """
    if not gaps:
        return [_block("primary", primary)] if primary.height else []

    blocks: list[Block] = []
    cursor: datetime | None = None
    for gap in gaps:
        head = primary.filter(pl.col("ts") <= gap.start)
        if cursor is not None:
            head = head.filter(pl.col("ts") >= cursor)
        if head.height:
            blocks.append(_block("primary", head))
        middle = secondary.filter((pl.col("ts") > gap.start) & (pl.col("ts") < gap.end))
        if middle.height:
            blocks.append(_block("secondary", middle))
        cursor = gap.end

    tail = primary.filter(pl.col("ts") >= cursor) if cursor is not None else primary
    if tail.height:
        blocks.append(_block("primary", tail))
    return blocks
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run pytest tests/test_archive_reconcile.py -v`
Expected: 10 passed.

- [ ] **Step 5: Commit**

```bash
git add cli/archive/reconcile.py tests/test_archive_reconcile.py
git commit -m "feat(archive): splice a primary book gap with a secondary block (spec 00050)

Blocks concatenate in source order and are never sorted — L2 updates carry
absolute quantities. Boundaries are strict on the secondary side and inclusive
on the primary side, so the rows of one wire message (which share a ts) are
never split across two blocks.

Co-Authored-By: <model> <noreply@anthropic.com>"
```

---

## Task 4: Reconciler — trade union with idempotent dedup (TDD)

**Interfaces — Produces:**
```python
@dataclass(frozen=True)
class TradeUnion:
    frame: pl.DataFrame
    added_from_secondary: int
    deduped_rows: int
    secondary_deficit: int        # ids the SECONDARY lacks — a QA signal, never a mint trigger

def union_trades(primary: pl.DataFrame, secondary: pl.DataFrame) -> TradeUnion
```

- [ ] **Step 1: Write the failing tests**

```python
def _trades(ids: list[int], *, offset: int = 0) -> pl.DataFrame:
    return pl.DataFrame({
        "ts": [H + timedelta(seconds=i + offset) for i in ids],
        "symbol": ["BTC/EUR"] * len(ids),
        "side": ["buy"] * len(ids),
        "price": [1.0] * len(ids),
        "qty": [1.0] * len(ids),
        "trade_id": [str(i) for i in ids],
    })

def test_primary_deficit_is_healed_from_the_secondary_ordered_by_trade_id():
    u = union_trades(_trades([1, 2, 5]), _trades([1, 2, 3, 4, 5]))
    assert u.added_from_secondary == 2
    assert u.frame["trade_id"].to_list() == ["1", "2", "3", "4", "5"]
    assert u.deduped_rows == 0

def test_no_deficit_is_a_no_op():
    u = union_trades(_trades([1, 2, 3]), _trades([1, 2, 3]))
    assert u.added_from_secondary == 0

def test_a_secondary_only_deficit_is_a_qa_signal_not_a_mint():
    u = union_trades(_trades([1, 2, 3]), _trades([1, 2]))
    assert u.added_from_secondary == 0
    assert u.secondary_deficit == 1

def test_intra_stream_duplicate_ids_are_deduped_with_a_count_primary_wins():
    # a pre-T0037 archive hour (T0026 reconnect replay) genuinely contains duplicate trade_ids
    primary = pl.concat([_trades([1, 2]), _trades([2])])       # id 2 twice
    u = union_trades(primary, _trades([1, 2, 3]))
    assert u.frame["trade_id"].to_list() == ["1", "2", "3"]
    assert u.deduped_rows == 1
    assert u.added_from_secondary == 1

def test_union_is_idempotent():
    once = union_trades(_trades([1, 2]), _trades([1, 2, 3]))
    twice = union_trades(once.frame, _trades([1, 2, 3]))
    assert twice.added_from_secondary == 0
    assert twice.frame["trade_id"].to_list() == once.frame["trade_id"].to_list()
```

- [ ] **Step 2: Run to verify failure.** Run: `uv run pytest tests/test_archive_reconcile.py -k trades -v` → `ImportError: cannot import name 'union_trades'`

- [ ] **Step 3: Implement (append to `cli/archive/reconcile.py`)**

```python
@dataclass(frozen=True)
class TradeUnion:
    frame: pl.DataFrame
    added_from_secondary: int
    deduped_rows: int
    secondary_deficit: int


def union_trades(primary: pl.DataFrame, secondary: pl.DataFrame) -> TradeUnion:
    """Heal a primary trade deficit from the secondary. Row-level union is safe here (and ONLY
    here): `trade_id` is globally unique and identical across hosts (spec 00050 constraint 2).

    Ordered by `trade_id` — per-pair monotone, so the result is time-ordered and deterministic.
    Deduped with primary priority: the deployed writer dedups intra-hour at capture time (T0037),
    but pre-fix archive hours contain reconnect-replay duplicates (T0026) and this must handle
    history. A secondary-only deficit is a QA signal, never a reason to mint.
    """
    pri_ids = set(primary["trade_id"].to_list()) if primary.height else set()
    sec_ids = set(secondary["trade_id"].to_list()) if secondary.height else set()

    missing = sec_ids - pri_ids
    to_add = secondary.filter(pl.col("trade_id").is_in(list(missing))) if missing else secondary.head(0)

    combined = pl.concat([primary, to_add]) if to_add.height else primary
    before = combined.height
    deduped = combined.unique(subset=["trade_id"], keep="first", maintain_order=True).sort("trade_id")

    return TradeUnion(
        frame=deduped,
        added_from_secondary=len(missing),
        deduped_rows=before - deduped.height - len(missing) + len(missing),  # rows dropped as dupes
        secondary_deficit=len(pri_ids - sec_ids),
    )
```
> **Implementer note:** the `deduped_rows` expression above is deliberately written out rather than simplified — verify it against `test_intra_stream_duplicate_ids_are_deduped_with_a_count_primary_wins` and simplify to `before - deduped.height` if the test agrees. Do not guess; run it.

- [ ] **Step 4: Run to verify pass.** Run: `uv run pytest tests/test_archive_reconcile.py -v` → 15 passed.

- [ ] **Step 5: Commit** (`feat(archive): union trades by trade_id with idempotent dedup (spec 00050)`)

---

## Task 5: Mint — atomic write of a reconciled final, sidecar, provenance, ledger (TDD)

**Files:** Create `cli/archive/mint.py`; Test `tests/test_archive_mint.py`.

**Interfaces — Consumes:** `Block`, `Gap` (Tasks 2–3). **Produces:**
```python
def mint_hour(reconciled_root: Path, pair: str, kind: str, hour: datetime, blocks: list[Block],
              *, gaps_healed: list[Gap], residual_gaps: list[Gap], schema: dict,
              tool_version: str) -> Path        # returns the minted final's path
def ledger_append(reconciled_root: Path, record: dict) -> None
def already_minted(reconciled_root: Path, pair: str, kind: str, hour: datetime) -> bool
```

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_archive_mint.py
import json
from datetime import UTC, datetime
from pathlib import Path
import polars as pl
import pytest
from cli.archive.mint import already_minted, ledger_append, mint_hour
from cli.archive.reconcile import Block
from cli.capture.segment_writer import BOOK_SCHEMA, verify_manifest

H = datetime(2026, 7, 16, 9, tzinfo=UTC)

def _blocks(tmp_path):  # two blocks, primary then secondary
    f1 = pl.DataFrame({"ts": [H], "symbol": ["BTC/EUR"], "type": ["update"], "side": ["bid"],
                       "price": [1.0], "qty": [1.0], "checksum": [0]}, schema=BOOK_SCHEMA)
    f2 = f1.clone()
    return [Block("primary", f1, H, H), Block("secondary", f2, H, H)]

def test_mint_writes_a_verifiable_final_with_provenance(tmp_path):
    p = mint_hour(tmp_path, "BTC/EUR", "book", H, _blocks(tmp_path), gaps_healed=[],
                  residual_gaps=[], schema=BOOK_SCHEMA, tool_version="test")
    assert p == tmp_path / "BTC" / "EUR" / "book" / "2026" / "07" / "16" / "09.parquet"
    assert p.exists()
    assert verify_manifest(p) is True                       # sidecar matches the final's bytes
    prov = json.loads(p.with_name("09.provenance.json").read_text())
    assert [b["source"] for b in prov["blocks"]] == ["primary", "secondary"]
    assert prov["pair"] == "BTC/EUR" and prov["kind"] == "book"

def test_rows_land_in_block_order_never_sorted(tmp_path):
    p = mint_hour(tmp_path, "BTC/EUR", "book", H, _blocks(tmp_path), gaps_healed=[],
                  residual_gaps=[], schema=BOOK_SCHEMA, tool_version="test")
    assert pl.read_parquet(p).height == 2

def test_an_existing_minted_final_is_never_overwritten(tmp_path):
    mint_hour(tmp_path, "BTC/EUR", "book", H, _blocks(tmp_path), gaps_healed=[], residual_gaps=[],
              schema=BOOK_SCHEMA, tool_version="test")
    assert already_minted(tmp_path, "BTC/EUR", "book", H) is True
    with pytest.raises(FileExistsError):
        mint_hour(tmp_path, "BTC/EUR", "book", H, _blocks(tmp_path), gaps_healed=[],
                  residual_gaps=[], schema=BOOK_SCHEMA, tool_version="test")

def test_no_partial_state_is_left_if_the_mint_is_interrupted(tmp_path):
    # a torn temp file must never be published as a final
    d = tmp_path / "BTC" / "EUR" / "book" / "2026" / "07" / "16"
    d.mkdir(parents=True)
    (d / "09.parquet.tmp").write_bytes(b"garbage")
    p = mint_hour(tmp_path, "BTC/EUR", "book", H, _blocks(tmp_path), gaps_healed=[],
                  residual_gaps=[], schema=BOOK_SCHEMA, tool_version="test")
    assert verify_manifest(p) is True

def test_ledger_is_append_only_jsonl(tmp_path):
    ledger_append(tmp_path, {"state": "minted", "pair": "BTC/EUR"})
    ledger_append(tmp_path, {"state": "both_streams_silent", "pair": "ETH/EUR"})
    lines = (tmp_path / "reconcile-ledger.jsonl").read_text().splitlines()
    assert [json.loads(l)["state"] for l in lines] == ["minted", "both_streams_silent"]
```

- [ ] **Step 2: Run to verify failure.** Expected: `ModuleNotFoundError: No module named 'cli.archive.mint'`

- [ ] **Step 3: Implement `cli/archive/mint.py`**

```python
"""Write path for reconciled hours (spec 00050).

Mirrors `SegmentWriter`'s committed-final invariant exactly, because the overlay is verified by the
same `verify_tree`: the sidecar is written from the temp file's bytes (which ARE the final's bytes)
BEFORE the atomic rename, so a `<HH>.parquet` on disk always means "committed, complete, manifested".
An existing final is never overwritten — a re-run is a no-op, and a provisionally-residual hour is
healed by a NEW mint plus a superseding ledger record, never by mutating a published file.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path

import polars as pl

from cli.archive.reconcile import Block, Gap
# `_replace_durably` is module-private in the capture package. Importing it is a deliberate, narrow
# coupling: the overlay MUST use byte-identical durability semantics to the raw mirrors, and a second
# implementation would be a second thing to get wrong.
from cli.capture.segment_writer import _replace_durably


def _hour_dir(root: Path, pair: str, kind: str, hour: datetime) -> Path:
    base, quote = pair.split("/")
    return root / base / quote / kind / f"{hour:%Y}" / f"{hour:%m}" / f"{hour:%d}"


def already_minted(root: Path, pair: str, kind: str, hour: datetime) -> bool:
    return (_hour_dir(root, pair, kind, hour) / f"{hour:%H}.parquet").exists()


def ledger_append(root: Path, record: dict) -> None:
    root.mkdir(parents=True, exist_ok=True)
    with (root / "reconcile-ledger.jsonl").open("a") as fh:
        fh.write(json.dumps(record, default=str) + "\n")


def mint_hour(
    root: Path, pair: str, kind: str, hour: datetime, blocks: list[Block], *,
    gaps_healed: list[Gap], residual_gaps: list[Gap], schema: dict, tool_version: str,
) -> Path:
    d = _hour_dir(root, pair, kind, hour)
    final = d / f"{hour:%H}.parquet"
    if final.exists():
        raise FileExistsError(f"reconciled final already minted: {final}")
    d.mkdir(parents=True, exist_ok=True)

    frame = pl.concat([b.frame for b in blocks])          # block order; NEVER sorted
    tmp = d / f"{hour:%H}.parquet.tmp"
    frame.write_parquet(tmp, compression="zstd")

    digest = hashlib.sha256(tmp.read_bytes()).hexdigest()
    man_tmp = d / f"{hour:%H}.parquet.sha256.tmp"
    man_tmp.write_text(f"{digest}  {final.name}\n")
    _replace_durably(man_tmp, final.with_name(final.name + ".sha256"))

    prov = {
        "pair": pair, "kind": kind, "hour": hour.isoformat(),
        "blocks": [
            {"source": b.source, "rows": b.frame.height,
             "from_ts": b.from_ts, "to_ts": b.to_ts} for b in blocks
        ],
        "gaps_healed": [{"start": g.start, "end": g.end, "seconds": g.seconds} for g in gaps_healed],
        "residual_gaps": [{"start": g.start, "end": g.end, "seconds": g.seconds} for g in residual_gaps],
        "sha256": digest, "tool": "zcrypto archive reconcile", "version": tool_version,
    }
    prov_tmp = d / f"{hour:%H}.provenance.json.tmp"
    prov_tmp.write_text(json.dumps(prov, indent=1, default=str) + "\n")
    _replace_durably(prov_tmp, d / f"{hour:%H}.provenance.json")

    _replace_durably(tmp, final)                          # publish LAST
    return final
```

- [ ] **Step 4: Run to verify pass.** Run: `uv run pytest tests/test_archive_mint.py -v` → 5 passed.

- [ ] **Step 5: Commit** (`feat(archive): mint reconciled hours atomically with provenance (spec 00050)`)

---

## Task 6: `zcrypto archive reconcile` command + textfile exporter (TDD)

**Files:** Modify `cli/archive/command.py`; Create `cli/archive/settle.py` (settle rule + correlated-loss detection); Test `tests/test_archive_reconcile_command.py`.

**Interfaces — Produces:** the CLI contract
`zcrypto archive reconcile <primary_root> <secondary_root> <reconciled_root> [--window-hours 48] [--min-gap-seconds 30] [--textfile PATH] [--detect-only/--mint]`

**`--detect-only` is the DEFAULT until T0039's soak pins the threshold** — it ledgers what it *would* splice and mints nothing.

- [ ] **Step 1: Write the failing tests** — cover: settle rule (an hour younger than `H+2h` is skipped); `both_streams_silent` ledgered + never minted; `total_loss` (hour absent from both mirrors, later hours exist) ledgered; `--detect-only` writes ledger records with `state: "would_mint"` and creates **no** parquet; `--mint` mints; a re-run is a no-op; the textfile exposes every spec'd series; exit code 0 on success.

```python
def test_detect_only_is_the_default_and_mints_nothing(tmp_path, monkeypatch):
    # ... build a primary tree with a planted gap and a covering secondary ...
    result = CliRunner().invoke(app, ["archive", "reconcile", str(pri), str(sec), str(rec)])
    assert result.exit_code == 0
    assert not list(rec.rglob("*.parquet"))                      # nothing minted
    states = [json.loads(l)["state"] for l in (rec / "reconcile-ledger.jsonl").read_text().splitlines()]
    assert "would_mint" in states

def test_both_streams_silent_is_ledgered_and_never_minted(tmp_path):
    # every pair silent in BOTH streams for > threshold -> correlated loss, no witness, never splice
    ...
    assert "both_streams_silent" in states
    assert not list(rec.rglob("*.parquet"))
```

- [ ] **Step 2: Run to verify failure.** Expected: `Error: No such command 'reconcile'`

- [ ] **Step 3: Implement `cli/archive/settle.py`** — the hour-selection rule and the two unconditional correlated-loss detectors. These need **no secondary witness**, so they work even when both streams are dark (which is precisely when the witness-based gap detector cannot fire).

```python
"""Which hours are ready to reconcile, and the losses no witness can heal (spec 00050)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

SETTLE_HOURS = 2      # finalization + one pull cycle have both had time to land
LATE_MINT_HOURS = 6   # past this, a present secondary hour is minted even with the primary absent


def settled_hours(*, now: datetime, window_hours: int) -> list[datetime]:
    """The trailing window of hours old enough to be complete on both mirrors."""
    newest = now.replace(minute=0, second=0, microsecond=0) - timedelta(hours=SETTLE_HOURS)
    return [newest - timedelta(hours=i) for i in range(window_hours)]


def is_late(hour: datetime, *, now: datetime) -> bool:
    """Past the late deadline: a complete secondary hour may be minted even if the primary's is
    still absent — nothing arriving later can add coverage the secondary does not already have."""
    return now - hour >= timedelta(hours=LATE_MINT_HOURS)


def hour_path(root: Path, pair: str, kind: str, hour: datetime) -> Path:
    base, quote = pair.split("/")
    return root / base / quote / kind / f"{hour:%Y}" / f"{hour:%m}" / f"{hour:%d}" / f"{hour:%H}.parquet"


def classify_dual_silence(
    pairs_silent_in_both: list[str], *, total_pairs: int
) -> str | None:
    """`both_streams_silent` when EVERY pair is silent in both streams at once — at depth 100 that
    has no benign explanation, and no witness exists to heal it. Unconditional: it must not depend
    on the secondary being alive, because the case it detects is precisely both being dark."""
    if total_pairs and len(pairs_silent_in_both) == total_pairs:
        return "both_streams_silent"
    return None
```

- [ ] **Step 4: Implement the Typer command** in `cli/archive/command.py`

```python
@archive_app.command()
def reconcile(
    primary_root: Path = typer.Argument(..., help="The primary mirror (raw, canonical-by-default)."),
    secondary_root: Path = typer.Argument(..., help="The secondary mirror (raw)."),
    reconciled_root: Path = typer.Argument(..., help="The overlay: only healed hours are minted here."),
    window_hours: int = typer.Option(48, "--window-hours", help="Trailing hours to re-scan each cycle."),
    min_gap_seconds: float = typer.Option(
        30.0, "--min-gap-seconds",
        help="Primary silence above this, with the secondary alive inside, is a gap. Default 30 s is "
             "2x the measured 14.78 s max natural quiescence and is NOT yet validated cross-host (T0039).",
    ),
    textfile: Optional[Path] = typer.Option(None, "--textfile", help="Prometheus textfile to write."),
    mint: bool = typer.Option(
        False, "--mint/--detect-only",
        help="DEFAULT is --detect-only: ledger what would be spliced and mint nothing. Do not flip to "
             "--mint until T0039's soak has pinned --min-gap-seconds from real cross-host data.",
    ),
) -> None:
```

- [ ] **Step 5: Run the full suite + commit.** Run `uv run pytest -q` (expect green) and `uv run pre-commit run -a`.

- [ ] **Step 6: Update `README.md` `## Usage`** with the new subcommand (`.claude/rules/readme-usage.md` requires it in the same change).

---

## Task 7: `cli/archive/reader.py` + continuity overlay mode (TDD)

**Files:** Create `cli/archive/reader.py`; Modify `infra/scripts/continuity.py`; Test `tests/test_archive_reader.py`.

**Interfaces — Produces:**
```python
def canonical_segments(primary_root: Path, reconciled_root: Path | None = None,
                       *, kind: str = "book") -> Iterator[tuple[str, datetime, Path]]
```

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_archive_reader.py
from cli.archive.reader import canonical_segments

def test_a_reconciled_hour_wins_over_the_raw_primary(tmp_path):
    pri = tmp_path / "raw"; rec = tmp_path / "overlay"
    _final(pri, "BTC/EUR", "book", H)                 # raw hour
    _final(rec, "BTC/EUR", "book", H)                 # healed hour
    got = {h: p for _, h, p in canonical_segments(pri, rec)}
    assert got[H].is_relative_to(rec)                 # reconciled-first

def test_raw_hours_with_no_overlay_still_resolve(tmp_path):
    pri = tmp_path / "raw"
    _final(pri, "BTC/EUR", "book", H)
    assert len(list(canonical_segments(pri, None))) == 1

def test_a_stale_part_file_is_never_yielded(tmp_path):
    # THE T0038 TRAP: a bare **/*.parquet glob matches 09.part0003.parquet and double-counts the hour.
    pri = tmp_path / "raw"
    _final(pri, "BTC/EUR", "book", H)
    _part(pri, "BTC/EUR", "book", H, seq=3)
    assert len(list(canonical_segments(pri, None))) == 1

def test_held_and_corrupt_files_are_never_yielded(tmp_path):
    pri = tmp_path / "raw"
    _final(pri, "BTC/EUR", "book", H)
    _held(pri, "BTC/EUR", "book", H)
    assert len(list(canonical_segments(pri, None))) == 1
```

- [ ] **Step 2: Run to verify failure.** Expected: `ModuleNotFoundError: No module named 'cli.archive.reader'`

- [ ] **Step 3: Implement `cli/archive/reader.py`**

```python
"""The canonical read surface (spec 00050 D6).

Consumers must NOT glob `**/*.parquet` over the archive: that also matches `<HH>.part####.parquet`
(the live hour) and, on the NAS mirror, thousands of already-merged stale part files rsync never
deleted (T0038) — so the obvious glob silently reads a large fraction of the archive TWICE. For L2
book deltas that is not cosmetic: rows carry ABSOLUTE quantities, so a doubled delta stream
reconstructs a different book. This helper is the safe way in, and the strict final-name match makes
that whole class of bug structurally impossible.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

FINAL_NAME = re.compile(r"^\d{2}\.parquet$")   # <HH>.parquet — never .part/.held/.corrupt


def _hours(root: Path, kind: str) -> Iterator[tuple[str, datetime, Path]]:
    for p in sorted(root.glob(f"*/*/{kind}/*/*/*/*.parquet")):
        if not FINAL_NAME.match(p.name):
            continue
        parts = p.parts
        pair = f"{parts[-7]}/{parts[-6]}"
        hour = datetime(int(parts[-4]), int(parts[-3]), int(parts[-2]), int(p.stem), tzinfo=UTC)
        yield pair, hour, p


def canonical_segments(
    primary_root: Path, reconciled_root: Path | None = None, *, kind: str = "book"
) -> Iterator[tuple[str, datetime, Path]]:
    """Yield `(pair, hour, path)` for every canonical hour: reconciled-first, primary otherwise."""
    overlay = {}
    if reconciled_root is not None and reconciled_root.exists():
        overlay = {(pair, hour): p for pair, hour, p in _hours(reconciled_root, kind)}
    seen = set()
    for pair, hour, p in _hours(primary_root, kind):
        seen.add((pair, hour))
        yield pair, hour, overlay.get((pair, hour), p)
    for (pair, hour), p in sorted(overlay.items()):
        if (pair, hour) not in seen:      # a wholly-missing primary hour, healed from the secondary
            yield pair, hour, p
```

- [ ] **Step 4: Add `--overlay` to `infra/scripts/continuity.py` as a SEPARATE mode**

Default (no flag) stays **raw-only** — the T0003 exit bar must never see the overlay, which heals gaps by design and would therefore mask exactly the raw-capture regressions the bar exists to catch. Add a test asserting the default is off:

```python
def test_continuity_overlay_is_off_by_default():
    a = argparse.ArgumentParser(); add_args(a)
    assert a.parse_args(["/tmp/root"]).overlay is None     # exit-bar isolation
```

- [ ] **Step 5: Run + commit.** `uv run pytest tests/test_archive_reader.py -v` → 4 passed; full suite green.

---

> **D7 (retention of redundant secondary hours on the NAS) requires no task:** the decision is *keep indefinitely*. Both mirrors together grow ~0.96 GB/day on a 27 TB volume, and keeping them preserves the one thing the redundant stream is uniquely good for late — recovering from a *latent* primary-stream defect found after the fact (T0036 was discovered 5 days after it began destroying data).

## Task 8: Ansible — secondary host_vars, rrsync key, prune timer, reboot assert

- [ ] Create `infra/ansible/host_vars/zcrypto-red/vars.yml`: `base_unattended_upgrades_reboot_time: "22:25"`, `capture_memory_limit: "1g"` (the `2g` default is 100% of a 2 GB box and could OOM the OS), `capture_cpu_limit: "0.9"` (1 vCPU), `sync_capture_authorized_key: <the red pubkey>`.
- [ ] Create `infra/ansible/host_vars/zcrypto-red/vault.yml` (per-value `!vault`, names readable — same format as `group_vars/capture_host/vault.yml`): `ansible_host`, `capture_healthcheck_url` (a NEW healthchecks.io check).
- [ ] Generate the `sync_capture_red` ed25519 keypair into `infra/ansible/files/` (private half vaulted, `.pub` committed plain).
- [ ] Add `capture_retention_days: 14` + a `zcrypto-capture-prune` systemd timer to the `capture` role. It deletes only aged `<HH>.parquet` finals + `.sha256` sidecars; it must **never** touch `.part`, `.held`, or `.corrupt` (live hour, quarantine, evidence). Test with a fixture tree: young finals spared, aged finals deleted, quarantine untouched.
- [ ] Add a converge-time assert that the two hosts' reboot times differ (pins the fleet-window policy in config).
- [ ] **Do not add `zcrypto-red` to the inventory yet** — that is Task 9, and it must not converge the primary pre-bank.

---

## Task 9: Secondary bring-up (attended)

- [ ] Create the healthchecks.io check; add `zcrypto-red` to `capture_host` **only** (never `engine_host`).
- [ ] `bootstrap.yml` → `site.yml` **with `--limit zcrypto-red`** (the embargo: the prune timer / reboot assert must not converge the primary before the clean-run gate banks).
- [ ] Verify by outcome: 10/10 pairs flowing; dead-man green; **the running image digest == the primary's deployed digest** (`sha256:63708539…`) — a pre-T0008 image self-inflicts ~200 correlated desyncs/day that no splice can heal; `ssh red` works with the shared deploy key.

---

## Task 10: NAS — second pull channel, reconcile step, Alloy keep-regex (attended)

- [ ] Build + push the CLI image containing `archive reconcile`, and **re-pin the NAS compose digest** — the command does not exist in the currently-pinned image, so the reconcile step cannot be enabled before this.
- [ ] Drop the red key; append the red host key to the pinned `known_hosts`; add `CAPTURE_RED_SOURCE` / `CAPTURE_RED_DEST` / `CAPTURE_RED_SSH_KEY` / `RECONCILE_TEXTFILE` to `compose.yaml` + the README env-var contract.
- [ ] Extend `pull-entrypoint.sh`: pull red (same best-effort `if ! … continuing` shape), then run `zcrypto archive reconcile` — **skipped on any cycle whose capture pull exited non-zero** (a multi-hour pull outage must not mint "healed" full-secondary hours for primary data that arrives later; the skip keeps the ledger honest for free).
- [ ] **Extend the Alloy keep-regex** (`infra/nas/config.alloy`, ending `…|zcrypto_gate_.*`) with `|zcrypto_reconcile_.*`. Without this every new series is **silently dropped** and no rule can ever fire. (`|zcrypto_capture_.*` is inert future-proofing — `cli/capture/` emits no Prometheus metrics today.)
- [ ] Verify: both mirrors pull + verify (`checked=N ok=N failed=0`); `reconcile.prom` appears; **the new series are visible in Grafana Cloud BEFORE any rule is pushed**.

---

## Task 11: Grafana — Role C dashboard row + 4 alert rules

- [ ] Push only after Task 10's series are confirmed visible (else every rule evaluates against a non-existent metric).
- [ ] Rules: reconcile exporter stale; **residual gap increased** (permanent loss — page; also fired by `both_streams_silent`/`total_loss`); source lag high; **healed-gap rate high** (warn — a chronically gappy primary whose gaps the secondary keeps healing never trips residual-gap or its dead-man, yet is a degrading host; this discharges T0003's gap-rate-alert sub-item).
- [ ] **T0034 guard:** `grafana-push.sh` takes datasource UIDs as unvalidated env vars and **never prunes**. Pass the correct UIDs explicitly (`grafanacloud-prom` / `grafanacloud-logs`), and **read the rules back** after pushing to prove they point at the right datasources.

---

## Task 12: Detect-only soak → pin `--min-gap-seconds` (T0039)

- [ ] Soak ≥ 48 h with the reconciler in `--detect-only`. Ledger every `would_mint`.
- [ ] Plot the cross-host distribution on **healthy** hours: primary-silence duration vs secondary-activity-inside. Pin `--min-gap-seconds` above its tail; record the derivation in T0039 the way the single-host one is recorded.
- [ ] Only then flip to `--mint`. If coalescing-induced asymmetry is real, strengthen the secondary-activity guard from the data (e.g. require ≥ N secondary update rows) — **not** from first principles.

---

## Task 13: Drills (legs A + B) — discharges T0003's alerting drill

- [ ] Preconditions: the ≥7-day clean-run gate is **banked**; both streams green ≥ 48 h; refuse to run inside either reboot window (21:25 / 22:25 UTC ± margin).
- [ ] **Leg A (primary kill):** pre-check the secondary's newest **book row per pair is < 60 s old**; **arm the timed restore BEFORE the stop** (`systemd-run --on-active=900 --unit=zcrypto-capture-restore systemctl start zcrypto-capture`) so the primary restarts even if the SSH session dies; stop; assert the healthchecks.io check flips down **and the alert email arrives** (this observed page **is** T0003's drill item); restart after ≥10 min. Within ~2 h assert: the reconciled hour exists; provenance shows one secondary block spanning `[stop → restart snapshot]`; the **overlay's** continuity report shows zero gap while the **raw primary mirror** (the exit bar's only input) shows the full gap — the honesty check; `healed_gap_seconds` incremented ≈ outage × streams; `residual_gap_seconds` unchanged.
- [ ] **Leg B (secondary kill):** same fences; its check pages; canonical view unaffected. *A redundant stream that can die silently is not redundancy — leg B proves it can't.*
- [ ] Afterwards (attended, ops node, **fixed-image replayer**): CRC-replay the spliced hour end-to-end — checksums validating **across the block boundaries** empirically confirm the state-convergence corollary for the top-10.

---

## Task 14: Closeout

- [ ] T0003 → alerting drill + Role C done; gap-rate alert done; correct the stale 04:00-reboot and "Role C = NAS capture" text; keep the ansible-lint / `name[casing]` / `getent` sub-items explicitly listed as the open remainder.
- [ ] T0032 → retention half done; fix the stale "D9 / secondary-only" pointer (this spec prunes both hosts and has no D9); withhold-while-alive verification + probe-outage blind spot stay open.
- [ ] T0008 → cross-reference: the splice covers host-local stuck-pair silence, de-risking the parked remainder.
- [ ] T0039 → pinned value + derivation; T0038 → reader-helper cross-ref; T0027/T0028 → corrected figures; 00048 → correct the eviction non-goal rationale (reasoned from the 20×-wrong fill rate).
- [ ] `README.md` `## Usage` (`zcrypto archive reconcile`); `docs/iterations-history-phase1.md` entry.
