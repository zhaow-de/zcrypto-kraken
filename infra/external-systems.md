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
<nas-ip>:/volume1/ZhaoCrypto  /home/zhaow/Projects/zcrypto-kraken-data  nfs  nfsvers=4.1,rw,noauto,x-systemd.automount,x-systemd.mount-timeout=10,soft,timeo=10,retrans=5,noatime,sync  0  0
```

Then start the systemd daemon:

```shell
sudo systemctl daemon-reload
sudo systemctl restart 'home-zhaow-Projects-zcrypto\x2dkraken\x2ddata.automount'
```

So that the NFS mount could take effect:

```shell
ls -la /home/zhaow/Projects/zcrypto-kraken-data
df -h
```

**SSH config**

Append the following lines to `~/.ssh/config` for some shortcuts to ease the remote connection. Assumptions:

- Same SSH key (`infra/ansible/files/deploy_ed25519`) is used for the deployment user (`deploy` as the Linode VPS and the local ops node, `zcrypto-deploy` at the Synology NAS)
- Except for NAS, the `deploy` user is provisioned by the Ansible script
- Both `deploy` and `zcrypto-deploy` on all the 4x nodes are passwordless sudo enabled

```
Host zcrypto
  HostName zcrypto.zhaow.me
  Port 10022
  User deploy
  IdentityFile ~/.ssh/zcrypto-deploy_ed25519
  IdentitiesOnly yes

Host red
  HostName zcrypto-red.zhaow.me
  Port 10022
  User deploy
  IdentityFile ~/.ssh/zcrypto-deploy_ed25519
  IdentitiesOnly yes

Host hp
  HostName <ops-node-ip>
  Port 22
  User deploy
  IdentityFile ~/.ssh/zcrypto-deploy_ed25519
  PreferredAuthentications publickey
  UpdateHostKeys no

Host nas
  HostName <nas-ip>
  Port 22
  User zcrypto-deploy
  IdentityFile ~/.ssh/zcrypto-deploy_ed25519
  PreferredAuthentications publickey
  UpdateHostKeys no
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
- DSM web -> Control Panel -> Terminal & SNMP, "Enable Telnet service" + "Enable SSH service"
- From the local workstation, `telnet <nas-ip>`, login with the Synology DSM admin (the one to login http://<nas-ip>:5000 for administration). `sudo -i`, then:
  - `cat /etc/passwd` to ensure no user has UID 1000
  - `cat /etc/group` to ensure no group has GID 1000 (The `1000:1000` above is to match the UID:GID of the local workstation, because the local workstation can create dirs/files in NAS shared folder via NFS. We align the UID:GID to ease the permission mapping and management)
- DSM web -> Control Panel -> User & Group:
  - "Advanced" tab, check "Enable user home service"
  - "User" tab, create users: `zcrypto`, `zcrypto-dummy`, `zcrypto-deploy`
  - "Group" tab, create group: `zcrypto`, add the three users above into the group
- DSM web -> Control Panel -> Shared Folder, "Create Shared Folder"
  - Name: `ZhaoCrypto`
  - Permissions: group `zcrypto` can "Read/Write"
  - Advanced Permissions: uncheck "Enabled advances share permissions"
  - NFS Permissions: create a new one:
    - Hostname or IP: `<home-lan>/24`
    - Privilege: `Read/Write`
    - Squash: `No mapping` (\<-- this is the root cause why we align the UID and GID between `zhaow`@local-workstation and `zcrypto`@nas)
    - Security: `sys`
    - Enable asynchronous: **checked**
    - Allow connections from non-priviledged ports (ports higher than 1024): **unchecked**
    - Allow users to access mounted subfolders: **checked**
- At the terminal:
  - `vim /etc/group` to change the GID of group to `1000` (or the same as group `zhaow`@local-workstation)
  - `vim /etc/passwd` to:
    - change the UID of user to `1000` (or the same as user `zhaow`@local-workstation)
    - change the home dir of user `zcrypto` and `zcrypto-dummy` to `/nonexist`
    - change the shell of user `zcrypto` and `zcrypto-dummy` to `/usr/bin/nologin`
    - double check the home dir of user `zcrypto-deploy` is `/var/services/homes/zcrypto-deploy`, and its shell is `/bin/sh`
  - `synouser --rebuild all` (NOTE: after this step, the user `zcrypto` will disappear from DSM web Control Panel -> User & Group)
  - `synogroup --rebuild all` (NOTE: after this step, the group `zcrypto` will disappear from DSM web Control Panel -> User & Group)
  - `mkdir -p /volume1/homes/zcrypto-deploy/.ssh/`, append the content of SSH public key for the deploy user (`infra/ansible/files/deploy_ed25519.pub`) to `/volume1/homes/zcrypto-deploy/.ssh/authorized_keys`
  - `chown -R zcrypto-deploy: /volume1/homes/zcrypto-deploy/.ssh/`
  - `chmod 0600 /volume1/homes/zcrypto-deploy/.ssh/authorized_keys`
  - `chown -R zcrypto: /volume1/ZhaoCrypto`
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
- As root, `echo "deploy ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/deploy && chmod 440 /etc/sudoers.d/deploy`

## Linode `zcrypto-primary`<a name="linode-zcrypto-primary"></a>

Linode 4 GB Shared CPU plan at DE, Frankfurt (eu-central)

### Bootstrap<a name="bootstrap-2"></a>

Linode web console, NETWORKING -> Firewalls: create a cloud firewall named `ssh10022` (default inbound policy `Drop`, default outbound `Accept`, inbound accepts limited to ICMP and the SSH port). The exact rule set is deliberately not recorded here — read it from the Linode console.

Create a new node:

- Name: `zcrypto-kraken-primary`
- Debian 13
- Firewall: `ssh10022`

Run `echo "deploy ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/deploy && chmod 440 /etc/sudoers.d/deploy`

## Linode `zcrypto-redundant`<a name="linode-zcrypto-redundant"></a>

Linode 2GB Shared CPU plan at NL, Amsterdam (nl-ams)

### Bootstrap<a name="bootstrap-3"></a>

Create a new node:

- Name: `zcrypto-kraken-redundant`
- Debian 13
- Firewall: `ssh10022`

Run `echo "deploy ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/deploy && chmod 440 /etc/sudoers.d/deploy`
