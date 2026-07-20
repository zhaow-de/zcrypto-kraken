# Spec 00065 — make the replay fingerprint's coverage structural (T0080)

## Goal

Replace `_REPLAY_CODE_PATHS`' hand-enumerated module list with the **transitive `cli.*` import closure** of the replay entry points, so spec `00060` D3's invariant — *"the modules that determine a replay's result"* — becomes true by construction instead of by whoever last remembered to add a file.

## Why

D3 has claimed that coverage since it was written. It has never held. The list has been wrong **three separate times**:

| round | added | how it was found |
|---|---|---|
| original | 4 modules | — |
| iter-109 review | +6 modules | review catch |
| spec `00064` D9 | +2 (`command.py`, `dataset.py`) | mutation audit |
| **still missing** | the re-export layers | adversarial verification of D9 |

Measured: the current twelve-module list covers **12 of the 54 modules** that actually determine a replay — about 22%. Each round added the specific file someone noticed and re-asserted the invariant as true. That is the fix-the-instance defect [[T0075]] documents, one level up, and it is why nobody re-checked.

**The residual hole is proven, not theoretical.** `cli/engine/concordance.py:24` imports `build_crossfreq_system_fast` *from `cli.portfolio`* — through the unhashed `__init__.py`. Rebinding it there:

```
BEFORE  replay_fingerprint : cc08f1e0ddfbfadc46aad5ffa1f4986c53643cc446340b552d359ee0c985cd1b
AFTER   replay_fingerprint : cc08f1e0ddfbfadc46aad5ffa1f4986c53643cc446340b552d359ee0c985cd1b
        tests              : 31 passed
```

Byte-identical, suite green, and every replay now runs the *verified* daily-oracle builder — a different verdict, served from cache as a stale PASS, on the artifact authorising real-money trading.

**Enumeration cannot fix this.** Any list records the modules someone thought of; only a computed closure records the modules that are actually reachable. This spec stops patching the list and changes what the list *is*.

## Decisions

- **D1 — roots are explicit and small; coverage is derived.** Three entry points: `cli/engine/concordance.py` (`replay_cycle`, `compare_targets`, `evaluate_gate`), `cli/engine/command.py` (`_snapshot_reader`, and the exception→verdict classification sites), `cli/ohlc/dataset.py` (`read_parquet`). Everything else is *computed*. The roots keep the whole-tuple pin discipline of `00064` D1 — three entries, asserted exactly — because the roots are now the only hand-maintained input and therefore the only thing that can silently drift.

- **D2 — static AST walk, never runtime `sys.modules`.** Reading `sys.modules` would be simpler and would capture real bindings, but it makes the fingerprint depend on **which CLI subcommand is running**, since a different entry point imports a different set. The fingerprint would then differ between `gate-export` and `report` for identical code, invalidating the cache on invocation shape rather than on code change. A static walk from fixed roots is deterministic and depends only on bytes on disk.

- **D3 — `cli.*` only; third-party is out.** `numpy`'s version is already digested separately (T0074), and walking site-packages would be enormous and version-noisy. An import of a non-`cli` module contributes nothing to the closure.

- **D4 — deterministic order.** Digest in sorted repo-relative path order. Set iteration order is not a stable input, and an unstable digest would rebuild the cache on every run — the failure mode that looks exactly like a working cache while doing no work.

- **D5 — resolve a `from cli.pkg import X` to BOTH `cli/pkg/__init__.py` and `cli/pkg/X.py` when the latter exists.** `X` may be a submodule or a re-exported name, and distinguishing them statically requires resolving the package's own `__init__`. Including both is over-inclusion, which D3's standing rationale makes safe. This is exactly the case the current list misses.

- **D6 — a file that cannot be parsed is still DIGESTED; only its edges are lost.** `imports_of` swallowing a syntax error must not mean the file drops out of coverage. Digest bytes unconditionally; use the AST only to find further edges. The safe direction is: always hash, sometimes fail to traverse. (Traversal loss is bounded — a file that does not parse also does not import.)

- **D7 — the guarantee is pinned by the exploit, not by the list.** The old exact-tuple pin cannot survive: there is no tuple any more. Its replacement is three pins — (i) the closure **contains** each critical module (the twelve, plus the three re-export layers and `errors.py`); (ii) **the exploit**: rebinding the fast builder in `cli/portfolio/__init__.py` must move the fingerprint — this is the guarantee, the closure is merely today's implementation of it; (iii) **determinism**: the same tree yields the same digest across runs and process restarts. Losing (iii) silently disables the cache.

- **D8 — never raises to the caller.** Spec `00060` D5 stands: a missing or unreadable module degrades this run to the no-cache path, logged, never aborting. Gate evidence outranks the cache.

- **D9 — one cold rebuild, and only one.** Changing what is digested invalidates the whole cache by design (~627 s on the NAS versus 55 s warm). `00064` D9 already forces one on this branch; landing this in the same PR means the fleet pays it **once**, not twice.

## Non-goals

- **Changing what a replay computes.** Test-and-fingerprint work only; `replay_cycle`, `compare_targets` and `evaluate_gate` are untouched.
- **Hashing third-party code** — D3.
- **Optimising the walk.** 58.6 ms measured (54 modules, walk 58.2 + digest 0.4) against a 55–627 s run: 0.1% of the cheapest case. Memoising it is a solution to a problem that does not exist.
- **Revisiting `00064`'s 19 pins.** They pin `evidence_fingerprint` and the fail-open paths, which this does not touch.

## Test list (TDD)

1. **Roots pinned exactly** — the three-entry root tuple, exact and ordered; removing or reordering any fails (D1).
2. **The exploit** — rebinding `build_crossfreq_system_fast` in `cli/portfolio/__init__.py` changes `replay_fingerprint`. Pre-change this is byte-identical; it is the whole point (D7-ii).
3. **Closure contains every critical module** — the twelve previously listed, plus `cli/portfolio/__init__.py`, `cli/risk/__init__.py`, `cli/alpha/__init__.py`, `cli/engine/errors.py` (D7-i).
4. **Determinism** — repeated calls, and a fresh process, produce the same digest; independent of `cwd` (D4, D7-iii).
5. **Sorted order is load-bearing** — digesting in unsorted order must fail the determinism pin.
6. **Submodule + package both resolved** — a `from cli.pkg import X` root pulls in `cli/pkg/__init__.py` *and* `cli/pkg/X.py` (D5).
7. **Unparseable module still digested** — a syntactically broken module inside the closure contributes its bytes; the fingerprint responds to editing it (D6).
8. **Never raises** — a missing root or unreadable module degrades to the no-cache path rather than propagating (D8).
9. **Non-`cli` imports excluded** — importing a third-party module does not enlarge the closure (D3).
10. **Regression** — the full suite passes; `00064`'s 19 pins are unaffected.
