# Iterations history — Phase 0 (Preparation & Ratification)

Per-iteration changelog for Phase 0. Appended at each iteration's close-out; see `.claude/rules/prose.md`.

## 2026-07-07 — iter-001: trial registry (Phase 0 · P0-1)

- **`cli/registry/`** — every trial is recorded through the append-only, integrity-checked JSONL registry; a non-finite metric is refused on write and on read, so the PoC's NaN-DSR result cannot recur.
- **Registry integrity** — a load raises on a gap, duplicate or reordered `trial_id`, on a `record_hash` mismatch, and on a family count below what is already recorded; a torn trailing line self-heals, so a crashed append never bricks the autonomous loop.
- **`docs/specs/00000-trial-registry-design.md` + `docs/plans/00000-trial-registry.md`** — the design an agent extending the registry reads first; the cross-record hash chain, the corruption CI test and SPA/DSR computation were deferred here and land in Phase 2.
- **Known minor** — an externally hand-edited last line lacking its trailing newline makes the *next* append concatenate; it fails loudly on the following load, never as a silent fake winner.
- **`T0000`** — the Phase-0 human-gated items, the D3(i) account actions and the live fee/AoP confirmation, were parked there.
## 2026-07-07 — iter-002: Kraken reference-data snapshot register (Phase 0 · P0-2)

- **`cli/snapshot/`** — Kraken's public reference endpoints are fetched, derived and rendered through it, stdlib-only and with no API key; Kraken's in-body `error` array raises instead of returning a result.
- **The snapshot register** (`docs/reference/kraken-snapshot-register.md`) — the ground truth universe selection reads instead of the endpoints: per-symbol margin/leverage and order minimums, the Kraken symbol-alias ledger (XBT=BTC, XDG=DOGE), and provenance; the raw snapshot JSON lands under `data/snapshots/` (gitignored) and the doc records its hash.
- **Known minor** — `fetch_public` on a malformed-but-`error`-free response (a missing `result`, not a shape Kraken's API returns) raises `KeyError` rather than `SnapshotError`.
- **`T0000`** — the live fee-tier, the July-9 AoP rule and the rollover bands stayed account-gated there; the L2 capture daemon is Phase 1.
## 2026-07-07 — iter-003: NautilusTrader Kraken adapter smoke test (Phase 0 · P0-3)

- **The NautilusTrader Kraken adapter's public data path is verified** — instruments, quotes, trades and bars stream from Kraken's public Spot WebSocket with no API key, run in a throwaway venv; `nautilus_trader` is deliberately not a project dependency, adding it being a Phase-6 step.
- **`docs/research/01.2.nautilus-kraken-adapter-memo.md`** — what an agent reads before wiring the adapter: the data-client API surface, the confirmed keyless public-data config, the rough edges to route around, and what the verdict does not cover (a short single-pair Spot-only run).
- **`T0000`** — the execution side (spot-margin/leverage/short/post-only order semantics and reconciliation) was parked for Phase 6, needing a trade key.
- **Phase 0's autonomous work ends here** — the remaining exit-bar items were human-gated in `T0000`, and the loop advances to Phase 1 (Data Foundation).
