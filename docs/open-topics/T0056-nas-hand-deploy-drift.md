---
status: open
ripe_when: any change lands in `infra/nas/` — the repo is not the NAS's source of truth, so every such change is silently inert until someone hand-deploys it
---

# The NAS runs whatever was last hand-copied to it, and nothing detects the drift

## Context — what

The NAS is the only fleet host that is **not** Ansible-managed: it runs Synology Container Manager, and `infra/nas/{compose.yaml,pull-entrypoint.sh,config.alloy}` reach it only when a human copies them. There is no converge, no drift check, and no alert. The repo therefore describes the NAS's *intent*, not its *state* — and the two silently diverged for days.

## Why this matters

Two live defects were found on 2026-07-16, both caused by this gap:

- **A feature nobody noticed was missing.** `zcrypto archive backfill-trades` was added to `pull-entrypoint.sh` in iter-100 (spec `00053`) and merged. It was never deployed. The NAS kept running a Jul-15 entrypoint, so the **daily trade-backfill gate never ran once** — the invariant iter-100 drove to zero came from a one-off manual run, not the scheduled job the spec describes. [[T0053]] (archived) reasons at length about that gate degrading; the gate was never live to degrade. Nothing in the repo, the metrics, or the alerts revealed this — the metric it publishes (`zcrypto_trade_backfill_*`) simply never existed, and its staleness alert was not provisioned.
- **A placeholder that destroys a load-bearing pin.** `infra/nas/compose.yaml` carries `image: ghcr.io/zhaow-de/zcrypto-capture:latest` with a comment saying "pin this to a digest at deploy time". Deploying the file *verbatim* — the obvious reading of "copy the repo file to the NAS" — therefore **overwrites the deployed `-compat` digest with the AVX `:latest`**. The NAS's Atom has no AVX, so the container dies instantly: `Illegal instruction (core dumped)`, every pull failing. This happened during spec `00054`'s cutover and took the NAS's pull loop down for ~90 s until the pin was restored (no data lost — the capture hosts hold the archive). A file that cannot be deployed as-written is a trap, not a template.

## Findings so far

- The deployed `pull-entrypoint.sh` was 2 days stale and 1 feature behind; nobody knew until the cutover diffed it.
- The correct NAS pin is the **`-compat`** (no-AVX) variant; the current one is `sha256:854ca39e7bb690b3af92dffa915ac2a20711cbcc593b68def386e5e6ff116e66`.
- `scp`/`sftp` to the NAS is refused ("Connection closed"); `ssh nas 'sudo tee <path>'` works and is what the cutover used.
- The NAS's Docker is at `/usr/local/bin/docker` — not on `sudo`'s PATH, so a bare `sudo docker …` fails with `command not found`. A script that ignores that failure reads its `grep -c` of the empty output as **0 problems found**: this produced a false "0 minted" all-clear during the cutover before it was caught.
- The NAS's timezone is **CEST**, and `docker logs --since` interprets its argument in *local* time. `--since <UTC timestamp>` therefore silently selects a 2-hour-wider window and returns stale lines. This produced two false "still failing" verdicts during the cutover.

## Suggested next steps

- Decide the model: (a) bring the NAS under Ansible (it is a Synology — the blocker is DSM, and this may be genuinely infeasible); (b) keep it hand-managed but add a **drift check** — a small job comparing the deployed files' checksums against the repo's and publishing a metric, so divergence is visible rather than discovered; or (c) accept drift and make deploys explicit + logged. Recommend (b): it is cheap, needs no DSM cooperation, and directly closes both defects above.
- **Fix the placeholder trap regardless of the model.** Either move the image pin to the `.env` (where every other per-deploy value already lives, and where `compose.yaml` can reference it as `${CAPTURE_IMAGE}`), or make the committed file carry no image line at all. As long as the committed file contains a runnable-but-wrong `:latest`, deploying it correctly requires remembering an unwritten rule — and the one time it was forgotten, the NAS died instantly.
- Record the NAS's operating quirks somewhere a future session reads *before* touching it (docker path, CEST-vs-UTC logs, no scp) — `infra/nas/README.md` is the natural home. Each one produced a wrong conclusion during the cutover.
