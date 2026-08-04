---
name: zcrypto-refdata-sweep
description: Run the Kraken reference-data re-confirmation sweep — the monthly routine, and the mandatory one immediately before the go/no-go. Re-fetches the public endpoints, re-renders docs/reference/kraken-snapshot-register.md, and reads the verdict from the rendered tables, never from the raw hash.
disable-model-invocation: false
---

# zcrypto-refdata-sweep

## What this is

The master plan marks fees, fee tiers, borrow-rollover rates, pair lists, MiCA status, tax rules and data pricing as **externally owned** — third-party facts that move without notice, where a stale one is **silent**. This sweep re-confirms the machine-readable subset and stamps the result, so "re-confirmed, identical" is always distinguishable from "never re-run".

Two occasions, same procedure: **monthly**, and **immediately before the go/no-go**, where the verdict is an input to the decision rather than a follow-up to it (that run belongs to `T0085`).

## The one rule that makes the verdict meaningful

**Read the verdict from the rendered tables, never from `raw_sha256`.** Kraken's full response churns constantly — sweep #1 saw 93 pairs removed and 13 added while every candidate held — so the hash changes on nearly every sweep for reasons that touch nothing we depend on. A sweep that treats hash movement as fact movement raises a false alarm every month and will be ignored by the third one.

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

2. **Diff the rendered tables** against the committed ones — the candidate basket, the fee/borrow/margin table, the alias ledger. Markdown separator styling differs harmlessly; compare cells.

3. **Update `docs/reference/kraken-snapshot-register.md`**: header (`Fetched at:`, `Raw snapshot sha256:`, the response counts), the provenance raw-file path, the changed tables, and **append a row to the re-confirmation log** — sweep number, timestamp, counts, hash prefix, verdict. **The stamp moves even when nothing changed**; that is the whole mechanism.

4. **State the consequence of any delta, do not just report it.** A delta touching **fees** or **`margin_rate`** (the borrow/rollover rate) invalidates downstream numbers — name them: `T0090`'s cost basis, the deployable's quoted band. Silence here is how a stale fee reaches a go/no-go.

5. **Commit** with the sweep number in the subject. If the sweep is the one before the go/no-go, say so — that run is a decision input.

## What this sweep does and does not cover

- **Covers** (public, no account): pair existence and `status`, margin flag, leverage bands, `ordermin`/`costmin`, per-asset **`margin_rate`** (the per-4h rollover rate) and `collateral_value`, `margin_call`/`margin_stop`, position limits.
- **Reports but does NOT own — the fee ladder.** `docs/reference/kraken-fee-schedule.md` is the fee source of truth, account-confirmed. The public endpoint was still serving the **pre-2026-07-09** schedule when checked on 2026-08-04, so the register's fee columns are a **drift detector on the endpoint**, never a costing anchor. If they move, reconcile against the fee-schedule file and say which is now right — do not adopt the endpoint's numbers because they are newer-looking.
- **Does not cover** (account-gated, parked in `T0000`): the account's own realised fee **tier**, AoP qualification, observed margin/rollover bands. The register's public base tier is the right anchor for a funded account at zero 30-day volume and the **wrong** one the moment volume climbs.
- **Does not cover** (no endpoint): MiCA status, tax rules, market-data pricing — human re-reads, and they belong to the go/no-go run.

## Failure modes worth naming

- **A changed hash reported as a changed fact.** See the rule above.
- **Reading `margin_rate` off the pair.** It is a property of the **asset**; the pair carries no such field, so a pair-side lookup yields `None` for every row and looks like "no borrow data" rather than a bug.
- **Costing off the register's fee columns.** They are the *endpoint's* view and were a month stale at sweep #1 — a reader who anchors a cost model to them adopts a superseded schedule that happens to look authoritative because it came from an API.
- **Trusting an "UNCHANGED" verdict for fields the register does not extract.** It renders what `derive_universe` extracts and nothing more. If a decision starts leaning on a field outside that set, extend the extraction first — sweep #1's review found `margin_rate` and `short_position_limit` moving inside one hour while the then-current table was blind to both.
