# Kraken Reference-Data Snapshot Register

**Iteration:** iter-002 · **Phase:** 0 (Preparation) · **Scope:** ground-truth Kraken **public** reference data for the
candidate basket (master-plan §3) — per-pair margin/leverage/order-minimum facts and the Kraken internal symbol-alias
ledger, fetched live from Kraken's public `AssetPairs`/`Assets` endpoints (no API key) and rendered by `cli/snapshot/`
(see `docs/specs/00001-snapshot-register-design.md`). This reconfirms the master-plan §14 ⏱ facts that are derivable
without a live account; the account-gated facts remain parked (see below).

**Fetched from:** `GET https://api.kraken.com/0/public/AssetPairs`, `GET https://api.kraken.com/0/public/Assets`
(1446 pairs / 840 assets in the full response at fetch time).

**Fetched at:** 2026-09-04T08:11:18+00:00 (UTC)
**Raw snapshot sha256:** `bb84ee1a30cc637d614be9b07a2589e1be74ccfaf1922c8c40fd65d9968c9fbc`

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
2–10× on nine of the ten EUR-quoted majors, and a lower 2–4×/2–5× band on the two BTC-quoted relative-value legs
(ETH/BTC, SOL/BTC) plus DOT/EUR, the one EUR major that caps at 2–5× — consistent with §3's "leverage caps per pair
to be pulled from `AssetPairs` as ground truth" note.

## Endpoint-reported fee ladder, borrow rate & margin bands

> **The fee columns here are NOT the fee source of truth — `kraken-fee-schedule.md` is.**
> Kraken's public `AssetPairs` still serves the **pre-2026-07-09 schedule** on all twelve candidates: base
> 0.25 % maker / 0.40 % taker with tier breaks at \$10k/\$50k. The response at large is not uniform — see the
> log's #2 row — but no pair in it carries the in-force \$2.5k break. The schedule actually in force since 2026-07-09 is
> **0.40 % maker / 0.80 % taker** at tier 1, with breaks at \$2.5k/\$10k/\$25k — account-confirmed on
> the logged-in Fee tab and recorded in `kraken-fee-schedule.md`, which supersedes these columns for
> every costing purpose.
>
> **What these columns are for, then:** a **drift detector on the endpoint itself**. The day they
> move is the day Kraken finally propagated a new schedule into the public API, and a sweep that
> sees them change should reconcile against `kraken-fee-schedule.md` rather than adopt them. Read
> the level from the account; read the *change* from here.

| Symbol | Taker % (base) | Maker % (base) | Fee tiers | Borrow: base (shorts) | Borrow: quote (longs) | Collateral value | Margin call | Margin stop | Long limit | Short limit |
|---|---|---|---|---|---|---|---|---|---|---|
| BTC/EUR | 0.4 | 0.25 | 12 | 0.01 | 0.02 | 0.99 | 80 | 40 | 130 | 100 |
| ETH/EUR | 0.4 | 0.25 | 12 | 0.02 | 0.02 | 0.99 | 80 | 40 | 2300 | 2300 |
| SOL/EUR | 0.4 | 0.25 | 12 | 0.02 | 0.02 | 0.925 | 80 | 40 | 16000 | 16000 |
| XRP/EUR | 0.4 | 0.25 | 12 | 0.02 | 0.02 | 0.95 | 80 | 40 | 1400000 | 1400000 |
| ADA/EUR | 0.4 | 0.25 | 12 | 0.02 | 0.02 | 0.925 | 80 | 40 | 4800000 | 4100000 |
| LINK/EUR | 0.4 | 0.25 | 12 | 0.02 | 0.02 | 0.9 | 80 | 40 | 98000 | 80000 |
| DOGE/EUR | 0.4 | 0.25 | 12 | 0.02 | 0.02 | 0.925 | 80 | 40 | 19000000 | 15000000 |
| LTC/EUR | 0.4 | 0.25 | 12 | 0.02 | 0.02 | 0.925 | 80 | 40 | 14000 | 13000 |
| DOT/EUR | 0.4 | 0.25 | 12 | 0.02 | 0.02 | 0.925 | 80 | 40 | 300000 | 270000 |
| AVAX/EUR | 0.4 | 0.25 | 12 | 0.02 | 0.02 | 0.9 | 80 | 40 | 98000 | 63000 |
| ETH/BTC | 0.4 | 0.25 | 12 | 0.02 | 0.01 | 0.99 | 80 | 40 | 1000 | 800 |
| SOL/BTC | 0.4 | 0.25 | 12 | 0.02 | 0.01 | 0.925 | 80 | 40 | 5600 | 5000 |

Borrow and margin columns carry no such caveat and **agree** with the account-confirmed figures:
`margin_rate` is the per-4h rollover rate on the **extended** currency, and the endpoint's per-asset
point values sit inside `kraken-fee-schedule.md`'s ranges (BTC 0.01 vs its 0.01–0.02 %; alts
0.02 vs its 0.02–0.04 %) — EUR excepted: that file's borrow table is keyed on the extended **base** currency (BTC
plus nine alts) and its only fiat figure is a worked example for a **USD** leg (~0.025 %), so the ten EUR rows' 0.02
long-leg rate is rendered here with no band in the schedule to sit inside, while the two /BTC rows' 0.01 quote does
sit inside BTC's band. **Both sides are rendered because they price opposite trades**: a
SHORT sells the borrowed base, so the base column prices it; a **LONG on margin buys with borrowed
quote currency**, so the quote column prices the book's long leg. That agreement is worth keeping,
because the borrow rate is the term that makes alt shorts ~2× BTC shorts and drives the
short-BTC-only thesis.

`margin_rate` lives on the *asset*, not the pair. Rendered as base tier plus ladder depth; the full
12-tier ladders live in the snapshot JSON so a future diff can name *which* tier moved.

**Account-gated, but not human-gated:** the account's realised fee **tier** depends on 30-day volume and needs the
live account — served by authenticated `kraken volume`, so the sweep reads it **automatically** and records it in the log below;
the log below holds the standing value (tier 1, \$46.71 30-day spot volume, read 2026-09-04), and `kraken-fee-schedule.md` owns the ladder that value selects from (⏱ account-confirmed 2026-07-07). MiCA status, tax rules and market-data pricing have no endpoint at all and are human
re-reads at the go/no-go.

## Symbol-alias ledger

| Kraken code | Common symbol |
| -- | -- |
| XBT | BTC |
| XDG | DOGE |

Resolved from the live `Assets` result (`XXBT.altname == "XBT"`, `XXDG.altname == "XDG"`), confirming the master-plan
§3 alias ledger (XBT=BTC, XDG=DOGE) against ground truth rather than a transcribed doc. Every other candidate-basket
asset's Kraken altname matches its common ticker directly (no alias).

## Provenance

- **Raw snapshot file:** `data/snapshots/kraken-refdata-20260904T081118Z.json` (gitignored; not committed — regenerate
  via `cli.snapshot.fetch_public("AssetPairs")` + `fetch_public("Assets")` fed into `build_snapshot(...)`).
- **Raw snapshot sha256:** `bb84ee1a30cc637d614be9b07a2589e1be74ccfaf1922c8c40fd65d9968c9fbc` — a sha256 over the
  canonical JSON of the raw `AssetPairs`/`Assets` results only (not `fetched_at`), so it is reproducible from the raw
  responses alone.
- **Derivation code:** `cli/snapshot/` (`fetch.py`, `assetpairs.py`, `register.py`), unit-tested against a trimmed,
  real (fetched-once-live) fixture under `tests/fixtures/` — see `docs/specs/00001-snapshot-register-design.md`.

## Re-confirmation log

The master plan marks these facts as externally owned and requires re-confirmation at Phase 0 and again at go-live;
\[[T0113]\] carries it as a **monthly** routine rather than a single pre-live step, because every entry here is a
third-party fact that can move in any month and a stale one is silent. **Each sweep bumps the header even when nothing
changed** — otherwise the next reader cannot tell a re-confirmed register from an abandoned one.

| Sweep | Fetched at (UTC) | Full response | Raw sha256 | Candidate-basket verdict | Account fee tier |
| -- | -- | -- | -- | -- | --- |
| #0 (Phase 0, iter-002) | 2026-07-07T03:29:00+00:00 | 1509 pairs / 809 assets | `e1510e98…3226e3` | 12/12 online + margin-enabled; the reference all later sweeps compare against | **Tier 1, \$0 30-day volume** — read from the logged-in Fee tab the same day (T0000), which is what makes `kraken-fee-schedule.md` authoritative |
| #1 (monthly, 2026-08-04) | 2026-08-04T10:40:09+00:00 | 1429 pairs / 824 assets | `89e15dba…922f24` | **UNCHANGED** — all 12 still online and margin-enabled, identical leverage bands, `ordermin`, `costmin` and aliases (re-rendered and diffed against the committed table: no cell moved) | **not re-read** — recorded blank rather than inherited; at \$0 volume the tier cannot have moved, but *cannot have* is not *was checked* |
| #2 (monthly, 2026-09-04) | 2026-09-04T08:11:18+00:00 | 1446 pairs / 840 assets | `bb84ee1a…8c9fbc` | **UNCHANGED (basket)** — all 12 still online and margin-enabled; leverage bands, `ordermin`, `costmin` and the alias ledger identical cell-by-cell. **The endpoint's borrow and limit columns moved**: `margin_rate` for shorts fell to 0.02 on ADA (was 0.04), AVAX (0.03) and DOT (0.024), so all nine alts now sit at the FLOOR of `kraken-fee-schedule.md`'s 0.02–0.04 % band — inside it, so no downstream figure is re-priced and `cli/costs/margin.py`'s bands still bound it; position limits moved on 7 legs (nothing outside this table reads them). Fee columns unchanged, so the drift detector is quiet. Venue churn: 4 pairs / 2 assets gone (CGN, ICX), 21 / 18 added — no candidate among them | **Tier 1, \$46.71 30-day spot volume** (futures \$0.00; AoP \$115.25) — read from the logged-in Fee tab 2026-09-04. Tier unchanged since #0, so nothing re-prices: \$46.71 selects the same tier-1 rates as \$0.00 (`cli/costs/fees.py`, run rather than assumed). The Fee tab quotes a shortfall one dollar above the break it targets — 46.71 + 2,454.29 = 2,501.00 = \$2,500 + \$1 — so it points at `kraken-fee-schedule.md`'s **\$2,500+** Tier 2, and the same convention reproduces #0's read (0.00 + 10,001 = \$10,000 + \$1). That +\$1 is an inferred UI convention, corroborated three times — this read, #0's, and the same screen's futures line (0.00 + 5,000,001 = \$5,000,000 + \$1, recorded here only as corroboration since the repo holds no futures ladder) — not a published boundary. #0's read was taken 2026-07-07, two days BEFORE the new schedule took effect, so its \$10,000 break was the then-current ladder correctly reported, not a stale screen. On the old ladder \$46.71 would have been quoted \$9,954.29 more, so **the account moved to the new ladder between 2026-07-07 and 2026-09-04 while the public endpoint has not** — this fetch still serves the twelve candidates at 0.25/0.40 with breaks at \$10k/\$50k, and no pair in the 1,446-pair response carries a \$2,500 break. The response is NOT uniform — by first-tier MAKER rate: 0.25 on 664 pairs, 0.23 on 682, 0.20 on 97 (which run 0.20/0.20 off a \$50k first break) and 0.00 on three, summing to the 1,446 — so this is scoped to the candidates deliberately: a uniformity claim would be a false baseline for a column this file declares a drift detector. That the account changed ladder is an inference from the boundary match; the Fee tab names no schedule version. AoP \$115.25 sits below the \$20,000 rung, the lowest the AoP ladder has, so it grants no tier; futures volume is \$0.00, below any threshold. Qualification takes the most favourable of the three, and none clears |

The last column exists because the account's own tier is the one fact here the **public** endpoints cannot supply — authenticated `kraken volume` serves it, and `cli/costs/fees.py` encodes the ladder it selects from. A sweep that silently carried the previous row's tier forward would manufacture exactly the false confirmation this log was built to make impossible, so an unperformed read is recorded as *not re-read*, never as unchanged.

**The verdict is read from the rendered candidate table, never from the raw hash.** Kraken's universe churns between
sweeps while the twelve §3 candidates hold, so the hash differs on a sweep in which no candidate fact moved —
**a changed hash is not a changed fact**, and treating it as one would manufacture an alarm every month.

**What stays parked: the observed margin/rollover bands.** No endpoint reports them and reading them takes a live
margin position, which no sweep does. The fee tier and AoP are read every sweep and recorded in the log above.

## Deferred: account-gated facts

Kraken's public endpoints do not carry the live maker/taker fee tier, the July-9-2026 Assets-on-Platform (AoP)
qualification rule, or the observed margin opening/rollover bands on majors — those require the live Kraken account.
**They are no longer "pending".** `T0000` collected them on 2026-07-07 and is **resolved and archived**
(`docs/open-topics/archive/T0000-phase0-account-actions.md`); the values live in
`docs/reference/kraken-fee-schedule.md`, and `cli/costs/fees.py` encodes that ladder verbatim. What
remains is keeping them current: the tier, the 30-day spot and futures volumes and the AoP held value are
the **automated** part of the monthly sweep (`/zcrypto-refdata-sweep` step 7, via `kraken volume`), and the
ladder's shape plus the AoP qualification ladder stay attended — the re-read that lost its trigger when T0000 was
archived, and now has one again.
