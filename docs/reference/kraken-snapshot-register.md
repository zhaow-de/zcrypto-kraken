# Kraken Reference-Data Snapshot Register

**Iteration:** iter-002 · **Phase:** 0 (Preparation) · **Scope:** ground-truth Kraken **public** reference data for the
candidate basket (master-plan §3) — per-pair margin/leverage/order-minimum facts and the Kraken internal symbol-alias
ledger, fetched live from Kraken's public `AssetPairs`/`Assets` endpoints (no API key) and rendered by `cli/snapshot/`
(see `docs/specs/00001-snapshot-register-design.md`). This reconfirms the master-plan §14 ⏱ facts that are derivable
without a live account; the account-gated facts remain parked (see below).

**Fetched from:** `GET https://api.kraken.com/0/public/AssetPairs`, `GET https://api.kraken.com/0/public/Assets`
(1429 pairs / 824 assets in the full response at fetch time).

**Fetched at:** 2026-08-04T10:40:09+00:00 (UTC)
**Raw snapshot sha256:** `89e15dba5edeb9766d5cefbbfe9fd80b807ace6a1585599664958c8414922f24`

> **This header always carries the LATEST sweep.** The re-confirmation log at the foot of this file
> records every sweep with its own counts and hash, so "re-confirmed, identical" is distinguishable
> from "never re-run" — the failure mode \[[T0113]\] exists to prevent.

## Candidate-basket margin & leverage ground truth

| Symbol | Kraken pair | wsname | Margin | Leverage buy | Leverage sell | Ordermin | Costmin | Status |
| -- | -- | -- | -- | -- | -- | -- | -- | -- |
| BTC/EUR | XXBTZEUR | XBT/EUR | yes | 2,3,4,5,6,7,8,9,10 | 2,3,4,5,6,7,8,9,10 | 0.00005 | 0.45 | online |
| ETH/EUR | XETHZEUR | ETH/EUR | yes | 2,3,4,5,6,7,8,9,10 | 2,3,4,5,6,7,8,9,10 | 0.001 | 0.45 | online |
| SOL/EUR | SOLEUR | SOL/EUR | yes | 2,3,4,5,6,7,8,9,10 | 2,3,4,5,6,7,8,9,10 | 0.06 | 0.45 | online |
| XRP/EUR | XXRPZEUR | XRP/EUR | yes | 2,3,4,5,6,7,8,9,10 | 2,3,4,5,6,7,8,9,10 | 1.65 | 0.45 | online |
| ADA/EUR | ADAEUR | ADA/EUR | yes | 2,3,4,5,6,7,8,9,10 | 2,3,4,5,6,7,8,9,10 | 20 | 0.45 | online |
| LINK/EUR | LINKEUR | LINK/EUR | yes | 2,3,4,5,6,7,8,9,10 | 2,3,4,5,6,7,8,9,10 | 0.55 | 0.45 | online |
| DOGE/EUR | XDGEUR | XDG/EUR | yes | 2,3,4,5,6,7,8,9,10 | 2,3,4,5,6,7,8,9,10 | 50 | 0.45 | online |
| LTC/EUR | XLTCZEUR | LTC/EUR | yes | 2,3,4,5,6,7,8,9,10 | 2,3,4,5,6,7,8,9,10 | 0.1 | 0.45 | online |
| DOT/EUR | DOTEUR | DOT/EUR | yes | 2,3,4,5 | 2,3,4,5 | 3.9 | 0.45 | online |
| AVAX/EUR | AVAXEUR | AVAX/EUR | yes | 2,3,4,5,6,7,8,9,10 | 2,3,4,5,6,7,8,9,10 | 0.5 | 0.45 | online |
| ETH/BTC | XETHXXBT | ETH/XBT | yes | 2,3,4,5 | 2,3,4,5 | 0.001 | 0.00002 | online |
| SOL/BTC | SOLXBT | SOL/XBT | yes | 2,3,4 | 2,3,4 | 0.06 | 0.00002 | online |

All twelve §3 candidate symbols resolve to an **online, margin-enabled** Kraken pair as of the fetch above — none are
missing and none have lost margin eligibility since the master plan was drafted. Leverage caps split into two bands:
2–10× on the ten EUR-quoted majors, and a lower 2–4×/2–5× band on the two BTC-quoted relative-value legs (ETH/BTC,
SOL/BTC) — consistent with §3's "leverage caps per pair to be pulled from `AssetPairs` as ground truth" note.

## Fee schedule, borrow rate & margin bands

| Symbol | Taker % (base) | Maker % (base) | Fee tiers | Borrow rate (base asset) | Collateral value | Margin call | Margin stop | Long limit | Short limit |
|---|---|---|---|---|---|---|---|---|---|
| BTC/EUR | 0.4 | 0.25 | 12 | 0.01 | 0.99 | 80 | 40 | 130 | 100 |
| ETH/EUR | 0.4 | 0.25 | 12 | 0.02 | 0.99 | 80 | 40 | 2300 | 2300 |
| SOL/EUR | 0.4 | 0.25 | 12 | 0.02 | 0.925 | 80 | 40 | 16000 | 16000 |
| XRP/EUR | 0.4 | 0.25 | 12 | 0.02 | 0.95 | 80 | 40 | 1400000 | 1400000 |
| ADA/EUR | 0.4 | 0.25 | 12 | 0.04 | 0.925 | 80 | 40 | 4400000 | 3100000 |
| LINK/EUR | 0.4 | 0.25 | 12 | 0.02 | 0.9 | 80 | 40 | 63000 | 32000 |
| DOGE/EUR | 0.4 | 0.25 | 12 | 0.02 | 0.925 | 80 | 40 | 18000000 | 11000000 |
| LTC/EUR | 0.4 | 0.25 | 12 | 0.02 | 0.925 | 80 | 40 | 17000 | 11000 |
| DOT/EUR | 0.4 | 0.25 | 12 | 0.024 | 0.925 | 80 | 40 | 390000 | 340000 |
| AVAX/EUR | 0.4 | 0.25 | 12 | 0.03 | 0.9 | 80 | 40 | 79000 | 29000 |
| ETH/BTC | 0.4 | 0.25 | 12 | 0.02 | 0.99 | 80 | 40 | 1000 | 800 |
| SOL/BTC | 0.4 | 0.25 | 12 | 0.02 | 0.925 | 80 | 40 | 6900 | 5100 |

Added at sweep #1 (2026-08-04), closing a gap the sweep's own review found: the register re-confirmed
status, margin, leverage and minimums while capturing **none** of the ⏱ cost facts the master plan
names as externally owned. The fee ladder and `margin_rate` are public and were available all along —
`margin_rate` **is** the borrow/rollover rate, and it lives on the *asset*, not the pair. Rendered as
base tier plus ladder depth; the full 12-tier ladders live in the snapshot JSON so a future diff can
name *which* tier moved.

**What sweep #1 measures:** taker **0.40 %** / maker **0.25 %** at the base tier, uniform across all
twelve pairs (12 tiers each); borrow rates spread 0.01–0.04 by asset (BTC cheapest, ADA dearest);
margin call 80 / stop 40 uniform; position limits varying by three orders of magnitude.

**An open question this raises about the cost model, stated rather than resolved.**
`CrossfreqSystemConfig.fee_per_side = 0.0040` is commented *"Kraken tier-1 MAKER, schedule effective
2026-07-09"* — but today's public tier-1 **maker** is 0.0025, and 0.0040 is today's **taker**. Either
the label always misidentified which side it is, or the schedule moved between 2026-07-09 and now.
**Sweep #0 cannot arbitrate, because it never captured fees** — which is precisely the gap this
section closes, and from sweep #2 onward the question is answerable by diff. Two things do not
change on either reading: the constant itself must stay frozen (record 44's figures reproduce only
at `0.0040 + 0.0020 = 0.006`, and its own comment says so), and [[T0090]]'s ruling does not depend on
the label, because it re-quoted maker and taker as separate bases rather than trusting one constant.
If the resolution turns out to be "the schedule moved", the affected downstream number is the
registered cost basis, and the honest read is the one T0090 already gives: a range, not a point.

**Still account-gated:** the *account's own* fee tier depends on 30-day volume and needs the live
account. This section is the **public schedule at the base tier** — the right anchor for a funded
account starting at zero volume, and the wrong one the moment volume climbs.

## Symbol-alias ledger

| Kraken code | Common symbol |
| -- | -- |
| XBT | BTC |
| XDG | DOGE |

Resolved from the live `Assets` result (`XXBT.altname == "XBT"`, `XXDG.altname == "XDG"`), confirming the master-plan
§3 alias ledger (XBT=BTC, XDG=DOGE) against ground truth rather than a transcribed doc. Every other candidate-basket
asset's Kraken altname matches its common ticker directly (no alias).

## Provenance

- **Raw snapshot file:** `data/snapshots/kraken-refdata-20260804T104009Z.json` (gitignored; not committed — regenerate
  via `cli.snapshot.fetch_public("AssetPairs")` + `fetch_public("Assets")` fed into `build_snapshot(...)`).
- **Raw snapshot sha256:** `89e15dba5edeb9766d5cefbbfe9fd80b807ace6a1585599664958c8414922f24` — a sha256 over the
  canonical JSON of the raw `AssetPairs`/`Assets` results only (not `fetched_at`), so it is reproducible from the raw
  responses alone.
- **Derivation code:** `cli/snapshot/` (`fetch.py`, `assetpairs.py`, `register.py`), unit-tested against a trimmed,
  real (fetched-once-live) fixture under `tests/fixtures/` — see `docs/specs/00001-snapshot-register-design.md`.

## Re-confirmation log

The master plan marks these facts as externally owned and requires re-confirmation at Phase 0 and again at go-live;
\[[T0113]\] carries it as a **monthly** routine rather than a single pre-live step, because every entry here is a
third-party fact that can move in any month and a stale one is silent. **Each sweep bumps the header even when nothing
changed** — otherwise the next reader cannot tell a re-confirmed register from an abandoned one.

| Sweep | Fetched at (UTC) | Full response | Raw sha256 | Candidate-basket verdict |
| -- | -- | -- | -- | -- |
| #0 (Phase 0, iter-002) | 2026-07-07T03:29:00+00:00 | 1509 pairs / 809 assets | `e1510e98…3226e3` | 12/12 online + margin-enabled; the reference all later sweeps compare against |
| #1 (monthly, 2026-08-04) | 2026-08-04T10:40:09+00:00 | 1429 pairs / 824 assets | `89e15dba…922f24` | **UNCHANGED** — all 12 still online and margin-enabled, identical leverage bands, `ordermin`, `costmin` and aliases (re-rendered and diffed against the committed table: no cell moved) |

**Sweep #1 note — the basket held while Kraken's universe did not.** The full response lost **80 pairs net** and gained
**15 assets** between #0 and #1, so the endpoint is demonstrably live and churning; none of that churn touched the
twelve §3 candidates. The raw hash differs for that reason alone, which is why the verdict is read from the rendered
candidate table rather than from the hash — **a changed hash is not a changed fact**, and treating it as one would
manufacture an alarm every month.

**Still deferred at #1:** the account-gated facts below (fee tier, AoP qualification, observed margin/rollover bands)
are unchanged in status — no live account action has been taken, so they remain parked rather than re-confirmed.

## Deferred: account-gated facts

Kraken's public endpoints do not carry the live maker/taker fee tier, the July-9-2026 Assets-on-Platform (AoP)
qualification rule, or the observed margin opening/rollover bands on majors — those require the live Kraken account.
They remain parked in **T0000**
(`docs/open-topics/T0000-phase0-account-actions.md`) pending the human account actions listed there; once confirmed,
they should be recorded into a future revision of this register.
