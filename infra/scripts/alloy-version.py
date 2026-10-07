#!/usr/bin/env python3
"""What an `alloy` run selects on a host, the version a bump may move the fleet to, and the hosts off the fleet's.

`reaches HOST` exits 0 when a play of `site.yml` that reaches HOST runs an `alloy`-tagged task, 1 when none does, and
2 when the tree cannot be read. The tags are read the way Ansible selects by them: a block, an `import_role` or an
`import_tasks` hands its tags and `when` to every task inside, a role entry's tags reach every task of its role, and
an `include_role` or `include_tasks` is one task, the tasks it brings in at run time unread.

`gate` prints the fleet file's version; the newest version above it that both Docker Hub, by a `v<x.y.z>` tag whose
registry index carries a linux/amd64 image, and apt.grafana.com's index carry, with the registry's index digest and
the index's own deb version string; and each newer version one source alone carries. A source that fails is exit 2.

`off-fleet` prints how many hosts of the inventory's `observed` group have an `alloy` row in `fleet-pins.md` off the
fleet file, or none, and names each on stderr.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
import urllib.request
from collections.abc import Callable, Mapping
from pathlib import Path

import yaml

ANSIBLE_DIR = Path(__file__).resolve().parents[1] / "ansible"
ROLES_DIR = ANSIBLE_DIR / "roles"
TAG = "alloy"
IMPORT_ROLE = ("ansible.builtin.import_role", "ansible.legacy.import_role", "import_role")
IMPORT_TASKS = ("ansible.builtin.import_tasks", "ansible.legacy.import_tasks", "import_tasks")
FLEET_FILE = ("group_vars", "observed", "alloy.yml")
PINS_FILE = ("docs", "reference", "fleet-pins.md")

TIMEOUT = 30
HUB_TAGS = "https://hub.docker.com/v2/repositories/grafana/alloy/tags?page_size=100&ordering=last_updated"
TOKEN = "https://auth.docker.io/token?service=registry.docker.io&scope=repository:grafana/alloy:pull"
MANIFEST = "https://registry-1.docker.io/v2/grafana/alloy/manifests/v{version}"
INDEX_ACCEPT = "application/vnd.oci.image.index.v1+json, application/vnd.docker.distribution.manifest.list.v2+json"
APT_INDEX = "https://apt.grafana.com/dists/stable/main/binary-amd64/Packages"
RELEASE_TAG = re.compile(r"v(\d+\.\d+\.\d+)")
DEB_VERSION = re.compile(r"(\d+\.\d+\.\d+)-(\d+)")
INDEX_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
IMAGE_CELL = re.compile(r"`([0-9a-f]{12})`")
PACKAGE_CELL = re.compile(r"`([^`]+)`")

Fetch = Callable[[str, Mapping[str, str]], tuple[bytes, Mapping[str, str]]]

_spec = importlib.util.spec_from_file_location("pins_converged", Path(__file__).with_name("pins-converged.py"))
_pins = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_pins)


def load(path: Path) -> list[dict]:
    return yaml.safe_load(path.read_text()) or []


def tags_of(node: dict) -> frozenset[str]:
    raw = node.get("tags") or []
    items = [raw] if isinstance(raw, str) else raw
    return frozenset(tag.strip() for item in items for tag in str(item).split(",") if tag.strip())


def when_of(task: dict) -> tuple[str, ...]:
    when = task.get("when", [])
    return tuple(str(c) for c in (when if isinstance(when, list) else [when]))


def walk(tasks, tags=frozenset(), gates=(), *, roles_dir: Path = ROLES_DIR, base: Path | None = None):
    """Each task leaf as `(task, tags, gates)`; `base` is the importing file's directory an `import_tasks` resolves in."""
    out = []
    for task in tasks or []:
        own = frozenset(tags | tags_of(task))
        conds = gates + when_of(task)
        role = next((key for key in IMPORT_ROLE if key in task), None)
        imported = next((key for key in IMPORT_TASKS if key in task), None)
        if role:
            args = task[role]
            path = roles_dir / args["name"] / "tasks" / f"{args.get('tasks_from', 'main')}.yml"
            out += walk(load(path), own, conds, roles_dir=roles_dir, base=path.parent)
        elif imported:
            if base is None:
                raise ValueError(f"{task.get('name')}: import_tasks with no importing file to resolve it against")
            path = base / task[imported]
            out += walk(load(path), own, conds, roles_dir=roles_dir, base=path.parent)
        elif any(k in task for k in ("block", "rescue", "always")):
            for key in ("block", "rescue", "always"):
                out += walk(task.get(key), own, conds, roles_dir=roles_dir, base=base)
        else:
            out.append((task, own, conds))
    return out


def role_leaves(role: str, inherited: frozenset[str], *, ansible_dir: Path = ANSIBLE_DIR):
    path = ansible_dir / "roles" / role / "tasks" / "main.yml"
    return walk(load(path), inherited, roles_dir=ansible_dir / "roles", base=path.parent)


def plays_reaching(host: str, *, ansible_dir: Path = ANSIBLE_DIR) -> list[dict]:
    plays = load(ansible_dir / "site.yml")
    groups = _pins.inventory_groups(ansible_dir.resolve().parents[1])
    return [play for play in plays if host in (groups.get(play["hosts"]) or {play["hosts"]})]


def _run_leaves(host: str, ansible_dir: Path):
    """`(where, task, tags)` in run order: a play's `pre_tasks`, its roles, its `tasks`, its `post_tasks`."""
    for play in plays_reaching(host, ansible_dir=ansible_dir):
        play_tags = tags_of(play)
        for section in ("pre_tasks", "roles", "tasks", "post_tasks"):
            if section == "roles":
                for entry in play.get("roles") or []:
                    leaves = role_leaves(entry["role"], play_tags | tags_of(entry), ansible_dir=ansible_dir)
                    yield from ((entry["role"], task, tags) for task, tags, _ in leaves)
            else:
                leaves = walk(play.get(section), play_tags, roles_dir=ansible_dir / "roles", base=ansible_dir)
                yield from ((play["hosts"], task, tags) for task, tags, _ in leaves)


def selected(tags, run_tags) -> bool:
    """Ansible's selection by `--tags` (its `Taggable.evaluate_tags`); `--skip-tags` is not read."""
    tags, asked = set(tags) or {"untagged"}, set(run_tags) or {"all"}
    return (
        "always" in tags
        or ("all" in asked and "never" not in tags)
        or not tags.isdisjoint(asked)
        or ("tagged" in asked and tags != {"untagged"} and "never" not in tags)
    )


def selection(host: str, run_tags, *, ansible_dir: Path = ANSIBLE_DIR) -> list[tuple[str, str]]:
    """`(where, task name)` for each task a run with these tags runs on the host, `where` a role or a play's hosts."""
    return [(where, task.get("name")) for where, task, tags in _run_leaves(host, ansible_dir) if selected(tags, run_tags)]


def reaches(host: str, *, ansible_dir: Path = ANSIBLE_DIR) -> bool:
    return any(TAG in tags for _, _, tags in _run_leaves(host, ansible_dir))


def fetch(url: str, headers: Mapping[str, str]) -> tuple[bytes, Mapping[str, str]]:
    with urllib.request.urlopen(urllib.request.Request(url, headers=dict(headers)), timeout=TIMEOUT) as response:
        return response.read(), dict(response.headers.items())


class GateFailed(Exception):
    pass


def _read(source: str, read: Callable[[], object]):
    try:
        return read()
    except Exception as exc:
        raise GateFailed(f"{source}: {type(exc).__name__}: {exc}") from exc


def _key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def fleet_version(ansible_dir: Path = ANSIBLE_DIR) -> dict[str, str]:
    return yaml.safe_load(ansible_dir.joinpath(*FLEET_FILE).read_text())


def hub_versions(fetch: Fetch) -> set[str]:
    body, _ = fetch(HUB_TAGS, {})
    return {m.group(1) for tag in json.loads(body)["results"] if (m := RELEASE_TAG.fullmatch(tag["name"]))}


def apt_versions(fetch: Fetch) -> dict[str, str]:
    """Each upstream version the `Package: alloy` stanzas carry, mapped to the Version string of its highest revision."""
    body, _ = fetch(APT_INDEX, {})
    best: dict[str, tuple[int, str]] = {}
    for stanza in body.decode().split("\n\n"):
        fields = dict(line.split(":", 1) for line in stanza.splitlines() if line[:1].strip() and ":" in line)
        if fields.get("Package", "").strip() != "alloy":
            continue
        m = DEB_VERSION.fullmatch(fields.get("Version", "").strip())
        if m and int(m.group(2)) > best.get(m.group(1), (-1, ""))[0]:
            best[m.group(1)] = (int(m.group(2)), m.group(0))
    return {upstream: deb for upstream, (_, deb) in best.items()}


def index_digests(fetch: Fetch, versions: list[str]) -> dict[str, str]:
    """Each version whose index carries a linux/amd64 image, mapped to the index digest the registry answers with."""
    if not versions:
        return {}
    body, _ = fetch(TOKEN, {})
    asked = {"Authorization": f"Bearer {json.loads(body)['token']}", "Accept": INDEX_ACCEPT}
    out = {}
    for version in versions:
        body, headers = fetch(MANIFEST.format(version=version), asked)
        digest = {name.lower(): value for name, value in headers.items()}["docker-content-digest"].strip()
        if not INDEX_DIGEST.fullmatch(digest):
            raise ValueError(f"v{version}'s Docker-Content-Digest is {digest!r}")
        platforms = [entry.get("platform") or {} for entry in json.loads(body)["manifests"]]
        if any(p.get("os") == "linux" and p.get("architecture") == "amd64" for p in platforms):
            out[version] = digest
    return out


def gate(fetch: Fetch = fetch, *, ansible_dir: Path = ANSIBLE_DIR) -> list[str]:
    fleet = _read("fleet file", lambda: fleet_version(ansible_dir))
    floor = _key(fleet["alloy_version"])
    images = _read("docker hub", lambda: {v for v in hub_versions(fetch) if _key(v) > floor})
    debs = _read("apt index", lambda: {v: deb for v, deb in apt_versions(fetch).items() if _key(v) > floor})
    indexed = _read("registry", lambda: index_digests(fetch, sorted(images, key=_key)))
    both = sorted(set(indexed) & set(debs), key=_key)
    lines = [f"fleet: {fleet['alloy_version']} {fleet['alloy_image_digest']} {fleet['alloy_deb_version']}"]
    if both:
        target = both[-1]
        lines.append(f"target: {target} {indexed[target]} {debs[target]}")
    else:
        lines.append("target: none — the fleet runs the newest version present in both")
    for version in sorted(set(indexed) ^ set(debs), key=_key, reverse=True):
        lines.append(f"image only: v{version}" if version in indexed else f"apt only: {debs[version]}")
    return lines


def _columns(header: list[str]) -> tuple[str, int, int, int] | None:
    """The table a header row opens, `image` or `package`, and its name, host and value columns."""
    for table, name, value in (("image", "service", "digest"), ("package", "package", "version")):
        hit = [k for k, cell in enumerate(header) if cell.startswith(value)]
        if name in header and hit:
            return table, header.index(name), header.index("host"), hit[0]
    return None


def alloy_rows(pins: Path) -> list[tuple[str, str, str]]:
    """`(host, table, value)` for each host of an `alloy` row: the image table's leading backticked 12 hex, the package
    table's leading backticked version, '' where the cell opens with neither. A file without both tables is refused."""
    rows: list[tuple[str, str, str]] = []
    found: set[str] = set()
    columns = None
    for line in pins.read_text().splitlines():
        if not line.startswith("|"):
            columns = None
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if "host" in (header := [cell.lower() for cell in cells]):
            columns = _columns(header)
            found |= {columns[0]} if columns else set()
            continue
        if columns is None or cells[columns[1]] != "alloy":
            continue
        table, _, host, value = columns
        m = (IMAGE_CELL if table == "image" else PACKAGE_CELL).match(cells[value])
        rows += [(name.strip(), table, m.group(1) if m else "") for name in cells[host].split(",")]
    if missing := {"image", "package"} - found:
        raise ValueError(f"{pins} has no {' and no '.join(sorted(missing))} table")
    return rows


def off_fleet(*, ansible_dir: Path = ANSIBLE_DIR) -> list[tuple[str, str]]:
    """`(host, why)` for each `observed` host whose `alloy` row is off the fleet file, or that has no `alloy` row."""
    root = ansible_dir.resolve().parents[1]
    fleet = fleet_version(ansible_dir)
    want = {"image": fleet["alloy_image_digest"].removeprefix("sha256:")[:12], "package": fleet["alloy_deb_version"]}
    rows = alloy_rows(root.joinpath(*PINS_FILE))
    off = []
    for host in sorted(_pins.inventory_groups(root).get("observed") or ()):
        mine = [(table, value) for name, table, value in rows if name == host]
        wrong = [
            f"{table} row at {value or 'no readable version'}, the fleet's is {want[table]}"
            for table, value in mine
            if value != want[table]
        ]
        if not mine:
            off.append((host, "no alloy row"))
        elif wrong:
            off.append((host, "; ".join(wrong)))
    return off


def main(argv: list[str] | None = None, *, fetch: Fetch = fetch) -> int:
    parser = argparse.ArgumentParser(prog="alloy-version.py", description=__doc__.split("\n\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    for command, purpose in (
        ("reaches", "does a play that reaches HOST run an alloy-tagged task"),
        ("gate", "the version a bump may move the fleet to, read from Docker Hub, the registry and apt.grafana.com"),
        ("off-fleet", "how many observed hosts have an alloy row off the fleet file, or none"),
    ):
        sub = commands.add_parser(command, help=purpose)
        sub.add_argument(
            "--ansible-dir", type=Path, default=ANSIBLE_DIR, metavar="DIR", help="the Ansible tree (default: this checkout's)"
        )
        if command == "reaches":
            sub.add_argument("host", metavar="HOST")
    args = parser.parse_args(argv)
    # Every failure exits 2: uncaught, it would exit 1, the answer that the host is not reached.
    try:
        if args.command == "gate":
            print("\n".join(gate(fetch, ansible_dir=args.ansible_dir)))
            return 0
        if args.command == "off-fleet":
            off = off_fleet(ansible_dir=args.ansible_dir)
            print(len(off))
            for host, why in off:
                print(f"  {host}: {why}", file=sys.stderr)
            return 0
        hit = reaches(args.host, ansible_dir=args.ansible_dir)
    except GateFailed as exc:
        print(f"gate: failed: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"{args.command}: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    if not hit:
        print(f"no play that reaches {args.host} runs an alloy-tagged task", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
