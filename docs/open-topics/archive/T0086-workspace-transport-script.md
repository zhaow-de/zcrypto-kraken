---
status: resolved
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

**Implemented 2026-07-21 (/zcrypto-auto-exec): `infra/scripts/workspace-transport.sh`** — the spec plus all seven gap items under the owner's rulings: both-repos-clean abort gate (uncommitted + stashes + linked worktrees, both machines), `git bundle` transport of branches **and tags** with destination detach→delete→fetch→checkout alignment, and destination-only branches **mirrored away** — deleted by sha, and only when the commits are contained in one of the source's own local branches; anything else aborts before a byte moves (item 1); `~/.claude/` rsync'd whole minus machine-local runtime/caches — and minus `.credentials.json`, keeping auth material out of the transfer per the item-4 ruling — with the plugins set+versions included (item 2); `~/.claude.json` (item 3); memo scp; scratchpad + `.superpowers` rsync; printed `uv sync` / `data fetch` / `engine seed` post-steps, each verified to exist in the current CLI (items 5–6); the quiet-point + `/tmp`-durability discipline in the header (item 7). `zsh -n` clean. The exclude list was designed from the machine's actual `~/.claude/` layout — and the pre-push review still caught a nested hole the top-level inspection missed: an unanchored `cache/` exclude also matched `plugins/cache/`, the pinned plugin *payloads*, which would have shipped plugin metadata pointing at absent installs — item 2's exact failure. Excludes are now anchored to the top level; two more review catches (a detached-HEAD abort, a reboot-empty scratchpad guard) are in.

**First real run, 2026-07-21 — it failed twice, and the failures were the deliverable.** Run from the ops node it died with `unknown host zcrypto-ops` (the case matched the node's DNS label `z-home-zcrypto`, not what `hostname -s` answers), and run with an explicit FQDN it reported `DESTINATION repo is dirty` against a repo that was clean. The second was the more instructive: `ssh … || die "…dirty"` cannot distinguish a failed connection from a dirty repo, and ssh exits **255** on host-key verification failure — so the script blamed a repo it never managed to query. Reproduced deliberately (`StrictHostKeyChecking=yes` + empty `known_hosts` → exit 255) before fixing. The owner completed that switch by hand.

**Both defects fixed, then the script was verified by the owner in BOTH directions** (2026-07-21).

**Then a four-lens adversarial review (54 agents, findings individually put through refutation) found 13 more defects in the fixed version** — 24 confirmed of 49 raised, the rest refuted. Two were found independently by all four lenses. All 13 are fixed:

- **Branch-membership test was a regex pipeline, not a set test.** `grep -qx` fails on a legal branch name like `fix/bug$` (BRE metacharacter), *and* `grep -q` SIGPIPEs its producer so under `pipefail` the pipeline returns 141 — "not on the source" — for **every** branch once the list is long enough. Either way branches that exist on the source get classified destination-only. Now an associative-array set; both failures reproduced against the old code and re-tested against the new.
- **The clean-repo gate was blind to linked worktrees.** `status --porcelain` reports the main worktree only, so a worktree holding a branch being force-updated passed the gate and then made `fetch --force` abort wholesale — *after* the detach, leaving the destination detached and every re-run reproducing it. This repo hands subagents worktrees by rule, so it was live. Now a preflight abort.
- **Deletion ran after the fetch**, so a stale destination branch named `fix` blocked fetching `fix/anything` (ref file where git needs a directory) and the deletion that would clear it never ran — permanently wedged. Order is now detach → delete → fetch (`--atomic`), which is also what lets a destination sitting *on* a doomed branch be handled at all.
- **`--all --contains` accepted a stale remote-tracking ref as proof of recoverability.** A force-push or closed-unmerged PR leaves `origin/x` naming a commit the remote no longer has; the destination's copy was then the only one, and deletable. Tightened to the source's own local branches, so the surviving invariant is checkable: anything deleted still exists on both machines under a named branch.
- **Deletion by name → by sha** (`update-ref -d <ref> <sha>`), since classification and execution are separated by a human-length confirmation pause.
- **`[[ -r /dev/tty ]]` does not detect "no terminal"** — it is `access(2)` on a 0666 device node and passes under `setsid`/cron, after which the read fails and `set -e` exits *before* the carefully written no-tty message could print. Now an actual `exec {fd}</dev/tty`; Ctrl-D no longer exits silently.
- **The memo and `~/.claude/` are destroyed with no proof and no preview** — both invisible to the clean-repo gate by construction (gitignored / not git), both holding work recoverable from nowhere. The plan now shows a memo digest comparison and an `rsync -n --delete` count, and the destination's memo is backed up outside the repo before being overwritten.
- Plus: self-transfer guard compared a FQDN against `hostname -s` and could never fire (now asks the peer over the proven channel); `%(refname:short)` is ambiguous when a tag shares a branch name (`lstrip=2`); bundle carried no tags; no cleanup trap and no completion marker (now a `~/.zcrypto-workspace-transport` sentinel written last, so an interrupted transfer is distinguishable from a finished one); `die()` lacked `-r` and mangled C-quoted paths; the unrecoverable-branch remedy text named a step that provably does not clear the abort.

**The post-review ordering was rehearsed end-to-end** against throwaway repo pairs carrying all three hazards at once (a linked worktree, a `fix` vs `fix/…` conflict, a metacharacter branch name, HEAD sitting on a doomed branch): the guard aborts, deletion precedes the fetch, tags transfer, and the destination's branch set ends exactly mirroring the source. The recoverability classifier is proven on known answers including the stale-`origin/*` case.

**What is verified by whom**: the owner ran the transport both directions on the pre-review version; the git-alignment path of the post-review version is rehearsed but not yet live-run. The remaining changes are either fail-safe preflight aborts or additive disclosures, and the confirmation gate means nothing destructive happens without the operator seeing it listed first — so the next real switch is the natural live exercise rather than an outstanding risk.

## Suggested next steps

_(none — resolved. The next switch exercises the post-review version, including the branch-mirroring path, which the confirmation gate discloses before acting.)_
