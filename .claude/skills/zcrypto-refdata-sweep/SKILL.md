---
name: zcrypto-refdata-sweep
description: Run the Kraken reference-data re-confirmation sweep — the monthly routine, and the mandatory one immediately before the go/no-go. Re-fetches the public endpoints, re-renders docs/reference/kraken-snapshot-register.md, and reads the verdict from the rendered tables, never from the raw hash.
disable-model-invocation: false
---

# zcrypto-refdata-sweep

## What this is

The master plan marks fees, fee tiers, borrow-rollover rates, pair lists, MiCA status, tax rules and data pricing as **externally owned** — third-party facts that move without notice, where a stale one is **silent**. This sweep re-confirms the machine-readable subset and stamps the result, so "re-confirmed, identical" is always distinguishable from "never re-run".

Two halves, one routine: an **automated** re-fetch of the public endpoints, and an **attended** re-read of the account's own fee tier (step 6) — the authoritative surface is behind a login, so no amount of API work replaces it. Two occasions, same procedure: **monthly**, and **immediately before the go/no-go**, where the verdict is an input to the decision rather than a follow-up to it.

## The one rule that makes the verdict meaningful

**Read the verdict from the rendered tables, never from `raw_sha256`.** Kraken's full response churns constantly, so the hash changes on nearly every sweep for reasons that touch nothing we depend on. A sweep that treats hash movement as fact movement raises a false alarm every month and will be ignored by the third one.

## Procedure

1. **Fetch and render.** Public endpoints, no API key, no account:

```python
import datetime, json, pathlib
from cli.snapshot.fetch import fetch_public
from cli.snapshot.assetpairs import CANDIDATE_SYMBOLS
from cli.snapshot.register import build_snapshot, render_markdown

ap, assets = fetch_public("AssetPairs"), fetch_public("Assets")
now = datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()
snap = build_snapshot(ap, assets, list(CANDIDATE_SYMBOLS), now)
stamp = snap["fetched_at"].replace("-", "").replace(":", "")[:15] + "Z"
pathlib.Path("data/snapshots").mkdir(parents=True, exist_ok=True)
pathlib.Path(f"data/snapshots/kraken-refdata-{stamp}.json").write_text(json.dumps(snap, indent=2, sort_keys=True))
print(render_markdown(snap))
```

The raw snapshot is gitignored on purpose — it is the evidence, not the artifact. **Keep it**: two archived snapshots are what let a later review compute an actual set difference instead of netting two totals.

2. **Run the costmin drift guard** — `uv run pytest tests/test_costmin_drift.py`. This is `COSTMIN`'s only guard, and it skips wherever `data/snapshots/` is absent — which includes CI, since the data root is gitignored — so this sweep, right after Step 1 mints a fresh snapshot, is the only place the guard can actually fire. Red means Kraken moved a ratified leg's `costmin`; update the constant in `cli/engine/instruments.py` to match and record the change here alongside the rest of the sweep's findings. `COSTMIN` is symbol-keyed over all twelve legs and each entry is a `(value, quote_currency)` pair in the snapshot's own vocabulary (`"EUR"`/`"BTC"`, never the adapter aliases `ZEUR`/`XXBT`) — the two `/BTC` legs' floors are BTC-denominated, so never copy a EUR value across.

3. **Run the identity checks — they REFUSE, they are not a table to read.** A selected pair changing identity underneath us is what makes this sweep load-bearing, and both halves are mechanical:

```python
import json, pathlib, urllib.request
from cli.snapshot.assetpairs import CANDIDATE_SYMBOLS, _COMMON_TO_KRAKEN
from cli.snapshot.register import sweep_refusals
from cli.snapshot.delistings import scan_delistings

# Rehydrate the snapshot step 1 just wrote — each block is its own interpreter, so `snap` does not
# survive from there. Pinned to the NEWEST file and its `fetched_at` printed, because the repair this
# would otherwise invite is loading "the snapshot" by hand: a clean verdict against last month's
# archived file is a FALSE CLEAN on the one routine that gates the go/no-go.
snap = json.loads(max(pathlib.Path("data/snapshots").glob("kraken-refdata-*.json")).read_text())
print("JUDGING SNAPSHOT:", snap["fetched_at"])   # must be the fetch you just took

refusals = sweep_refusals(snap)
bases = {s.split("/")[0] for s in CANDIDATE_SYMBOLS} | {s.split("/")[1] for s in CANDIDATE_SYMBOLS}
assets = tuple(sorted(bases | {_COMMON_TO_KRAKEN[b] for b in bases if b in _COMMON_TO_KRAKEN}))
with urllib.request.urlopen("https://status.kraken.com/api/v2/scheduled-maintenances.json", timeout=30) as r:
    announced = scan_delistings(json.load(r), assets)
print("REFUSALS:", refusals or "none"); print("ANNOUNCED DELISTINGS:", announced or "none")
```

**Any refusal stops the sweep** — a pair gone from `AssetPairs`, a `status` that stopped saying `online`, or an altname that drifted from the committed alias. Each names the pair and the observed value; decide whether a corporate action happened before going further, and record it in `docs/reference/symbol-corporate-action-ledger.md`. **An announced delisting naming a selected asset is the same finding with a quarter's notice** — the venue publishes an asset delisting 93–116 days ahead — so it is a planning input, not an emergency. **Read every hit's own dates before treating it as one**: the same filter catches funding-rail discontinuations, which can be published after they take effect. Both cover asset codes in the Kraken spellings (`XBT`, `XDG`) as well as the common ones. Quote-book migration is covered by neither: no endpoint reports one, an accepted gap rather than an oversight.

4. **Diff the rendered tables** against the committed ones — the candidate basket, the fee/borrow/margin table, the alias ledger. Markdown separator styling differs harmlessly; compare cells.

5. **Update `docs/reference/kraken-snapshot-register.md`**: header (`Fetched at:`, `Raw snapshot sha256:`, the response counts), the provenance raw-file path, the changed tables, and **append a row to the re-confirmation log** — sweep number, timestamp, counts, hash prefix, verdict. **The stamp moves even when nothing changed**; that is the whole mechanism.

   **The row's first two cells have a required shape** — the daily pass reads the last row of that table to decide whether the next sweep is due. The first cell must **begin** `#<n>`, and the second must be a full ISO stamp: `| #2 (monthly, 2026-09-04) | 2026-09-04T10:40:09+00:00 | … |`. A first cell written any other way (`Sweep 2`, `2 (monthly)`) is skipped in silence, the row above answers in its place, and the pass reports a sweep that just ran as overdue.

6. **State the consequence of any delta, do not just report it.** A delta touching **fees** or **`margin_rate`** (the borrow/rollover rate) invalidates downstream numbers — name them: `T0090`'s cost basis, the deployable's quoted band. Silence here is how a stale fee reaches a go/no-go.

7. **The attended half — re-read the account's own fee tier.** The public endpoint cannot see it, and `docs/reference/kraken-fee-schedule.md` is authoritative precisely because it was read from the logged-in account. Ask the owner to open **Kraken Pro → Fee tab** and report two values: the **current tier** and the **30-day USD spot volume**. Then:
   - **Unchanged** → note it in the register's log row (`account tier` column) and bump nothing else. The confirmation is the point; an unbumped stamp is indistinguishable from a skipped read.
   - **Changed** → correct `kraken-fee-schedule.md` *and* say what it invalidates: `cli/costs/fees.py` encodes that ladder verbatim, so a tier move re-prices every quoted figure that reads it — name `T0090`'s cost basis and the deployable's quoted band explicitly.
   - **Owner unavailable** → record the row as `not re-read`, never as unchanged. A blank is honest; a false confirmation is the failure this whole routine exists to prevent.

   At \$0 30-day volume the tier *cannot* move, so run it cheaply now; it is load-bearing once real fills flow.

8. **Commit** with the sweep number in the subject. If the sweep is the one before the go/no-go, say so — that run is a decision input.

## What this sweep does and does not cover

- **Covers** (public, no account): pair existence and `status`, margin flag, leverage bands, `ordermin`/`costmin`, per-asset **`margin_rate`** (the per-4h rollover rate) and `collateral_value`, `margin_call`/`margin_stop`, position limits.
- **Reports but does NOT own — the fee ladder.** `docs/reference/kraken-fee-schedule.md` is the fee source of truth, account-confirmed. The public endpoint can lag the account-confirmed schedule by weeks, so the register's fee columns are a **drift detector on the endpoint**, never a costing anchor. If they move, reconcile against the fee-schedule file and say which is now right — do not adopt the endpoint's numbers because they are newer-looking.
- **No endpoint covers, so step 6 asks a human**: the account's own realised fee **tier** and 30-day volume — that is exactly what the attended half re-reads, not something this routine skips. AoP qualification and the observed margin/rollover bands stay unautomated too; `docs/reference/kraken-fee-schedule.md` is where they live and the anchor for any costing question — never the register's endpoint columns, at any volume.
- **Does not cover** (no endpoint): MiCA status, tax rules, market-data pricing — human re-reads, and they belong to the go/no-go run.

## Failure modes worth naming

- **A changed hash reported as a changed fact.** See the rule above.
- **Reading `margin_rate` off the pair.** It is a property of the **asset**; the pair carries no such field, so a pair-side lookup yields `None` for every row and looks like "no borrow data" rather than a bug.
- **Costing off the register's fee columns.** They are the *endpoint's* view — a reader who anchors a cost model to them adopts a superseded schedule that happens to look authoritative because it came from an API.
- **Trusting an "UNCHANGED" verdict for fields the register does not extract.** It renders what `derive_universe` extracts and nothing more. If a decision starts leaning on a field outside that set, extend the extraction first — fields outside the table move without the table seeing them.
