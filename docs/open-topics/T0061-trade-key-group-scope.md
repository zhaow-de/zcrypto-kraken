---
status: open
ripe_when: before go-live hardening (T0049), or the next time the trade key is rotated anyway
---

# The live trade key is group-scoped to capture_host

## Context — what

The live Kraken trading credential (`kraken_trade_api_key` + `kraken_trade_api_secret`) lives in `infra/ansible/group_vars/capture_host/vault.yml`. `capture_host` is `zcrypto` + `zcrypto-red`, so the **capture-only secondary resolves the live trading credential**; no `group_vars/engine_host/` exists at all. The only thing confining the key to `zcrypto` is **play targeting**: `site.yml`'s engine play converges `engine_host` (which contains only `zcrypto`), and `engine.env.j2` is the sole template that renders the values. Group-vars resolution happens on the controller, so nothing has landed on `zcrypto-red`'s disk — but membership, not targeting, is what the inventory comments present as the boundary.

## Why this matters

The inventory says `zcrypto-red` "must never join engine_host, or the live Kraken trade key would be rendered onto a host that has no business holding it" — implying group scope is the protection. It is not: any future play or role that mis-targets `capture_host` with the engine template renders the live trading key onto an internet-facing capture box, with no group boundary in the way. The 2026-07-17 branch review caught `group_vars/observed/vault.yml`'s header **asserting the engine_host scoping already exists** ("the same reasoning that keeps the live trade key in engine_host rather than capture_host" — false, corrected in the same change that registered this topic); a comment claiming the protection exists is precisely what ensures the real mis-scope never gets fixed. The exposure widens whenever `capture_host` gains members or new plays (e.g. T0020's capture-VPS Alloy work).

## Findings so far

- Boolean-probe evidence from the 2026-07-16 vault re-scoping (commits `4acb7f0`, `8b6d21c`): `zcrypto-red` resolves the trade-key vars (`trade=True`); `zcrypto-ops` and `localhost` do **not** (spec 00051 D10 holds for ops).
- The move is small — two `!vault` ciphertext blocks relocate verbatim (same vault password; per-value encryption means no decrypt is ever needed) — but it touches the **live trading credential**, so it is human-gated: schedule it into go-live hardening (T0049) or fold it into the next trade-key rotation, when the values are being replaced anyway.

## Suggested next steps

All steps are the exact recipe the 2026-07-16 `observed`-group move used — ciphertext-verbatim, boolean-probe verified, never a decrypted value anywhere:

1. `mkdir -p infra/ansible/group_vars/engine_host`, create `group_vars/engine_host/vault.yml` with a header comment (scope: the engine play's live trading credential; `engine_host` = `zcrypto` only), and copy the `kraken_trade_api_key:` and `kraken_trade_api_secret:` blocks **verbatim as ciphertext** (the whole `!vault |` block, unmodified) from `group_vars/capture_host/vault.yml`. Do not decrypt, re-encrypt, or run any command that prints values.
2. Delete those two blocks from `group_vars/capture_host/vault.yml` (leaving its other secrets untouched).
3. Verify by **boolean probes only** (from `infra/ansible/`; NEVER `ansible-inventory --host/--list` — it prints every secret): `ansible zcrypto -m debug -a "msg={{ kraken_trade_api_key is defined }}"` → expect `True`; same probe on `zcrypto-red` → expect **`False`** (the fix); on `zcrypto-ops` → expect `False` (D10 still holds). Repeat for `kraken_trade_api_secret`.
4. Preview the engine play (`./scripts/run.sh site.yml --limit zcrypto --tags engine --check --diff` with the usual digest vars) and confirm the engine env template still resolves — the check must show no failure on undefined variables and no diff on the (0600, `no_log`) env file; never print the rendered file.
5. Then correct the T0061 pointer in `group_vars/observed/vault.yml`'s header (its parenthetical describes the pre-move state) and close this topic.
