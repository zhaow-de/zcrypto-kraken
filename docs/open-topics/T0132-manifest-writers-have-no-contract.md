---
status: open
ripe_when: a consumer needs to read manifests generically. Spec `00086` is NOT one and no longer waits on this — its provenance identity is computed from file bytes, and its only manifest touch is a vouched-hash cross-check that walks any JSON shape without extracting structure. So the trigger is "someone proposes a generic manifest reader again", and the answer should be "normalise first" — two attempts at such a consumer have now failed nine cold-review rounds against this exact heterogeneity. Also ripe if a manifest writer is being touched for another reason and the change could cheaply carry a shared shape
---

# The manifest writers have no contract, so nothing can read them generically

## Context — what

Five committed writers emit `manifest.json` for canonical datasets, plus one externally-produced freeze. They agree on nothing structural:

| writer | dataset(s) | `series` shape | set digest | timestamp |
|---|---|---|---|---|
| `cli/backfill/backfill.py` | `ohlc-full`, `ohlc-15m` | `[pair][interval]` nested | `basket_sha256` | `fetched_at` |
| `cli/derivatives/funding.py` | `derivatives-funding` | `[symbol]` flat | `basket_sha256` | `fetched_at` |
| `cli/derivatives/oi.py` | `derivatives-oi` | `[symbol]` flat | `basket_sha256` | `fetched_at` |
| `cli/ohlc/reach.py` | `ohlc-reach` | **`list[dict]` rows** | `basket_sha256` + `detached_sha256` | `fetched_at` |
| `cli/ohlc/ingest.py` (v0, retired) | `ohlc` | `list[dict]` rows | **none** | — |
| external freeze | `ohlc-holdout-*` | `[asset]` flat | **`manifest_sha256`** | **`pulled_at`** |

Four `series` shapes, two set-digest spellings, two timestamp keys, and one dataset with no set digest under either name.

Two further hazards measured 2026-08-08:

- **`ohlc-reach` carries a per-run nonce.** Its `series_digest` moves on every rebuild with zero content change — so any consumer hashing it reads a false drift alarm.
- **`ohlc-15m`'s `source` is an absolute machine-local path.** A manifest rebuilt on another host changes it, so any consumer including `source` in a digest gets a false difference between nodes holding identical bytes.

## Why this matters

This is not a tidiness complaint — it has already cost a full design cycle. Spec `00086`'s first version tried to capture dataset provenance generically from any manifest. It failed **four consecutive rework-and-cold-review rounds** (10 → 6 → 6 → 5 blocking findings, both reviewers rejecting every round). The findings kept *moving* rather than recurring: round 1 was "the holdout set is unregisterable", round 4 was "`derivatives-funding`/`-oi` are unregisterable" and "`ohlc-reach` false-alarms". Every round handled one more shape and met another.

The root cause is that there is no contract to read against, so a generic reader is really a pile of special cases discovered one review at a time. A second design then narrowed to a two-adapter allowlist and still did not converge — five more rounds, stopped by judgement rather than agreement.

**What finally shipped (2026-08-09) did not solve this; it stopped depending on it.** `00086`'s provenance derives dataset identity from the bytes a run reads, so no manifest is parsed in the identity path and the four `series` shapes, two digest spellings, per-run nonce and machine-local path cost it nothing. Its one manifest touch is a vouched-hash cross-check that walks any JSON without extracting structure, so it is not a generic reader either.

So nothing is blocked on this today, and that is precisely the risk: the zoo is unchanged and the next consumer that genuinely needs to read a manifest generically pays the whole cost again. **That is what this topic exists to prevent.**

## Findings so far

- The table above, read from the writers themselves rather than from the files, so it reflects what will be emitted next time rather than what happened to be on disk.
- The holdout manifest is **not ours to normalise** — it is produced by an external freeze process. Any contract has to either accommodate it or explicitly exclude it.
- Nothing currently reads manifests generically. `cli/data/rebuild.py` reads specific ones; `cli/data/sync.py::_verify_new_files` verifies per-series hashes at ingest. So there is no live breakage — this is a latent cost, payable on the next generic consumer.

## Suggested next steps

- **(design, when triggered)** Decide the contract: required keys (`series`, a set digest under ONE name, a timestamp under ONE name), a single `series` shape, and an explicit rule for per-run values — a nonce like `ohlc-reach`'s `series_digest` and a machine-local `source` must be OUTSIDE anything a consumer would hash, or absent.
- **(autonomous, after that)** A single shared writer/reader in `cli/` that every producer calls, so the shape cannot drift per-writer again; plus a test walking every `data/*/manifest.json` on disk and asserting conformance.
- **(decide explicitly)** Whether existing manifests are migrated, versioned in place, or left as legacy shapes behind adapters. They are gitignored data, so a migration is a rebuild, not a rewrite of history.
- **(carry)** `00086`'s two manifest adapters were the concrete statement of what a generic consumer needs — they were **deleted** when the design moved to observed bytes, so a migration has no in-repo consumer to build against. Recover the requirement from `git show 82379bf4:cli/registry/provenance.py` rather than from anything at HEAD.
