"""`infra/scripts/cache-proxy-harness.py`'s render, fetch and the run's refusals and teardown. No case reaches the
registry: every `fetch` passes `get=`; none enters a namespace or starts HAProxy."""

import contextlib
import difflib
import hashlib
import importlib.util
import io
import json
import os
import re
import signal
import stat
import subprocess
import sys
import tarfile
import threading
import time
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


def _seconds(value: str) -> float:
    return float(value[:-2]) / 1000 if value.endswith("ms") else float(value.removesuffix("s"))


def test_the_harness_timers_are_the_rendered_templates():
    text = harness.render(TEMPLATE.read_text())

    def keywords(line_pattern: str) -> dict[str, str]:
        words = re.search(line_pattern, text, re.M)[0].split()
        return dict(zip(words, words[1:]))

    defaults = keywords(r"^    timeout check \S+$") | keywords(r"^    timeout connect \S+$")
    vote = keywords(r"^    server via-node1 .*$")
    route = keywords(r"^    server valkey .*$")
    inter, fastinter, downinter = (_seconds(vote[word]) for word in ("inter", "fastinter", "downinter"))
    check = _seconds(defaults["check"])
    budget = max(min(_seconds(defaults["connect"]), inter), check)
    fall, rise = int(vote["fall"]), int(vote["rise"])
    assert (harness.INTER, harness.FASTINTER, harness.TIMEOUT_CHECK) == (inter, fastinter, check)
    assert harness.ROUTE_FALL == _seconds(route["inter"]) * int(route["fall"])
    assert harness.ROUTE_RISE == _seconds(route["inter"]) * int(route["rise"])
    assert harness.SWITCHED_VOTE_RISE == check + downinter + (rise - 1) * fastinter
    assert harness.VOTE_FALL == inter + fall * budget + (fall - 1) * fastinter


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


def test_a_whiteout_removes_a_lower_layers_entry_and_never_its_own_layers(tmp_path):
    digest, get, _ = _registry(
        _layer({"etc/gone": b"g"}), _layer({"etc/": None, "etc/keep": b"k", "etc/.wh.keep": b"", "etc/.wh.gone": b""})
    )
    tree = tmp_path / "tree"
    harness.fetch(digest, tree, get=get)
    assert os.listdir(tree / "etc") == ["keep"]
    assert (tree / "etc/keep").read_bytes() == b"k"


def test_a_later_layer_writes_into_a_directory_a_lower_layer_left_without_owner_write(tmp_path):
    digest, get, _ = _registry(
        _layer({"ro": 0o555, "ro/gone": b"g", "ro/sub": 0o555, "ro/sub/old": b"o", "wide": 0o555}),
        _layer({"ro/f": b"x", "ro/.wh.gone": b"", "ro/sub/.wh..wh..opq": b"", "wide": 0o700}),
    )
    tree = tmp_path / "tree"
    try:
        harness.fetch(digest, tree, get=get)
        assert (tree / "ro/f").read_bytes() == b"x"
        assert sorted(os.listdir(tree / "ro")) == ["f", "sub"]
        assert os.listdir(tree / "ro/sub") == []
        modes = [stat.S_IMODE((tree / name).stat().st_mode) for name in ("ro", "ro/sub", "wide")]
        assert modes == [0o555, 0o555, 0o700]
    finally:
        for name in ("ro", "ro/sub"):
            if (tree / name).is_dir(follow_symlinks=False):
                (tree / name).chmod(stat.S_IMODE((tree / name).stat().st_mode) | stat.S_IWUSR)


def test_a_directory_a_later_layer_removes_keeps_no_mode_of_the_lower_one(tmp_path):
    digest, get, _ = _registry(_layer({"ro": 0o555, "ro/a": b"a"}), _layer({".wh.ro": b"", "ro/b": b"b"}))
    tree = tmp_path / "tree"
    try:
        harness.fetch(digest, tree, get=get)
        assert os.listdir(tree / "ro") == ["b"]
        assert stat.S_IMODE((tree / "ro").stat().st_mode) != 0o555
    finally:
        if (tree / "ro").is_dir(follow_symlinks=False):
            (tree / "ro").chmod(stat.S_IMODE((tree / "ro").stat().st_mode) | stat.S_IWUSR)


def test_a_directory_a_later_layer_recreates_under_a_removed_one_keeps_no_mode_of_the_lower_one(tmp_path):
    digest, get, _ = _registry(
        _layer({"ro": 0o555, "ro/sub": 0o555, "ro/sub/old": b"o"}), _layer({".wh.ro": b"", "ro/sub/f": b"f"})
    )
    tree = tmp_path / "tree"
    try:
        harness.fetch(digest, tree, get=get)
        assert os.listdir(tree / "ro/sub") == ["f"]
        assert stat.S_IMODE((tree / "ro/sub").stat().st_mode) != 0o555
    finally:
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


def test_a_recorded_mode_under_a_link_out_of_the_tree_is_never_set(tmp_path):
    outside = tmp_path / "outside"
    (outside / "sub").mkdir(parents=True)
    (outside / "sub").chmod(0o755)
    tree = tmp_path / "tree"
    (tree / "own").mkdir(parents=True)
    (tree / "link").symlink_to(outside)
    harness._set_modes({tree / "link/sub": 0o700, tree / "own": 0o700})
    assert stat.S_IMODE((outside / "sub").stat().st_mode) == 0o755
    assert stat.S_IMODE((tree / "own").stat().st_mode) == 0o700


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
    second = signalled.start([sys.executable, "-c", "import time; time.sleep(30)", str(tmp_path)])
    signalled.processes.append(_Stuck())
    signalled.processes[1].wait = lambda timeout=None: sys.exit(143)
    # Stopped first, a process that will not stop fails before the signal lands; the signal must still unwind.
    signalled.processes.append(_Stuck())
    signalled.table_made = True
    try:
        with pytest.raises(SystemExit):
            signalled.stop_all()
        assert second.poll() is not None
        assert deleted[1:] == [("delete", "table", "inet", "start")]
    finally:
        if second.poll() is None:
            second.kill()
            second.wait()


@pytest.mark.parametrize("failure", [RuntimeError("nft delete table inet start exited 1"), subprocess.TimeoutExpired(["nft"], 1.0)])
def test_a_signal_during_a_stop_still_unwinds_when_the_table_will_not_delete(monkeypatch, failure):
    deleted = []

    def refuse(*args):
        deleted.append(args)
        raise failure

    monkeypatch.setattr(harness, "_nft", refuse)
    procs = harness.Procs("start")
    procs.processes.append(_Stuck())
    procs.processes[0].wait = lambda timeout=None: sys.exit(143)
    procs.table_made = True
    with pytest.raises(SystemExit):
        procs.stop_all()
    assert deleted == [("delete", "table", "inet", "start")]


def test_a_read_inside_a_window_ends_at_the_windows_end(monkeypatch):
    asked = []

    def urlopen(url, timeout):
        asked.append(timeout)
        return io.BytesIO(b"")

    monkeypatch.setattr(harness.urllib.request, "urlopen", urlopen)
    harness._scrape()
    harness._scrape(time.monotonic() + 0.25)
    assert asked[0] == harness.MARGIN and 0 < asked[1] <= 0.25, asked


def test_a_terminated_run_still_stops_what_its_case_started(tmp_path):
    script = f"""
import importlib.util, sys, time
spec = importlib.util.spec_from_file_location("harness", {str(REPO / "infra/scripts/cache-proxy-harness.py")!r})
harness = importlib.util.module_from_spec(spec)
spec.loader.exec_module(harness)
harness.unwind_on_signals()

def body(procs):
    print(procs.start([sys.executable, "-c", "import time; time.sleep(30)", {str(tmp_path)!r}]).pid, flush=True)
    time.sleep(30)

harness.run_case("start", body)
"""
    runner = subprocess.Popen([sys.executable, "-c", script], stdout=subprocess.PIPE, text=True)
    child = int(runner.stdout.readline())
    try:
        runner.terminate()
        runner.wait(timeout=5)
        with pytest.raises(ProcessLookupError):
            os.kill(child, 0)
    finally:
        runner.stdout.close()
        with contextlib.suppress(ProcessLookupError):
            os.kill(child, signal.SIGKILL)


def test_the_run_command_unwinds_on_sigterm_and_sighup(monkeypatch):
    signals = (signal.SIGTERM, signal.SIGHUP)
    seen = {}
    monkeypatch.setattr(harness, "run", lambda *args: seen.update({s: signal.getsignal(s) for s in signals}) or 0)
    before = {s: signal.getsignal(s) for s in signals}
    try:
        assert harness.main(["run", "--rootfs", "tree", "--scratch", "scratch"]) == 0
    finally:
        for signum, handler in before.items():
            signal.signal(signum, handler)
    assert list(seen.values()) == [harness._exit_on_signal] * 2


def test_the_run_refuses_when_no_unprivileged_namespace_can_be_made(monkeypatch, tmp_path):
    (tmp_path / harness.IMAGE_DIGEST_FILE).write_text("sha256:" + "0" * 64 + "\n")

    asked = []

    def unshare(argv, **kwargs):
        asked.append(argv)
        return subprocess.CompletedProcess(argv, 1, "", "unshare: unshare failed: Operation not permitted\n")

    def execv(*args):
        raise AssertionError(f"re-ran under unshare: {args}")

    monkeypatch.setattr(harness.os, "access", lambda path, mode: True)
    monkeypatch.setattr(harness.subprocess, "run", unshare)
    monkeypatch.setattr(harness.os, "execv", execv)
    assert harness.run(tmp_path, tmp_path / "scratch", ["parse"]) == 2
    # The probe carries the scratch, so a read by command line finds it.
    assert [str((tmp_path / "scratch").resolve()) in argv for argv in asked] == [True]


def test_a_run_that_breaks_outside_its_cases_still_prints_its_summary(monkeypatch, tmp_path, capsys):
    (tmp_path / harness.IMAGE_DIGEST_FILE).write_text("sha256:" + "0" * 64 + "\n")
    first = f"HAProxy version {harness.PINNED_VERSION}-1a2b3c4 2026/10/01 - https://haproxy.org/"

    def broken(run, rootfs):
        raise RuntimeError("the worker's maps vanished")

    monkeypatch.setattr(harness.socket, "if_nameindex", lambda: [(1, "lo")])
    monkeypatch.setattr(harness.subprocess, "run", lambda argv, **kwargs: subprocess.CompletedProcess(argv, 0, first + "\n", ""))
    monkeypatch.setattr(harness, "haproxy_argv", lambda root: ["haproxy"])
    monkeypatch.setattr(harness, "_mapping_read", broken)
    assert harness.run_inside(tmp_path, tmp_path / "scratch", list(harness.CASES)) == 1
    printed = capsys.readouterr()
    assert printed.out.splitlines()[-1] == f"0 passed, 0 failed -- {first} -- image {'0' * 12}"
    assert "the worker's maps vanished" in printed.err


def test_a_refuse_is_acknowledged_only_once_the_listener_closed():
    named, held = ["node2"], [(0.0, 0.0, 0.0)]
    closed, still_open = (threading.Event(), threading.Event()), (threading.Event(), threading.Event())
    closed[1].set()
    assert harness.peer_command("refuse\n", named, held, *closed) == "ok"
    assert harness.peer_command("refuse\n", named, held, *still_open) != "ok"
    assert harness.peer_command("name node1\n", named, held, *still_open) == "ok" and named == ["node1"]


def test_a_held_window_runs_its_length_and_starts_no_read_in_its_last_step():
    end = time.monotonic() + 0.3
    reads = list(harness._window(end))
    assert time.monotonic() >= end
    assert reads and all(end - read >= harness.STEP for read in reads), [end - read for read in reads]


def test_the_mapping_read_refuses_a_master_whose_maps_it_cannot_read(tmp_path):
    for pid, children in {20: "21 22 ", 21: "", 22: ""}.items():
        (tmp_path / f"{pid}/task/{pid}").mkdir(parents=True)
        (tmp_path / f"{pid}/task/{pid}/children").write_text(children)
    (tmp_path / "21/maps").write_text("7f00-7f10 r-xp 00000000 fd:01 12 /usr/lib/libnss_files.so.2\n")
    with pytest.raises(harness.Refused, match="PID 20"):
        harness.foreign_code(20, "/x/root", proc=tmp_path)
    # A master that exited after listening is an unreaped zombie, whose maps read empty without an error.
    (tmp_path / "20/maps").write_text("")
    with pytest.raises(harness.Refused, match="PID 20"):
        harness.foreign_code(20, "/x/root", proc=tmp_path)
    (tmp_path / "20/maps").write_text("55d0-55e0 r-xp 00000000 fd:01 11 /x/root/usr/local/sbin/haproxy\n")
    assert harness.foreign_code(20, "/x/root", proc=tmp_path) == ["/usr/lib/libnss_files.so.2"]


def test_a_mapping_read_refused_exits_2(monkeypatch, tmp_path):
    (tmp_path / harness.IMAGE_DIGEST_FILE).write_text("sha256:" + "0" * 64 + "\n")
    first = f"HAProxy version {harness.PINNED_VERSION} 2026/10/01 - https://haproxy.org/"

    def unread(run, rootfs):
        raise harness.Refused("the maps of the once-per-run HAProxy's master, PID 20, could not be read")

    monkeypatch.setattr(harness.socket, "if_nameindex", lambda: [(1, "lo")])
    monkeypatch.setattr(harness.subprocess, "run", lambda argv, **kwargs: subprocess.CompletedProcess(argv, 0, first + "\n", ""))
    monkeypatch.setattr(harness, "haproxy_argv", lambda root: ["haproxy"])
    monkeypatch.setattr(harness, "_mapping_read", unread)
    assert harness.run_inside(tmp_path, tmp_path / "scratch", list(harness.CASES)) == 2


def test_a_run_whose_mapping_read_did_not_happen_fails_even_on_parse(monkeypatch, tmp_path, capsys):
    (tmp_path / harness.IMAGE_DIGEST_FILE).write_text("sha256:" + "0" * 64 + "\n")
    first = f"HAProxy version {harness.PINNED_VERSION} 2026/10/01 - https://haproxy.org/"

    class Master:
        pid = 20

        def poll(self):
            return None

    def run(argv, stdout=None, **kwargs):
        if "-c" in argv:
            stdout.write(b"Configuration file is valid\n")
        return subprocess.CompletedProcess(argv, 0, first + "\n", "")

    monkeypatch.setattr(harness.socket, "if_nameindex", lambda: [(1, "lo")])
    monkeypatch.setattr(harness.subprocess, "run", run)
    monkeypatch.setattr(harness, "haproxy_argv", lambda root: ["haproxy"])
    monkeypatch.setattr(harness, "_start_haproxy", lambda procs, directory, haproxy: (Master(), 0.0))
    monkeypatch.setattr(harness, "foreign_code", lambda pid, root: [])
    monkeypatch.setattr(harness, "_listening", lambda process, deadline: True)
    assert harness.run_inside(tmp_path, tmp_path / "listened", ["parse"]) == 0
    capsys.readouterr()
    monkeypatch.setattr(harness, "_listening", lambda process, deadline: False)
    assert harness.run_inside(tmp_path, tmp_path / "unheard", ["parse"]) == 1
    printed = capsys.readouterr().out.splitlines()
    assert [line for line in printed if line.startswith("FAIL ")] == [
        f"FAIL maps: the once-per-run HAProxy did not listen within {harness.START:.2f} s, so no mapping read happened"
    ], printed


def test_a_mapping_read_refuses_a_master_that_exits_before_its_workers_are_read(monkeypatch, tmp_path):
    class Master:
        pid = 20

        def __init__(self, exit_code):
            self.exit_code = exit_code

        def poll(self):
            return self.exit_code

    masters = []
    monkeypatch.setattr(harness, "_start_haproxy", lambda procs, directory, haproxy: (masters[-1], 0.0))
    monkeypatch.setattr(harness, "_listening", lambda process, deadline: True)
    # An exited master's `children` reads empty without an error, so the walk finds no worker and reads nothing foreign.
    monkeypatch.setattr(harness, "foreign_code", lambda pid, root: [])
    (tmp_path / "live").mkdir()
    (tmp_path / "exited").mkdir()
    masters.append(Master(None))
    assert harness._mapping_read(harness.Run(tmp_path / "live", ["haproxy"], "global\n"), tmp_path) == []
    masters.append(Master(0))
    with pytest.raises(harness.Refused, match="PID 20"):
        harness._mapping_read(harness.Run(tmp_path / "exited", ["haproxy"], "global\n"), tmp_path)
