from __future__ import annotations

import re
from pathlib import Path

import yaml
from ansible.parsing.dataloader import DataLoader
from ansible.template import Templar, trust_as_template

from tests.test_infra_converge_guards import assert_that, truthy


def variables(role_dir: Path, secrets: dict, exclude=(), **extra) -> dict:
    # A default that templates another variable is trusted, so it resolves the way the play resolves it.
    defaults = yaml.safe_load((role_dir / "defaults/main.yml").read_text())
    trusted = {k: trust_as_template(v) if isinstance(v, str) and "{{" in v else v for k, v in defaults.items() if k not in exclude}
    return {**trusted, **secrets, **extra}


def render(role_dir: Path, name: str, secrets: dict, exclude=(), **extra) -> str:
    text = (role_dir / "templates" / name).read_text()
    return Templar(loader=DataLoader(), variables=variables(role_dir, secrets, exclude, **extra)).template(trust_as_template(text))


def blocks(lines: list[str]) -> list[tuple[str, list]]:
    """A Caddyfile body as (line, children) pairs: a line ending in `{` opens a block its `}` closes."""
    out: list[tuple[str, list]] = []
    stack = [out]
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line == "}":
            stack.pop()
        elif line.endswith("{"):
            children: list = []
            stack[-1].append((line[:-1].strip(), children))
            stack.append(children)
        else:
            stack[-1].append((line, []))
    assert len(stack) == 1, "unbalanced braces"
    return out


def site(caddyfile: dict[str, list], hostname: str) -> dict[str, list]:
    assert set(caddyfile) == {"", hostname}, f"one global block and one site: {sorted(caddyfile)}"
    body = caddyfile[hostname]
    lines = [line for line, _ in body]
    assert len(lines) == len(set(lines)), "a repeated line: Caddy routes a handle by the first, this dict by the last"
    return dict(body)


def users(handle: list) -> list[str]:
    (auth,) = [children for line, children in handle if line == "basic_auth"]
    for _user, children in auth:
        assert children == []
    pairs = [line.split() for line, _ in auth]
    for user, hashed in pairs:
        assert re.fullmatch(r"\$2[aby]\$\d\d\$[./A-Za-z0-9]{53}", hashed), f"{user} carries something that is not a bcrypt hash"
    return [user for user, _ in pairs]


def upstream(handle: list) -> str:
    (proxy,) = [line for line, _ in handle if line.startswith("reverse_proxy ")]
    return proxy.split()[1]


def assert_preflight(task: dict, secrets: dict, override: dict, refused: str | None, include_vars: dict | None = None) -> None:
    """`include_vars` are the including role's own variables, which the message names by design: the message must
    render the same over them and the fault list alone, and the no-value check reads `secrets` and `override` alone,
    skipping an empty value, which is a substring of every message."""
    ((name, expression),) = task["vars"].items()
    scope = {k: v for k, v in {**(include_vars or {}), **secrets, **override}.items() if v is not None}
    faults = Templar(loader=DataLoader(), variables=scope).template(trust_as_template(expression))
    assert faults == ([refused] if refused else [])
    scope[name] = faults
    assert truthy(assert_that(task), scope) is (refused is None)
    message = trust_as_template(task["ansible.builtin.assert"]["fail_msg"])
    rendered = Templar(loader=DataLoader(), variables=scope).template(message)
    alone = {k: v for k, v in (include_vars or {}).items() if v is not None} | {name: faults}
    assert rendered == Templar(loader=DataLoader(), variables=alone).template(message), "the refusal depends on a secret"
    values = [str(value) for value in (*secrets.values(), *override.values()) if value is not None]
    assert all(value not in rendered for value in values if value), "the refusal printed a value"
    assert (refused or "") in rendered
