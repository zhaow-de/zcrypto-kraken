"""Remove the Docker images a fleet host no longer needs, keeping every digest the pins file records.
The capture daemon STOPS APPENDING below `DEFAULT_MIN_FREE_BYTES` in `cli/capture/gap_monitor.py`,
and L2 capture is unbackfillable, so a host that never prunes is one image pull away from
permanent data loss.
`docs/reference/fleet-pins.md` is the authority for which digests must survive, and the moment it
is updated is the moment a prune is correct: run this from the pins-update step, strictly AFTER
the new row is written, or the run takes the digest that row is about.
Usage:  uv run python infra/scripts/prune-host-images.py <host> [--apply] [--keep D] [--pins PATH]
Dry-run by default. `--apply` removes one explicit `repo@sha256:<digest>` at a time, never `docker
image prune -a`, which would take the recorded rollback operands.
Neither authority sees a PRE-STAGED digest: an image pulled for a converge that has not happened
is resident, unrecorded and attached to no container, so it is indistinguishable from a stale one.
Prune only the host that just converged, and pass `--keep <digest12>` for anything staged for a
converge still to come.
"""

import argparse
import dataclasses
import re
import shlex
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DEFAULT_PINS = REPO / "docs/reference/fleet-pins.md"

# The digest shorthand is the cell's LEADING backticked token -- anchored, never merely the first
# 12-hex found. A cell reading ``revision `f54431a6c0de` — `aaaaaaaaaaaa` `` would otherwise keep
# the revision and leave the real pin removable, silently: "revisions are 8 hex" is a habit of the
# file, not an invariant of it.
LEADING_DIGEST12 = re.compile(r"^`([0-9a-f]{12})`")

# Unanchored -- for finding rows orphaned outside the table, where any position counts.
ANY_DIGEST12 = re.compile(r"`[0-9a-f]{12}`")

SEPARATOR_CELL = re.compile(r"^:?-{3,}:?$")

# A row may legitimately have NO rollback path -- a first-ever pin of a new service. The file says
# so explicitly; refusing such a row would disable this script fleet-wide, and the only way to
# satisfy a stricter parser would be to invent an operand digest, i.e. write false data into the
# authority file. A typo'd digest matches neither this nor a digest, so it still refuses.
OPERAND_NONE = re.compile(r"^(—|–|-|n/a|none|\(none\)|first pin|\(first pin\))$", re.IGNORECASE)

MANUAL_KEEP = re.compile(r"^[0-9a-f]{12}$")


class PruneError(Exception):
    """Refusal: something this script must read is not readable the way it must be."""


class PinsError(PruneError):
    """The pins file cannot serve as the authority -- refuse rather than compute a keep-set.

    Every path here is the catastrophic direction: an under-populated keep-set removes an image the
    file means to protect, and a rollback operand is not running, so nothing else covers it.
    """


@dataclasses.dataclass(frozen=True)
class HostAccess:
    ssh: str
    docker: tuple[str, ...]


# ssh aliases and the docker invocation per host; `docs/reference/fleet.md` is the source. The NAS
# is the odd one out: docker is at /usr/local/bin/docker, needs sudo, and is NOT on a
# non-interactive ssh PATH -- called bare there, `docker ps` returns empty and reads as "no
# containers" rather than "command not found", i.e. a keep-set missing every resident image.
HOSTS = {
    "zcrypto": HostAccess(ssh="zcrypto", docker=("docker",)),
    "zcrypto-red": HostAccess(ssh="red", docker=("docker",)),
    "zcrypto-ops": HostAccess(ssh="hp", docker=("docker",)),
    "nas": HostAccess(ssh="nas", docker=("sudo", "/usr/local/bin/docker")),
}


@dataclasses.dataclass(frozen=True)
class PinRow:
    service: str
    hosts: tuple[str, ...]
    current: str
    operand: str  # "" when the row explicitly declares no rollback path


@dataclasses.dataclass(frozen=True)
class HostImage:
    repo: str
    digest: str  # full "sha256:<64 hex>", or "" for an image carrying no repo digest
    image_id: str
    size: str

    @property
    def short(self) -> str:
        return self.digest.removeprefix("sha256:")[:12]

    @property
    def ref(self) -> str:
        return f"{self.repo}@{self.digest}"


@dataclasses.dataclass(frozen=True)
class ContainerImage:
    """A container's image reference. Stopped containers count: their image is equally unremovable,
    and leaving it out of the host authority turns a correct refusal by docker into a spurious
    FAILED line and a non-zero exit."""

    container: str
    ref: str  # verbatim `.Config.Image` -- never `.Image`, which is host-dependent

    @property
    def repo(self) -> str:
        return split_ref(self.ref)[0]

    @property
    def short(self) -> str:
        return split_ref(self.ref)[1]


@dataclasses.dataclass(frozen=True)
class PrunePlan:
    host: str
    keep: dict[str, list[str]]  # digest12 -> the pins rows that name it
    extra_keep: frozenset[str]  # --keep operands: pre-staged digests no authority can see
    containers: tuple[ContainerImage, ...]
    unrecorded: tuple[ContainerImage, ...]  # resident container, digest-pinned, absent from the file
    unresolved: tuple[ContainerImage, ...]  # container not digest-pinned -> its repo is protected
    no_digest: tuple[HostImage, ...]  # managed-repo images carrying no repo digest -> unremovable
    managed_repos: frozenset[str]
    remove: tuple[HostImage, ...]


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _leading_digest(cell: str) -> str:
    match = LEADING_DIGEST12.match(cell.strip())
    return match.group(1) if match else ""


def parse_pins_table(text: str) -> list[PinRow]:
    """The `## Current pins` table of the pins file, as rows.

    Only the FIRST contiguous block of table lines is read -- the non-image package table sits
    under the same heading, separated by prose -- and any row stranded below that block is a
    refusal, never a silent omission.
    """
    lines = text.splitlines()
    starts = [i for i, ln in enumerate(lines) if ln.strip() == "## Current pins"]
    if not starts:
        raise PinsError("no '## Current pins' heading in the pins file — there is no keep-set to derive")

    section: list[str] = []
    for line in lines[starts[0] + 1 :]:
        if line.startswith("## "):
            break
        section.append(line)

    block: list[str] = []
    tail: list[str] = []
    for i, line in enumerate(section):
        if line.startswith("|"):
            block.append(line)
        elif block:
            tail = section[i:]
            break

    # A row stranded BELOW the block -- separated by a stray blank line, an HTML comment, one
    # indented row, or a second image table -- would vanish from the keep-set, taking that row's
    # ROLLBACK OPERAND with it. That is precisely the deletion this script exists to prevent, and
    # the container union cannot mask it: an operand is by definition not attached to a container.
    # The live file has no such token outside the block, so this refuses only on the defect.
    stray = [ln for ln in tail if ln.startswith("|") and ANY_DIGEST12.search(ln)]
    if stray:
        raise PinsError(
            f"{len(stray)} pins row(s) sit below a break in the '## Current pins' table and would be silently "
            f"dropped from the keep-set — rejoin the table before pruning: {stray[0]!r}"
        )

    if len(block) < 3:
        raise PinsError(
            f"the '## Current pins' table holds {max(len(block) - 2, 0)} rows — refusing, "
            "since an empty keep-set removes every managed image on the host"
        )

    header = _cells(block[0])
    if not all(SEPARATOR_CELL.match(c) for c in _cells(block[1])):
        raise PinsError(f"the pins table has no header separator: {block[1]!r}")

    def column(name: str, matches) -> int:
        hits = [i for i, cell in enumerate(header) if matches(cell)]
        if len(hits) != 1:
            raise PinsError(f"the pins table header names no unique {name!r} column: {header}")
        return hits[0]

    i_service = column("service", lambda c: c == "service")
    i_host = column("host", lambda c: c == "host")
    i_digest = column("digest", lambda c: c.startswith("digest"))
    i_operand = column("rollback operand", lambda c: c.startswith("rollback operand"))

    rows: list[PinRow] = []
    for line in block[2:]:
        cells = _cells(line)
        # An escaped pipe inside a code span would over-split the row and shift every column; the
        # count check turns that into a refusal instead of a silently wrong keep-set.
        if len(cells) != len(header):
            raise PinsError(f"pins row has {len(cells)} cells against a {len(header)}-cell header: {line!r}")
        hosts = tuple(h.strip() for h in cells[i_host].split(",") if h.strip())
        if not hosts:
            raise PinsError(f"pins row names no host: {line!r}")
        current = _leading_digest(cells[i_digest])
        if not current:
            raise PinsError(f"pins row does not open its digest cell with a backticked 12-hex digest: {line!r}")
        operand = _leading_digest(cells[i_operand])
        if not operand and not OPERAND_NONE.match(cells[i_operand]):
            raise PinsError(
                f"pins row's rollback operand is neither a leading backticked 12-hex digest nor an explicit "
                f"'no rollback path' marker: {line!r}"
            )
        rows.append(PinRow(service=cells[i_service], hosts=hosts, current=current, operand=operand))
    return rows


def keep_for_host(rows: list[PinRow], host: str) -> dict[str, list[str]]:
    """Every digest the file says must survive on `host`, mapped to the rows that say so.

    A UNION across rows, not a per-service or per-repo cap: capture and the engine share a repo on
    one host and diverge mid-rollout, so four digests of one repo can all be live at once.
    """
    rows_for_host = [row for row in rows if host in row.hosts]
    if not rows_for_host:
        raise PinsError(f"no pins row names host {host!r} — refusing, since an empty keep-set removes every managed image")

    keep: dict[str, list[str]] = {}
    for row in rows_for_host:
        for digest, kind in ((row.current, "current"), (row.operand, "operand")):
            if digest:  # a row may declare no rollback path
                keep.setdefault(digest, []).append(f"{row.service}/{kind}")
    return keep


def split_ref(ref: str) -> tuple[str, str]:
    """(repository, first 12 of the digest). The digest is "" for a tag-pinned reference."""
    name, sep, digest = ref.partition("@")
    if sep and digest.startswith("sha256:"):
        return name, digest.removeprefix("sha256:")[:12]
    tail = name.rsplit("/", 1)[-1]  # a registry port is a colon too, but always before the last slash
    if ":" in tail:
        name = name[: len(name) - len(tail) + tail.index(":")]
    return name, ""


def plan(
    *,
    host: str,
    rows: list[PinRow],
    images: list[HostImage],
    containers: list[ContainerImage],
    extra_keep: tuple[str, ...] = (),
) -> PrunePlan:
    for digest in extra_keep:
        if not MANUAL_KEEP.match(digest):
            raise PruneError(f"--keep wants a bare 12-hex digest, got {digest!r} — a typo here silently keeps nothing")

    keep = keep_for_host(rows, host)
    unresolved = tuple(c for c in containers if not c.short)
    unrecorded = tuple(c for c in containers if c.short and c.short not in keep)

    # The managed repos are DERIVED, never hardcoded: a repo is managed because the host holds an
    # image the pins file names. Anything else on the host -- vendor containers on the NAS, a
    # locally built image -- is therefore untouchable by construction.
    managed = {img.repo for img in images if img.short and img.short in keep and img.repo != "<none>"}
    # A container not pinned by digest cannot be matched against the file at all, so nothing in its
    # repo can be judged safe: protect the whole repo rather than guess.
    managed -= {c.repo for c in unresolved}

    keep_all = set(keep) | {c.short for c in containers if c.short} | set(extra_keep)
    # Two tags of one image list twice under the same digest; removing the ref twice would report a
    # spurious FAILED for the second.
    by_ref: dict[str, HostImage] = {}
    for img in images:
        if img.repo in managed and img.short and img.short not in keep_all:
            by_ref.setdefault(img.ref, img)
    return PrunePlan(
        host=host,
        keep=keep,
        extra_keep=frozenset(extra_keep),
        containers=tuple(containers),
        unrecorded=unrecorded,
        unresolved=unresolved,
        no_digest=tuple(img for img in images if img.repo in managed and not img.short),
        managed_repos=frozenset(managed),
        remove=tuple(by_ref.values()),
    )


def parse_image_ls(stdout: str) -> list[HostImage]:
    images: list[HostImage] = []
    for line in stdout.splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) != 4:
            raise PruneError(f"unparsable image line: {line!r}")
        repo, digest, image_id, size = (p.strip() for p in parts)
        images.append(HostImage(repo=repo, digest="" if digest == "<none>" else digest, image_id=image_id, size=size))
    return images


def parse_df_avail_bytes(stdout: str) -> int:
    """The Available column of `df -Pk`, in bytes. POSIX -P guarantees one line per filesystem."""
    lines = [ln for ln in stdout.splitlines() if ln.strip()]
    if len(lines) < 2:
        raise PruneError(f"no filesystem line in the disk report: {stdout!r}")
    fields = lines[-1].split()
    if len(fields) < 4 or not fields[3].isdigit():
        raise PruneError(f"unparsable disk report line: {lines[-1]!r}")
    return int(fields[3]) * 1024


class Docker:
    """The whole host seam. Every method is one blocking ssh; nothing else here touches a host."""

    def __init__(self, host: str) -> None:
        self.host = host
        self.access = HOSTS[host]

    def _ssh(self, argv: tuple[str, ...], *, check: bool = True) -> tuple[int, str, str]:
        remote = " ".join(shlex.quote(a) for a in argv)
        proc = subprocess.run(["ssh", self.access.ssh, remote], capture_output=True, text=True)
        if check and proc.returncode != 0:
            raise PruneError(f"{remote} on {self.host} exited {proc.returncode}: {proc.stderr.strip()}")
        return proc.returncode, proc.stdout, proc.stderr

    def _docker(self, *argv: str, check: bool = True) -> tuple[int, str, str]:
        return self._ssh((*self.access.docker, *argv), check=check)

    def containers(self) -> list[ContainerImage]:
        # -a: a STOPPED container still holds its image against removal, so omitting it turns a
        # correct docker refusal into a spurious FAILED line and a non-zero exit.
        names = [n for n in self._docker("ps", "-a", "--format", "{{.Names}}")[1].split() if n]
        if not names:
            return []
        # `.Config.Image` -- what the container was created from. Never `.Image`, which is a
        # host-dependent local id under classic storage.
        refs = self._docker("inspect", "--format", "{{.Config.Image}}", *names)[1].split()
        if len(refs) != len(names):
            raise PruneError(f"{self.host}: {len(names)} containers but {len(refs)} image refs — refusing to guess the pairing")
        return [ContainerImage(container=n, ref=r) for n, r in zip(names, refs, strict=True)]

    def images(self) -> list[HostImage]:
        fmt = "{{.Repository}}\t{{.Digest}}\t{{.ID}}\t{{.Size}}"
        return parse_image_ls(self._docker("image", "ls", "--digests", "--format", fmt)[1])

    def free_bytes(self) -> int:
        root = self._docker("info", "--format", "{{.DockerRootDir}}")[1].strip()
        if not root:
            raise PruneError(f"{self.host}: docker reports no root directory")
        return parse_df_avail_bytes(self._ssh(("df", "-Pk", root))[1])

    def remove_image(self, ref: str) -> tuple[bool, str]:
        code, out, err = self._docker("image", "rm", ref, check=False)
        return code == 0, (err.strip() or out.strip())


def _gib(n: int) -> str:
    return f"{n / 1024**3:.2f} GiB"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Remove the Docker images a fleet host no longer needs. The keep-set is the union of every "
        "fleet-pins row naming the host (current pin + rollback operand) plus every image a container holds. "
        "Run it right after that host's pins row is updated — never before, or it takes the digest that row is "
        "about — and pass --keep for any digest pre-staged for a converge still to come.",
    )
    parser.add_argument("host", choices=sorted(HOSTS))
    parser.add_argument("--apply", action="store_true", help="actually remove; without it nothing is touched")
    parser.add_argument("--pins", type=Path, default=DEFAULT_PINS, help=f"pins file (default {DEFAULT_PINS})")
    parser.add_argument(
        "--keep",
        action="append",
        default=[],
        metavar="DIGEST12",
        help="also keep this digest — for an image pre-staged for a converge that has not happened yet, "
        "which no authority can distinguish from a stale one. Repeatable.",
    )
    args = parser.parse_args(argv)

    rows = parse_pins_table(args.pins.read_text())
    docker = Docker(args.host)
    containers = docker.containers()
    images = docker.images()
    result = plan(host=args.host, rows=rows, images=images, containers=containers, extra_keep=tuple(args.keep))

    print(f"host {args.host} (ssh {docker.access.ssh}, docker {' '.join(docker.access.docker)})")
    print(f"pins  {args.pins}")
    print(f"keep from pins ({len(result.keep)}):")
    for digest, labels in sorted(result.keep.items()):
        print(f"  {digest}  {', '.join(labels)}")
    for digest in sorted(result.extra_keep):
        print(f"  {digest}  kept by hand (pre-staged)")
    print(f"containers ({len(result.containers)}):")
    for container in result.containers:
        print(f"  {container.container:<28} {container.ref}")
    print(f"managed repos: {', '.join(sorted(result.managed_repos)) or '(none)'}")
    print(f"resident images: {len(images)}   free before: {_gib(docker.free_bytes())}")

    for container in result.unresolved:
        print(f"WARNING: {container.container} is not pinned by digest ({container.ref}) — its whole repo is protected here")
    for container in result.unrecorded:
        print(
            f"UNRECORDED PIN: {container.container} runs {container.ref}, which the pins file does not record — kept; the file is wrong"
        )
    if result.no_digest:
        print(
            f"NOTE: {len(result.no_digest)} managed-repo image(s) carry no repo digest — skipped, and their space is not reclaimable here"
        )

    if not result.remove:
        print("nothing to remove")
    else:
        print(f"removable ({len(result.remove)}):")
        for img in result.remove:
            print(f"  {img.ref}  ({img.size})")

    if not args.apply:
        print("DRY RUN — nothing removed. Re-run with --apply once the pins row is committed.")
        return 0

    before = docker.free_bytes()
    failed = 0
    for img in result.remove:
        ok, message = docker.remove_image(img.ref)
        print(f"  {'removed ' if ok else 'FAILED  '} {img.ref}{'' if ok else f': {message}'}")
        failed += 0 if ok else 1
    after = docker.free_bytes()
    print(f"free after: {_gib(after)}   reclaimed: {_gib(after - before)}")

    if failed:
        print(f"{failed} removal(s) failed")
    if result.unrecorded:
        print(f"{len(result.unrecorded)} resident image(s) are not recorded in the pins file — record them before the next prune")
    return 1 if (failed or result.unrecorded) else 0


if __name__ == "__main__":
    sys.exit(main())
