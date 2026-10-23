# B2 trial 8 — the daily long-side liquidation de-risk one threshold step up, at 3.0, on the A2-4h ensemble, on the frozen `ohlc-full` set

**Ruling:** the owner, attended, 2026-10-23. After reading 5 found no cell with potential (`[iter-186] B2's twelve crowding signals read for forward returns by tail where arm A is long below its full-long size on frozen ohlc-full (reading 5)`), the owner's family call and pick, verbatim: "hold B2, try the de-risk variant next". The controller then asked two questions. Which signal — the long-side liquidations of record 54, the funding of record 51, the open interest of record 52 or the ratios' maximum of record 53, each offered with its record's net loss — answered, verbatim: "Long-side liq (Recommended)". Which knob — the threshold one step up with the scale kept at 0.5, the scale 0.25 at the trial's threshold, both at once, or two trials under one spec — answered, verbatim: "Threshold up (Recommended)". The questions as first put misstated record 54's threshold as 2.0; record 54's metrics carry `threshold` 2.5, where spec 00138 D3's rule landed, so one step up is 3.0, not 2.5. The controller asked again with the step from 2.5, and the owner confirmed, verbatim: "3.0, scale 0.5 (Recommended)". The plan records the pick, the four answers and the correction as the decisions-log entry `[iter-187] B2's next step after the re-risk reading`, which resolves T0023's trigger. Standing and unchanged: the owner's instrument ruling "Frozen ohlc-full (Recommended)" (the first `[iter-181]` ruling entry), and, carried from trial 2 by spec 00138's ruling, the treatment "Unchanged (Recommended)" and the head-to-head read "From-2021 primary (Recommended)", read from the signal's own start (spec 00138 D8). The DSR leg binds at `var_trials` 0.0 by the owner's first `[iter-176]` ruling. Every call past those words and past what specs 00128, 00133, 00137 and 00138 fix is marked **Author's call** where it is made. **Iteration:** iter-187, branch `research/iter-187-b2-liq-derisk-threshold`. **Topic:** T0023 under T0016. **Goal:** pre-register B2's trial 8 — trial 5 (registry trial 54) one threshold step up: spec 00128's half-scale de-risk on the adopted A2-4h ensemble while the asset's daily long-side liquidation z-score exceeds 3.0, on record 54's instrument, signal, bar, arms, costing and matrix — as numbered decisions with code-level definitions, one committed research subject with its evaluate-only pre-flight twin, registered through `zcrypto research eval --register` and spec 00133's trial-attempts log. Spec 00138 is this spec's precedent and its form, frozen by record 54's `spec_hash` and not edited: its D2, D3, D6 and D8–D11 are carried here for one trial, each change named where it is made, and spec 00139's operating model and hash rule are the current form. The landed record spends one trial of Bucket B's shared budget: 14 remain today (`docs/open-topics/T0016-bucket-b-c-alpha-families.md`), 13 after.

## The measured basis

Every figure below was measured on 2026-10-23 in this branch's worktree at develop's `53e0b98c4`, before the subjects' code was written into it — the first program between 13:56:34Z and 13:57:40Z, the second at 13:57:56Z, the shell checks after them — with `data/ohlc-full` and `data/liquidations-daily` symlinked read-only from the main checkout's `data/` and the main checkout's `.local/trial-attempts.jsonl` read, never written: positions, scales, engagement counts and turnover only — no return of either arm, no head-to-head and no bar leg over the real data, and neither subject run over the real sets. Each program ran from the worktree root, `uv run python <it>`, and is pasted whole with its output.

The trial's program, the inputs half at 3.0 through `_b2_overlay_inputs` — the function the subject's build calls — and the same signal scaled at record 54's 2.5 beside it:

```python
import json
from datetime import UTC, datetime
from pathlib import Path

from cli.alpha.b2 import B2Config, derisk_scales, per_year_engaged_counts, per_year_positions_differ, scale_positions
from cli.registry.observed import ObservedReader
from cli.registry.record import compute_hash
from cli.research import subjects

print("start", datetime.now(UTC).isoformat(timespec="seconds"))
reader = ObservedReader(Path("data"))
inputs = subjects._b2_overlay_inputs("b2-liq-z3-derisk", subjects._b2_liq_signal, 3.0, reader, "ohlc-full", None, False)
close, arm_a, signal, n = inputs.close, inputs.arm_a, inputs.signal, len(inputs.close)
block = reader.block()
print("block", compute_hash(block), {d: (len(e["files"]), e["rows"], e["span"]) for d, e in block.items()})
print("vouched", reader.vouched_status())
start = subjects._b2_overlay_start(inputs)
print(f"return indices {n}; the signal's own start: index {start}, close {close[start]}, returns from it {n - start}")
held = {a: sum(p > 0 and z is not None for p, z in zip(arm_a[a], signal[a])) for a in subjects._ASSETS}
print(f"arm A's long asset-stamps {sum(p > 0 for a in subjects._ASSETS for p in arm_a[a])}; where the signal is defined {sum(held.values())}, per asset {held}")
print("signal exactly at 2.5 or 3.0 at a long stamp:", sum(p > 0 and z in (2.5, 3.0) for a in subjects._ASSETS for p, z in zip(arm_a[a], signal[a])))
print("the rule's pick on this block:", subjects._b2_engagement_threshold(signal, arm_a))
turnover_a = subjects.book_turnover(arm_a)
engaged_at = {}
for t in (2.5, 3.0):
    scales = derisk_scales(signal, config=B2Config(z_threshold=t))
    engaged = {a: sum(p > 0 and s < 1 for p, s in zip(arm_a[a], scales[a])) for a in subjects._ASSETS}
    total = sum(engaged.values())
    from_start = sum(arm_a[a][k] > 0 and scales[a][k] < 1 for a in subjects._ASSETS for k in range(start, n))
    entries = {
        a: sum(arm_a[a][k] > 0 and scales[a][k] < 1 and not (k and arm_a[a][k - 1] > 0 and scales[a][k - 1] < 1) for k in range(n))
        for a in subjects._ASSETS
    }
    arm_b = scale_positions(arm_a, scales)
    differ = per_year_positions_differ(arm_a, arm_b, close)
    turnover_b = subjects.book_turnover(arm_b)
    print(f"--- threshold {t}")
    print(f"  engaged {total} of {sum(held.values())} long asset-stamps where the signal is defined ({100 * total / sum(held.values()):.2f} %); before the start {total - from_start}, from it {from_start}")
    print(f"  per asset {engaged}")
    print(f"  share per asset { {a: round(100 * engaged[a] / held[a], 2) for a in subjects._ASSETS} }")
    print(f"  per close year {per_year_engaged_counts(arm_a, scales, close)}")
    print(f"  entries {sum(entries.values())}, per asset {entries}; asset-stamps per entry {total / sum(entries.values()):.2f}")
    print(f"  closes where the books differ {sum(differ.values())}; turnover A {turnover_a!r} B {turnover_b!r}, B over A {100 * (turnover_b / turnover_a - 1):.2f} %")
    print(f"  added turnover {turnover_b - turnover_a:.4f}, its cost at 0.006 per side {0.006 * (turnover_b - turnover_a):.4f} in per-bar return summed")
    engaged_at[t] = {(a, k) for a in subjects._ASSETS for k in range(n) if arm_a[a][k] > 0 and scales[a][k] < 1}
print("every asset-stamp engaged at 3.0 is engaged at 2.5:", engaged_at[3.0] <= engaged_at[2.5])
engagement = subjects._b2_overlay_engagement(inputs, "binperp_liq_long_z30d")
record_54 = json.loads(Path("docs/reference/trial-registry.jsonl").read_text().splitlines()[53])
print("the subject's engagement at 3.0:", {k: engagement[k] for k in ("engaged_per_asset", "engaged_per_year", "primary_returns", "threshold")})
print("its coverage equals record 54's:", engagement["binperp_liq_long_z30d_coverage"] == record_54["metrics"]["binperp_liq_long_z30d_coverage"], "; record 54's block:", record_54["dataset_hash"])
print("end", datetime.now(UTC).isoformat(timespec="seconds"))
```

Its output, whole:

```text
start 2026-10-23T13:56:34+00:00
block 816f62f931468b96f39f6fcbbdbfeee5124fa64fb062a98554895870de30474f {'liquidations-daily': (10, 15048, ['2022-08-25 00:00:00+00:00', '2026-10-20 00:00:00+00:00']), 'ohlc-full': (10, 173373, ['2013-09-10 20:00:00+00:00', '2026-03-31 20:00:00+00:00'])}
vouched {'ohlc-full': 'checked (36 vouched hashes)', 'liquidations-daily': 'checked (10 vouched hashes)'}
return indices 27337; the signal's own start: index 19731, close 2022-10-11 00:00:00+00:00, returns from it 7606
arm A's long asset-stamps 93462; where the signal is defined 41332, per asset {'ADA': 3786, 'AVAX': 3884, 'BTC': 4588, 'DOGE': 4176, 'DOT': 4012, 'ETH': 4259, 'LINK': 4192, 'LTC': 4201, 'SOL': 4391, 'XRP': 3843}
signal exactly at 2.5 or 3.0 at a long stamp: 0
the rule's pick on this block: 2.5
--- threshold 2.5
  engaged 1750 of 41332 long asset-stamps where the signal is defined (4.23 %); before the start 0, from it 1750
  per asset {'ADA': 162, 'AVAX': 181, 'BTC': 166, 'DOGE': 227, 'DOT': 161, 'ETH': 168, 'LINK': 151, 'LTC': 185, 'SOL': 168, 'XRP': 181}
  share per asset {'ADA': 4.28, 'AVAX': 4.66, 'BTC': 3.62, 'DOGE': 5.44, 'DOT': 4.01, 'ETH': 3.94, 'LINK': 3.6, 'LTC': 4.4, 'SOL': 3.83, 'XRP': 4.71}
  per close year {'2013': 0, '2014': 0, '2015': 0, '2016': 0, '2017': 0, '2018': 0, '2019': 0, '2020': 0, '2021': 0, '2022': 79, '2023': 635, '2024': 491, '2025': 485, '2026': 60}
  entries 273, per asset {'ADA': 25, 'AVAX': 27, 'BTC': 28, 'DOGE': 31, 'DOT': 27, 'ETH': 29, 'LINK': 22, 'LTC': 28, 'SOL': 28, 'XRP': 28}; asset-stamps per entry 6.41
  closes where the books differ 822; turnover A 146.18534602048504 B 152.683741195202, B over A 4.45 %
  added turnover 6.4984, its cost at 0.006 per side 0.0390 in per-bar return summed
--- threshold 3.0
  engaged 1080 of 41332 long asset-stamps where the signal is defined (2.61 %); before the start 0, from it 1080
  per asset {'ADA': 102, 'AVAX': 109, 'BTC': 109, 'DOGE': 155, 'DOT': 84, 'ETH': 78, 'LINK': 109, 'LTC': 106, 'SOL': 108, 'XRP': 120}
  share per asset {'ADA': 2.69, 'AVAX': 2.81, 'BTC': 2.38, 'DOGE': 3.71, 'DOT': 2.09, 'ETH': 1.83, 'LINK': 2.6, 'LTC': 2.52, 'SOL': 2.46, 'XRP': 3.12}
  per close year {'2013': 0, '2014': 0, '2015': 0, '2016': 0, '2017': 0, '2018': 0, '2019': 0, '2020': 0, '2021': 0, '2022': 67, '2023': 362, '2024': 363, '2025': 252, '2026': 36}
  entries 174, per asset {'ADA': 17, 'AVAX': 17, 'BTC': 19, 'DOGE': 22, 'DOT': 14, 'ETH': 14, 'LINK': 17, 'LTC': 16, 'SOL': 18, 'XRP': 20}; asset-stamps per entry 6.21
  closes where the books differ 566; turnover A 146.18534602048504 B 150.3168010079799, B over A 2.83 %
  added turnover 4.1315, its cost at 0.006 per side 0.0248 in per-bar return summed
every asset-stamp engaged at 3.0 is engaged at 2.5: True
the subject's engagement at 3.0: {'engaged_per_asset': {'ADA': 102, 'AVAX': 109, 'BTC': 109, 'DOGE': 155, 'DOT': 84, 'ETH': 78, 'LINK': 109, 'LTC': 106, 'SOL': 108, 'XRP': 120}, 'engaged_per_year': {'2013': 0, '2014': 0, '2015': 0, '2016': 0, '2017': 0, '2018': 0, '2019': 0, '2020': 0, '2021': 0, '2022': 67, '2023': 362, '2024': 363, '2025': 252, '2026': 36}, 'primary_returns': 7606, 'threshold': 3.0}
its coverage equals record 54's: True ; record 54's block: 816f62f931468b96f39f6fcbbdbfeee5124fa64fb062a98554895870de30474f
end 2026-10-23T13:57:40+00:00
```

What it establishes:

- **The block is record 54's**: `ohlc-full`'s ten 4h files (173,373 rows, 2013-09-10 20:00 → 2026-03-31 20:00) beside `liquidations-daily`'s ten (15,048 rows, 2022-08-25 → 2026-10-20), `compute_hash` `816f62f931468b96f39f6fcbbdbfeee5124fa64fb062a98554895870de30474f`, record 54's `dataset_hash`; `vouched_status` reads `checked (36 vouched hashes)` and `checked (10 vouched hashes)`.
- **The signal and its start are record 54's**: `_b2_liq_signal` over the frozen union's 27,337 return indices, every asset's signal held from index 19,731, close 2022-10-11 00:00, 7,606 returns to the window's end; its per-asset, per-close-year coverage equals record 54's stored `binperp_liq_long_z30d_coverage`. No engagement falls before that start at either threshold, so the primary read holds every engaged stamp.
- **The inputs half reproduces record 54 at 2.5**: 1,750 engaged long asset-stamps (2022 79, 2023 635, 2024 491, 2025 485, 2026 60), the books differing at 822 closes, and arm B's turnover 152.683741195202 against arm A's 146.18534602048504 — record 54's stored `engaged_per_year`, `stamps_positions_differ`, `turnover_b` and `turnover_a`; spec 00138 D3's rule picks 2.5 on this block.
- **The engagement at 3.0 against 2.5**: of arm A's 93,462 long asset-stamps, 41,332 hold the signal; 1,080 of them exceed 3.0 (2.61 %), every one among the 1,750 above 2.5 (4.23 %). Per asset 78 (ETH, 1.83 %) to 155 (DOGE, 3.71 %) against 151 (LINK) to 227 (DOGE); per close year 2022 67, 2023 362, 2024 363, 2025 252 and 2026 36 against 79, 635, 491, 485 and 60. No signal value at a long stamp equals 2.5 or 3.0, so "strictly above" decides no stamp.
- **The de-risks and the turnover**: 174 entries at 3.0 against 273 at 2.5 — an entry an engaged asset-stamp whose asset was not engaged at the close before — 6.21 and 6.41 engaged asset-stamps an entry, about the six closes a day's figure is held; the books differ at 566 closes against 822. Arm B's turnover is 150.3168010079799, 2.83 % above arm A's against record 54's 4.45 %: the turnover the de-risk adds is 4.1315 against 6.4984, its cost at 0.006 per side 0.0248 against 0.0390 in per-bar return summed over the 27,337 returns — the cost arm B carries into the head-to-head before any return of its own.

The count, the run's time and the name, a second program:

```python
import json
from datetime import UTC, datetime
from pathlib import Path

from cli.registry import attempts, budget
from cli.research import subjects
from tests.retired_subjects import RETIRED_SUBJECTS

print("read at", datetime.now(UTC).isoformat(timespec="seconds"))
lines = [json.loads(x) for x in open("/home/zhaow/Projects/zcrypto-kraken/.local/trial-attempts.jsonl")]
landed = attempts.files_landed(Path("docs/reference/trial-registry.jsonl"), Path("docs/reference/reading-ledger.jsonl"))
c = attempts.reconcile(lines, landed, log_id=lines[0]["log_id"], bucket_of=budget.BUCKET_OF)
print({f: sum(r["family"] == f for r in c.records) + sum(o.family == f for o in c.orphans) for f in ("B1", "B2")}, "remain", budget.BUDGET["B"] - c.spent("B"), [o.describe() for o in c.orphans])
print("required_n('B2')", c.required_n("B2"), "; B2 records", [r["trial_id"] for r in c.records if r["family"] == "B2"])
print("open attempts (a begin with no end):", sorted({x["attempt"] for x in lines if x["kind"] == "begin"} - {x["attempt"] for x in lines if x["kind"] == "end"}))
for attempt in (6, 7, 8):
    begin = next(x for x in lines if x["kind"] == "begin" and x["attempt"] == attempt)
    end = next(x for x in lines if x["kind"] == "end" and x["attempt"] == attempt)
    took = datetime.fromisoformat(end["timestamp"]) - datetime.fromisoformat(begin["timestamp"])
    print(f"attempt {attempt} ({begin['invocation']['subject']}): begin {begin['timestamp']}, end {end['timestamp']}, {took.total_seconds():.0f} s, failed {end['failed']}")
names = set(subjects.SUBJECTS) | RETIRED_SUBJECTS
for new in ("b2-liq-z3-derisk", "b2-liq-z3-derisk-preflight"):
    print(new, "equals or opens with a hyphen:", sorted(x for x in names if new == x or new.startswith(f"{x}-")), "; it opens:", sorted(x for x in names if x.startswith(f"{new}-")))
print("b2-liq-derisk-z3 equals or opens with a hyphen:", sorted(x for x in names if "b2-liq-derisk-z3" == x or "b2-liq-derisk-z3".startswith(f"{x}-")))
```

Its output, whole:

```text
read at 2026-10-23T13:57:56+00:00
{'B1': 5, 'B2': 6} remain 14 []
required_n('B2') 7 ; B2 records [51, 52, 53, 54, 55, 56]
open attempts (a begin with no end): []
attempt 6 (b2-liq-derisk): begin 2026-10-21T16:30:26.980038+00:00, end 2026-10-21T16:34:28.520591+00:00, 242 s, failed None
attempt 7 (b2-liq-reentry): begin 2026-10-22T04:50:02.278641+00:00, end 2026-10-22T04:54:22.165544+00:00, 260 s, failed None
attempt 8 (b2-funding-reentry): begin 2026-10-22T05:17:03.809333+00:00, end 2026-10-22T05:21:28.010749+00:00, 264 s, failed None
b2-liq-z3-derisk equals or opens with a hyphen: [] ; it opens: []
b2-liq-z3-derisk-preflight equals or opens with a hyphen: [] ; it opens: []
b2-liq-derisk-z3 equals or opens with a hyphen: ['b2-liq-derisk']
```

- **The count**: the registry holds B2's records 51–56 and the trial-attempts log no orphan and no open attempt, so `required_n("B2")` is 7 — the six landed records and this trial — the count this trial declares (D4); bucket B has spent 11 of 25 (B1 5, B2 6), 14 remaining, 13 once this trial's record lands.
- **The run's time**: record 54's `--register` run took 242 s from its attempt's `begin` line to its `end` (attempt 6 of log `60c9f39c`), the re-entries' 260 s and 264 s. This trial's run is record 54's build at another constant and count, so about four minutes, one process well under 600 s; its pre-flight computes one kill bar where the trial computes seven, so less.
- **The name**: no registered or retired subject's name equals `b2-liq-z3-derisk` or `b2-liq-z3-derisk-preflight` or opens either with a hyphen, and neither opens one; `b2-liq-derisk-z3`, the name record 54's would take with the threshold appended, opens with the retired `b2-liq-derisk` and a hyphen (D5).

Spec 00138 frozen, and arm A's code path since record 54's run:

```text
$ sha256sum docs/specs/00138-b2-three-overlays-design.md; python3 -c 'import json; r = json.loads(open("docs/reference/trial-registry.jsonl").read().splitlines()[53]); print("record", r["trial_id"], r["spec_hash"], r["invocation"]["commit"])'
252359f8ebcc15edadf08c321015bd57ddc92e873196949a66e7ee09095280a4  docs/specs/00138-b2-three-overlays-design.md
record 54 252359f8ebcc15edadf08c321015bd57ddc92e873196949a66e7ee09095280a4 32b8edd0b6095db2133fa792cfac2f3514ed9e72
$ git log --oneline 32b8edd0b6095db2133fa792cfac2f3514ed9e72..HEAD -- cli/alpha cli/features cli/portfolio cli/benchmark cli/validation cli/backtest cli/research/subjects.py cli/registry cli/ohlc cli/derivatives cli/liquidations cli/data uv.lock pyproject.toml .python-version | cat
53e0b98c4 build(deps): Bump websockets from 17.2 to 17.3 (#753)
194c3bc06 feat(research): B2's re-risk reading — the twelve crowding signals' forward returns by tail where arm A is long below its full-long size, on a frozen set's full history
a16c99393 feat(research): arm A's full-long size rebuilt beside reading 3's arm A, and the flags and counts of the state below it, for B2's re-risk reading
6bdfd3d69 docs: the pre-review's eight sites -- the OI z-scores', block draw's, block contrast's and inputs' docstrings trimmed, two fixture comments trimmed or cut, and the conventions entry's floor clause naming each thin cell's state
2eeee8346 feat(research): B2's second signal reading — the eight untested crowding signals' forward returns by tail and by arm A's state on a frozen set's full history
3ca6e2eee feat(alpha): the OI change's and momentum's z-scores on the OI grid, the stationary-bootstrap draw held as its blocks, and the block contrast at the far percentiles it is given
ea7395f47 docs: the pre-review's eight sites -- the subjects module's docstring names readings beside records and trials, the reading's docstrings trimmed to what the code does not say, two restated comments cut, and spec 00140's chunked-twin sentence measured
82cc3f343 feat(research): B2's signal reading — the four trialled crowding signals' forward returns by tail and by arm A's state on a frozen set's full history
7f38030f4 feat(alpha): the chunked event contrast — event_contrast's rows over the same resamples, a chunk at a time, with its far bounds
018b4b183 docs: the pre-review's six sites -- four comments of the re-entry machinery trimmed to what the code does not say, a fixture comment the lists repeat cut, and the plan's conventions-entry item 2 as committed
efd544869 feat(research): B2 trials 6–7's subjects — the liquidation-cascade and funding-extreme re-entries and their pre-flight twins on a frozen set's full history
2048d92f3 feat(alpha): the B2 re-entry's full-long size, its positions held a day from the trigger, and their per-year count
$ git show --stat --format="%h %s" 53e0b98c4 | cat
53e0b98c4 build(deps): Bump websockets from 17.2 to 17.3 (#753)

 pyproject.toml |  2 +-
 uv.lock        | 92 +++++++++++++++++++++++++++++-----------------------------
 2 files changed, 47 insertions(+), 47 deletions(-)
```

- **Spec 00138 is frozen**: its sha256 is record 54's `spec_hash`; it is not edited.
- **Arm A's code path since record 54's run** at `32b8edd0b`: spec 00139's re-entries and specs 00140–00142's readings, each adding functions to `cli/alpha/b2.py` and `cli/research/subjects.py` and changing none (each spec's closed list), and the websockets bump, `pyproject.toml` and `uv.lock` alone. The 2.5 block above, record 54's figures each, shows the inputs half unmoved; the pre-flight's (b) reads arm A's returns before the run (D6).

## Operating model

- **One session, one machine.** Four named sessions share the repository (`docs/reference/multi-agent-protocol.md`); this trial runs under one, the session holding this branch's worktree, `.claude/worktrees/iter187`, on the workstation `zcrypto-ops`, whose main checkout holds the one listed trial-attempts log (`docs/reference/trial-attempt-logs.txt`). No other session runs a bucket-B subject while this branch is open — the ruled subjects outside this spec are frozen by their landed counts, refused by spec 00133 D4 before their fit — no second machine and no restored or copied log; each of those is spec 00133's to count and refuse, not this spec's to design for.
- **The processes.** The pre-flight and the trial are each one `uv run zcrypto research eval` process in this worktree, awaited to its exit, one at a time — no daemon, timer or concurrent run, and no step reads a run as ended while its process lives. Both read `data/ohlc-full` and `data/liquidations-daily`, symlinks to the main checkout's sets, each frozen and attested; a run writes nothing under them and makes no network call, and nothing this spec runs has a live writer.
- **The trial-attempts log** — `.local/trial-attempts.jsonl` in the main checkout, shared by every worktree and appended under its flock (spec 00133 D1); an attempt is identified by (log id, attempt id, its `begin` line's hash), open from its `begin` line to its `end` line, alive while its recorded `pid` runs under its recorded boot (spec 00133 D2, D3).
- **The registry and the reading ledger** — tracked, append-only, hash-chained; this worktree is their one writer while the branch is open. `--register` refuses a tree with uncommitted changes, so the record is committed with its decisions-log entry and landed-count literal before anything else lands (D6).

## Hypothesis (trial 8, pre-registered by this spec's sha256)

Spec 00138's trial 5, one threshold step up: a day of forced selling of leveraged longs in the perpetual flags a boundary where the spot book's long in that asset carries more downside than the ensemble's trend signal prices, so **halving the asset's position while the 30-day z-score of its daily long-side liquidated notional exceeds 3.0 improves the ensemble's net-of-cost performance, through a lower drawdown at the engaged stamps, against the unconditioned ensemble.** Arm A is the adopted equal-weight three-arm A2-4h ensemble exactly as records 45, 46 and 48–56 built it; arm B the same ensemble through the overlay. What 3.0 changes from trial 5 is how rare "extreme" is: the de-risk acts at 1,080 of record 54's 1,750 engaged long asset-stamps, the days past three sigma, and adds 2.83 % to arm A's turnover where record 54 added 4.45 % (the measured basis). The trial is judged by D4's matrix on its own record; what its verdict changes is D7's.

**The contamination, stated.** This trial is no independent look. Its instrument, signal, arm A, bar and matrix are record 54's, and its engaged stamps a subset of record 54's. It was picked after record 54's REJECT — matrix row 3: from the signal's start its head-to-head against arm A negative (`head_to_head_spa_p_primary` 0.9835082458770614), its maximum drawdown 0.76 % below arm A's — and after readings 3–5, none of which found a cell with potential: reading 3 read this signal's upper tail with arm A long, every horizon carrying a re-risk's sign, and reading 5 below arm A's full-long size, every horizon a de-risk's; reading 4 read the short side's and the total's. Its threshold is record 54's pre-registered park variant (spec 00138 D8's park row, "the threshold one step up — 3.0 from 2.5"; record 54's notes, "park variants, pre-registered: scale 0.25, threshold 3.0"), chosen by the owner under "hold B2" with those results known. Its count is the family's true count, 7 — records 51–56 and this one — the three readings' looks in its design (spec 00142 D8); at `var_trials` 0.0 the count moves no figure of the bar (D2).

## D1 — the pick: one trial, the long-side liquidation de-risk at 3.0, scale 0.5

- The owner's four answers (the Ruling): B2 held, the de-risk variant next; record 54's signal, the daily long-side liquidations; the threshold one step up; 3.0 with the scale kept at 0.5. One iteration, one branch, this spec and its plan, one plan review, one task loop; one trial subject with its pre-flight twin, one bar, one matrix, one record.
- The alternatives offered and set aside: as the signal, the funding of record 51, the open interest of record 52 or the ratios' maximum of record 53 — the decisions log's `[iter-184]` entry sums records 51–54's gross over the 27,337 returns at −0.046, −0.092, −0.033 and −0.023, record 54's the smallest loss of the four de-risks; as the knob, the scale 0.25 at record 54's 2.5, both knobs at once, or two trials under one spec, each its own B slot.
- The budget: the landed record spends one of Bucket B's 14 remaining (spec 00133 D5; `BUDGET["B"]` 25, B1 5 and B2 6 spent); a stop, a refused build or a refusal from the count spends none.

## D2 — the instrument, its windows and the bar: record 54's unchanged

- Spec 00138 D2, carried: `--dataset ohlc-full`, no `--window`, no `--as-of`; the union `_capturing_union(reader, "ohlc-full", 240, None, None, False)`, 27,338 stamps, 27,337 return indices; the arms on `_ffill_btc`'s BTC-only fill, the benchmark on the raw prices; `decisive_start = 1380`; `calendar_year_slices(series, h4_ts)` with `STUB_YEARS = (2013, 2026)` dropped; the frozen benchmark `benchmark_4h_net_of_cost(h4_prices, cost_per_side=0.006)`; the kill bar `a1_kill_bar(net_b, bench, n_trials=7, var_trials=0.0, mean_block=30, seed=42, cost_stressed_returns=net_b_x15, regime_slices=calendar_year_slices(net_b, h4_ts), benchmark_slices=calendar_year_slices(bench, h4_ts), decisive_start=1380, n_resamples=2000)`, the SPA grid blocks {30, 102} × seeds {42, 7, 1234}, the headline cell (30, 42), the five others recorded and never read; every net through `net_of_cost` at 0.006 per side, the ×1.5 series at `1.5 × 0.006`.
- `var_trials` 0.0 by the owner's word, so the DSR leg is the PSR against 0 at every count: `dsr_pass` needs an annualised net Sharpe above 0.466 over the 27,337 returns (spec 00138's measured basis); the count (D4) moves no figure of the bar, and this spec claims no deflation from it.
- Arm A and its pre-flight are spec 00138 D2's: the three adopted A2 arms (`_B2_A2_ARMS`), `short="off"`, vol and basket lookback 180, 2,190 periods a year, their equal-weight per-asset mean, built by `_b2_overlay_inputs`' own expression; arm A's bar the same call on `net_a` at (30, 42), read `passes` 1 at the pre-flight (D6).

## D3 — the treatment, the signal and the threshold

- **The treatment**, spec 00138 D3's: at return index `k`, for asset `a`, arm B's position is `0.5 ×` arm A's where the signal is not `None` and strictly above 3.0, else arm A's — `derisk_scales(signal, config=B2Config(z_threshold=3.0))` and `scale_positions`, the scale 0.5 `B2Config`'s default; no hold-through, each de-risk and re-risk a trade charged 0.006 per side; a `None` leaves the position unchanged; the ensemble is long-only, so a rule for shorts is inert.
- **The signal**, spec 00138 D6's, unchanged: `_b2_liq_signal(reader, h4_ts)`, keyed `binperp_liq_long_z30d` — per coin `daily_zscore_grid_feature(rows["ts"], rows["long_usd"], h4_ts)` over `liquidations-daily/<COIN>/daily.parquet` read whole, the 30-day z-score of the day's long-side liquidated notional, a lower bound, read from the first close at or after the day ends; the same attested block record 54 read (the measured basis).
- **Author's call — 3.0 a pre-registered constant, `_B2_LIQ_Z3_THRESHOLD`, not spec 00138 D3's rule.** The rule chooses between 2.0 and 2.5 and picks 2.5 on this block (measured), so applied here it would re-run record 54; the owner's 3.0 is spec 00138 D8's park row's "one step up — 3.0 from 2.5", record 54's pre-registered variant. A constant, as the OI and ratio legs' thresholds are (spec 00138 D3), fixed by this spec's sha256 before any arm B is computed and recorded as `threshold`; a change after a result is a new trial. Measured, it engages 2.61 % of the long stamps where the signal is defined, further from trial 2's 4.93 % than 2.5's 4.23 %: the owner's knob reads "extreme" rarer than the rule's aim, which is the variant's question.
- **The scale 0.5**, the owner's "scale 0.5": the scale 0.25 is a park variant (D4), never this trial's.

## D4 — the head-to-head from the signal's own start, the bar, the drawdown pair, the matrix and the count

- **The signal's own start**, spec 00138 D8's: `_b2_overlay_start(inputs)`, the first return index at which every asset's signal is defined — 19,731, close 2022-10-11 00:00, 7,606 returns, record 54's, every engaged stamp at or after it (measured) — recorded as `primary_returns`.
- **The head-to-head**: `net_of_cost_verdict(net_b[start:], net_a[start:], mean_block=30, seed=42, n_resamples=2000)`, primary, keyed `head_to_head_mean_outperf_primary` and `head_to_head_spa_p_primary`; the full window beside it, `head_to_head_mean_outperf_full` and `head_to_head_spa_p_full`.
- **The drawdown pair**, from the start: `max_drawdown(net_b[start:])`, `max_drawdown(net_a[start:])` and `max_drawdown_reduction_pct = 100 × (A − B) / A`; B's below A's when the reduction exceeds 1e-6.
- **Refused before any bar**, spec 00138 D8's two: fewer than 2 return indices carrying every asset's signal, and an arm A that never draws down from the start.
- **The matrix**, spec 00138 D8's, its park variants an **Author's call**:

| Kill bar (B vs frozen benchmark) | Head-to-head (B vs A, from the signal's own start) | Verdict |
| --- | --- | --- |
| pass | B beats A (mean outperformance > 0 and SPA p < 0.05) and B's maximum drawdown below A's | **adopt** the overlay |
| pass | B > A point estimate, SPA n.s., and B's maximum drawdown below A's | **park** (variant candidates: the scale 0.25 at 3.0; the threshold 3.5) |
| pass | B ≤ A (mean outperformance ≤ 0), or B's maximum drawdown not below A's | **reject** the overlay |
| fail | any — arm A having passed the same bar before the run | **reject** |

  The rows are disjoint and cover every outcome. **Author's call — the rule is `_b2_overlay_verdict` itself**, the function record 54's subject declares, unchanged, so the matrix is record 54's to the line and its plan's row tests its proof:

```python
def _b2_overlay_verdict(m: dict) -> str | None:
    if not m["arm_a_passes"] or not any(m["engaged_per_year"].values()):
        return None
    if not m["passes"]:
        return "reject"
    if m["head_to_head_mean_outperf_primary"] > 0 and m["max_drawdown_reduction_pct"] > 1e-6:
        return "adopt" if m["head_to_head_spa_p_primary"] < 0.05 else "park"
    return "reject"
```

- **The count**: 7, `_B2_LIQ_Z3_N_TRIALS` — the family's true count with this trial, `required_n("B2")` measured 7 from the registry and the trial-attempts log (records 51–56, no orphan, plus one; `cli/registry/attempts.py`'s `required_n`). **Author's call**: fixed by this spec's hash, never raised in place; spec 00133 D4 refuses a declared count below `required_n`, so an orphan landing before this run — another session's B2 attempt, which the operating model rules out — refuses it, the trial going back to the owner through T0023, a further count a new subject under a new spec.

## D5 — the subjects, their record and the build

- **Two subjects** in `cli/research/subjects.py`, both `spec="docs/specs/00143-b2-liq-derisk-threshold-design.md"`, `_ASSETS`, intervals `(240,)`: the trial `b2-liq-z3-derisk` — `metric_keys=_b2_overlay_metric_keys("binperp_liq_long_z30d")`, seeds (42, 7, 1234), `verdict=_b2_overlay_verdict`, `no_verdict` record 54's text word for word ("instrument finding: arm A fails the bar this window sets, or the overlay engages at no stamp; no verdict, the trial unspent"), `family="B2"`, `n_trials=_B2_LIQ_Z3_N_TRIALS` — and its evaluate-only twin `b2-liq-z3-derisk-preflight` — `metric_keys=_b2_overlay_preflight_keys("binperp_liq_long_z30d")`, seeds (42,), no rule, family or count, so `--register` refuses it, its plain eval is admitted and `--reading` keeps a stop (spec 00133 D7). No incumbent: arm A is built in the run. Both refuse `--as-of` before any read: "<subject> evaluates a frozen set's 4h series, never the rolling dataset as of a day: drop --as-of and pass a frozen --dataset".
- **Author's call — the names `b2-liq-z3-derisk` and `b2-liq-z3-derisk-preflight`**: spec 00141 D2's rule — a name opening with a registered or retired subject's name and a hyphen makes `tests/test_retired_subjects.py`'s case match count the live subject's cases as the other's, unmarked — so no registered or retired name may equal either or open it with a hyphen, and neither may open one; the basis's second program measures both empty, and `b2-liq-derisk-z3`, record 54's name with the threshold appended, opening with the retired `b2-liq-derisk`. The signal and its threshold stand in the name, `z3` the threshold in sigmas.
- **The keys**: the overlays' 42 and 22 (spec 00138 D9), the trial's `threshold` 3.0 and the twin's too; `engaged_per_asset` and `engaged_per_year` count the long asset-stamps the de-risk halves.
- **The record** (spec 00129 D1, D2, D4; spec 00133 D4, D8): family `B2`; `n_trials_in_family` 7; variant `B2-liq-z3-derisk-a2eq-full-v1` (**Author's call**: record 54's form, `B2-<signal>-derisk-a2eq-full-v1`, the signal's slot carrying the threshold as the subject's name does); iteration `iter-187`; the command computes `spec_hash`, this file's sha256, and the verdict by the subject's rule; seeds (42, 7, 1234); `datasets` the reader's block, measured `816f62f931468b96f39f6fcbbdbfeee5124fa64fb062a98554895870de30474f`, record 54's; `attempt` the trial-attempts log's; `notes` caller text written before the run (D6).
- **Author's call — the build is the overlay machinery unchanged.** `_build_b2_liq_z3_derisk` and `_build_b2_liq_z3_derisk_preflight` call `_b2_overlay_build` with the subject's name, the key `binperp_liq_long_z30d`, `_b2_liq_signal`, the constant `_B2_LIQ_Z3_THRESHOLD`, `_b2_overlay_metrics` or `_b2_overlay_preflight_metrics` and `_B2_LIQ_Z3_N_TRIALS`, so the trial's build differs from record 54's by its threshold, its count and its name alone and no function body is new; the twin computes no position or return of arm B. A compute error is a `SubjectError` naming the subject and its window.
- **The files the build touches, a closed list**: `cli/research/subjects.py` — the constants `_B2_LIQ_Z3_THRESHOLD` and `_B2_LIQ_Z3_N_TRIALS`, the wrappers `_build_b2_liq_z3_derisk` and `_build_b2_liq_z3_derisk_preflight` and two `SUBJECTS` entries, no existing function changed; `README.md`'s `--subject` row; the tests the plan names. No change to `cli/alpha/*`, `cli/features/*`, `cli/portfolio/*`, `cli/registry/*`, `cli/engine/*`, `cli/liquidations/*`, specs 00128, 00137 and 00138, the subjects of trials 1–7 and readings 1–5, or any adopted artifact.

## D6 — the pre-flight and the run, through spec 00133's trial-attempts log

- **The gate**: the plan review closed, the branch's reads (`pre-review`, `review`, `re-review`) closed with no open Critical or Important, and nothing this spec pins changed since.
- **The steps**, in order: (1) the spec hash, `sha256sum docs/specs/00143-b2-liq-derisk-threshold-design.md`, never edited after; (2) the develop check — `git fetch origin develop` and `git diff --quiet $(git merge-base HEAD origin/develop) origin/develop -- docs/reference/trial-registry.jsonl docs/reference/reading-ledger.jsonl`, develop's appends since the branch's base and never the branch's own — before the append; (3) the data-gated basis test on the run's tree; (4) the twin's plain eval, read in this order — (a) the block, `816f62f9…30474f`, `liquidations-daily` `checked (10 vouched hashes)`; (b) arm A's seven anchors at record 45's stored precision (spec 00137 D7's (b)); (c) `engaged_per_asset`, `engaged_per_year`, the signal's coverage, `primary_returns` and `threshold` equal to the measured basis (the plan's data-gated literals, the coverage record 54's stored one); (d) the dead knob — the engaged total above 0; (e) arm A's `passes` 1 — a failure of (a)–(e) an instrument finding, the run kept as a reading under iter-187 (`--reading --iteration iter-187 --spec-hash <(1)> --notes "<what failed>"`), the trial unspent; (5) on a pass, the trial's one run, `--register --iteration iter-187 --family B2 --n-trials 7 --variant B2-liq-z3-derisk-a2eq-full-v1 --spec-hash <(1)> --notes "<written before the run>"`, no `--verdict` and no plain eval before or after it (spec 00133 D7; spec 00137 D10); (6) the record's checks and its commit — the registry line, the decisions-log verdict entry and the landed-count literal together, since the tie tests hold only over the three.
- **The hash rule**: before (1), nobody computes arm B's returns, a head-to-head or any bar leg of arm B over the real data, nor runs `b2-liq-z3-derisk` or its twin over the real sets; positions, scales, engagement counts and turnover are allowed, and are what the measured basis and the data-gated test hold. No return of arm B is computed over the real data before the trial's `--register` run, and the trial subject is never run as a plain eval.
- **The notes, written before the run** (spec 00137 D10's): the subject over `ohlc-full`, full history; the arms, the signal and the threshold; the hypothesis; the count and `var_trials` 0.0; the read from the signal's own start deciding, the full-window read beside it; the pre-flight's figures, quoted; the park variants; the matrix pre-registered by this spec's sha256.
- A refusal from the count, a refused build, a stop by the rule under `--register`: spec 00137 D10's handling — a refusal from the count or a refused build keeps no record and is T0023's with its line quoted, a stop by the rule a reading carrying its attempt, which counts 0; none spends a trial.

## D7 — what a verdict changes

- **Adopt** is a research-registry fact on the A2 ensemble alone and does not touch the live book: the daily liquidations are Coinalyze's history, fetched once into a frozen block, a lower bound, and a live feed is a new spec. Deploying follows spec 00138 D11's B1 precedent — a P1 combination trial over record 47's book, outside every bucket's budget; then the live feed's spec; then T0123's promotion path — and T0123's `ripe_when`, which reads any ADOPT, gains in the record's commit the qualification that this record ripens it only once that combination trial adopts.
- **Park** names its variant candidates in the record — the scale 0.25 at 3.0, and the threshold one step further, 3.5 — each a new trial of the shared budget, put to the owner through T0023.
- **Reject** archives the hypothesis in the record and the decisions log.
- **No verdict** — a pre-flight stop, the rule's stop under `--register`, or a refused build — spends no trial; T0023 records what failed.
- After the verdict, B2's next step — a park variant, a further leg, or closing the family — is the owner's family call through T0023's trigger, recorded as a `[iter-NNN] B2's next step after trial 8` entry.

## Out of scope

The scale 0.25 and both knobs at once, each a park variant or a later trial of its own; the threshold 3.5 and any other; spec 00138 D3's engagement rule re-applied; the funding, OI and ratio de-risks' variants; a re-risk, a re-entry or any trial on another liquidation side, window or interval; a trial on the 1-minute tape or on any instrument but frozen `ohlc-full`; a second fetch of the daily history; a live liquidation feed; Bucket B's other families (B3, B4-legs), T0016's; any change to an existing function, subject, record or spec.
