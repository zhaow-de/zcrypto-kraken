# Internet access portal (`zaccess`) — design

**Spec 00075.** Reach three home-network services from anywhere on the internet, through the Linode bridgehead `zaccess.zhaow.me`, without the home network ever accepting an inbound connection:

1. **G1 — SSH to the ops node**: `ssh -p 20022 zhaow@zaccess.zhaow.me` lands on `zcrypto-ops:22`. Always live, durable across reboots of either host.
2. **G2 — a web terminal onto the ops node's tmux**: the `zcrypto` session, owned by `zhaow`, served through [agentboard](https://github.com/gbasin/agentboard) — a `browser → HTTPS → agentboard → tmux → Claude Code` chain for networks whose firewalls permit only HTTPS egress. Deliberately no SSH in this chain: agentboard runs on the ops node and speaks to the local tmux server over its socket.
3. **G3 — the Synology DSM web console** (`nas:5001`), reachable from a browser.

The ops node runs a Claude Code session inside tmux for autonomous research loops that run continuously for weeks. **That session is the asset this project must not disturb.** The three access paths are not used simultaneously (owner's statement).

## Current state (measured 2026-07-29)

| | bridgehead `zaccess.zhaow.me` | ops `zcrypto-ops` |
| --- | --- | --- |
| OS / kernel | Debian 13 trixie · 6.12.88 | Debian 13 trixie · 6.12.95 |
| Resources | 1 vCPU · 967 MB RAM · 25 GB disk | 24 cores · 64 GB RAM |
| Addresses | `172.104.135.227` · `2a01:7e01::2000:7eff:fe6d:e991` | LAN `192.168.100.6` (static) |
| ISP egress | n/a (public IP) | dynamic residential — the reason D4 chooses WireGuard |
| sshd | `:10022` (hand-set in the main `sshd_config`); **root now key-only, password auth disabled** — interim drop-in `10-zaccess-interim.conf` hand-placed 2026-07-29 and verified over a fresh connection; the Phase-2 hardening converge supersedes and removes it | `:22` — was Debian defaults / home-LAN only; once the G1 relay exposed it to the internet, `access_ops` ships a key-only drop-in (`PasswordAuthentication no`) |
| Firewall | nftables installed, no ruleset loaded; **Linode Cloud Firewall configured** — permits `80`/`443`/`10022`/`20022` tcp, `51820` udp, ICMP. A second filter layer in front of nftables: a future port addition must open both | (managed by this repo already) |
| Users | none (no uid ≥ 1000) | `zhaow` (uid 1000) · `zcrypto-deploy` |
| Notable | no docker/nginx/caddy/fail2ban/unattended-upgrades | this repo's `base`/`chrony`/`docker`/`ops` roles converge it |

Other measured facts:

- **tmux on ops**: 3.5a; session `zcrypto` with one client at 212x56 running `claude`; global `window-size` at its default `latest` — the mechanism that would reflow the session when a differently-sized client attaches (D13). `~/.tmux.conf` sets exactly `mouse on` and `history-limit 10000`.
- **NAS** `192.168.100.5`: `:5000` returns HTTP 200 (no HTTPS redirect); `:5001` presents a real Sectigo wildcard for `*.zhaow.pro` (SAN `*.zhaow.pro, zhaow.pro`), `notAfter` 2027-01-26 — so the ops→NAS leg can be fully verified, not merely encrypted (D7). The NAS keeps its pre-existing `*.zhaow.pro` cert (it is not Ansible-managed); the access portal's own names are `.me`, so D7 validates the upstream against `z-home-storage.zhaow.pro` specifically.
- `zhaow.me` is on Route53; the `zaccess` A record already resolves to the Linode; `z-home-*` names resolve publicly to RFC1918 addresses.
- Bridgehead ports 80/443/20022 are closed (nothing listening); `51820/udp` unopened.
- **agentboard v0.4.5**: no built-in authentication ("anyone who can reach the server has full access to your terminal sessions" — its own docs); advertises hibernation/wake for dormant sessions — actively dangerous to a weeks-long run (D13). Runtime ambiguous from packaging (`engines: bun >= 1.3.14` on the main package, `node >= 18` on the platform package) — resolved by the Phase-7 spike, not guessed.
- `net.ipv4.ip_forward` on ops is `1` at runtime, persisted nowhere (a Docker side effect) — D6 removes every dependency on it.

## Target topology

```
                          Internet
                             │
       :20022/tcp ───────────┤ :443/tcp (tmux. / nas.)
       (v4 + v6)             │ :80/tcp  (ACME HTTP-01 + redirect)
                             ▼
   ┌───────────────────────────────────────────────────────┐
   │ bridgehead   zaccess (access_host)                    │
   │   sshd :10022             zcrypto-deploy, key-only    │
   │   Caddy :80/:443          mTLS gate + automatic ACME  │
   │   zaccess-ssh-proxy       [::]:20022 + 0.0.0.0:20022  │
   │   nftables inet filter, policy DROP                   │
   │   Alloy (native, apt-pinned) → Grafana Cloud          │
   │   zaccess0  10.99.0.1/24            :51820/udp        │
   └───────────────────────────┬───────────────────────────┘
                               │  WireGuard — initiated by ops,
                               │  PersistentKeepalive=25
                               │  AllowedIPs = 10.99.0.2/32
                               ▼
   ┌───────────────────────────────────────────────────────┐
   │ ops   zcrypto-ops (ops_host)                          │
   │   zaccess0  10.99.0.2/24                              │
   │   sshd :22                        key-only (G1 hardening)│
   │   agentboard :4040                binds 10.99.0.2     │
   │   zaccess-nas-proxy :5001         socket-proxyd relay │
   │   textfile timer: wg handshake + NAS cert notAfter    │
   └───────────────────────────┬───────────────────────────┘
                               │ LAN
                               ▼
                    NAS 192.168.100.5:5001 (DSM)
```

| Goal | Path |
| --- | --- |
| G1 SSH | client → bridgehead `:20022` → `zaccess-ssh-proxy` → `10.99.0.2:22` → ops sshd |
| G2 tmux | client → Caddy `tmux.zaccess.zhaow.me` (mTLS) → `10.99.0.2:4040` → agentboard → tmux `zcrypto` as `zhaow` |
| G3 NAS | client → Caddy `nas.zaccess.zhaow.me` (mTLS) → `10.99.0.2:5001` → `zaccess-nas-proxy` → `192.168.100.5:5001` |

## Decisions

- **D1 — Subdomains, not subpaths; port 80 stays open for ACME.** Neither upstream survives a base path (agentboard documents none; DSM assumes the host root). `tmux.zaccess.zhaow.me` and `nas.zaccess.zhaow.me` each take their own **HTTP-01** certificate, so no Route53 credential is ever placed on the internet-facing VPS (DNS-01 would require one). Port 80 serves only ACME challenges and a redirect — a small, well-understood surface deliberately preferred over TLS-ALPN-01, whose coexistence with D2's required client certificates would fail silently at first renewal rather than at deploy time.
- **D2 — mTLS client certificates are the sole web gate, on both subdomains; the MacBook is the only enrolled device.** agentboard has no authentication and fronts a live Claude Code session holding the owner's credentials — the edge is the *only* control. The certificate is required at the TLS handshake: an attacker reaching 443 cannot speak HTTP to the application at all. The NAS subdomain gets the same gate; DSM's login becomes a second factor. No phone/tablet enrolment; the web client is always a desktop browser (which also shrinks the D13 sizing problem).
- **D3 — Caddy pins the exact client leaf, not just the CA.** Leaf pinning makes revocation real: a lost laptop is one deleted PEM and a reload. The bridgehead holds only public material for the auth system (CA cert + pinned leaf); full VPS compromise mints nothing. The CA private key stays vaulted and is only ever used on the workstation.
- **D4 — WireGuard, not a reverse SSH tunnel.** The ops egress address is dynamic residential; WireGuard roams invisibly where an `ssh -R` tunnel dies and restarts. UDP (no TCP-in-TCP), kernel-space (negligible on a 967 MB VPS), and each additional service is a port, not another tunnel.
- **D5 — IPv4-only tunnel; IPv6 served at the edge.** Both exposed TCP services are userspace relays that listen on `[::]` + `0.0.0.0` and connect onward over IPv4; Caddy serves IPv6 natively. Public IPv6 reachability without v6 addressing inside the tunnel.
- **D6 — Both exposed TCP services are `systemd-socket-proxyd` relays; no NAT, no IP forwarding anywhere.** `zaccess-ssh-proxy` (bridgehead `:20022` → `10.99.0.2:22`) and `zaccess-nas-proxy` (ops `10.99.0.2:5001` → `192.168.100.5:5001`). DNAT+masquerade would depend on `ip_forward=1` on both hosts — on ops an unowned Docker side effect, on the bridgehead a direct contradiction of the CIS baseline (the same class of defect that once took down all container egress in this repo). Relays also shrink `AllowedIPs` to `10.99.0.2/32`: a compromised VPS reaches exactly one host on three ports and has **no route into `192.168.100.0/24`**. SSH stays end-to-end encrypted — the relay copies bytes and can decrypt nothing. Accepted residuals: ops's sshd logs the source as `10.99.0.1`; ops userspace is in both relayed paths (ops is the tunnel endpoint regardless).
- **D7 — The NAS is reached on `:5001` with full certificate verification.** The ops→NAS leg is plain LAN outside WireGuard's cover; on `:5000` it would carry DSM session cookies and the admin password in cleartext. DSM presents a real Sectigo wildcard, so Caddy verifies properly with `tls_server_name` — no `tls_insecure_skip_verify` anywhere. Accepted residual: a lapsed Sectigo certificate fails NAS access **closed** — correct direction, now also **monitored** (D12).
- **D8 — Fifth host in the fleet, one playbook, one stack.** The access channel lands in this repo rather than a standalone one: two Ansible stacks converging the same host is the worse hazard — the isolation would rest on a point-in-time audit and on adjacent identity surfaces (a second deploy user beside an `exclusive: true` key task) holding only until either side refactors. New inventory group `access_host`, host `zaccess`; it joins `observed` and nothing else — never `engine_host`/`capture_host`, so the primary guard is unreachable by construction. `bootstrap.yml` gains a bridgehead play; `site.yml` gains one play — roles `base`, `hardening`, `firewall`, `fail2ban`, `chrony`, `access` (new) — with a charter note like the other tiers; the ops play gains `access_ops` (new role, tagged `access`). Identity follows the fleet convention: `zcrypto-deploy` with its own per-host key, `deploy_zaccess_ed25519` (public in `files/`, private vaulted); on ops nothing new is created. No `docker` on the bridgehead: Caddy from apt, WireGuard in-kernel, socket-proxyd from systemd — the host runs no containers. A separate `zaccess.yml` playbook was considered and rejected: it preserves run-isolation but converges ops from two entrypoints. The `firewall` role gains `firewall_extra_tcp_ports` / `firewall_extra_udp_ports` (default `[]`); capture hosts must render **byte-identically** after the change, proven by a render test.
- **D9 — Caddy from the upstream apt repository, version-pinned.** ACME issuance *and renewal* are intrinsic to the process — no timer, no deploy hook, nothing to schedule. WebSocket upgrade (which agentboard needs) works unconfigured; mTLS is a small block. Debian 13 ships Caddy 2.6.2 (late 2022) — too far behind for the host that guards everything.
- **D10 — sshd and OS hardening take the fleet's `hardening` role wholesale.** The role wraps `devsec.hardening.os_hardening` + `ssh_hardening` (pinned 10.6.0), and `ssh_hardening` **replaces `sshd_config` entirely** — port from `hardening_ssh_port` (already 10022), `PermitRootLogin prohibit-password` (root-key break-glass; root's `authorized_keys` deliberately unmanaged), password and keyboard-interactive off, `AllowUsers` overridden for this host to `zcrypto-deploy root` (no `zcrypto-data` — the NAS pull channel does not exist here). Two group-level overrides make the baseline correct for a docker-less edge host: `hardening_extra_sysctl` drops the fleet default's `net.ipv4.ip_forward: 1` (a Docker-host accommodation; here the CIS default `0` is exactly D6's no-forwarding stance) and keeps only the two kernel keys, and the role's stale-drop-in removal is parameterized so the hardening converge deletes `10-zaccess-interim.conf` the moment it takes ownership of the whole file (a drop-in is orphaned anyway once `ssh_hardening` writes a config with no `Include`). The bootstrap play touches no sshd config at all — the interim drop-in governs until Phase 2. `hardening_root_ttys` already includes `ttyS0` (Linode LISH), so the serial break-glass survives the CIS baseline unchanged.
- **D11 — Bridgehead observability: native Alloy from Grafana's pinned apt repo, in scope from Phase 2.** The bridgehead joins `observed` like every tier, but not via Docker — adding the Docker daemon to the internet edge solely to host the telemetry agent inverts the host's no-container simplicity; native-pinned-apt is exactly D9's pattern. What ships: node metrics (OOM and disk-full are this host's realistic deaths), WireGuard handshake age **from both ends** (textfile timers — bridgehead in `access`, ops in `access_ops` — because a dead bridgehead cannot report its own tunnel), and **edge certificate expiry** — read by the same probe shape as the NAS leg (`openssl s_client` → `notAfter` → gauge), one script on each host, so the alert is independent of Caddy's metric surface. Alert rules (attended push): bridgehead dark (nodata), WG handshake stale (either side), Caddy cert expiry < 14 days, disk high-water — each summary carries an `infra/runbooks/README.md` anchor authored in the same change. The keep-regex + CI metric-admission guard extend to the new host. Its `config.alloy` needs **no drift assert**: the copy is ungated, so every converge ships it and a hand edit cannot outlive the next run — the other tiers assert precisely because their copies are digest-gated and an ordinary converge skips them. Named consequences: the bridgehead holds the Grafana Cloud push credentials (same exposure class as the capture VPSes — public-IP hosts that already hold them), and the fleet gains one non-containerized Alloy (version pinned in `fleet-pins.md` instead of a digest). **No hc.io dead-man for the bridgehead**: Grafana Cloud is external to both home and Linode, so nodata alerting already covers "the bridgehead died"; hc.io stays the capture/ops failure domain — a decision, not a gap.
- **D12 — The NAS's Sectigo certificate is monitored, not just load-bearing.** The ops-side textfile timer additionally reads `notAfter` off `192.168.100.5:5001` and exports it as a gauge; the cert-expiry alert covers it. This is the one certificate in the design that expires without anyone's automation renewing it (2027-01-26), and D7 makes its lapse fail G3 closed.
- **D13 — agentboard runs as `zhaow`, pinned, and must never manage the `zcrypto` session.** It binds `10.99.0.2:4040` (the tunnel address — off the LAN with no firewall rule needed), ordered after `wg-quick@zaccess0`. tmux does not lock sessions, so concurrent home-LAN attach continues to work. The three real risks, in severity order: (1) **destructive session management** — hibernation/wake heuristics vs a weeks-long run: `TMUX_SESSION` points at agentboard's own disposable session, `zcrypto` is surfaced only via `DISCOVER_PREFIXES`, and **agentboard does not go live until the Phase-7 spike proves it cannot hibernate, kill, or resize a session it merely discovered**; (2) **resize churn** — a web client attaching reflows the discovered session to its pty size. The intended fix was `window-size manual` (+ `default-size`) in the managed tmux conf, **but that was found (2026-07-30, the hard way) to CRASH the tmux 3.5a server on the next `new-session`** — it poisoned `~/.tmux.conf`, and when agentboard created its own session the whole server died, taking the live `zcrypto` with it. So the pin is **dropped** (guard test `tests/test_infra_tmux_conf_no_window_size_manual.py`): with `window-size latest` (the default) the browser terminal simply follows the client's size, which the 2026-07-30 monkey test confirmed is **good UX, not a defect** — resizing the browser, the ops terminal, and an Ubuntu terminal all reflowed cleanly and coexisted, so the "reflow" the pin fought is the desired behaviour; (3) **the nested-attach fallback is ALSO unsafe on tmux 3.5a** — a nested `tmux attach` to the same server crashes it too. What the 2026-07-30 spike + incident actually proved: agentboard on the shared socket with the SAFE config does **not** crash anything and refuses to kill/hibernate a discovered session (`"Cannot kill external sessions"`); the only real hazard was the `window-size manual` pin, now removed. Every agentboard upgrade is a security-relevant change (D2 makes the edge the only control).
- **D14 — Goals land in risk order: G1, then G3, then G2.** DSM is a known-good upstream; proving Caddy→tunnel against it first means an agentboard misbehavior is already isolated to agentboard. Phase 5 proves mTLS against a static response before any upstream exists, so ACME failures and proxy failures cannot be mistaken for one another.
- **D15 — `~/.tmux.conf` is Ansible-managed.** A template in `access_ops`, owned `zhaow:zhaow`, starting as exactly the current two lines (`mouse on`, `history-limit 10000`) plus the managed-file header; hand edits are overwritten at the next converge — that is the deal "managed" makes. tmux reads the file only at server start, so a converge can never reflow the live session by editing it; a change-triggered handler (`tmux source-file`, run as `zhaow`, guarded on a running server) is the deliberate, bounded apply step — the same reload-on-change shape the fleet's Alloy configs use. The file stays exactly those two lines: the D13 `window-size manual` pin that was to join it here is dropped — it crashes tmux 3.5a (see D13).
- **D16 — Client-leaf provisioning is a script deliverable**: `infra/scripts/zaccess-client-cert.sh issue <name> [--days N]` (default **365**; client certs face no browser-imposed lifetime cap, and expiry is only the backstop — revocation is the control). It signs on the workstation with the CA key streamed from the vault (`ansible-vault view` piped into openssl — the key never touches disk in cleartext), emits the `.p12`, and drops the leaf PEM into `roles/access/files/pinned-leaves/<name>.pem` — simultaneously the readable authorized-device record and the operand Caddy's pin list renders from. Revocation is the file's absence: delete the PEM, converge, reload. No overwrite of an existing name. The verification revocation drill is a procedure over this script (`issue drill-throwaway` → converge → confirm → delete → converge → confirm refusal).
- **D17 — One plan, one branch, one PR.** This is a side access channel bearing neither trading nor data loads; consistency with the repo's one-component-one-PR convention outweighs a transport/edge split. Phases 0–7 are the plan's internal order.
- **D18 — Route53 records are created by hand, once** — the `tmux.`/`nas.` subdomain records beside the existing `zaccess` A/AAAA — and recorded in `docs/reference/fleet.md`. DNS automation for four static records is machinery with no second customer: an explicit drop, not a deferral.
- **D19 — No new open topics from this work package.** Everything is either in this spec, in the plan, or an explicit drop (D18). The plan-level "HOW" deferrals (unit shapes, CA parameters, the agentboard spike procedure, the sshd `Port` reconciliation sequence) are plan content, not topic material.

## Secrets

Additions to the existing vault (chain unchanged):

| Secret | Renders |
| --- | --- |
| `deploy_zaccess_ed25519` private half | nowhere — used by `scripts/run.sh`'s throwaway agent |
| WG private key ×2 (bridgehead, ops) + preshared key | each host's `/etc/wireguard/zaccess0.conf`, root 0600 |
| mTLS CA private key | nowhere — workstation-only signing via D16's script |
| client leaf bundle (`.p12` + passphrase) | the MacBook keychain (operator action); vault holds the durable copy |

Public halves (WG pubkeys, CA cert, leaf PEMs, `deploy_zaccess_ed25519.pub`) stay plaintext as the readable record of what is authorized where. The Grafana Cloud push credentials are already in `group_vars/observed/vault.yml`; the bridgehead reads them by membership. **Named residual**: the vault is a crown-jewel store one notch further — live trade key, WG keys, and a CA key under one GPG key; consistent with the existing posture, recorded rather than implied.

## Phased execution — one plan

| # | Phase | Complete when |
| --- | --- | --- |
| 0 | Inventory + identity | `access_host`/`zaccess` in inventory; `deploy_zaccess_ed25519` + WG/CA/leaf secrets vaulted; nothing converged |
| 1 | Bootstrap | `zcrypto-deploy` reaches the bridgehead (user + exclusive key + sudo only — no sshd change; the interim drop-in still governs) |
| 2 | Bridgehead baseline | hardening/firewall/fail2ban/chrony/unattended-upgrades live (nftables default-drop; `ssh_hardening` owns sshd, interim drop-in removed); **native Alloy shipping node metrics; bridgehead-dark + disk alerts live** |
| 3 | WireGuard link | `wg show` handshake fresh; survives reboot of both ends; **handshake-age metrics from both ends, stale alert live** |
| 4 | SSH exposure | **G1** — `ssh -p 20022 zhaow@zaccess.zhaow.me` from an external network lands on ops |
| 5 | CA + Caddy + DNS | mTLS proven against a static page; both certificates issued; **cert-expiry metric + alert live** |
| 6 | NAS relay | **G3** — DSM usable in a browser; **NAS-cert `notAfter` probe live** |
| 7 | agentboard | **G2** — `zcrypto` usable in a browser; D13 spike gates cleared; tmux `window-size` pin landed |

Bridgehead converges are attended (internet-facing) but owe no bake — this is not the capture path. Order within the plan follows D14: G1 → G3 → G2.

## Verification

- **Idempotence** — a second converge is clean under `--check --diff`.
- **Lockout safety** — every sshd change is `sshd -t`-validated and applied with a fallback session verified before the old path closes; Linode's LISH console is the break-glass.
- **G1 from a genuinely external network**, and from an IPv6-only network if available (exercises D5's edge-IPv6 claim).
- **mTLS negative test — the load-bearing one**: requesting either subdomain with no client certificate must fail at the *TLS handshake*. An HTTP status code returned means the gate is not where this design says it is.
- **mTLS positive test** — `curl --cert … --key …` returns 200.
- **Revocation drill** — via D16's script and a throwaway leaf.
- **Certificate auto-renewal** — both certificates confirmed Caddy-*managed* (not static files), a forced renewal against Let's Encrypt staging succeeds end-to-end, and the **cert-expiry alert replaces any calendar check permanently**: renewal failing for two weeks is a page, not a journal entry nobody reads.
- **tmux non-disruption** — with the live `zcrypto` session running: attach/detach via agentboard repeatedly; window dimensions, pane process, and scrollback unchanged; home-LAN SSH attach still works afterwards.
- **Reboot durability** — reboot each host independently; all three paths return unattended.
- **Tunnel resilience** — restart `wg-quick@zaccess0` on ops and confirm re-establishment plus the stale alert firing and resolving; a real ISP address change is verified opportunistically and recorded in `docs/reference/fleet.md`'s bridgehead section.
- **Guards are proven by constructing the failure they name** — the pin list fed an unpinned leaf, the firewall render test fed an extra port, the mTLS gate fed a certless request — never by reading the assertion.

## Non-goals

- No other home-LAN service is exposed; the bridgehead reaches exactly `10.99.0.2` on `:22`/`:4040`/`:5001` and has no route into `192.168.100.0/24`.
- No phone/tablet enrolment — one leaf, the MacBook (D2).
- No IPv6 inside the tunnel (D5).
- DSM is not Ansible-managed — this project only relays TCP to it.
- Not a general-purpose VPN; not multi-user; no high availability (one VPS, one tunnel — failure means no remote access until repaired).
- No hc.io dead-man for the bridgehead (D11).
- No DNS automation (D18).

## Risks

1. **agentboard may hibernate, kill, or resize the live `zcrypto` session** — highest severity; D13 mitigates by construction, the Phase-7 spike gates go-live, the nested-attach fallback stands.
2. **agentboard is young (v0.4.5) and unauthenticated** — pinned; D2's edge is the sole control; every re-pin is security-relevant and attended (recorded in `fleet-pins.md`).
3. **Caddy's client-auth directives drift across versions** — version pinned; exact syntax verified against that version's docs at plan time.
4. **DSM's Sectigo certificate expires 2027-01-26** — fails G3 closed (correct direction), now monitored (D12).
5. **`Port` is additive across sshd config files** — live only until Phase 2: the interim drop-in carries no `Port` line, and once `ssh_hardening` owns the whole file there are no drop-ins left to collide. The Phase-2 converge is still lockout-critical (it rewrites sshd config over the connection using it) — same validated-then-reload sequence the capture hosts already survived.
6. **Single points of failure** — one VPS, one tunnel; LISH is the only out-of-band path, and only to the bridgehead.
7. **A managed `~/.tmux.conf` overwrites hand edits** — by design (D15); the operator's tweaks go through the repo.
8. **One non-containerized Alloy diverges from the fleet convention** — accepted (D11); pinned via apt version, drift-asserted like every other tier.

## Deferred to the plan (HOW, not WHAT)

- The sshd `Port` reconciliation sequence on the bridgehead and the interim-drop-in replacement order.
- The nftables extra-ports rendering and the byte-identity render test for capture hosts.
- `systemd-socket-proxyd` unit shapes (socket activation, dual-family listening, ordering against `wg-quick@zaccess0`).
- CA parameters, leaf lifetime default plumbing, `.p12` packaging; the exact `ansible-vault view → openssl` pipeline of D16.
- The agentboard runtime spike (Bun vs Node), pinned install method, the spike procedure proving D13's non-destructiveness gate, and the unit environment (`TMUX_SESSION`, `DISCOVER_PREFIXES`, bind address).
- Alloy native-install specifics (repo pinning, unit, config layout) and the textfile-timer shapes on both hosts.
- Alert rule expressions and their runbook sections.
