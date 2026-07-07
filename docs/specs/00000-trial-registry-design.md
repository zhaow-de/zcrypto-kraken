# Trial Registry — Design (Phase 0 · P0-1)

**Iteration:** iter-001 · **Phase:** 0 (Preparation) · **Status:** design approved (unattended loop)
**Master plan refs:** `docs/research/00.master-plan.md` §7 (ratified stack — "validation owned, auditable, tested"), §9 item 7 (registry integrity by construction).

## Problem & context

Every future research iteration (Phase 2+) evaluates a **trial** — one `(spec, dataset, seed(s))` run through the validation harness, producing metrics and a verdict. Those results must land in an **append-only, integrity-checked registry** so that (a) the multiple-testing trial count is honest, and (b) any verdict is auditable later.

This is the first-class deliverable §9 calls "integrity by construction." It exists because the PoC's registry was *broken*: it emitted a **NaN deflated-Sharpe (DSR)** that re-parsed cleanly and minted a fake "winner." The single most important property here is that **a NaN/inf metric — a DSR above all — can never enter or leave the registry silently.**

## Goals

- A typed **trial record** and an **append-only JSONL store** with **loud-failure** integrity checks, stdlib-only, living at `cli/registry/`.
- Encode the NaN-DSR failure so it cannot recur — on **both** the write and read paths.
- Be robust enough to serve the **autonomous** Phases 1–5 loop unattended (a crashed append must not brick it).

## Non-goals (deferred to Phase 2, per §9)

- Cross-record **hash-chain** tamper-evidence (`prev_hash` + chain verification).
- The pipeline-level **CI test** that corrupts a registry copy and requires loud failure.
- **SPA/DSR computation** and a named `dsr`-present guard (no caller can produce a real DSR until the harness exists).

These graft on later by adding one field / one test — no reformat. We do **not** pre-build scaffolding for them (Simplicity First).

## The trial record

A frozen dataclass, serialized one-per-line. **Caller-supplied** fields are validated; **store-owned** fields are stamped by the store and rejected if a caller supplies them.

| Field | Type | Source | Rule |
|---|---|---|---|
| `trial_id` | int | store | Monotonic, **contiguous** `1..N` in file order. |
| `schema_version` | int | store | Stamped `SCHEMA_VERSION`; load raises if a line's version is unknown. |
| `timestamp` | str | store | tz-aware UTC ISO-8601 (`datetime.now(timezone.utc).isoformat()`). |
| `iteration` | str | caller | `iter-NNN` tag; non-empty. |
| `family` | str | caller | Strategy family (A1/B2/…); the DSR-deflation grouping key; non-empty. |
| `spec_hash` | str | caller | Content hash of the strategy spec; non-empty (registry does not recompute it). |
| `dataset_hash` | str | caller | Content hash of the dataset (§8: reference a hash, never "latest"); non-empty. |
| `seeds` | list[int] | caller | Seed(s) evaluated; **present, may be empty** (deterministic strategies like the B3 gate have no seed). |
| `metrics` | dict | caller | Non-empty JSON object; leaves are finite numbers nested to any depth via dicts and lists (§9 outputs: CPCV path-Sharpe lists, per-fold dicts, CI pairs). **Every numeric leaf must be finite.** |
| `n_trials_in_family` | int | caller | Pre-registered family trial count for DSR deflation; `>= 1` **and** `>= count of prior same-family records`. |
| `verdict` | str | caller | One of `VERDICTS = {adopt, reject, park}`. |
| `run_ref` | str \| None | caller | Optional id / content-hash pointing at the run bundle in `runs/` (the evidence). Nullable at Phase 0. |
| `notes` | str | caller | Free text; default `""`. |
| `record_hash` | str | store | sha256 over the canonical serialization of all *other* fields (see Immutability). |

## Storage & serialization

- **Append-only JSONL**, UTF-8, LF-terminated. The store opens the file **only** in mode `"a"`; the public API exposes **no update or delete** — append-only is enforced *structurally*, not just by convention.
- **Canonical serialization** (load-bearing): `json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)`. Sorted keys + compact separators make each line byte-stable so `record_hash` reproduces on reload; float formatting uses Python's guaranteed shortest round-trip `repr`, which is stable across CPython patch releases.
- **The NaN defense (the core of this design):**
  - **Write path:** `allow_nan=False` means the store *physically cannot emit* the bare `NaN` / `Infinity` tokens — a non-finite value raises `ValueError` at dump time, before anything touches disk.
  - **Read path:** `json.loads(line, parse_constant=_reject)` where `_reject` raises `RegistryCorruptionError` — so a hand-edited or externally-produced poison token fails **loudly on read** instead of deserializing to `float('nan')`.
  - **Layered on top:** a generic **finiteness assert** (`math.isfinite` over every numeric leaf) that **recurses into dicts AND lists** — because the harness's own outputs are structured (§9: the CPCV distribution of ~45 path Sharpes is a *list*; bootstrap CIs are pairs; cost-stress variants are nested). A dict-only or scalar-only walk would wave a NaN buried one level down straight through.
- **Types:** validated structurally; `bool` is rejected where `int` is expected (`bool` subclasses `int` — mirrors `cli/config.py`'s existing guard). Numpy scalars are rejected, not coerced (they would break deterministic serialization).

## Integrity asserts (Phase 0)

Run on **append** (the new record) and on **load** (every persisted record). Every violation raises — never a silent coerce.

1. **Required fields present + correctly typed** (incl. bool-as-int rejection).
2. **All metric leaves finite** — the recursive dict+list `isfinite` walk; plus the write/read NaN-token guards above.
3. **`trial_id` contiguous & increasing** — ids are exactly `1..N` in file order (first is `1`). Contiguity (not mere strict-increase) turns a dropped/duplicated/reordered line into an observable gap.
4. **`verdict` ∈ VERDICTS.**
5. **`n_trials_in_family` sanity** — `>= 1` and `>= count of prior records in the same family` (you cannot have *tried* fewer than you've *recorded*; closes the understate-the-denominator gaming that inflates a deflated Sharpe).
6. **`schema_version` known** — load raises if a line's version ≠ `SCHEMA_VERSION`.
7. **Well-formed JSONL** — a malformed *interior* or *complete* line raises `RegistryCorruptionError` (never skipped). A torn *trailing* line is handled separately (below).
8. **`record_hash` matches** — see Immutability.

## Immutability model

Baseline "a lightweight per-record check on re-read" is **vacuous without stored state to compare against**, so each record carries a **self-hash**: `record_hash = sha256(canonical_json(record_without_hash))`, computed by the store at append. On load, the store recomputes each record's hash from its other fields and raises on any mismatch — catching a silent finite→finite edit (e.g. `sharpe 0.30 → 0.90`) that the finiteness assert cannot see.

**Honest limit (stated in the module docstring):** this detects **accidental / careless** in-place edits and — together with contiguity — deletion, truncation, and reordering. It is **not** tamper-evidence against an editor who also recomputes the hash; closing that gap is exactly the Phase-2 cross-record hash-chain. Append-only-ness itself is enforced structurally (open `"a"` only; no update/delete API).

## Identity & concurrency

- **Single-writer is the contract** (the autonomous loop is sequential). But `trial_id` assignment must never trust stale in-memory state, so `append()` re-derives `next_id` **from the file on disk**, inside an `fcntl.flock(LOCK_EX)` critical section spanning read-tail → assign → write → `os.fsync`. `flock` is advisory + weak on NFS, but on the single-host Linux deployment surface (§8) it is cheap stdlib insurance against a second process (a sweep + a manual run) minting a duplicate id. The in-memory `.records` cache is a read convenience; the file is the authority.

## Torn-tail recovery (autonomous-loop safety)

A crash mid-append leaves a **partial trailing line** — a known, benign, self-inflicted state. Raising on it would halt every subsequent iteration until a human intervened. So on load, **iff** the file does not end in `\n` **and** its final line fails to parse, the store **truncates exactly that one trailing partial line** (physically, so the next append is clean) and logs it **loudly** via `get_logger("registry.store")`. Every *complete* line and every *interior* line still raises `RegistryCorruptionError`. Body corruption stays loud-fail; only the self-inflicted torn tail self-heals.

## API surface

```
TrialRegistry(path: Path)          # loads + validates existing JSONL (all asserts; torn-tail self-heal). Empty/absent file = empty registry.
  .append(*, iteration, family, spec_hash, dataset_hash, seeds, metrics,
          n_trials_in_family, verdict, run_ref=None, notes="") -> TrialRecord
                                   # keyword-only (many string args must not transpose); validates, stamps store-owned
                                   # fields under flock, writes one line + fsync, returns the frozen record.
  .records -> tuple[TrialRecord, ...]   # read-only snapshot
  .__len__() -> int
```

Module also exports: `TrialRecord` (frozen dataclass), `RegistryError` (base), `RegistryCorruptionError(RegistryError)`, `VERDICTS`, `SCHEMA_VERSION`, and helpers `canonical_json()` / `compute_hash()`.

## Module layout

Library package (not a Typer subcommand), stdlib-only, mirroring the `cli/logging/` multi-file style:

- `cli/registry/__init__.py` — re-exports the public names.
- `cli/registry/record.py` — `TrialRecord` dataclass; `canonical_json()`, `compute_hash()`; single-record `validate()`.
- `cli/registry/store.py` — `TrialRegistry`: load (+ torn-tail heal), `append()` (flock/fsync), the cross-record asserts (contiguity, family-count).
- `cli/registry/errors.py` — `RegistryError`, `RegistryCorruptionError`.

## Testing

`tests/test_registry_*.py`. Beyond happy-path append/reload round-trips, the **planted-corruption** suite must include:

- a hand-planted **bare-`NaN`-token** line → `RegistryCorruptionError` on load (proves `json.loads`' default acceptance is closed);
- an attempt to `append()` a metric of `float('nan')` / `inf`, incl. **buried in a nested dict and in a list** → raises before write;
- a **torn trailing line** → self-healed + loud log, registry still appendable; vs. a **torn interior line** → raises;
- `trial_id` **gap / duplicate / reorder** → raises;
- a **`record_hash` mismatch** (mutated finite→finite value) → raises;
- **bool-as-int** and unknown-`schema_version` rejection;
- `n_trials_in_family` **below the prior family count** → raises;
- `seeds=[]` accepted; empty `metrics` rejected.

## Alternatives considered

Design was generated by a 3-proposal panel (minimal-stdlib / validation-rigor / phase-2-forward-compat) + an adversarial critic. Key resolutions: the **stateful `TrialRegistry(path)` object** (ergonomics) was kept but made to **re-read `next_id` under lock** (killing the minimal proposal's silent-divergence-under-concurrency bug); the **NaN read-path guard** (`parse_constant`) was made mandatory, not optional, because a finiteness assert alone leaves the exact PoC round-trip open; **metrics** was widened to nested+list to hold the harness's real outputs; **torn-tail self-heal** and the **`n_trials_in_family` cross-check** were added; and the forward-compat proposal's `_HASH_STRATEGIES` dispatch table + reserved `prev_hash` field were **dropped** as speculative Phase-2 scaffolding (Simplicity First), keeping only its cheap known-`schema_version` guard.

## Closeout (planned)

On merge: append an `iter-001` entry to `docs/iterations-history.md`; the Phase 0 human items stay parked in `T0000`. (Authored at closeout, not now.)
