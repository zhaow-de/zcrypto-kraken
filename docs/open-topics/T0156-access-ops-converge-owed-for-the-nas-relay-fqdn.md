---
status: open
ripe_when: "the next `access_ops` converge — one run of `site.yml --limit zaccess --tags access` applies it; nothing else is waiting on it"
---

# The NAS relay's FQDN swap is committed but not converged

## Context — what

The IP→FQDN swap changed `roles/access_ops/templates/zaccess-nas-proxy.service.j2`'s `ExecStart` from `192.168.100.5:5001` to `z-home-storage.zhaow.pro:5001`. No `access_ops` converge has run since, so the tunnel-side relay on `zcrypto-ops` still runs the IP form. The repo and the fleet disagree on this one unit until that converge lands; `docs/reference/fleet.md` records the live state (the IP), not the template's.

## Why this matters

Two reasons the drift is worth tracking rather than assuming:

- **`Accept=no` with no `--exit-idle-time`.** One long-lived `systemd-socket-proxyd` instance holds the socket, so `daemon-reload` alone never replaces its `ExecStart` — the unit would keep relaying to the IP indefinitely after a converge that merely rewrote the file. The role now carries a `restart zaccess-nas-proxy` handler notified from the template task, so the class is closed; this topic tracks the one deploy that still owes the run.
- **`fleet.md` must not run ahead of the fleet.** The row was briefly written to the FQDN before any converge and has been put back to the IP. It flips at the converge, not before.

## Findings so far

- The relay carries already-TLS'd DSM traffic Caddy forwards over the tunnel; a restart is a brief interruption of that path only, and nothing on the capture or trade paths touches it.
- The FQDN resolves on the ops host today (the four archive-pull channels already address it by name), so the converge is not gated on a DNS change.
- The monitoring path was deliberately kept off DNS: `zaccess-probe-ops.sh.j2` connects by IP and passes the FQDN as `-servername`, so the certificate is still validated by name while a resolution failure cannot silently drop `zaccess_tls_not_after_seconds` — that alert is `noDataState: OK`, and the certificate behind it is the one nothing renews.

## Suggested next steps

- Run `infra/ansible/scripts/converge.sh site.yml --limit zaccess --tags access` (attended; it previews `--check --diff` and takes a typed confirm). Expect the two template tasks to report changed and the `restart zaccess-nas-proxy` handler to fire.
- Verify by outcome on `zcrypto-ops`: `systemctl show -p ExecStart zaccess-nas-proxy.service` names `z-home-storage.zhaow.pro:5001`, and the DSM UI still loads through the relay.
- Re-true `docs/reference/fleet.md`'s socket-proxyd row to the FQDN in the same change, and close this topic.
