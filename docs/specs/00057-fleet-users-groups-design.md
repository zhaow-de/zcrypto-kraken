# Fleet users/groups regularization — design (spec 00057)

**Goal:** Give every host in the fleet one uniform, purpose-separated set of OS accounts — `zcrypto-deploy` (interactive/admin), `zcrypto-data` (machine-to-machine data path), `zcrypto-engine` (the money-mover), `zcrypto-alloy` (telemetry), `zhaow` (research) — replacing today's mixed, partly-hand-managed naming, so that identity (not convention or accident) enforces the trust boundaries.

**Context.** This design was reached by consensus during OPS-6 (spec `00056`), when the hot-out authoring handoff (`zhaow` → a `deploy`-owned outbox) exposed how tangled the current accounts are: on the ops node the data-path containers run as `deploy` (the sudo user) and the machine-to-machine (m2m) pull-export forced-command keys live on `deploy` and are **hand-installed** (not Ansible), while the capture/engine hosts use `kraken-*` names and the NAS uses `zcrypto-*`. This spec is the **WHAT**; execution is phased into per-host plans (below), the first of which (ops) is the immediate follow-on to OPS-6.

## Current state (measured 2026-07-18)

| Host | interactive+sudo | m2m / container run-as | research | telemetry | custody |
| --- | --- | --- | --- | --- | --- |
| **zcrypto** (capture+engine) | `deploy` 1000 | `kraken-capture` 999 (capture ctr) · `kraken-engine` 997 (engine ctr) | — | — | — |
| **zcrypto-red** (capture) | `deploy` | `kraken-capture` | — | — | — |
| **ops** | `deploy` 1001 | **`deploy` 1001** (poller/reconciler/panel) · `kraken-capture` 988 *(vestigial)* | `zhaow` 1000 | `zcrypto-alloy` 999 | — |
| **nas** | `zcrypto-deploy` 1030 | *(see note)* | — | *(see note)* | *(see note)* |
| **workstation** | — | — | `zhaow` 1000 | — | — |

Docker is **rootful** everywhere; containers get a run-as identity via `--user`, invoked by root/systemd — so the m2m user never needs docker-group or rootless access.

**NAS note — renames already applied manually (2026-07-18):** the user renamed `zcrypto` → **`zcrypto-data`** (uid **1000** kept — the archive-pull container's numeric `user: 1000:1000` and all custody ownership are unaffected) and `zcrypto-dummy` → **`zcrypto-alloy`** (uid 1031). The **group** `zcrypto` (gid 1000) was left as-is, so custody is now `zcrypto-data:zcrypto`. Consequence for OPS-6: its committed nas role still says `owner: zcrypto` (now absent) and needs a `→ zcrypto-data` touch-up to stay converge-able — handled in the OPS-6 finish, not here.

## Target model

| User | Role | zcrypto | zcrypto-red | ops | nas | workstation |
| --- | --- | :-: | :-: | :-: | :-: | :-: |
| **`zcrypto-deploy`** | interactive + sudo; Ansible + human ssh **only**; never in the data path; `authorized_keys` = **one** key (`exclusive: true`) | ✔ | ✔ | ✔ | ✔ *(exists)* | — |
| **`zcrypto-data`** | m2m: runs the data containers, owns the data, does/serves the m2m pulls; **no sudo, no tty, no password; `/bin/bash` jailed to rrsync by the forced-command keys** (not `nologin` — it would block the pulls) | ✔ *(capture ctr)* | ✔ | ✔ *(poller/reconciler/panel)* | ✔ *(= renamed `zcrypto`, uid/gid 1000)* | — |
| **`zcrypto-engine`** | dedicated money-mover (was `kraken-engine`); runs the engine container | ✔ | — | — | — | — |
| **`zcrypto-alloy`** | dedicated, non-secret-owning telemetry user; uniform `docker.sock` pattern | ✔ | ✔ | ✔ *(exists)* | ✔ *(= renamed `zcrypto-dummy`)* | — |
| **`zhaow`** | personal interactive research, uid/gid **1000** | — | — | ✔ | — | ✔ |

**Retired:** the `deploy` and `kraken-*` names — every service/admin account becomes `zcrypto-*`; the only un-prefixed user is `zhaow`, correct because it is a *personal* identity, not a service account.

## Decisions

- **D1 — `zcrypto-deploy` is interactive+admin only, and holds exactly one key.** Its `authorized_keys` carries only its own login key (`files/*deploy*_<host>.pub`), installed by `bootstrap.yml` with `exclusive: true` so hand-added entries cannot drift back in. Every m2m forced-command export moves off it to `zcrypto-data`. Renaming `deploy` → `zcrypto-deploy` fleet-wide is pure convention alignment (the ssh aliases already hide the username); the one delicate part is that it renames the account Ansible connects *as* — home dir, sudoers, group memberships, `~/.ssh/authorized_keys`, `ansible_user`, and the ssh-config `User` all move together with a clean cutover (a plan/HOW concern). This rename is **in scope and done in each host's migration phase, ops first — not deferred**: precisely *because* it is delicate, doing it early avoids accumulating the interactive/m2m drift this model exists to remove. The vaulted key files keep their `deploy_<host>` names (named by purpose; the context is unambiguous — no rename).

- **D2 — `zcrypto-data` is the single m2m identity.** It runs every data-path container (`--user`), owns every data tree, and both *initiates* pulls (the NAS's archive-pull) and *serves* them (the forced-command exports on the producer hosts). No sudo, no tty, **no password**. Its shell is `/bin/bash`, **not** `nologin` (corrected during ops-phase execution): sshd runs a `command="rrsync -ro …"` forced command via the account's *login shell*, so `nologin` swallows it (`"account not available"`) and every pull fails. The `command=`/`restrict` keys jail each key to one read-only subtree with no pty/forwarding, and there is no password, so no interactive login is reachable despite the real shell — the "no interactive login" intent met by the correct mechanism. **Any pull-serving user in the capture/engine phase ([[T0068]]) needs a real shell for the same reason.** It needs no docker-group/rootless access (root/systemd invokes docker; the container's identity is `--user zcrypto-data`).

- **D3 — `zcrypto-engine` stays a dedicated identity, renamed from `kraken-engine`.** The engine is the only component that places real trades, so it keeps its own confined account as defense-in-depth, even though (see D4) the trade key does not *require* user-level isolation. Only on `zcrypto` (the sole `engine_host`), Ansible-provisioned, unchanged in behavior.

- **D4 — the trade key is isolated at the compose/root layer, not by OS user.** The engine role delivers the key only into the engine container's environment, from a root-only file — so it is readable neither from the host by any non-root account nor by any other container, regardless of run-as user. This is *why* D3 is a defense-in-depth choice rather than a hard requirement, and why `kraken-capture` can safely fold into `zcrypto-data`.

- **D5 — `zcrypto-alloy` is uniform across every host, including the engine host — an accepted residual.** Alloy uses the same telemetry pattern everywhere. That carries the docker-access residual already tracked and accepted in `T0042`, which on the engine host also reaches the trade-key domain; the owner **accepts it for uniformity/simplicity** (one Alloy shape fleet-wide) rather than special-casing the engine host. `zcrypto-alloy` stays non-root and non-secret-owning — the same mitigation used everywhere. The residual's specifics stay in `T0042`, not here.

- **D6 — reuse, don't recreate, on the NAS.** `zcrypto` already *is* the data role (custody owner + archive-pull run-as, uid 1000), so it is renamed in place to `zcrypto-data` **keeping uid/gid 1000** (already done manually). This (a) preserves the ro-NFS ↔ `zhaow` read alignment (both uid 1000), (b) needs zero custody re-chown, and (c) keeps the numeric `user: 1000:1000` in `compose.yaml` valid. A separate NAS user would force a new uid and break all three. The NAS **group** `zcrypto` (gid 1000) is deliberately left un-renamed — no value even cosmetically — so custody stays `zcrypto-data:zcrypto`.

- **D7 — `zhaow` is unchanged and stays un-prefixed.** uid/gid **1000** on both ops and workstation is a hard constraint (manually guaranteed) so `$HOME` and NFS ownership line up. It is the personal research identity, correctly outside the `zcrypto-*` service-account scheme.

- **D8 — `zcrypto-data`'s uid may differ per host, and that is fine.** It is 1000 on the NAS (the custody/NFS alignment) but auto-assigned elsewhere; cross-host data moves by rsync-over-ssh (the receiver re-owns), so no cross-host uid dependency exists. Only `zhaow` (D7) needs a pinned uid.

## Phased execution

The model is fleet-wide; the migration is split by host-class, because the capture/engine hosts carry the **live, unbackfillable** capture stream and the trade key and must be moved with more ceremony.

1. **Ops iteration (immediate — the OPS-6 follow-on).** Migrate the ops node's whole data path `deploy → zcrypto-data`: container run-as, data-tree ownership, and the four m2m forced-command keys (liquidations/panel/reconciled/hot), which also become **Ansible-provisioned** (satisfying the "everything on captures/red/ops is Ansible-provisioned" constraint). Chosen approach: **`zcrypto-data` serves the pulls** (the "Full" option) — the NAS repoints its four sources `deploy@ops → zcrypto-data@ops` with a **dual-key transition** so the live liquidations pull never drops, and `deploy` leaves the ops data path entirely. hot-out becomes `zcrypto-data`-owned with `zhaow` authoring into it via a shared group (setgid), finally wiring the OPS-6 hot-out authoring direction. Also rename `deploy → zcrypto-deploy` on ops (D1). Tracked as **[[T0067-fleet-users-groups-ops-migration]]**.

2. **Capture/engine iteration (later).** `kraken-capture` → `zcrypto-data` and `kraken-engine` → `zcrypto-engine` on `zcrypto`/`zcrypto-red`, move their pull-export forced commands to `zcrypto-data` + Ansible-provision them, rename `deploy → zcrypto-deploy`, and **deploy `zcrypto-alloy`** to the capture hosts for the first time — landing the accepted D5 telemetry residual. Highest-ceremony because of the unbackfillable capture stream and the live trade key. Tracked as **[[T0068-fleet-users-groups-capture-engine-migration]]**.

The NAS renames (D6) are already applied manually; the workstation needs none (only `zhaow`). Per the standing constraint, the NAS and workstation are changed by the owner manually; captures/red/ops are Ansible-provisioned.

## Non-goals

- **Not rootless docker.** Docker stays rootful with root/systemd invoking it and `--user zcrypto-data`; a rootless migration is a separate, larger question and is out of scope.
- **No behavioral change to the engine, capture, or telemetry pipelines** — this is an identity/ownership/naming regularization, not a functional change. The one deliberate exception is D1's `authorized_keys` cleanup (m2m keys leave `deploy`).
- **Not the OPS-6 channel itself.** OPS-6 delivers the topology + exchange tool + channel + fetch; this iteration finalizes the ops node's *identity* and the hot-out *authoring* writability that OPS-6 deferred.

## Deferred to the plans (HOW, not WHAT)

- The `deploy → zcrypto-deploy` cutover **mechanics** (home-dir move, sudoers, ssh-config `User`, `ansible_user`, group memberships) — a careful `bootstrap.yml` change. The *decision* to rename is D1 and firmly in scope; only the step-by-step is plan-level.
- The exact dual-key transition ordering for each of the four ops pull channels (verify-each-still-pulling before tearing down the old path), and near-zero poller downtime.

## Iterations-history

Append the `iter-<NNN>` entry to `docs/iterations-history-phase1.md` at each phase's closeout (per `iterations-history.md`).
