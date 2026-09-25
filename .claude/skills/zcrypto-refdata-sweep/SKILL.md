---
name: zcrypto-refdata-sweep
description: Run the Kraken reference-data re-confirmation sweep — the monthly routine, and the mandatory one immediately before the go/no-go. Re-fetches the public endpoints, re-renders docs/reference/kraken-snapshot-register.md, and reads the verdict from the rendered tables, never from the raw hash.
disable-model-invocation: false
---

# zcrypto-refdata-sweep

## What this is

The master plan marks fees, fee tiers, borrow-rollover rates, pair lists, MiCA status, tax rules and data pricing as **externally owned** — third-party facts that move without notice, where a stale one is **silent**. This sweep re-confirms the machine-readable subset and stamps the result, so "re-confirmed, identical" is always distinguishable from "never re-run".

Two halves, one routine: an **automated** re-fetch — the public endpoints, plus the account's own live fee tier and 30-day volume via authenticated `kraken volume` — and an **attended** re-read of what no endpoint serves, the full tier ladder's shape and the AoP qualification ladder, which live behind a login. Two occasions, same procedure: **monthly**, and **immediately before the go/no-go**, where the verdict is an input to the decision rather than a follow-up to it.

## The one rule that makes the verdict meaningful

**Read the verdict from the rendered tables, never from `raw_sha256`.** Kraken's full response churns constantly, so the hash changes on nearly every sweep for reasons that touch nothing we depend on. A sweep that treats hash movement as fact movement raises a false alarm every month and will be ignored by the third one.

## Procedure

1. **Fetch, render and check identity** — `uv run zcrypto snapshot sweep`. It needs no API key: it fetches the public endpoints and the venue's maintenance feed, archives the raw snapshot at `data/snapshots/kraken-refdata-<stamp>.json`, and prints `JUDGING SNAPSHOT: <fetched_at>`, the refusals, the announced delistings and the rendered tables; it exits non-zero on a refusal, and on a failed fetch before anything is archived -- the `REFUSALS:` block names the first, the last `ERROR` line the second -- and either stops the sweep.

   **A refusal** is a pair gone from `AssetPairs`, a `status` that stopped saying `online`, or an altname that drifted from the committed alias. Each names the pair and the observed value; decide whether a corporate action happened before going further, and record it in `docs/reference/symbol-corporate-action-ledger.md`. **An announced delisting naming a selected asset is the same finding with a quarter's notice** — the venue publishes an asset delisting 93–116 days ahead — so it is a planning input, not an emergency. **Read every hit's own dates before treating it as one**: the same filter catches funding-rail discontinuations, which can be published after they take effect. Both cover asset codes in the Kraken spellings (`XBT`, `XDG`) as well as the common ones. Quote-book migration is covered by neither: no endpoint reports one, an accepted gap rather than an oversight.

   The raw snapshot is gitignored on purpose — it is the evidence, not the artifact. **Keep it**: two archived snapshots are what let a later review compute an actual set difference instead of netting two totals.

2. **Run the costmin drift guard** — `uv run pytest tests/test_costmin_drift.py`. This is `COSTMIN`'s only guard against venue-side drift, and it skips wherever `data/snapshots/` is absent — which includes CI, since the data root is gitignored — so this sweep, right after Step 1 mints a fresh snapshot, is the only place the guard can actually fire. Red means Kraken moved a ratified leg's `costmin`; update the constant in `cli/engine/instruments.py` to match and record the change here alongside the rest of the sweep's findings. `COSTMIN` is symbol-keyed over all twelve legs and each entry is a `(value, quote_currency)` pair in the snapshot's own vocabulary (`"EUR"`/`"BTC"`, never the adapter aliases `ZEUR`/`XXBT`) — the two `/BTC` legs' floors are BTC-denominated, so never copy a EUR value across.

3. **Diff the rendered tables** against the committed ones — the candidate basket, the fee/borrow/margin table, the alias ledger. Markdown separator styling differs harmlessly; compare cells.

4. **Update `docs/reference/kraken-snapshot-register.md`**: header (`Fetched at:`, `Raw snapshot sha256:`, the response counts), the provenance raw-file path, the changed tables, and **append a row to the re-confirmation log** — sweep number, timestamp, counts, hash prefix, verdict. **The stamp moves even when nothing changed**; that is the whole mechanism.

   The row's first two cells are parsed by `infra/scripts/ops_daily.py::_LOG_ROW` — copy the previous row's shape; `tests/test_ops_daily.py::test_the_real_registers_newest_log_row_is_the_one_its_header_names` goes red on a row the parser would skip.

5. **State the consequence of any delta, do not just report it.** A delta touching **fees** or **`margin_rate`** (the borrow/rollover rate) invalidates downstream numbers — name them: the deployable's cost basis (`T0214`, the re-pricing at rung 2), the deployable's quoted band. Silence here is how a stale fee reaches a go/no-go.

6. **Read the account's own fee tier — automated first, then attended for what it cannot say.** Run `kraken volume --pair BTCUSD -o json` from the **workstation** (never a remote host — `CLAUDE.md`'s Secrets rule); it is authenticated and read-only. The response keys its per-pair blocks by the venue's own altname, so `BTCUSD` comes back under `XXBTZUSD` — read the key the payload returns, never the one you asked for. There, `fees.<key>.fee` is the live **taker** rate and `fees_maker.<key>.fee` the **maker** rate, each block also carrying `nextfee`/`nextvolume` for the next tier and its threshold; `inputs` carries `domain_spot_volume_30d`, `domain_futures_volume_30d` and `domain_assets_on_platform` — the 30-day spot volume, the futures volume, and the AoP held value. That is every number the register's log row records. Prefer them over the register's public `AssetPairs` fee columns, which lag the account-confirmed schedule.

   Then ask the owner for only what the endpoint does not serve: the **full tier ladder's shape** if a row looks wrong, and the **AoP qualification ladder** — which held value grants which tier, not the held value itself, which `domain_assets_on_platform` supplies. If the API read is unavailable, fall back to **Kraken Pro → Fee tab** for the **current tier** and the **30-day USD spot volume**. Either way:
   - **Unchanged** → note it in the register's log row (`account tier` column) and bump nothing else. The confirmation is the point; an unbumped stamp is indistinguishable from a skipped read.
   - **Changed** → correct `kraken-fee-schedule.md` *and* state what it invalidates as step 5 does: `cli/costs/fees.py` encodes that ladder verbatim, so a tier move re-prices every quoted figure that reads it.
   - **Neither read happened** → record the row as `not re-read`, never as unchanged; a tier the API did read is logged even when the attended remainder is not, and an unasked remainder is noted in that same row. A blank is honest; a false confirmation is the failure this whole routine exists to prevent.


7. **Commit** with the sweep number in the subject. If the sweep is the one before the go/no-go, say so — that run is a decision input.
8. **The closeout the routine owes**: the register is an operator-and-agent surface, so the account of what the sweep changed belongs in the sweep's own PR description, never a later fold; and every count or "all N" in the register's prose and in `infra/runbooks/reference-data.md`'s endpoint claims is generated from the same rendered data as the table it describes, never typed beside it.

## What this sweep does and does not cover

- **Covers** (public, no account): pair existence and `status`, margin flag, leverage bands, `ordermin`/`costmin`, per-asset **`margin_rate`** (the per-4h rollover rate) and `collateral_value`, `margin_call`/`margin_stop`, position limits.
- **Reports but does NOT own — the fee ladder.** `docs/reference/kraken-fee-schedule.md` is the fee source of truth, account-confirmed. The public endpoint can lag the account-confirmed schedule by weeks, so the register's fee columns are a **drift detector on the endpoint**, never a costing anchor. If they move, reconcile against the fee-schedule file and say which is now right — do not adopt the endpoint's numbers because they are newer-looking.
- **No PUBLIC endpoint covers, so step 6 reads them from the account**: the realised fee **tier** and 30-day volume come from authenticated `kraken volume`, not from a human and not from the register's public columns. What stays attended is the full ladder's shape, the AoP qualification ladder and the observed margin/rollover bands; `docs/reference/kraken-fee-schedule.md` is where they live and the anchor for any costing question — never the register's endpoint columns, at any volume.
- **Does not cover** (no endpoint): MiCA status, tax rules, market-data pricing — human re-reads, and they belong to the go/no-go run.

## Failure modes worth naming

- **A changed hash reported as a changed fact.** See the rule above.
- **Trusting an "UNCHANGED" verdict for fields the register does not extract.** It renders what `derive_universe` extracts and nothing more. If a decision starts leaning on a field outside that set, extend the extraction first — fields outside the table move without the table seeing them.
