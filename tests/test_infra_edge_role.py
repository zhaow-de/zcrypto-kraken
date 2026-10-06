from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

from tests import role_render
from tests.test_infra_converge_guards import find_task, iter_tasks, load_tasks, set_facts, when_conditions

REPO = Path(__file__).resolve().parents[1]
ANSIBLE = REPO / "infra/ansible"
ROLE = ANSIBLE / "roles/edge"
TASKS = ROLE / "tasks/main.yml"
HANDLERS = ROLE / "handlers/main.yml"
HOSTNAME = "edge.example.test"
HASH_A = "$2b$10$" + "a" * 53
HASH_B = "$2b$10$" + "b" * 53
REQUIRED = {"edge_role_name": "probe", "edge_hostname": HOSTNAME, "edge_acme_email": "ops@example.test", "edge_upstream_port": 8000}
TWO_USERS = {"path": "/push", "port": 9000, "users": [{"name": "alice", "hash": HASH_A}, {"name": "bob", "hash": HASH_B}]}
ONE_USER = {"path": "/write", "port": 9001, "users": [{"name": "alice", "hash": HASH_A}]}
HEAD_MATCHER = "@a_page_link_pre_resolved_without_a_login"


def _render(**extra) -> str:
    return role_render.render(ROLE, "Caddyfile.j2", {}, **(REQUIRED | extra))


def _caddyfile(**extra) -> dict[str, list]:
    return dict(role_render.blocks(_render(**extra).splitlines()))


def _site(**extra) -> dict[str, list]:
    return role_render.site(_caddyfile(**extra), HOSTNAME)


def _routing(site: dict[str, list]) -> list[str]:
    return [line for line in site if line.startswith(("handle", "@"))]


# --- the Caddyfile: each parameter's render -----------------------------------------------------------------------
def test_no_routes_renders_the_one_handle_to_the_upstream_with_no_credential_added():
    site = _site()
    assert _routing(site) == ["handle"]
    assert site["handle"] == [("reverse_proxy 127.0.0.1:8000", [])]


def test_the_edge_listens_on_443_alone_and_takes_its_certificate_there():
    assert _caddyfile()[""] == [("email ops@example.test", []), ("auto_https disable_redirects", [])]
    assert _site()["tls"] == [("issuer acme", [("disable_http_challenge", [])])]
    assert not re.search(r"(?m)^\s*(http://|:80\b)", _render())


def test_a_route_renders_its_users_hashes_and_its_upstream():
    site = _site(edge_basic_auth_routes=[TWO_USERS, ONE_USER])
    assert _routing(site) == ["handle /push", "handle /write", "handle"]
    push, write = site["handle /push"], site["handle /write"]
    assert role_render.users(push) == ["alice", "bob"] and role_render.users(write) == ["alice"]
    assert dict(push)["basic_auth"] == [(f"alice {HASH_A}", []), (f"bob {HASH_B}", [])]
    assert (role_render.upstream(push), role_render.upstream(write)) == ("127.0.0.1:9000", "127.0.0.1:9001")
    assert site["handle"] == [("reverse_proxy 127.0.0.1:8000", [])]


def test_an_empty_404_set_renders_no_matcher_and_a_set_renders_one_answering_404():
    assert _routing(_site(edge_paths_404=[])) == ["handle"]
    site = _site(edge_paths_404=["/metrics", "/swagger*"])
    assert _routing(site) == ["@served_without_a_login path /metrics /swagger*", "handle @served_without_a_login", "handle"]
    assert site["handle @served_without_a_login"] == [("respond 404", [])]


def test_the_head_matcher_renders_only_with_paths_and_carries_the_cookie_name():
    assert _routing(_site(edge_session_cookie="sid")) == ["handle"]
    site = _site(edge_head_paths=["/d/*", "/alerting/*"], edge_session_cookie="sid")
    assert _routing(site) == [HEAD_MATCHER, f"handle {HEAD_MATCHER}", "handle"]
    assert site[HEAD_MATCHER] == [("method HEAD", []), ("path /d/* /alerting/*", []), ("not header_regexp Cookie sid=", [])]
    assert site[f"handle {HEAD_MATCHER}"] == [("respond 200", [])]


def test_every_parameter_set_routes_the_authenticated_paths_first_and_the_upstream_last():
    site = _site(
        edge_basic_auth_routes=[ONE_USER], edge_paths_404=["/metrics"], edge_head_paths=["/d/*"], edge_session_cookie="sid"
    )
    assert _routing(site) == [
        "handle /write",
        "@served_without_a_login path /metrics",
        "handle @served_without_a_login",
        HEAD_MATCHER,
        f"handle {HEAD_MATCHER}",
        "handle",
    ]


# --- packages: Caddy from the cloudsmith repository, followed from apt --------------------------------------------
def test_caddy_comes_from_the_cloudsmith_repository_and_is_never_forced_held_or_pinned_to_a_version():
    tasks = iter_tasks(load_tasks(TASKS))
    (repository,) = [task["ansible.builtin.deb822_repository"] for task, _ in tasks if "ansible.builtin.deb822_repository" in task]
    assert repository == {
        "name": "caddy",
        "types": ["deb"],
        "uris": "https://dl.cloudsmith.io/public/caddy/stable/deb/debian",
        "suites": ["any-version"],
        "components": ["main"],
        "signed_by": "https://dl.cloudsmith.io/public/caddy/stable/gpg.key",
        "install_python_debian": True,
    }
    (install,) = [task["ansible.builtin.apt"] for task, _ in tasks if "ansible.builtin.apt" in task]
    assert install == {"name": "caddy", "state": "present", "update_cache": True}, "the repository task refreshes no cache"
    assert "ansible.builtin.dpkg_selections" not in {key for task, _ in tasks for key in task}, "a hold skips caddy silently"


# --- the preview on a node that has nothing yet -------------------------------------------------------------------
_CHANGED, _UNCHANGED, _SKIPPED = {"changed": True}, {"changed": False}, {"changed": False, "skipped": True}


# Each disjunct of the two facts has a case in which it alone is true.
@pytest.mark.parametrize(
    ("check", "repository", "install", "expected"),
    [
        (True, _CHANGED, _SKIPPED, (True, True)),  # a fresh node's preview
        (True, _UNCHANGED, _CHANGED, (False, True)),  # caddy alone still to install
        (True, _UNCHANGED, _UNCHANGED, (False, False)),  # an established node's preview
        (False, _CHANGED, _CHANGED, (False, False)),  # the real first converge
    ],
)
def test_the_two_preview_facts_are_true_only_where_a_preview_has_no_package_to_find(check, repository, install, expected):
    tasks = load_tasks(TASKS)
    variables = {"ansible_check_mode": check, "edge_caddy_repo": repository}
    first = set_facts(find_task(tasks, "note a preview that runs before the Caddy repository exists"), variables)
    variables |= first | {"edge_caddy_install": install}
    second = set_facts(find_task(tasks, "note a preview that runs before caddy is installed"), variables)
    assert (bool(first["edge_repo_previewed"]), bool(second["edge_units_previewed"])) == expected


def test_what_needs_the_repository_or_the_unit_skips_the_preview_that_has_neither():
    tasks = load_tasks(TASKS)
    install = find_task(tasks, "caddy present — version FOLLOWED from apt, never forced or held")
    assert when_conditions(install) == ["not edge_repo_previewed"]
    units = [(task["name"], gates) for task, gates in iter_tasks(tasks) if "ansible.builtin.systemd_service" in task]
    assert units == [("caddy enabled + started", ("not edge_units_previewed",))], units
    assert find_task(tasks, "Caddyfile — the one public listener's routes")["notify"] == "reload caddy"
    (handler,) = yaml.safe_load(HANDLERS.read_text())
    assert (handler["name"], handler["ansible.builtin.systemd_service"]) == ("reload caddy", {"name": "caddy", "state": "reloaded"})
    assert when_conditions(handler) == ["not edge_units_previewed"]


# --- the role is reached by an include alone ----------------------------------------------------------------------
def test_no_play_lists_the_role_since_a_role_both_listed_and_included_runs_twice_the_first_time_on_its_defaults():
    plays = load_tasks(ANSIBLE / "site.yml")
    listed = [role if isinstance(role, str) else role["role"] for play in plays for role in play.get("roles", [])]
    assert listed and "edge" not in listed, listed
