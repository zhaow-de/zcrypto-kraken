# Fleet deploys

L2 capture is unbackfillable — a mistake on `zcrypto` (primary) or `zcrypto-red` (secondary) is permanent data loss. **Before any converge, re-pin, restart, image prune or panel regeneration, read the owning skill** — `.claude/skills/zcrypto-rollout-image/SKILL.md` for app-image digests and every tier's converge mechanics, `.claude/skills/zcrypto-bump-alloy/SKILL.md` for Alloy digests; both are readable even where skill invocation is blocked. Below is what must hold before either file is open, and what both share.

## Invariants

- **Never re-pin the primary or the engine to a capture-image digest whose secondary bake gate has not passed** — the roles refuse it mechanically (`-e canary_override="<reason>"` is the emergency bypass). Skipping or degrading the gate takes the user's explicit approval, never silently.
- **Never converge or reboot inside a published Kraken maintenance window** — `https://status.kraken.com/api/v2/scheduled-maintenances.json`, the entries carrying `WebSocket` or `REST` in `components`. They appear only 2–6 days ahead: check at planning time and again immediately before.
- **`-e converge_primary=true` restarts live capture and/or the engine — mean it.** Never run `site.yml` un-tagged on the primary: a bare run pulls in the engine play and can restart the LIVE trade engine.
- **The engine converges or restarts only inside the 4-hourly inter-cycle gap** (boundaries 00/04/08/12/16/20 UTC) — `site.yml` re-asserts the window (`-e engine_window_override="<reason>"` bypasses); a failed boundary is never retried.
- **Adding a capture pair: PRIMARY first, secondary second** — the role refuses secondary-first. A pair-list change is config, not a re-pin.
- **A schema-widening deploy converges every READER of the record format before the WRITER.**
- **The NAS runs only `-compat` builds** — an AVX build is a silent `Illegal instruction` on the Atom; prove `runtime=compat` by running polars in the pulled image, never by reading a label. Every apply task in the nas role is gated on `-e nas_apply_compose=true`; without it the converge is render-only.
- **Panel regeneration is the point of no return** — no old tree survives and rollback is another full rebuild; only through `zcrypto-panel-regenerate`, on the user's word.
- **One PR per rollout, merged within the day; never branch other work from it.**

## Every converge, every tier

- Converge via `infra/ansible/scripts/converge.sh` — it requires `--limit`, runs and displays the `--check --diff` preview, and takes a typed confirm before the real pass (preview-only: pass `--check`). `--limit` is mandatory for ops too: a bare `site.yml` still runs the NAS play.
- Digests come from `docs/reference/fleet-pins.md` — the roles refuse to replace a running digest the file does not record (`-e pins_override="<reason>"` bypasses). Pull the digest on the host first; every preflight refuses a digest the host has not pulled.
- `fleet-pins.md` is a STATE record: re-true the row from `converge.sh`'s line in `docs/reference/deploy-log.jsonl` — never from memory — commit that line with the row, and put the converge's evidence in the commit message, never in the file.
- **Read a running image's digest from the container, never from the compose file** — `docker inspect --format '{{.Config.Image}}' <name>`.
- **A `config.alloy` edit makes Alloy the subject**: pass the currently-running Alloy digest (`capture_alloy_digest` / `ops_alloy_digest`) or the drift assert refuses; an EMPTY `-e …_digest=` still counts as defined and renders a broken image ref. A new metric family needs the host's keep-regex edit and a first scrape verified by VALUE — `(no series)` is FAIL, never a zero.
- A `daemon.json` diff refuses to apply without `-e daemon_json_ack=true` — the docker role is shared, so the ack gates every host.
- **Images are removed only by `infra/scripts/prune-host-images.py <host>`, after that host's new pins row is written, only for the host that just converged** — a capture host stops appending at 1 GiB free; `--keep <digest12>` anything pre-staged for a leg still to come.
- Verify by outcome, never by exit code: ops via `infra/scripts/ops-postverify.sh`; capture via the pulled copy's hour boundaries, the NAS pull's `failed=0`, and `continuity.py`; the engine via its next `cycle-HH.json` — the skills carry each.

## Alert-rule lifecycle

- **Deleting a rule from `infra/grafana/alerts.yaml` does not retire it** — the push upserts and never deletes; retiring is `GRAFANA_PRUNE=1` with the orphan report naming exactly the uid.
- **Never prune the superseded rule before its replacement's first sample is verified by VALUE** — `delta()`/`increase()` are blind to a condition already present in a series' first sample. Order: converge → push → verify the value → prune → confirm the old uid 404s.
- A rule pushed before its metric's first record pages a spurious no-data alert — push after the first record, or knowingly accept one self-healing page; journal-seed an eagerly-registered gauge instead of publishing `0.0`.

## Ansible secrets

- **Never run `ansible-inventory --host`, `--list`, or `--graph --vars`.** `infra/ansible/ansible.cfg` sets `vault_password_file`, so all three silently decrypt the vault and print every secret (incl. the live Kraken trade key) in cleartext — and `vault-pass.sh` itself refuses those ancestries. Use `--graph` / `--list-tags`, or pipe through a key-names-only filter.
- **Never wrap `converge.sh` in `timeout`** — it is attended by design (the confirm reads `/dev/tty`); `timeout` kills the wrapper while its `ansible-playbook` child keeps converging a production host with nothing supervising it. Let it run, or background the whole invocation.
