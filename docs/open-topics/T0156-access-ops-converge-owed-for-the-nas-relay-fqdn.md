---
status: open
ripe_when: "the next `access_ops` converge — one run of `site.yml --limit zcrypto-ops --tags access` applies it; nothing else is waiting on it"
---

# The NAS relay's FQDN swap is committed but not converged

## Context — what

The IP→FQDN swap changed `roles/access_ops/templates/zaccess-nas-proxy.service.j2`'s `ExecStart` from `192.168.100.5:5001` to `z-home-storage.zhaow.pro:5001`. No `access_ops` converge has run since, so the tunnel-side relay on `zcrypto-ops` still runs the IP form. The repo and the fleet disagree on this one unit until that converge lands; `docs/reference/fleet.md` records the live state (the IP), not the template's.

## Why this matters

Two reasons the drift is worth tracking rather than assuming:

- **`Accept=no` with no `--exit-idle-time`.** One long-lived `systemd-socket-proxyd` instance holds the socket, so `daemon-reload` alone never replaces its `ExecStart` — the unit would keep relaying to the IP indefinitely after a converge that merely rewrote the file. The role now carries a `restart zaccess-nas-proxy.socket` + `restart zaccess-nas-proxy` handler pair, each notified from its own template task rather than from a shared two-item loop — a loop assigns its whole notify list to every item and gates on the aggregate result, so it cannot notify them selectively. That closes the class for this relay. The bridgehead's `zaccess-ssh-proxy` is the identical shape, but a restart handler there would cut the operator's own session — `:20022` is that host's public SSH relay into the ops node — so it is guarded the other way, by an assert that fails the converge when the running relay's target no longer matches the rendered one. This topic tracks the one deploy that still owes the run.
- **`fleet.md` must not run ahead of the fleet.** The row was briefly written to the FQDN before any converge and has been put back to the IP. It flips at the converge, not before.

## Findings so far

- The relay carries already-TLS'd DSM traffic Caddy forwards over the tunnel; a restart is a brief interruption of that path only, and nothing on the capture or trade paths touches it.
- The FQDN resolves on the ops host today (the four archive-pull channels already address it by name), so the converge is not gated on a DNS change.
- The monitoring path was deliberately kept off DNS: `zaccess-probe-ops.sh.j2` connects by IP and passes the FQDN as `-servername`, so SNI still selects the right certificate (the probe itself verifies nothing — Caddy's `tls_trusted_ca_certs` + `tls_server_name` are what validate this leg) while a resolution failure cannot silently drop `zaccess_tls_not_after_seconds` — that alert is `noDataState: OK`, and the certificate behind it is the one nothing renews.

## Suggested next steps

- Run `infra/ansible/scripts/converge.sh site.yml --limit zcrypto-ops --tags access` (attended; it previews `--check --diff` and takes a typed confirm). The `access_ops` role runs in the **ops-node** play, not the bridgehead's — `--limit zaccess` converges the wrong host and reports success. Expect whatever `roles/access_ops/` has moved since the 2026-08-05 converge — at this branch's tip that is **two** items, the relay's `service` unit (the `socket` unit is untouched) and the ops-side probe script, whose cert-probe comment this branch also rewrote. Re-derive rather than trusting the count: any further template edit before the converge changes it. Two handlers fire — `reload systemd` and `restart zaccess-nas-proxy`; the probe-script task deliberately notifies nothing, since the timer reads the script fresh on its next tick.
- Verify by outcome on `zcrypto-ops`: `systemctl show -p ExecStart zaccess-nas-proxy.service` names `z-home-storage.zhaow.pro:5001`, and the DSM UI still loads through the relay.
- Re-true `docs/reference/fleet.md`'s socket-proxyd row to the FQDN in the same change, and close this topic.
