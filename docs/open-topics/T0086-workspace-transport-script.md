---
status: partial
ripe_when: the next real workstation↔ops switch — run `infra/scripts/workspace-transport.sh` for the first time and verify the continue-where-left-off outcome; that run closes this topic
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

## Done so far

**Implemented 2026-07-21 (/zcrypto-auto-exec): `infra/scripts/workspace-transport.sh`** — the spec plus all seven gap items under the owner's rulings: both-repos-clean abort gate (uncommitted + stashes, both machines), `git bundle --branches` transport with destination detach→fetch→checkout alignment and a warn-never-delete report for destination-only branches (item 1); `~/.claude/` rsync'd whole minus machine-local runtime/caches — and minus `.credentials.json`, keeping auth material out of the transfer per the item-4 ruling — with the plugins set+versions included (item 2); `~/.claude.json` (item 3); memo scp; scratchpad + `.superpowers` rsync; printed `uv sync` / `data fetch` / `engine seed` post-steps, each verified to exist in the current CLI (items 5–6); the quiet-point + `/tmp`-durability discipline in the header (item 7). `zsh -n` clean. The exclude list was designed from the machine's actual `~/.claude/` layout — and the pre-push review still caught a nested hole the top-level inspection missed: an unanchored `cache/` exclude also matched `plugins/cache/`, the pinned plugin *payloads*, which would have shipped plugin metadata pointing at absent installs — item 2's exact failure. Excludes are now anchored to the top level; two more review catches (a detached-HEAD abort, a reboot-empty scratchpad guard) are in.

**Deliberately not executed**: a real transfer `--delete`-overwrites the destination's session state, and only the owner knows which machine is currently newer — running it blind from the loop risked exactly the clobber this script exists to prevent.

## Suggested next steps

- **(First real switch — closes the topic)** Run `infra/scripts/workspace-transport.sh` on the source machine at a quiet point, follow the printed post-steps on the destination, and confirm the continue-where-left-off outcome (session resumes, memo intact, unpushed branches present, plugins aligned). Fix-forward anything the first run surfaces.
