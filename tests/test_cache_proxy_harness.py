"""`infra/scripts/cache-proxy-harness.py`'s render, fetch and the run's refusals and teardown. No case reaches the
registry: every `fetch` passes `get=`; none enters a namespace or starts HAProxy."""

import contextlib
import difflib
import hashlib
import importlib.util
import io
import json
import os
import stat
import subprocess
import sys
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


def _layer(entries: dict[str, bytes | str | None | int | tuple[str, str]]) -> bytes:
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
            elif isinstance(value, int):
                info.type, info.mode = tarfile.DIRTYPE, value
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


def test_a_directory_without_owner_write_takes_its_mode_after_its_members(tmp_path):
    digest, get, _ = _registry(_layer({"ro": 0o555, "ro/sub": 0o555, "ro/sub/f": b"f"}))
    tree = tmp_path / "tree"
    try:
        harness.fetch(digest, tree, get=get)
        assert (tree / "ro/sub/f").read_bytes() == b"f"
        assert [stat.S_IMODE((tree / name).stat().st_mode) for name in ("ro", "ro/sub")] == [0o555, 0o555]
    finally:
        # The scratch is removable only once both directories take owner-write back.
        for name in ("ro", "ro/sub"):
            if (tree / name).is_dir(follow_symlinks=False):
                (tree / name).chmod(stat.S_IMODE((tree / name).stat().st_mode) | stat.S_IWUSR)


def test_a_directory_without_owner_search_takes_its_mode_after_the_directory_beneath_it(tmp_path):
    digest, get, _ = _registry(_layer({"ro": 0o644, "ro/sub": 0o555}))
    tree = tmp_path / "tree"
    harness.fetch(digest, tree, get=get)
    assert stat.S_IMODE((tree / "ro").stat().st_mode) == 0o644
    (tree / "ro").chmod(0o755)
    assert stat.S_IMODE((tree / "ro/sub").stat().st_mode) == 0o555


def test_a_directory_keeps_only_the_mode_bits_the_tar_filter_keeps(tmp_path):
    digest, get, _ = _registry(_layer({"wide": 0o1777}))
    tree = tmp_path / "tree"
    harness.fetch(digest, tree, get=get)
    assert stat.S_IMODE((tree / "wide").stat().st_mode) == 0o755


def test_a_deferred_mode_never_follows_a_link_a_later_member_made(tmp_path):
    outside = tmp_path / "outside"
    (outside / "sub").mkdir(parents=True)
    (outside / "sub").chmod(0o755)
    digest, get, _ = _registry(_layer({"a/sub": 0o700, "a": str(outside)}))
    tree = tmp_path / "tree"
    harness.fetch(digest, tree, get=get)
    assert stat.S_IMODE((outside / "sub").stat().st_mode) == 0o755
    assert os.readlink(tree / "a") == str(outside)
    assert (tree / harness.IMAGE_DIGEST_FILE).read_text().strip() == digest


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


def test_the_run_refuses_a_namespace_with_any_interface_but_lo():
    assert harness.loopback_only(["lo"])
    assert not harness.loopback_only(["lo", "eth0"]) and not harness.loopback_only(["eth0"]) and not harness.loopback_only([])


def test_the_inner_run_starts_nothing_in_a_namespace_with_any_interface_but_lo(monkeypatch, tmp_path):
    started = []

    class Started(Exception):
        pass

    def record(argv, *args, **kwargs):
        started.append(argv)
        raise Started(argv)

    rootfs = tmp_path / "rootfs"
    rootfs.mkdir()
    (rootfs / harness.IMAGE_DIGEST_FILE).write_text("sha256:" + "0" * 64 + "\n")
    monkeypatch.setattr(harness.subprocess, "Popen", record)
    monkeypatch.setattr(harness.subprocess, "run", record)
    monkeypatch.setattr(harness.socket, "if_nameindex", lambda: [(1, "lo"), (2, "eth0")])
    assert harness.run_inside(rootfs, tmp_path / "scratch", list(harness.CASES)) == 2
    assert started == []
    monkeypatch.setattr(harness.socket, "if_nameindex", lambda: [(1, "lo")])
    with contextlib.suppress(Started):
        harness.run_inside(rootfs, tmp_path / "scratch", list(harness.CASES))
    assert started[:1] == [["/usr/bin/ip", "link", "set", "lo", "up"]], started


def test_the_run_refuses_a_binary_that_does_not_print_the_pinned_version():
    pin = harness.PINNED_VERSION
    assert harness.version_ok(f"HAProxy version {pin} 2026/10/01 - https://haproxy.org/")
    assert harness.version_ok(f"HAProxy version {pin}-1a2b3c4 2026/10/01 - https://haproxy.org/")
    assert not harness.version_ok("HAProxy version 0.0.1 2026/10/01 - https://haproxy.org/")
    assert not harness.version_ok(f"HAProxy version {pin}0 2026/10/01 - https://haproxy.org/")


def test_the_run_refuses_a_tree_the_fetch_did_not_finish(tmp_path):
    assert not harness.tree_whole(tmp_path)
    (tmp_path / harness.IMAGE_DIGEST_FILE).write_text("sha256:" + "0" * 64 + "\n")
    assert harness.tree_whole(tmp_path)


def test_a_case_that_raises_prints_fail_and_stops_every_process_it_started(tmp_path):
    argv = [sys.executable, "-c", "import time; time.sleep(30)", str(tmp_path)]
    twin = subprocess.Popen(argv)
    started = []

    def body(procs):
        started.append(procs.start(argv))
        raise RuntimeError("the case broke")

    try:
        line = harness.run_case("start", body)
        assert line.startswith("FAIL start") and "the case broke" in line, line
        assert started and started[0].poll() is not None
        with pytest.raises(subprocess.TimeoutExpired):  # a process the case did not start, on the same command line, lives on
            twin.wait(timeout=0.5)
    finally:
        for process in [twin, *started]:
            if process.poll() is None:
                process.kill()
                process.wait()


def test_a_mapping_outside_the_tree_is_foreign():
    maps = "\n".join(
        [
            "55d0-55e0 r--p 00000000 fd:01 11 /x/root/usr/local/sbin/haproxy",
            "55e0-55f0 rw-p 00000000 00:00 0 [heap]",
            "7f00-7f10 r-xp 00000000 fd:01 12 /x/root/usr/lib/x86_64-linux-gnu/libc.so.6",
            "7f10-7f20 r-xp 00000000 fd:01 13                          /usr/lib/x86_64-linux-gnu/libssl.so.3",
            "7f20-7f30 rw-p 00000000 00:00 0 ",
            "7ffd-7ffe r-xp 00000000 00:00 0 [vdso]",
            "7f30-7f40 r-xp 00000000 fd:01 14                          /x/rootfs/lib/libz.so.1",
            "7f40-7f50 rw-s 00000000 00:01 15 /dev/zero (deleted)",
        ]
    )
    assert harness.foreign_mappings(maps, "/x/root") == ["/usr/lib/x86_64-linux-gnu/libssl.so.3", "/x/rootfs/lib/libz.so.1"]


def test_the_mapping_read_covers_every_descendant_of_the_process(tmp_path):
    tasks = {10: {10: "11 12 ", 13: "14 "}, 11: {11: ""}, 12: {12: "15 "}, 14: {14: ""}, 15: {15: ""}}
    for pid, threads in tasks.items():
        for tid, children in threads.items():
            (tmp_path / f"{pid}/task/{tid}").mkdir(parents=True)
            (tmp_path / f"{pid}/task/{tid}/children").write_text(children)
    assert sorted(harness.process_tree(10, proc=tmp_path)) == [10, 11, 12, 14, 15]


def _image_tree(root: Path, entrypoint: str) -> Path:
    for path in ("usr/lib64/ld-linux-x86-64.so.2", "usr/local/sbin/haproxy"):
        (root / path).parent.mkdir(parents=True, exist_ok=True)
        (root / path).write_bytes(b"")
    (root / "lib64").symlink_to("usr/lib64")
    (root / "etc").mkdir()
    (root / "etc/ld.so.conf").write_text("/usr/lib64\n")
    (root / "usr/local/bin").mkdir(parents=True)
    (root / "usr/local/bin/docker-entrypoint.sh").write_text(entrypoint)
    return root


def test_the_run_refuses_an_entrypoint_whose_haproxy_flags_it_cannot_read(tmp_path):
    flags = '#!/bin/sh\nset -- haproxy "$@"\nset -- haproxy -W -db "$@"\nexec "$@"\n'
    assert harness.haproxy_argv(_image_tree(tmp_path / "flags", flags))[-2:] == ["-W", "-db"]
    for name, script in {"bare": '#!/bin/sh\nset -- haproxy "$@"\nexec "$@"\n', "none": '#!/bin/sh\nexec haproxy "$@"\n'}.items():
        with pytest.raises(harness.Refused, match="docker-entrypoint.sh"):
            harness.haproxy_argv(_image_tree(tmp_path / name, script))


class _Stuck:
    """A process whose wait outlasts its timeout, killed or not."""

    stdin = stdout = stderr = None
    args = ["stuck"]

    def poll(self):
        return None

    def terminate(self):
        pass

    def kill(self):
        pass

    def wait(self, timeout=None):
        raise subprocess.TimeoutExpired(self.args, timeout)


def test_a_process_that_will_not_stop_leaves_the_rest_of_the_teardown_to_run(monkeypatch, tmp_path):
    deleted = []
    monkeypatch.setattr(harness, "_nft", lambda *args: deleted.append(args) or "")
    procs = harness.Procs("start")
    sleeper = procs.start([sys.executable, "-c", "import time; time.sleep(30)", str(tmp_path)])
    procs.processes.append(_Stuck())
    procs.table_made = True
    try:
        with pytest.raises(subprocess.TimeoutExpired):
            procs.stop_all()
        assert sleeper.poll() is not None
        assert deleted == [("delete", "table", "inet", "start")]
    finally:
        if sleeper.poll() is None:
            sleeper.kill()
            sleeper.wait()
    signalled = harness.Procs("start")
    signalled.processes.append(_Stuck())
    signalled.processes[0].wait = lambda timeout=None: sys.exit(143)
    signalled.table_made = True
    with pytest.raises(SystemExit):
        signalled.stop_all()
    assert deleted[1:] == [("delete", "table", "inet", "start")]
