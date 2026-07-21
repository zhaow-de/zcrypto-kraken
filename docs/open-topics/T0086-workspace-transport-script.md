---
status: open
ripe_when: NOW — fully specified below; take as a small standalone change, or at latest before the next workstation↔ops switch
---

# `infra/scripts/` workspace-transport script — move the working environment between workstation and ops

## Context — what

A ZSH script to transport the full working environment between the workstation (`ZhaoPrecision.fritz.box`) and the ops node (`z-home-zcrypto.zhaow.pro`) so work continues on the other machine exactly where it left off. Both check out the repo at `~/Projects/zcrypto-kraken`, same user `zhaow`, aligned UID/GID (1000), aligned utilities (`sops`, `uv`, `jq`, …); `~/.ssh/id_ed25519` on both; workstation `sudo` needs a password; the two machines are never used simultaneously. Run from either machine, transferring source → destination:

- check the source repo has no uncommitted or stashed changes; record all fetched branches, the current branch, and HEAD
- align the destination repo's git state (local branches, current branch, HEAD)
- `scp` `docs/memo.local.md`
- `rsync --delete -a` (perms + timestamps): `~/.claude/projects/-home-zhaow-Projects-zcrypto-kraken/`, `/tmp/claude-1000/-home-zhaow-Projects-zcrypto-kraken/`, `~/Projects/zcrypto-kraken/.superpowers`

## Why this matters

The session state (Claude transcripts + memory, scratchpad, SDD ledgers, the memo) is what makes "continue exactly where I left off" possible; today a machine switch loses or forks it. The git-state alignment prevents the worse failure — two machines silently diverging on the same branches.

## Findings so far — the gap audit (2026-07-21, requested at grooming)

What the spec above does **not** yet cover for a seamless continue:

1. **Unpushed local branches have no transport mechanism.** "Align git state" cannot come from `origin` when branches were never pushed (this repo's convention keeps branches local until PR-open). Concrete fix: `git bundle create` (all refs) at the source, transfer, `git fetch <bundle>` at the destination — atomic and works in both directions.
2. **`~/.claude` beyond `projects/`**: `settings.json`, global `CLAUDE.md`, `keybindings.json`, `plugins/` (set *and* versions — a plugin installed mid-session on one machine is silently absent on the other), `agents/`, `commands/`, personal `skills/`. Decide: rsync the lot (minus caches) or a verify-aligned check that fails loudly on drift.
3. **`~/.claude.json`**: MCP server configs (the Slack MCP that carries scheduled reminders), project trust/allowlists. Without it the destination session has different tools and permissions.
4. **Out-of-repo auth, verify-present rather than copy** (key-material transfer policy is the owner's): `gh` CLI auth, the sops age key (`~/.config/sops/age/`), the ansible vault password file (path per `infra/ansible/ansible.cfg` — outside the repo), `~/.ssh/config` aliases (`zcrypto`/`red`/`nas`/`hp`) and `known_hosts` entries.
5. **`data/` root is regenerable, not transferable** (large, gitignored): the script should *print* the post-transfer steps — `uv run zcrypto data fetch` (NAS hub mirror) + `uv run zcrypto engine seed` (price store) — not rsync them.
6. **Machine-local caches**: `.venv` → `uv sync` post-step; `~/.cache/pre-commit` regenerates (first gate run is slower).
7. **Quiet-point discipline**: transfer only with no background agents/workflows mid-flight (running processes do not transfer; their on-disk task state does), and immediately before switching — `/tmp` does not survive a reboot, so the scratchpad copy is only as durable as the destination's uptime.

## Suggested next steps

- **(Autonomous)** Implement the script per the spec plus the gap items, with the owner's 2026-07-21 ruling applied — **rsync is enough** (the environments differ little in practice; switches happen several times a week): extend the rsync set with `~/.claude/` (minus cache dirs) and `~/.claude.json` (items 2–3), use a `git bundle` for unpushed refs (item 1), print the `data fetch` / `engine seed` / `uv sync` post-steps (items 5–6), and note the quiet-point/`/tmp` caveat (item 7) in the script's header. No verify-present machinery — item 4's auth material is already aligned on both machines.
