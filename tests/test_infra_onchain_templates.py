"""The on-chain node's image and its ops wiring, read from the files themselves; no image is built here."""

import re
import shlex
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
NODE_DOCKERFILE = REPO / "infra/docker/bitcoind/Dockerfile"

NODE_TARBALL = "bitcoin-32.1-x86_64-linux-gnu.tar.gz"
NODE_SHA256 = "61545c17c3120fb7412f896d248b11993af04ec8817aad3649c55b2afb044963"


def _instructions(path: Path) -> list[tuple[str, str]]:
    """(keyword, arguments) per instruction, comment lines dropped and continuation lines joined."""
    kept = "\n".join(line for line in path.read_text(encoding="utf-8").splitlines() if not line.lstrip().startswith("#"))
    out = []
    for line in re.sub(r"\\\n", " ", kept).splitlines():
        keyword, _, arguments = line.strip().partition(" ")
        if keyword:
            out.append((keyword.upper(), arguments.strip()))
    return out


def test_the_node_image_checks_its_pinned_sha256_before_it_extracts():
    instructions = _instructions(NODE_DOCKERFILE)
    assert [a for k, a in instructions if k == "FROM"] == ["debian:bookworm-slim"]
    args = dict(a.partition("=")[::2] for k, a in instructions if k == "ARG")
    assert {NODE_TARBALL, NODE_SHA256} <= set(args.values()), args
    runs = [a for k, a in instructions if k == "RUN"]
    assert len(runs) == 1, runs
    # `/bin/sh -c` runs without `-e`: a `;` anywhere in the chain carries the build past a failed check.
    assert ";" not in runs[0], runs[0]
    expanded = re.sub(r"\$\{(\w+)\}", lambda m: args.get(m.group(1), m.group(0)), runs[0])
    steps = [shlex.split(step) for step in expanded.split("&&")]
    check = ["echo", f"{NODE_SHA256}  {NODE_TARBALL}", "|", "sha256sum", "-c", "-"]
    assert check in steps, steps
    extracts = [i for i, step in enumerate(steps) if step[0] == "tar" and NODE_TARBALL in step]
    assert extracts, steps
    assert steps.index(check) < min(extracts), steps
