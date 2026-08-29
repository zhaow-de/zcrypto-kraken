---
status: open
---

# `zcrypto engine flatten` — the red button

## Context — what

A market crash where everything must be converted to EUR within minutes has no primitive today: the kill switch cancels resting orders and refuses intents but **closes no position**; the only close path is a hand-signed probe plan through the 15-minute maker-first machine, with a 60-minute expiry and a pre-boundary blackout — built to be slow and careful, the opposite of a red button. The owner ruled the primitive on 2026-08-29: **whole account, market orders, kill file first.** Spec `00106` (this branch) is the design; this topic is its git-tracked residual holder.

## Why this matters

Scenario D (unattended open positions) and drill B in spec `00105` both end in "the operator's response is B" — and B does not exist. Rung 1 holds real margin positions across rollovers by design ([[T0018]]); a provider-level event ([[T0088]], accepted as-is with no standby) leaves the engine dead with positions open, and the master plan §10's "watchdog-triggered flatten-or-freeze runbook" was never built. The kill file plus a Kraken web UI is the entire emergency surface until this lands.

## Findings so far

- **The ruling, and what it overrides.** Whole account (pre-existing spot balances included — engine-owned-only is not "everything to EUR"); **market** orders, because in a crash the price is not the variable, time is; the kill file written first so nothing re-opens. Spec `00090` D6 records *"Rejected: MARKET as the fallback — unbounded price on the live path when a bounded marketable limit does the same job"* — that rejection stands for the probe machine; `00106` overrides it **for this command only**, and says so, because a bounded IOC in a fast market leaves residue and the residue is the exposure.
- **No market path exists in the engine**: `cli/engine/executor.py` builds only `order_factory.limit(...)` (GTC post-only, then IOC); nothing in `cli/engine/` constructs a market order. Margin closers today ride `_classify_margin_close` — sized from the Cache's live position with the venue's `reduce_only` flag — and spot disposals ride `_classify_spot_close` with an owner-supplied `qty`. `settle-position` is UI-only for the adapter (spec `00090` context).
- **The command must work while the engine is disarmed, kill-latched, or stopped** — that is the whole point. A hand-placed kill file on an idle engine cancels nothing until the next restart; while a plan rests, the 5-second poll revokes it. So the command's first act after the kill file is to wait for `level=none` (or the engine to be stopped), then cancel everything the venue still holds — never assuming the engine cancelled anything (what a `systemctl stop` does to a venue-resting GTC order is unverified in the repo).
- **The open design fork the spec settles**: out of process (a standalone invocation against the venue's REST surface, independent of the node and its state machine) versus inside the node (reusing the exec client but inheriting the plan machinery). The spec rules; the ruling's reasons are recorded there.
- **Fills raced by a cancel, dust below `ordermin`, and a leg the venue rejects** are the three ways "flat" fails to mean flat; the exit code must distinguish flat / partial / venue unreachable, and the journal must record what was attempted and what the venue answered, per action.

## Suggested next steps

- **(autonomous)** Write plan `00106` from the spec on its own branch; cold spec+plan review at the **Fable floor** (live trade path); execute with TDD against a fake venue client that records submissions and answers; whole-branch review at the Fable floor; PR; merge on CI green. The code ships **disarmed** in the sense that nothing invokes it — it reaches the fleet only on the converge below.
- **(autonomous)** The runbook section `infra/runbooks/engine-procedures.md#engine-flatten` — PROCEDURE: when to press it, the exact invocation, what the exit codes mean, and what to read on Kraken afterwards — lands with the code.
- **(human)** The engine converge carrying `00106` (with `rest-hold`), inside an inter-cycle gap, per `zcrypto-rollout-image` and the canary rule.
- **(human)** After the converge — the wrapper reaches the host only then — the live read-only dry-run on the engine host **through the wrapper**, the engine running and a spot balance present — the five read shapes proven against the real venue and recorded as a row in `docs/reference/adapter-verification/<version>.md`; until it exists the command's live use is unverified and the runbook says so.
- **(human)** Drill B at rung 1 against A2's real position and a small spot balance: decision-to-flat is the number; the drill-log entry closes this topic's execution half. Anything the drill finds that the spec did not foresee lands here.
