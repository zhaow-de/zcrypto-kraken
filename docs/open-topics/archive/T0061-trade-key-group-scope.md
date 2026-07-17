---
status: resolved
---

# The live trade key is group-scoped to capture_host

## Context — what

The live Kraken trading credential (`kraken_trade_api_key` + `kraken_trade_api_secret`) lives in `infra/ansible/group_vars/capture_host/vault.yml`. `capture_host` is `zcrypto` + `zcrypto-red`, so the **capture-only secondary resolves the live trading credential**; no `group_vars/engine_host/` exists at all. The only thing confining the key to `zcrypto` is **play targeting**: `site.yml`'s engine play converges `engine_host` (which contains only `zcrypto`), and `engine.env.j2` is the sole template that renders the values. Group-vars resolution happens on the controller, so nothing has landed on `zcrypto-red`'s disk — but membership, not targeting, is what the inventory comments present as the boundary.

## Why this matters

The inventory says `zcrypto-red` "must never join engine_host, or the live Kraken trade key would be rendered onto a host that has no business holding it" — implying group scope is the protection. It is not: any future play or role that mis-targets `capture_host` with the engine template renders the live trading key onto an internet-facing capture box, with no group boundary in the way. The 2026-07-17 branch review caught `group_vars/observed/vault.yml`'s header **asserting the engine_host scoping already exists** ("the same reasoning that keeps the live trade key in engine_host rather than capture_host" — false, corrected in the same change that registered this topic); a comment claiming the protection exists is precisely what ensures the real mis-scope never gets fixed. The exposure widens whenever `capture_host` gains members or new plays (e.g. T0020's capture-VPS Alloy work).

## Findings so far

- Boolean-probe evidence from the 2026-07-16 vault re-scoping (commits `4acb7f0`, `8b6d21c`): `zcrypto-red` resolves the trade-key vars (`trade=True`); `zcrypto-ops` and `localhost` do **not** (spec 00051 D10 holds for ops).
- The move is small — two `!vault` ciphertext blocks relocate verbatim (same vault password; per-value encryption means no decrypt is ever needed) — but it touches the **live trading credential**, so it is human-gated: schedule it into go-live hardening (T0049) or fold it into the next trade-key rotation, when the values are being replaced anyway.

## Done so far — RESOLVED 2026-07-17 (owner present, as the gate required)

The recipe below was executed exactly as written, with one deliberate extension.

- **`group_vars/engine_host/vault.yml` created**; `kraken_trade_api_key`, `kraken_trade_api_secret` **and `engine_healthcheck_url`** moved into it. The third var was not in the original recipe: it is consumed by the *same single template* (`roles/engine/templates/engine.env.j2`) and shares the identical mis-scope, so leaving it behind would have made the new group's own definition ("what the engine play needs") false on arrival — the exact class of claim-vs-fact gap that produced this topic. It is a dead-man ping URL, not a credential, and carries a safe role default (`engine_healthcheck_url: ""`), so the extension added no risk.
- **Ciphertext verified byte-identical** to the pre-move blocks (659 / 812 / 661 chars, compared programmatically against `git show HEAD:…capture_host/vault.yml`). Same vault password, per-value encryption — nothing was decrypted, re-encrypted, or printed at any point.
- **The fix, proven by boolean probe** (never a value):

  | host | before | after |
  |---|---|---|
  | `zcrypto` (engine_host) | `key==True secret==True` | `key==True secret==True hc==True` |
  | `zcrypto-red` (capture-only) | **`key==True secret==True`** | **`key==False secret==False hc==False`** |
  | `zcrypto-ops` | `key==False secret==False` | `key==False secret==False hc==False` |

- **The engine play is unaffected** — dry-run (`--limit zcrypto --tags engine -e converge_primary=true -e engine_image_digest=<the running digest>`, `--check --diff`): `ok=30 changed=0 failed=0`. `changed=0` is the strongest available evidence: the `engine.env` the play *would* render is byte-identical to what is live, so the variables resolve to the same values through the new scope. (The task is `no_log: true` + `diff: false`, so nothing leaked even under `--diff`.)
- **`group_vars/observed/vault.yml`'s header corrected**: its parenthetical described the pre-move state (it was itself the review finding that registered this topic — a comment asserting a boundary that did not exist). It now states the boundary that does.
- **`capture_host/vault.yml`** keeps only genuinely capture-scoped values (`ansible_host`, `healthchecks_api_key`, `capture_healthcheck_url`); its header's read-example no longer names a variable that left the file, and a note records where the engine's secrets went.

**Adding a host to `engine_host` now grants it the live trade key** — that is the group's entire purpose, and why it has exactly one member. The inventory's long-standing comment ("`zcrypto-red` must never join `engine_host`, or the live Kraken trade key would be rendered onto a host that has no business holding it") is, as of this change, describing a real mechanism rather than an intention.

**Observed while here, not fixed (out of scope, no security consequence):** `ansible_host` and `capture_healthcheck_url` live in `group_vars/capture_host/` while `host_vars/zcrypto-red/` overrides both — i.e. for those two the group file is effectively holding `zcrypto`'s per-host values as "defaults the secondary happens to override". Mild, and nothing sensitive rides on it. (`healthchecks_api_key` is **not** in that category: no host overrides it, and it is genuinely shared — the project-wide API key for creating checks. An earlier draft of this note claimed all three were overridden; the review that checked it found two. That the topic *about a comment asserting a boundary that did not exist* shipped its own unverified assertion is the lesson, restated.)

## The recipe that was executed (retained for the record)

All steps are the exact recipe the 2026-07-16 `observed`-group move used — ciphertext-verbatim, boolean-probe verified, never a decrypted value anywhere:

1. `mkdir -p infra/ansible/group_vars/engine_host`, create `group_vars/engine_host/vault.yml` with a header comment (scope: the engine play's live trading credential; `engine_host` = `zcrypto` only), and copy the `kraken_trade_api_key:` and `kraken_trade_api_secret:` blocks **verbatim as ciphertext** (the whole `!vault |` block, unmodified) from `group_vars/capture_host/vault.yml`. Do not decrypt, re-encrypt, or run any command that prints values.
2. Delete those two blocks from `group_vars/capture_host/vault.yml` (leaving its other secrets untouched).
3. Verify by **boolean probes only** (from `infra/ansible/`; NEVER `ansible-inventory --host/--list` — it prints every secret): `ansible zcrypto -m debug -a "msg={{ kraken_trade_api_key is defined }}"` → expect `True`; same probe on `zcrypto-red` → expect **`False`** (the fix); on `zcrypto-ops` → expect `False` (D10 still holds). Repeat for `kraken_trade_api_secret`.
4. Preview the engine play (`./scripts/run.sh site.yml --limit zcrypto --tags engine --check --diff` with the usual digest vars) and confirm the engine env template still resolves — the check must show no failure on undefined variables and no diff on the (0600, `no_log`) env file; never print the rendered file.
5. Then correct the T0061 pointer in `group_vars/observed/vault.yml`'s header (its parenthetical describes the pre-move state) and close this topic.
