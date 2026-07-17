---
status: resolved
---

# The NAS runs whatever was last hand-copied to it, and nothing detects the drift

## Context — what

The NAS **was** the only fleet host not Ansible-managed (fixed on `feat/ops5-offload` — see Done so far): it runs Synology Container Manager, and `infra/nas/{compose.yaml,pull-entrypoint.sh,config.alloy}` reached it only when a human copied them. There was no converge, no drift check, and no alert. The repo therefore described the NAS's *intent*, not its *state* — and the two silently diverged for days.

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

## Done so far

All three originally-suggested steps are delivered on `feat/ops5-offload` (commits `acb830f` — the `nas` role, `host_vars/nas`, the TZ guard — and `1ac9ccd` — the flag-gated apply fixes):

- **The model was decided as option (a), bring the NAS under Ansible** — the `nas` role deploys `pull-entrypoint.sh`/`compose.yaml`/`config.alloy` verbatim from `infra/nas/`, renders the `.env` + `alloy-secrets.env` from the vault, and applies via the flag-gated `-e nas_apply_compose=true` tasks; `run.sh` loads `deploy_nas_ed25519` into its throwaway agent. The DSM blocker turned out not to exist (plain ssh + `ansible_ssh_transfer_method: piped`).
- **The placeholder trap is dead**: `compose.yaml` pins via `${CAPTURE_IMAGE:?...}` (and `${ALLOY_IMAGE:?...}`) from the ansible-rendered `.env`, so a copy without the rendered pin refuses to start instead of silently running `:latest` on the AVX-less Atom.
- **The quirks are recorded** in `infra/nas/README.md` (docker at `/usr/local/bin/docker` off sudo's PATH, CEST-vs-UTC `docker logs --since`, no scp/sftp) and encoded in `host_vars/nas/vars.yml`; the TZ guard turns the CEST quirk into a hard converge refusal.
- **Resolved 2026-07-17 — the maiden converge ran and verified by outcome.** The owner ratified the model with the rationale that decided it: **quirks become code, not prompt-knowledge**. The converge: the TZ guard **PASSED on live UTC evidence** — the owner flipped DSM to UTC (recorded in `infra/external-systems.md`), and the guard's fail-first behavior had already been proven in `--check` the day the TZ was still CEST. **8 changed**, including **both digest pins via the rendered `.env`** — the `:latest` traps are dead in the *deployed* state, not just the repo. Deployed entrypoint sha == repo sha, and the apply tasks ran (`up -d` + both restart tasks). `run.sh` loads the NAS deploy key into its throwaway agent (fixed after review).
- **No live deferred sub-item remains.** The originally-mooted drift *detection* is moot by construction — hand-deploys no longer exist, the converge IS the deploy path. The NAS's alerts/dashboards belong to [[T0020]], not here.
