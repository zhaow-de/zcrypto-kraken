# VPS engine-journal retention — prune-after-verified-pull (spec 00070, T0021)

**Goal.** Bound the VPS engine journal at a 60-day local tail (owner ruling 2026-07-26, raised from an earlier 14 before deploy) without ever destroying gate evidence or perturbing order generation.

**Scope.** A daily systemd timer on the engine host (`zcrypto`) that deletes whole aged journal day-directories under `/var/lib/zcrypto-engine/journal`. Nothing else: capture's tree is untouched, the NAS archive is untouched, no CLI surface changes.

## The measurements this design rests on

| fact | measured 2026-07-26 |
| --- | --- |
| journal growth | 13 MB/day ≈ 0.38 GB/month |
| VPS free | 51 GB of 79 GB (32% used) ⇒ **~11 years** of headroom |
| journal today | 16 day-dirs, 197 MB |
| steady state at 60 d | ~780 MB — 1.5% of free space |
| NAS mirror completeness | **16 of 16 VPS days present — zero missing** |
| journal pull cadence | hourly; lag ceiling 4.10 h, alerted at 6 h (spec `00069`/T0069) |

Retention here is therefore **not** a capacity rescue — it is hygiene with a decade of slack. That framing is deliberate: it means the design may pay any amount of caution for safety, because there is no deadline forcing a cheaper choice.

## D1 — What "prune-after-verified-pull" resolves to

The topic asks that pruning run "only after the NAS's verified replay of the day succeeded". A literal mechanical handshake is rejected: the architecture is **pull-only** (the NAS pulls from the VPS over an `rrsync -ro` forced command, spec `00051` D10), so a NAS→VPS acknowledgement would require a new write-capable path *into the trade-key host*. Buying disk hygiene with a weakened trust boundary is the wrong trade.

The condition is instead satisfied by **margin plus monitoring**, and both are measured rather than assumed:

- **Margin.** A day is deletable only at age > 60 days. The NAS pulls hourly, so a day survives **~1,440 pull opportunities** before it becomes eligible.
- **Monitoring.** A pull outage long enough to threaten that margin is impossible to miss: `zcrypto_gate_journal_pull_lag_seconds` pages at 6 h (T0069), so 60 days of failed pulls would have paged ~240 times.
- **Verification at deploy.** Mirror completeness is checked before the timer is enabled (16/16 above), and re-checkable at any time by comparing day-dir sets.

This is written down as a deliberate, evidence-backed choice — not an oversight — so a future reader does not "fix" it by adding a callback channel.

## D2 — The keep-newest-N floor (the load-bearing guard)

`cli/engine/cycle.py:270` derives each cycle's orders as a delta against the most recent journaled cycle, located by globbing the journal tree. With **no** prior record, `prev_targets is None`, every delta becomes the full target, and the engine emits orders to establish the entire book from scratch ("the shadow book starts flat").

An age-only prune reaches that state in one scenario: **the engine stops for longer than the retention window.** Every day then exceeds 14 days, a naive sweep empties the journal, and the next start emits a full book instead of deltas. Shadow-mode today; real orders after go-live.

**The prune therefore always keeps the newest `retention_days` day-directories, regardless of age.** Both conditions must hold for deletion:

1. the directory's ISO date is strictly older than `today_utc − retention_days`, **and**
2. it is not among the newest `retention_days` directories present.

The floor counts **day-directories, not successfully journaled cycles** — a day whose cycles all failed still creates a dir (holding only `failed-cycle-HH.json` sidecars, which `cli/engine/cycle.py`'s `*/cycle-*.json` glob does not match). So 60 consecutive days of total cycle failure could still strand the lookup. That is not worth guarding against here: it requires two months of continuous failure that pages the whole time, and any guard would key on the same records the outage is failing to produce.

In healthy operation the two conditions coincide exactly. Under a stopped engine, (2) alone preserves the tail — the guard is inert until the day it is the only thing standing between a prune and a spurious book rebuild.

## D3 — What may be deleted, and the glob that is the safety argument

Only entire day-directories whose names match `20[0-9][0-9]-[0-9][0-9]-[0-9][0-9]` — the engine's own `%Y-%m-%d` layout. Anything else in the journal root is left untouched, unconditionally: an unexpected name is evidence something else is writing there, which is a reason to stop, not to sweep.

Deletion is recursive within a matched day-dir (it holds `cycle-HH.json`, `failed-cycle-HH.json` sidecars, `orders.jsonl`, and `snapshots/cycle-NN/*.parquet`) — the day is the unit the engine and the gate both reason about, so partial days are never produced.

Refusals, before any deletion: a non-existent journal dir; a system root (`/`, `/var`, `/var/lib`, `/usr`, `/etc`, `/home`); a non-integer or `< 1` retention.

## D4 — Cutoff by absolute date, never `-mtime`

The cutoff is computed as a **UTC calendar date** and compared against the directory's own parsed name, not against filesystem mtimes. Two reasons: `-mtime +N` truncates to whole days (a boundary a day fuzzier than the operator asked for), and mtimes are rewritten by any touch — including a restore or an rsync — while the directory *name* is the day's identity. The current UTC day can never satisfy `date < today − 60`, so it is excluded by construction rather than by a special case.

## D5 — Observability: a log line, and why that is the right answer here

The script prints one structured line: `zcrypto-engine-journal-prune: deleted=<n> kept=<n> retention_days=<n> cutoff="<date>" dir=<path>`, shipped to Loki by the capture-host Alloy's journal source. That is the whole observability story, matching the sibling `zcrypto-capture-prune` on the same host.

**It emits no metric, and that follows from the architecture rather than from laziness.** Since spec `00069` app metrics on this fleet come from **`/metrics` endpoints Alloy scrapes** (`capture_app` :9101, `engine_app` :9102) — which requires a *live process*. A daily oneshot exists for about a second; there is nothing to scrape. The fleet's mechanism for that class is the node-exporter textfile collector, and the ops node keeps one for exactly that reason (its four ephemeral timers). The capture/engine hosts deliberately run **none** (`roles/capture/files/config.alloy`), so a `.prom` written here would be read by nobody.

The gap that leaves — a timer that silently stops running emits no signal — **is already covered at the level that matters**. The failure mode is "the journal resumes growing at 13 MB/day against 51 GB free", and the *Capture · spool disk low* alert fires at <10% free on this same root filesystem. That alert is the honest backstop, not a hand-wave: it names the prune timers as the first thing to check. Building a bespoke metric to detect a condition that takes years to become visible, on a host whose disk is already alerted, would be ceremony.

The script still *supports* `--textfile` (and is tested for it) so the same binary serves a host that does have a collector — the ops node — without a rewrite. The unit simply does not pass it.

`--dry-run` prints and counts without deleting, so the first production run can be proven before it is armed.

## D6 — Systemd hardening and schedule

`ProtectSystem=strict` with `ReadWritePaths=` the journal dir only, plus `NoNewPrivileges`/`PrivateTmp`/`ProtectHome` — mirroring the capture prune, so a bug in the script *cannot* reach a path outside the journal even if its own globs were wrong. Structure, not promise.

Schedule **01:23 UTC daily**, `Persistent=true`: clear of the 4-hourly cycle boundaries (nearest is 00:00, 83 min away), clear of the capture prune on the same host (03:17), and clear of both maintenance windows (21:25 / 22:25).

## Out of scope

- Any durable-archive change: the NAS copy already is the archive (T0021's second next-step is answered — no compaction work is needed here).
- Tamper-evidence "across the prune boundary": the gate scores the **NAS** copy, so a VPS-local day that has been pulled is no longer evidence. Tampering with a pruned-or-prunable VPS day is invisible to the gate and equally harmless to it; nothing new is required.
- Retention for capture segments (already spec `00050` D8) and for the NAS archive (never pruned, by design).
