#!/usr/bin/env python3
"""The engine role's cache proxy configuration, rendered for an unprivileged namespace, and the pinned HAProxy
image it runs on.

    uv run python infra/scripts/cache-proxy-harness.py fetch --digest sha256:<64 hex> --into <dir>

fetch  a network read: pulls `library/haproxy` anonymously from Docker Hub by its index digest, checks the index,
       the linux/amd64 manifest and every layer against their sha256, and applies the layers in order, whiteouts
       included, into <dir>, which must be absent or empty; no member, hard link or whiteout acts outside it.
       `.harness-image-digest` is written last, so a tree without it is a fetch that did not finish. The tree is
       read as a filesystem image only: nothing Python is ever run from inside it.

Exit: 0 fetched, 2 refused (a digest that does not match, a member reaching outside the tree, a non-empty
<dir>), 1 any other error, printed.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import shutil
import sys
import tarfile
import urllib.request
from collections.abc import Callable, Mapping
from pathlib import Path

import jinja2

NODES = (
    {"name": "node1", "address": "127.0.0.11"},
    {"name": "node2", "address": "127.0.0.12"},
    {"name": "node3", "address": "127.0.0.13"},
)
MASTER_NAME = "zcache"
REQUIREPASS = "harness-dummy-requirepass"
TEMPLATE = Path(__file__).resolve().parents[1] / "ansible/roles/engine/templates/haproxy.cfg.j2"
# The namespace maps one user and has no /var/lib/haproxy, and a wildcard 6379 would collide with the scripted
# Valkeys on the same port.
EDITS = (
    ("    chroot /var/lib/haproxy\n", ""),
    ("    user haproxy\n", ""),
    ("    group haproxy\n", ""),
    ("    bind 0.0.0.0:6379\n", "    bind 127.0.0.1:6379\n"),
)

IMAGE_DIGEST_FILE = ".harness-image-digest"
REPOSITORY = "https://registry-1.docker.io/v2/library/haproxy"
TOKEN_URL = "https://auth.docker.io/token?service=registry.docker.io&scope=repository:library/haproxy:pull"
ACCEPT = ", ".join(
    (
        "application/vnd.oci.image.index.v1+json",
        "application/vnd.docker.distribution.manifest.list.v2+json",
        "application/vnd.oci.image.manifest.v1+json",
        "application/vnd.docker.distribution.manifest.v2+json",
    )
)
WHITEOUT = ".wh."
OPAQUE = ".wh..wh..opq"
# The bits the `tar` filter keeps of a member's mode: no setuid, setgid or sticky, no group or other write.
TAR_FILTER_MODE = 0o755
DIGEST = re.compile(r"sha256:[0-9a-f]{64}")


class FetchRefused(Exception):
    pass


def render(template: str) -> str:
    env = jinja2.Environment(trim_blocks=True, lstrip_blocks=False, undefined=jinja2.StrictUndefined)
    text = env.from_string(template).render(
        engine_cache_proxy_nodes=list(NODES),
        engine_cache_proxy_master_name=MASTER_NAME,
        cache_sentinel_requirepass=REQUIREPASS,
    )
    for old, new in EDITS:
        text = text.replace(old, new)
    return text


def _urllib_get(url: str, headers: Mapping[str, str]) -> bytes:
    request = urllib.request.Request(url)
    # A blob answers with a redirect to its storage host, which must not receive the registry's bearer token.
    for name, value in headers.items():
        request.add_unredirected_header(name, value)
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def _verified(body: bytes, digest: str) -> bytes:
    if "sha256:" + hashlib.sha256(body).hexdigest() != digest:
        raise FetchRefused(f"the bytes served for {digest} hash to another digest")
    return body


def _member_ok(name: str) -> bool:
    return not os.path.isabs(name) and ".." not in name.split("/")


def _inside(into: Path, path: str) -> Path:
    root = os.path.realpath(into)
    resolved = os.path.realpath(into / path, strict=os.path.ALLOW_MISSING)
    if resolved == root or resolved.startswith(root + "/"):
        return Path(resolved)
    raise FetchRefused(f"{path!r} resolves to {resolved}, outside the tree")


def _remove(path: Path) -> None:
    if path.is_dir(follow_symlinks=False):
        shutil.rmtree(path)
    elif os.path.lexists(path):
        path.unlink()


def _empty(directory: Path, written: set[Path]) -> None:
    """Remove what lower layers put under `directory`, keeping what this layer wrote."""
    if not directory.is_dir(follow_symlinks=False):
        return
    for entry in directory.iterdir():
        if entry not in written:
            _remove(entry)
        elif entry.is_dir(follow_symlinks=False):
            _empty(entry, written)


def _apply(blob: bytes, into: Path) -> None:
    written: set[Path] = set()
    modes: dict[Path, int] = {}
    with tarfile.open(fileobj=io.BytesIO(blob)) as layer:
        for member in layer:
            base = os.path.basename(member.name)
            whiteout = base.removeprefix(WHITEOUT) if base.startswith(WHITEOUT) else None
            names = [member.name]
            if member.islnk():
                names.append(member.linkname)
            if whiteout is not None:
                names.append(whiteout)
            refused = [name for name in names if not _member_ok(name)]
            # Either names the directory holding the marker, which a whiteout never removes.
            if whiteout in ("", "."):
                refused.append(whiteout)
            if refused:
                raise FetchRefused(f"layer member {member.name!r} names {refused[0]!r}, which no layer may act on")
            directory = _inside(into, os.path.dirname(member.name))
            if member.islnk():
                _inside(into, member.linkname)
            if base == OPAQUE:
                _empty(directory, written)
                continue
            if whiteout is not None:
                _remove(directory / whiteout)
                continue
            existing = directory / base
            if not (member.isdir() and existing.is_dir(follow_symlinks=False)):
                _remove(existing)
            try:
                layer.extract(member, into, set_attrs=not member.isdir(), filter="tar")
            except tarfile.FilterError as exc:
                raise FetchRefused(str(exc)) from exc
            written.add(existing)
            if member.isdir():
                modes[existing] = member.mode & TAR_FILTER_MODE
        # A directory's mode waits for its members, as `extractall` defers it: one without owner-write would
        # refuse them. Deepest first, so a parent without owner-search still lets its children be set.
        for path, mode in sorted(modes.items(), key=lambda item: len(item[0].parts), reverse=True):
            if path.is_dir(follow_symlinks=False):
                path.chmod(mode)


def fetch(digest: str, into: Path, get: Callable[[str, Mapping[str, str]], bytes] = _urllib_get) -> None:
    if into.exists() and (not into.is_dir() or any(into.iterdir())):
        raise FetchRefused(f"{into} is not an empty directory")
    token = json.loads(get(TOKEN_URL, {}))["token"]
    headers = {"Authorization": f"Bearer {token}", "Accept": ACCEPT}
    index = json.loads(_verified(get(f"{REPOSITORY}/manifests/{digest}", headers), digest))
    amd64 = [
        entry
        for entry in index.get("manifests", [])
        if entry.get("platform", {}).get("os") == "linux" and entry.get("platform", {}).get("architecture") == "amd64"
    ]
    if len(amd64) != 1:
        raise FetchRefused(f"the index lists {len(amd64)} linux/amd64 manifests, not one")
    manifest_digest = amd64[0]["digest"]
    manifest = json.loads(_verified(get(f"{REPOSITORY}/manifests/{manifest_digest}", headers), manifest_digest))
    layers = []
    for layer in manifest["layers"]:
        layers.append(_verified(get(f"{REPOSITORY}/blobs/{layer['digest']}", headers), layer["digest"]))
        print(f"verified {layer['digest']}")
    into.mkdir(parents=True, exist_ok=True)
    for blob in layers:
        _apply(blob, into)
    (into / IMAGE_DIGEST_FILE).write_text(digest + "\n")


def _digest(value: str) -> str:
    if not DIGEST.fullmatch(value):
        raise argparse.ArgumentTypeError("expected sha256:<64 lowercase hex>")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    fetch_command = commands.add_parser("fetch", help="pull the pinned image's layers into an empty directory")
    fetch_command.add_argument("--digest", required=True, type=_digest)
    fetch_command.add_argument("--into", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        fetch(args.digest, args.into)
    except FetchRefused as exc:
        print(f"refused: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print(f"fetched {args.into} from haproxy@{args.digest[:19]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
