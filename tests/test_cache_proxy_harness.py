"""`infra/scripts/cache-proxy-harness.py`'s render and fetch. No case reaches the registry: every `fetch` passes `get=`."""

import difflib
import hashlib
import importlib.util
import io
import json
import os
import tarfile
from collections.abc import Callable
from pathlib import Path

import jinja2
import pytest
import yaml

REPO = Path(__file__).resolve().parents[1]
TEMPLATE = REPO / "infra/ansible/roles/engine/templates/haproxy.cfg.j2"
_SPEC = importlib.util.spec_from_file_location("cache_proxy_harness", REPO / "infra/scripts/cache-proxy-harness.py")
harness = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(harness)

OCI_INDEX = "application/vnd.oci.image.index.v1+json"
OCI_MANIFEST = "application/vnd.oci.image.manifest.v1+json"
OCI_LAYER = "application/vnd.oci.image.layer.v1.tar+gzip"


def _digest(body: bytes) -> str:
    return "sha256:" + hashlib.sha256(body).hexdigest()


def _layer(entries: dict[str, bytes | str | None | tuple[str, str]]) -> bytes:
    out = io.BytesIO()
    with tarfile.open(fileobj=out, mode="w:gz") as tar:
        for name, value in entries.items():
            info = tarfile.TarInfo(name)
            if isinstance(value, bytes):
                info.size = len(value)
                tar.addfile(info, io.BytesIO(value))
                continue
            if isinstance(value, str):
                info.type, info.linkname = tarfile.SYMTYPE, value
            elif value is None:
                info.type, info.mode = tarfile.DIRTYPE, 0o755
            else:
                info.type, info.linkname = tarfile.LNKTYPE, value[1]
            tar.addfile(info)
    return out.getvalue()


def _registry(*layers: bytes, impostor: bytes | None = None) -> tuple[str, Callable, list[str]]:
    blobs: dict[str, bytes] = {}
    manifests: dict[str, bytes] = {}

    def manifest(platform: dict[str, str], platform_layers: tuple[bytes, ...]) -> dict:
        config = json.dumps({"os": platform["os"], "architecture": platform["architecture"]}).encode()
        for blob in (config, *platform_layers):
            blobs[_digest(blob)] = blob
        body = json.dumps(
            {
                "schemaVersion": 2,
                "mediaType": OCI_MANIFEST,
                "config": {"mediaType": "application/vnd.oci.image.config.v1+json", "digest": _digest(config), "size": len(config)},
                "layers": [{"mediaType": OCI_LAYER, "digest": _digest(blob), "size": len(blob)} for blob in platform_layers],
            }
        ).encode()
        manifests[_digest(body)] = body
        return {"mediaType": OCI_MANIFEST, "digest": _digest(body), "size": len(body), "platform": platform}

    index = json.dumps(
        {
            "schemaVersion": 2,
            "mediaType": OCI_INDEX,
            "manifests": [
                manifest(
                    {"os": "linux", "architecture": "arm64", "variant": "v8"}, (_layer({"usr/local/sbin/haproxy": b"other"}),)
                ),
                manifest({"os": "linux", "architecture": "amd64"}, layers),
                manifest({"os": "unknown", "architecture": "unknown"}, ()),
            ],
        }
    ).encode()
    asked: list[str] = []

    def get(url: str, headers) -> bytes:
        asked.append(url)
        wanted = url.rsplit("/", 1)[-1]
        if "/token" in url:
            return json.dumps({"token": "t"}).encode()
        if "/manifests/" in url:
            return manifests.get(wanted, index)
        if "/blobs/" in url:
            if impostor is not None and wanted == _digest(layers[-1]):
                return impostor
            if wanted in blobs:
                return blobs[wanted]
        raise LookupError(url)

    return _digest(index), get, asked


def test_the_harness_render_differs_from_the_roles_only_in_the_named_lines():
    env = jinja2.Environment(trim_blocks=True, lstrip_blocks=False, undefined=jinja2.StrictUndefined)
    text = TEMPLATE.read_text()
    role = env.from_string(text).render(
        engine_cache_proxy_nodes=list(harness.NODES),
        engine_cache_proxy_master_name=harness.MASTER_NAME,
        cache_sentinel_requirepass=harness.REQUIREPASS,
    )
    changed = [ln for ln in difflib.ndiff(role.splitlines(), harness.render(text).splitlines()) if ln[:2] in ("- ", "+ ")]
    assert changed == [
        "-     chroot /var/lib/haproxy",
        "-     user haproxy",
        "-     group haproxy",
        "-     bind 0.0.0.0:6379",
        "+     bind 127.0.0.1:6379",
    ]
    assert [n["address"] for n in harness.NODES] == ["127.0.0.11", "127.0.0.12", "127.0.0.13"]
    defaults = yaml.safe_load((REPO / "infra/ansible/roles/engine/defaults/main.yml").read_text())
    # The anchored expect's length marker reads as the fleet's.
    assert [len(n["address"]) for n in harness.NODES] == [len(n["address"]) for n in defaults["engine_cache_proxy_nodes"]]


def test_the_fetch_refuses_an_index_whose_digest_is_not_the_pin(tmp_path):
    digest, get, asked = _registry(_layer({"usr/local/sbin/haproxy": b"pinned"}))
    other = "sha256:" + hashlib.sha256(b"another index").hexdigest()
    with pytest.raises(harness.FetchRefused):
        harness.fetch(other, tmp_path / "refused", get=get)
    assert not any("/blobs/" in url for url in asked)
    assert not (tmp_path / "refused").exists() or not any((tmp_path / "refused").iterdir())
    harness.fetch(digest, tmp_path / "pinned", get=get)
    assert (tmp_path / "pinned/usr/local/sbin/haproxy").read_bytes() == b"pinned"
    assert (tmp_path / "pinned" / harness.IMAGE_DIGEST_FILE).read_text().strip() == digest


ESCAPES = {
    "dotdot": {"../outside/planted": b"x"},
    "member-through-a-link": {"link/pointer": b"x"},
    "whiteout-through-a-link": {"link/.wh.victim": b""},
    "whiteout-of-dotdot": {"etc/.wh...": b""},
    "whiteout-of-nothing": {"etc/.wh.": b""},
    "whiteout-of-a-dot": {"etc/.wh..": b""},
    "hard-link-out": {"x": ("hard", "../outside/victim")},
    "hard-link-through-a-link": {"x": ("hard", "link/victim")},
}


@pytest.mark.parametrize("escape", ESCAPES)
def test_the_fetch_writes_no_member_outside_its_tree(tmp_path, escape):
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "victim").write_text("kept")
    (outside / "pointer").symlink_to(outside / "victim")
    base: dict[str, bytes | str] = {"etc/base": b"b"}
    if escape.endswith("-through-a-link"):
        base["link"] = str(outside)
    digest, get, _ = _registry(_layer(base), _layer(ESCAPES[escape]))
    tree = tmp_path / "tree"
    with pytest.raises(harness.FetchRefused):
        harness.fetch(digest, tree, get=get)
    assert (tree / "etc/base").read_bytes() == b"b"
    assert sorted(os.listdir(outside)) == ["pointer", "victim"]
    assert (outside / "victim").read_text() == "kept"
    assert (outside / "victim").stat().st_nlink == 1
    assert os.readlink(outside / "pointer") == str(outside / "victim")
    assert not (tree / harness.IMAGE_DIGEST_FILE).exists()


def test_a_later_layer_replaces_a_lower_layers_link(tmp_path):
    digest, get, _ = _registry(
        _layer({"etc/alt": "/usr/bin/x", "etc/f": b"lower", "etc/g": "f"}),
        _layer({"etc/alt": "/usr/bin/y", "etc/g": b"upper"}),
    )
    tree = tmp_path / "tree"
    harness.fetch(digest, tree, get=get)
    assert os.readlink(tree / "etc/alt") == "/usr/bin/y"
    assert not (tree / "etc/g").is_symlink()
    assert (tree / "etc/g").read_bytes() == b"upper"
    assert (tree / "etc/f").read_bytes() == b"lower"


def test_a_later_layers_whiteouts_remove_what_they_name(tmp_path):
    digest, get, _ = _registry(
        _layer({"etc/a": b"a", "etc/b": b"b", "opt/x/old": b"o"}),
        _layer({"etc/.wh.a": b"", "opt/x/.wh..wh..opq": b"", "opt/x/new": b"n"}),
    )
    tree = tmp_path / "tree"
    harness.fetch(digest, tree, get=get)
    assert not os.path.lexists(tree / "etc/a")
    assert (tree / "etc/b").read_bytes() == b"b"
    assert os.listdir(tree / "opt/x") == ["new"]
    assert list(tree.rglob(".wh.*")) == []


def test_the_fetch_refuses_a_layer_whose_bytes_are_not_its_digest(tmp_path):
    digest, get, _ = _registry(
        _layer({"usr/local/sbin/haproxy": b"pinned"}),
        impostor=_layer({"usr/local/sbin/haproxy": b"impostor"}),
    )
    tree = tmp_path / "tree"
    with pytest.raises(harness.FetchRefused):
        harness.fetch(digest, tree, get=get)
    assert not os.path.lexists(tree / "usr/local/sbin/haproxy")
    assert not (tree / harness.IMAGE_DIGEST_FILE).exists()


def test_the_fetch_refuses_a_tree_already_holding_a_file(tmp_path):
    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / "left").write_text("partial")
    digest, get, _ = _registry(_layer({"usr/local/sbin/haproxy": b"pinned"}))
    with pytest.raises(harness.FetchRefused):
        harness.fetch(digest, tree, get=get)
    assert os.listdir(tree) == ["left"]
    assert (tree / "left").read_text() == "partial"
