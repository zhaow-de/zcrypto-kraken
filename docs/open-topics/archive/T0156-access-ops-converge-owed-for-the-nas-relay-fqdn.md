---
status: resolved
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

## Resolution

**Converged 2026-08-26.** `site.yml --limit zcrypto-ops --tags access` — `ok=19 changed=4 failed=0`.
The relay's `service` unit and the ops-side probe script changed, the `socket` unit did not, and the
`restart zaccess-nas-proxy` handler fired.

Verified by outcome on the host, against the RUNNING process rather than the unit file — the whole
point of this topic was that the two can disagree:

- `/proc/<MainPID>/cmdline` reads `systemd-socket-proxyd z-home-storage.zhaow.pro:5001`; the restart
  genuinely applied, so the silent no-op is disproved rather than assumed fixed.
- `ActiveEnterTimestamp` 2026-08-26 22:37:03 UTC — the restart is this converge's, not an older one.
- The relay still forwards: a TLS handshake through `10.99.0.2:5001` returns `CN=*.zhaow.pro`,
  `notAfter Jan 26 23:59:59 2027 GMT`.
- The rewritten probe emits both series — `zaccess_wireguard_handshake_age_seconds` and
  `zaccess_tls_not_after_seconds{target="nas-dsm"} 1801007999` (= 2027-01-26 23:59:59 UTC, matching
  the handshake), so moving DNS out of the probe cost no observability.

`docs/reference/fleet.md`'s socket-proxyd row now records the FQDN, because the fleet is finally in
that state. The agentboard pin moved 0.4.8 → 0.4.23 on the same converge and is recorded in
`fleet-pins.md`.

The defect class this topic named — an `Accept=no` socket-proxyd relay whose rendered unit never
reaches the running instance — is closed on both relays: the NAS relay by a per-half handler pair,
the bridgehead's `zaccess-ssh-proxy` by an end-of-role assert that refuses a converge on drift rather
than restarting a relay that carries operator sessions.
