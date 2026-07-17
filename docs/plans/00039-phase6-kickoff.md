# Phase-6 Kickoff Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Execute spec `docs/specs/00039-phase6-kickoff-design.md`: add NautilusTrader to the locked environment, run the §7 adapter-verification probes attended, write the verification memo with a pass/fail verdict, and close the iteration.

**Architecture:** One small committed-code task (the dependency + an import/version smoke test), then orchestrator-run attended probe drivers per the established scratchpad pattern (read-only probes first; order-placing probes only on the human's explicit go), then docs/lifecycle. The key ceremony and its vault commit are already done (`0402bc3`); T0018/T0005 topic sync is already done (`bb67cb9`).

**Tech Stack:** Python 3.14, uv, `nautilus-trader==1.230.0` (cp314 wheels verified on PyPI), stdlib.

## Global Constraints

- **Attended-only money surface**: probes that place orders (spec probes 4–6) run only in the orchestrating session, each batch preceded by the human's explicit go. No subagent ever places, modifies, or cancels an order. Probe scripts never print key material; secrets load via `ansible-vault view --vault-password-file infra/ansible/scripts/vault-pass.sh infra/ansible/group_vars/capture_host/vault.yml` in-process. **(Correction, 2026-07-17 — T0061: this command is doubly wrong and always was. (a) The trade key no longer lives in `group_vars/capture_host/vault.yml`; it moved to `group_vars/engine_host/vault.yml`, so that the capture-only secondary stops resolving the live credential. (b) `ansible-vault view` never worked on these files anyway: they use per-VALUE encryption, not whole-file, so `view` returns "input is not vault encrypted data". The working recipe — extract one block, de-indent, decrypt on stdin — is documented in `group_vars/capture_host/vault.yml`'s own header. Stage 6b's executor: read that header, not this line.)**
- **Zero-fill discipline** (spec decision 4): resting probes priced ≥ 25 % away from market, canceled immediately after acknowledgment; the only intended fill is probe 5's ~€10 BTC round-trip. An unexpected fill is a reportable finding, bounded by order size.
- **Fallback trigger scope** (spec decision 1): only an order-semantics/reconciliation failure (probes 2, 4–6) auto-triggers the thin-custom fallback; any other failure is documented and escalated to the human. A probe unexecutable *as designed* is a protocol artifact — redesign and re-run, never an adapter failure.
- **Precondition for probes 4–6**: spot wallet holds ≥ €50 EUR (ceremony verification 2026-07-10 read **0 assets** — the human funds or transfers before these probes run).
- Ruff 132/double quotes; gate `uv run pre-commit run -a`; commits carry the actual-model trailers; every Claude-authored commit gets subagent review + `Reviewed-by:` trailer before push (spec/plan/closeout-docs commits exempt per `commit-messages.md`).

______________________________________________________________________

### Task 1 (subagent, TDD): nautilus-trader dependency + adapter smoke test

**Files:** Modify `pyproject.toml` + `uv.lock` (via `uv add "nautilus-trader==1.230.0"` — never hand-edit the lock), create `tests/test_nautilus_adapter.py`.

Steps:

- [ ] Write the failing test first (`tests/test_nautilus_adapter.py`): assert `nautilus_trader.__version__ == "1.230.0"`; assert the official Kraken adapter is importable (`import nautilus_trader.adapters.kraken` and, discovered from the installed package, its config/factory module — e.g. the exec/data client config classes; use the exact names found in the installed 1.230.0 tree). Run: `uv run pytest tests/test_nautilus_adapter.py -v` → FAIL (ModuleNotFoundError).
- [ ] `uv add "nautilus-trader==1.230.0"` (exact pin: the §7 verification memo is version-specific; Dependabot proposes bumps, each re-gated by the memo's re-check note).
- [ ] Re-run the test → PASS. Full suite `uv run pytest` → green (~954 tests).
- [ ] `uv run pre-commit run -a` → clean; commit `build(config): add nautilus-trader 1.230.0 with kraken adapter smoke test`.

### Task 2 (orchestrator, attended): read-only probes 1–3

Scratchpad driver(s) (`probe_readonly.py`), per the spec's protocol section: (1) auth + balance through the **adapter's** components (not raw REST — the §7 subject is the adapter); (2) reconciliation read — open orders + positions at client start, expect empty-or-actual; (3) WS market data — subscribe trades/quotes for the 10 EUR pairs, expect ticks on liquid pairs within seconds, clean shutdown. Harness shape: the adapter's HTTP/exec client directly where feasible, a minimal `TradingNode` where the client demands the full node — record which shape each probe used (the memo needs it). Read-only: no explicit go needed beyond this plan's approval. Capture expected-vs-observed per probe for the memo.

### Task 3 (orchestrator, attended, human-go gated): order probes 4–6

Precondition: spot EUR ≥ €50 confirmed. Scratchpad driver (`probe_orders.py`) executing spec probes 4 (zero-fill ×4: far post-only rest+cancel; crossing post-only → rejection event; leveraged long rest+cancel; leveraged short rest+cancel), 5 (~€10 BTC market buy → reconcile → close), 6 (post-run reconciliation: orders/positions empty, balances reflect only probe 5). **Stop and obtain the human's explicit go immediately before running each of probes 4 and 5.** Every acknowledgment, event, and reconciliation snapshot logged to the scratchpad for the memo.

### Task 4 (orchestrator): verification memo + closeout

- [ ] Write `docs/research/14.phase6-adapter-verification.md`: per-probe expected vs observed, the pass/fail verdict per the spec's pre-registered rule, the harness shapes used, and a re-check note for future version bumps. Append it to the mdformat allowlist in `.pre-commit-config.yaml` (research-report rule).
- [ ] Human action (after the memo lands): remove the workstation IP from the key's allowlist (spec decision 3 closure); confirm in the memo's closing line.
- [ ] Append the iter-079 entry to `docs/iterations-history.md` (kickoff decisions ratified, key ceremony, verification verdict, T0018/T0005 sync, go-live criteria pre-registered).
- [ ] `uv run pre-commit run -a` → stage everything → commit; PR into `develop` titled `feat(config): iter-079 — phase-6 kickoff: adapter verification, key ceremony, go-live pre-registration` (aggregated trailers per `pull-requests.md`); hold the merge for the human's go.
