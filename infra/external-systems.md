# MEMO: External System Provision

Home-LAN addresses are redacted (`<nas-ip>`, `<ops-node-ip>`, `<home-lan>/24`) — this repo is public. Substitute the real values from your own network when following these steps.

<!-- mdformat-toc start --slug=github --maxlevel=3 --minlevel=2 -->

- [Local workstation](#local-workstation)
  - [Spec](#spec)
  - [Bootstrap](#bootstrap)
- [Self-managed: Synology NAS](#self-managed-synology-nas)
  - [Spec](#spec-1)
  - [Initial setup](#initial-setup)
- [Self-managed: HP home server](#self-managed-hp-home-server)
  - [Spec](#spec-2)
  - [Bootstrap](#bootstrap-1)
- [Linode `zcrypto-primary`](#linode-zcrypto-primary)
  - [Bootstrap](#bootstrap-2)
- [Linode `zcrypto-redundant`](#linode-zcrypto-redundant)
  - [Bootstrap](#bootstrap-3)

<!-- mdformat-toc end -->

## Local workstation<a name="local-workstation"></a>

Dell Mobile Precision Workstation 7730

### Spec<a name="spec"></a>

|  | Model | Comment |
| -- | -- | -- |
| CPU | 1x Intel Xeon E-2186M 2.90GHz, 12M Cache, 6C12T |  |
| RAM | 4x 32GB DDR4 2667MT/s |  |
| HDD | 3x Samsung NVMe SM961 1024GB | No RAID, logical volume |

IP: home network dynamic.

### Bootstrap<a name="bootstrap"></a>

- Ubuntu Desktop 26.04 LTS
- User: `zhaow:zhaow` (`1000:1000`)
- SSH private key `zhaow-master-2018` with `0600` permission added to the agent with `ssh-add zhaow-master-2018`

**NFS mount**

Add the following line to `/etc/fstab`:

```
<nas-ip>:/volume1/ZhaoCrypto  /mnt/zhao-crypto  nfs  ro,nfsvers=3,nolock,soft,timeo=100,retrans=3,noatime,nosuid,nodev,noauto,x-systemd.automount,x-systemd.mount-timeout=15  0  0
```

Then start the systemd daemon:

```shell
sudo systemctl daemon-reload
sudo mount -a
sudo systemctl restart 'mnt-zhao\x2dcrypto.automount'
```

So that the NFS mount could take effect:

```shell
ls -la /mnt/zhao-crypto
df -h
```

**SSH config**

Append the following lines to `~/.ssh/config` for some shortcuts to ease the remote connection. Assumptions:

- Each node has its own deploy SSH key: locally `~/.ssh/zcrypto-deploy-{zcrypto,red,ops,nas}_ed25519`, pubkeys recorded in `infra/ansible/files/` (see its `README.md`) — for the deployment user (`zcrypto-deploy`)
- Except for NAS, the `zcrypto-deploy` user is provisioned by the Ansible play
- User `zcrypto-deploy` on all the 4x nodes are passwordless sudo enabled

```
Host zcrypto
  HostName zcrypto.zhaow.me
  Port 10022
  User zcrypto-deploy
  IdentityFile ~/.ssh/zcrypto-deploy-zcrypto_ed25519
  PreferredAuthentications publickey
  IdentitiesOnly yes
  UpdateHostKeys yes

Host red
  HostName zcrypto-red.zhaow.me
  Port 10022
  User zcrypto-deploy
  IdentityFile ~/.ssh/zcrypto-deploy-red_ed25519
  PreferredAuthentications publickey
  IdentitiesOnly yes
  UpdateHostKeys yes

Host hp
  HostName <ops-node-ip>
  Port 22
  User zcrypto-deploy
  IdentityFile ~/.ssh/zcrypto-deploy-ops_ed25519
  PreferredAuthentications publickey
  IdentitiesOnly yes
  UpdateHostKeys yes

Host nas
  HostName <nas-ip>
  Port 22
  User zcrypto-deploy
  IdentityFile ~/.ssh/zcrypto-deploy-nas_ed25519
  PreferredAuthentications publickey
  IdentitiesOnly yes
  UpdateHostKeys yes
```

## Self-managed: Synology NAS<a name="self-managed-synology-nas"></a>

Synology DS1618+

### Spec<a name="spec-1"></a>

|  | Model | Comment |
| -- | -- | -- |
| CPU | 1x Intel Atom C3538 2.10GHz 4C |  |
| RAM | 2x 16GB DDR4 |  |
| HDD | 6x WD60EFAX 5.5TB | 26.2TB after RAID5 |

IP: home network `<nas-ip>`

### Initial setup<a name="initial-setup"></a>

- From DSM web, install `Container Manager` from Package Center
- DSM web -> Control Panel -> Regional Options -> Time Zone: **(GMT) Greenwich Mean Time** — the NAS clock must stay UTC: `docker logs --since` parses its argument in the host's **local** time. The `nas` Ansible role's first act is a fail-closed TZ guard (`date +%z` must print `+0000`), so a rebuilt NAS left on local time fails every converge until this is set (see `infra/nas/README.md`).
- DSM web -> Control Panel -> Terminal & SNMP, "Enable Telnet service" + "Enable SSH service"
- DSM web -> Control Panel -> File Services -> FTP, "Enable SFTP service" (otherwise, `scp` command from the modern OpenSSH client will not work)
- From the local workstation, `telnet <nas-ip>`, login with the Synology DSM admin (the one to login http://<nas-ip>:5000 for administration). `sudo -i`, then:
  - `cat /etc/passwd` to ensure no user has UID 1000
  - `cat /etc/group` to ensure no group has GID 1000 (The `1000:1000` above is to match the UID:GID of the local workstation, because the local workstation can create dirs/files in NAS shared folder via NFS. We align the UID:GID to ease the permission mapping and management)
- DSM web -> Control Panel -> User & Group:
  - "Advanced" tab, check "Enable user home service"
  - "User" tab, create users: `zcrypto-data`, `zcrypto-alloy`, `zcrypto-deploy`
  - "Group" tab, create group: `zcrypto`, add `zcrypto-data`, `zcrypto-deploy` above into the group (`zcrypto-alloy` **must** be excluded. It runs telemetry, never touches the ZhaoCrypto data — least-privilege)
- DSM web -> Control Panel -> Shared Folder, "Create Shared Folder"
  - Name: `ZhaoCrypto`
  - Permissions: group `zcrypto-data` can "Read/Write"
  - Advanced Permissions: uncheck "Enabled advances share permissions"
  - NFS Permissions: create a new one (Both the ops node and the workstation read the canonical trees through this export, automounted read-only at `/mnt/zhao-crypto`; the export-side **Read-Only** privilege is the server half of spec `00051` D10's "no write path toward custody" boundary — without this rule the boundary rests solely on the client-side `ro` mount flag):
    - Hostname or IP: `<home-lan>/24`
    - Privilege: `Read only`
    - Squash: `No mapping` (\<-- this is the root cause why we align the UID and GID between `zhaow`@local-workstation and `zcrypto-data`@nas)
    - Security: `sys`
    - Enable asynchronous: **checked**
    - Allow connections from non-priviledged ports (ports higher than 1024): **checked**
    - Allow users to access mounted subfolders: **checked**
- DSM web -> Control Panel -> Notification:
  - "Email": **uncheck** "Receive notifications directly in your Synology Account when system status changes or errors occur. These notifications are sent through Synology's email server"
  - "Webhooks": create a new webhook,
    - Provider: `Custom`
    - Rule: `Warning`
    - Provider name: `Slack Notification`
    - Subject: `[z-home-nas]`
    - Webhook URL: `https://hooks.slack.com/services/T0BG...` (replace it will the real Slack incoming message webhook)
    - Send notification messages in English: **checked**
    - HTTP Method: `POST`
    - Content-Type: `application/json`
    - HTTP Body: `{"text": "@@TEXT@@"}`
- DSM web -> Package Center -> Settings -> Package Sources, add a new source:
  - Name: `SynoCommunity`
  - Location: `https://packages.synocommunity.com`
- DSM web -> Package Center -> Community. Install `Python 3.14`, `Perl`
- At the terminal:
  - `vim /etc/group` to:
    - change the GID of group `zcrypto` to `1000` (or the same as group `zhaow`@local-workstation)
    - add users `zcrypto-data` and `zcrypto-deploy` to the system group `administrators` (at Synology DSM, only users in `administrators` group can use SSH — `zcrypto-deploy` for admin/Ansible, and `zcrypto-data` because it **receives the inbound hot-push over SSH**, spec 00057)
  - `vim /etc/passwd` to:
    - change the UID of user `zcrypto-data` to `1000` (or the same as user `zhaow`@local-workstation)
    - change the home dir of user `zcrypto-alloy` to `/nonexist`
    - change the home dir of user `zcrypto-data` to `/var/services/homes/zcrypto-data` — unlike `zcrypto-alloy`, `zcrypto-data` **receives the inbound hot-push over SSH** (spec 00057), so it needs a real home for `~/.ssh/authorized_keys` (the DSM symlink path — resilient to a `/volume1`→`/volume2` layout change; matches `zcrypto-deploy`'s home)
    - change the shell of user `zcrypto-alloy` to `/usr/bin/nologin`
    - change the shell of user `zcrypto-data` to `/bin/sh` (same as `zcrypto-deploy`) — `zcrypto-data` **serves the inbound hot-push**, which runs an rrsync forced command via the account's login shell, so it needs a real shell (`/usr/bin/nologin` would swallow the forced command). DSM accepts **only its own built-in shells** as an SSH login shell: a custom rrsync-only wrapper (like the one the ops host uses) is refused — DSM authenticates the key but then denies the session *before* exec'ing the shell, at any path, script or binary, and regardless of `/etc/shells` (verified 2026-07-19). So the rrsync-only restriction here is enforced **solely by the key's `command="…rrsync…",restrict` forced command** (installed by the `nas` role; it fully jails the key — no shell, no arbitrary command), not by the login shell as on ops.
    - double check the home dir of user `zcrypto-deploy` is `/var/services/homes/zcrypto-deploy`, and its shell is `/bin/sh`
  - `synouser --rebuild all` (NOTE: after this step, the user `zcrypto-data` will disappear from DSM web Control Panel -> User & Group)
  - `synogroup --rebuild all` (NOTE: after this step, the group `zcrypto` will disappear from DSM web Control Panel -> User & Group)
  - `mkdir -p /volume1/homes/zcrypto-deploy/.ssh/`, append the content of the NAS deploy public key (`infra/ansible/files/deploy_nas_ed25519.pub`) to `/volume1/homes/zcrypto-deploy/.ssh/authorized_keys`
  - `chown -R zcrypto-deploy: /volume1/homes/zcrypto-deploy/.ssh/`
  - `chmod 0600 /volume1/homes/zcrypto-deploy/.ssh/authorized_keys`
  - `mkdir -p /var/services/homes/zcrypto-data/.ssh && chown -R zcrypto-data: /var/services/homes/zcrypto-data/.ssh && chmod 0700 /var/services/homes/zcrypto-data/.ssh` — the `nas` role installs the hot-push `rrsync` forced-command key into `~zcrypto-data/.ssh/authorized_keys` (spec 00057); this ensures the home + `.ssh` exist for it. **After** the `zcrypto-data` push path is verified end-to-end, remove the old hot-push key from `~zcrypto-deploy/.ssh/authorized_keys` (the migration fallback; a from-scratch install never has it).
  - `chown -R zcrypto-data:zcrypto /volume1/ZhaoCrypto`
  - `chown -R zcrypto:users /volume1/ZhaoCrypto/@eaDir`
  - `echo "zcrypto-deploy ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/zcrypto-deploy && chmod 440 /etc/sudoers.d/zcrypto-deploy`
  - Put the following script in a file and run it:
    ```shell
    set -euo pipefail

    TARGET="${1:-/volume1/ZhaoCrypto}"
    GROUP="zcrypto"

    if [ "$(id -u)" != "0" ]; then
        echo "error: must run as root (sudo) — chmod/chgrp on ${GROUP}-owned files needs it" >&2
        exit 1
    fi
    if [ ! -d "$TARGET" ]; then
        echo "error: target is not a directory: $TARGET" >&2
        exit 1
    fi

    # Guard against a mistyped / too-shallow target: this runs as root and recurses, so a
    # stray `/` or `/volume1` would rewrite the whole volume. Require >= 2 path components
    # (e.g. /volume1/ZhaoCrypto), counting slashes in the resolved path.
    RESOLVED="$(readlink -f "$TARGET")"
    if [ "$(printf '%s' "$RESOLVED" | tr -cd / | wc -c)" -lt 2 ]; then
        echo "error: refusing a too-shallow target (need >= /volumeX/share): $RESOLVED" >&2
        exit 1
    fi

    # In every pass: `-xdev` stays on this filesystem (never cross into a nested mount), the
    # `@eaDir` prune skips Synology metadata subtrees, `xargs -0` handles odd names, and `--`
    # stops a path beginning with `-` being read as an option.
    # group -> zcrypto  (`-h`: a symlink's group is set on the link itself, never its target)
    find "$TARGET" -xdev -name '@eaDir' -prune -o -print0 | xargs -0r chgrp -h "$GROUP" --
    # directories -> 0775  (chmod also strips any Synology ACL on the entry)
    find "$TARGET" -xdev -name '@eaDir' -prune -o -type d -print0 | xargs -0r chmod 0775 --
    # files -> 0664
    find "$TARGET" -xdev -name '@eaDir' -prune -o -type f -print0 | xargs -0r chmod 0664 --

    echo "normalized $TARGET: dirs 0775, files 0664, group $GROUP, ACLs stripped"
    ```
- DSM web -> Control Panel -> Terminal & SNMP, uncheck "Enable Telnet service"

## Self-managed: HP home server<a name="self-managed-hp-home-server"></a>

HP Elite 800 Mini G9

### Spec<a name="spec-2"></a>

|  | Model | Comment |
| -- | -- | -- |
| CPU | 1x Intel Core i7-13700 13th Gen, 16C24T |  |
| RAM | 2x 32GB DDR5 4800MT/s |  |
| HDD | 1x Samsung SSD 990 PRO 4TB |  |

IP: home network `<ops-node-ip>`

### Bootstrap<a name="bootstrap-1"></a>

- Ubuntu Server 26.04 LTS
- User: `zhaow:zhaow`
- Place the content of SSH public key `zhaow-master-2018.out` to `/root/.ssh/authorized_keys`
- As root, `echo "zcrypto-deploy ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/zcrypto-deploy && chmod 440 /etc/sudoers.d/zcrypto-deploy`
- As root, `apt update && apt install git gh`
- As `zhaow`, `curl -LsSf https://astral.sh/uv/install.sh | sh`

## Linode `zcrypto-primary`<a name="linode-zcrypto-primary"></a>

Linode 4 GB Shared CPU plan at DE, Frankfurt (eu-central)

### Bootstrap<a name="bootstrap-2"></a>

Linode web console, NETWORKING -> Firewalls: create a cloud firewall named `ssh10022` (default inbound policy `Drop`, default outbound `Accept`, inbound accepts limited to ICMP and the SSH port). The exact rule set is deliberately not recorded here — read it from the Linode console.

Create a new node:

- Name: `zcrypto-kraken-primary`
- Debian 13
- Firewall: `ssh10022`

Run `echo "zcrypto-deploy ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/zcrypto-deploy && chmod 440 /etc/sudoers.d/zcrypto-deploy`

## Linode `zcrypto-redundant`<a name="linode-zcrypto-redundant"></a>

Linode 2GB Shared CPU plan at NL, Amsterdam (nl-ams)

### Bootstrap<a name="bootstrap-3"></a>

Create a new node:

- Name: `zcrypto-kraken-redundant`
- Debian 13
- Firewall: `ssh10022`

Run `echo "zcrypto-deploy ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/zcrypto-deploy && chmod 440 /etc/sudoers.d/zcrypto-deploy`
