#!/usr/bin/env python3
"""What an `alloy` run selects on a host, read off the committed Ansible tree.

`reaches HOST` exits 0 when a play of `site.yml` that reaches HOST runs an `alloy`-tagged task, 1 when none does, and
2 when the tree cannot be read. The tags are read the way Ansible selects by them: a block, an `import_role` or an
`import_tasks` hands its tags and `when` to every task inside, a role entry's tags reach every task of its role, and
an `include_role` or `include_tasks` is one task, the tasks it brings in at run time unread.
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

import yaml

ANSIBLE_DIR = Path(__file__).resolve().parents[1] / "ansible"
ROLES_DIR = ANSIBLE_DIR / "roles"
TAG = "alloy"
IMPORT_ROLE = ("ansible.builtin.import_role", "ansible.legacy.import_role", "import_role")
IMPORT_TASKS = ("ansible.builtin.import_tasks", "ansible.legacy.import_tasks", "import_tasks")

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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="alloy-version.py", description=__doc__.split("\n\n")[0])
    commands = parser.add_subparsers(dest="command", required=True)
    reach = commands.add_parser("reaches", help="does a play that reaches HOST run an alloy-tagged task")
    reach.add_argument(
        "--ansible-dir", type=Path, default=ANSIBLE_DIR, metavar="DIR", help="the Ansible tree (default: this checkout's)"
    )
    reach.add_argument("host", metavar="HOST")
    args = parser.parse_args(argv)
    # Every failure exits 2: uncaught, it would exit 1, the answer that the host is not reached.
    try:
        hit = reaches(args.host, ansible_dir=args.ansible_dir)
    except Exception as exc:
        print(f"reaches: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    if not hit:
        print(f"no play that reaches {args.host} runs an alloy-tagged task", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
