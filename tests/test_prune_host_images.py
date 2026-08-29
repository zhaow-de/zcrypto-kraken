"""TDD for `infra/scripts/prune-host-images.py` — the image prune the pins-update step runs.

Nothing in the fleet removed Docker images until this script existed: on 2026-08-23 zcrypto-red
held 13 images (35.73 GB, 88% reclaimable) on a 49 GB disk against 7.2 GB of actual capture data,
at <10% free. The capture daemon stops appending below `DEFAULT_MIN_FREE_BYTES` (1 GiB), and L2
capture is unbackfillable, so that was one image pull from permanent data loss.

Every test here constructs the defect it names rather than asserting the happy path, and none of
them touches a host: all host I/O sits behind `Docker`, and the planner is pure.

THE load-bearing case is `test_capture_and_engine_diverged_on_zcrypto_keep_four_capture_digests`:
capture and the engine are independent rows on the SAME host sharing ONE image repo, so mid-rollout
that repo legitimately needs four resident digests. The real pins file cannot exercise it (both rows
currently carry the same digest), hence the synthetic fixture.

The mirror of that case is the SILENT UNDER-KEEP: any shape that drops a row drops that row's
rollback operand, which no container holds, so nothing else in the design covers it. Those tests
live under "the catastrophic direction".
"""

import ast
import importlib.util
import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "infra/scripts/prune-host-images.py"


def _load():
    # Standalone script (stdlib only, so it runs anywhere), loaded by path. Registered in
    # sys.modules before exec so dataclasses can resolve annotations against it.
    spec = importlib.util.spec_from_file_location("prune_host_images_under_test", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


pm = _load()

CAPTURE_REPO = "ghcr.io/zhaow-de/zcrypto-capture"
ALLOY_REPO = "grafana/alloy"
FOREIGN_REPO = "synology/surveillance"

CAP_CUR = "a1a1a1a1a1a1"
CAP_OP = "b2b2b2b2b2b2"
ENG_CUR = "c3c3c3c3c3c3"
ENG_OP = "d4d4d4d4d4d4"
ALLOY_CUR = "e5e5e5e5e5e5"
ALLOY_OP = "f6f6f6f6f6f6"
STALE = "999999999999"

HEADER = (
    "| service | host | digest (sha256, first 12) | since (UTC) | rollback operand (verified resident at the re-pin) |\n"
    "| --- | --- | --- | --- | --- |"
)


def _pins(rows: str, *, heading: str = "## Current pins", header: str = HEADER, after: str = "") -> str:
    """A pins file shaped like the real one: prose, the table, then the next section."""
    return (
        f"# Fleet pins\n\nThe CURRENT pin and rollback operand for every service.\n\n"
        f"{heading}\n\n{header}\n{rows}\n{after}\n## Standing constraints\n\n- Prose.\n"
    )


DIVERGED_ROWS = "\n".join(
    [
        f"| capture | zcrypto | `{CAP_CUR}` — spec `00099`, revision `deadbeef` | 2026-08-23 09:25:29 | `{CAP_OP}` (2026-08-20) |",
        f"| engine | zcrypto | `{ENG_CUR}` — still **DISARMED** | 2026-08-23 10:21:03 | `{ENG_OP}` (2026-08-19) |",
        f"| alloy | zcrypto, zcrypto-red, zcrypto-ops, nas | `{ALLOY_CUR}` (v1.18.0) | 2026-07-27 | `{ALLOY_OP}` (v1.17.1) |",
    ]
)

ONE_ROW = f"| capture | zcrypto | `{CAP_CUR}` | 2026-08-23 | `{CAP_OP}` (2026-08-20) |"


def _full(short: str) -> str:
    return "sha256:" + short + "0" * (64 - len(short))


def _img(repo: str, short: str, size: str = "3.25GB") -> object:
    return pm.HostImage(repo=repo, digest=_full(short), image_id=short[:12], size=size)


def _container(name: str, repo: str, short: str) -> object:
    return pm.ContainerImage(container=name, ref=f"{repo}@{_full(short)}")


# --------------------------------------------------------------------------------------------
# The real file — the parser is proven against the live authority, not only synthetic fixtures.
# --------------------------------------------------------------------------------------------


def test_the_real_pins_file_parses_into_exactly_the_service_host_pairs_the_fleet_runs():
    """Pinned by exact pairs, not by a `>= 6` floor: a floor is satisfied by a row set that has
    silently LOST a row and gained two, which is the very failure the stray-row guard exists for."""
    rows = pm.parse_pins_table(pm.DEFAULT_PINS.read_text())

    assert {(row.service, row.hosts) for row in rows} == {
        ("capture", ("zcrypto",)),
        ("capture", ("zcrypto-red",)),
        ("engine", ("zcrypto",)),
        ("alloy", ("zcrypto", "zcrypto-red", "zcrypto-ops", "nas")),
        ("ops (timers + liquidations)", ("zcrypto-ops",)),
        ("archive-pull", ("nas",)),
    }
    assert {h for row in rows for h in row.hosts} == set(pm.HOSTS)
    for row in rows:
        assert len(row.current) == 12, row
        assert len(row.operand) == 12, row


def test_the_real_file_puts_capture_and_the_engine_on_one_host_sharing_one_repo():
    """The premise of the union requirement. If this ever stops holding, the four-digest case below
    is arguing about a shape the fleet no longer has."""
    rows = pm.parse_pins_table(pm.DEFAULT_PINS.read_text())

    assert {"capture", "engine", "alloy"} <= {row.service for row in rows if "zcrypto" in row.hosts}


@pytest.mark.parametrize("host", ["zcrypto", "zcrypto-red", "zcrypto-ops", "nas"])
def test_the_multi_host_alloy_row_contributes_to_every_host_it_names(host):
    """The host cell lists four hosts comma-separated. Read as one opaque string, Alloy's digests
    would be missing from every host's keep-set and the resident Alloy would be pruned."""
    rows = pm.parse_pins_table(pm.DEFAULT_PINS.read_text())
    (alloy,) = [row for row in rows if row.service == "alloy"]

    keep = pm.keep_for_host(rows, host)

    assert alloy.current in keep, host
    assert alloy.operand in keep, host


def test_the_real_zcrypto_keep_set_carries_every_row_that_names_the_host():
    rows = pm.parse_pins_table(pm.DEFAULT_PINS.read_text())
    expected = {d for row in rows if "zcrypto" in row.hosts for d in (row.current, row.operand)}

    assert set(pm.keep_for_host(rows, "zcrypto")) == expected


# --------------------------------------------------------------------------------------------
# The load-bearing edge case: two rows, one host, one repo, four live digests.
# --------------------------------------------------------------------------------------------


def test_capture_and_engine_diverged_on_zcrypto_keep_four_capture_digests():
    """Mid-rollout the engine still runs the previous digest while capture already carries the new
    one, and each row also names its own rollback operand — so ONE repo legitimately needs FOUR
    resident digests. Any per-repo "keep the last two" rule deletes a live rollback path."""
    rows = pm.parse_pins_table(_pins(DIVERGED_ROWS))

    keep = pm.keep_for_host(rows, "zcrypto")
    assert set(keep) == {CAP_CUR, CAP_OP, ENG_CUR, ENG_OP, ALLOY_CUR, ALLOY_OP}

    images = [_img(CAPTURE_REPO, d) for d in (CAP_CUR, CAP_OP, ENG_CUR, ENG_OP, STALE)]
    images += [_img(ALLOY_REPO, ALLOY_CUR), _img(ALLOY_REPO, ALLOY_OP)]
    containers = [
        _container("zcrypto-capture", CAPTURE_REPO, CAP_CUR),
        _container("zcrypto-engine", CAPTURE_REPO, ENG_CUR),
        _container("grafana-alloy", ALLOY_REPO, ALLOY_CUR),
    ]

    plan = pm.plan(host="zcrypto", rows=rows, images=images, containers=containers)

    assert [i.short for i in plan.remove] == [STALE]
    survivors = {i.short for i in images if i.repo == CAPTURE_REPO} - {i.short for i in plan.remove}
    assert survivors == {CAP_CUR, CAP_OP, ENG_CUR, ENG_OP}


def test_an_operand_named_only_in_another_hosts_row_is_not_kept_here():
    """The secondary's operand is resident on the primary too (both pulled it). Keeping the whole
    file's digests everywhere would make the prune a no-op on exactly the host that needs it."""
    red_only = "0f0f0f0f0f0f"
    rows = pm.parse_pins_table(
        _pins(
            "\n".join(
                [
                    ONE_ROW,
                    f"| capture | zcrypto-red | `{CAP_CUR}` | 2026-08-22 | `{red_only}` (2026-08-18) |",
                ]
            )
        )
    )

    keep = pm.keep_for_host(rows, "zcrypto")
    assert red_only not in keep

    images = [_img(CAPTURE_REPO, d) for d in (CAP_CUR, CAP_OP, red_only)]
    plan = pm.plan(host="zcrypto", rows=rows, images=images, containers=[_container("zcrypto-capture", CAPTURE_REPO, CAP_CUR)])

    assert [i.short for i in plan.remove] == [red_only]


# --------------------------------------------------------------------------------------------
# The host's own truth outranks the file: a resident container's image is never removed, and its
# absence from the file is the loud finding — the file is wrong, and a pin recorded only on a host
# is one prune from unrecoverable.
# --------------------------------------------------------------------------------------------


def test_a_container_digest_absent_from_the_pins_file_is_kept_and_flagged():
    unrecorded = "7e7e7e7e7e7e"
    rows = pm.parse_pins_table(_pins(ONE_ROW))
    images = [_img(CAPTURE_REPO, d) for d in (CAP_CUR, CAP_OP, unrecorded, STALE)]
    containers = [_container("zcrypto-capture", CAPTURE_REPO, unrecorded)]

    plan = pm.plan(host="zcrypto", rows=rows, images=images, containers=containers)

    assert unrecorded not in {i.short for i in plan.remove}
    assert [c.container for c in plan.unrecorded] == ["zcrypto-capture"]
    assert [i.short for i in plan.remove] == [STALE]


def test_a_container_pinned_by_tag_rather_than_digest_protects_its_whole_repo():
    """Its digest cannot be matched against the file at all, so nothing in that repo is safe to
    judge — protect it rather than guess."""
    rows = pm.parse_pins_table(_pins(ONE_ROW))
    images = [_img(CAPTURE_REPO, d) for d in (CAP_CUR, CAP_OP, STALE)]
    containers = [pm.ContainerImage(container="zcrypto-capture", ref=f"{CAPTURE_REPO}:latest")]

    plan = pm.plan(host="zcrypto", rows=rows, images=images, containers=containers)

    assert plan.remove == ()
    assert [c.container for c in plan.unresolved] == ["zcrypto-capture"]


def test_an_image_from_an_unmanaged_repo_is_never_in_the_removal_set():
    """The NAS runs vendor containers this file knows nothing about. The managed repos are DERIVED —
    a repo is managed only because the host holds an image the pins file names."""
    rows = pm.parse_pins_table(_pins(ONE_ROW))
    images = [_img(CAPTURE_REPO, CAP_CUR), _img(CAPTURE_REPO, CAP_OP), _img(CAPTURE_REPO, STALE)]
    images += [_img(FOREIGN_REPO, "1c1c1c1c1c1c"), _img(FOREIGN_REPO, "2c2c2c2c2c2c")]

    plan = pm.plan(host="zcrypto", rows=rows, images=images, containers=[])

    assert FOREIGN_REPO not in plan.managed_repos
    assert [i.short for i in plan.remove] == [STALE]


def test_an_image_carrying_no_repo_digest_is_never_removed_and_is_counted():
    """`docker image rm repo@sha256:` cannot even be spelled for it, and `<none>` is not a repo.
    Counted so `reclaimed:` never quietly hides deliberately-skipped space."""
    rows = pm.parse_pins_table(_pins(ONE_ROW))
    images = [
        _img(CAPTURE_REPO, CAP_CUR),
        _img(CAPTURE_REPO, CAP_OP),
        pm.HostImage(repo="<none>", digest="", image_id="0badf00d0bad", size="1.1GB"),
        pm.HostImage(repo=CAPTURE_REPO, digest="", image_id="0badf00d0bae", size="1.1GB"),
    ]

    plan = pm.plan(host="zcrypto", rows=rows, images=images, containers=[])

    assert plan.remove == ()
    assert "<none>" not in plan.managed_repos
    assert [i.image_id for i in plan.no_digest] == ["0badf00d0bae"]


def test_two_tags_of_one_digest_are_removed_once():
    """`docker image ls` lists a multi-tagged image once per tag; removing the same ref twice books
    a spurious FAILED and a non-zero exit on a completely healthy prune."""
    rows = pm.parse_pins_table(_pins(ONE_ROW))
    images = [_img(CAPTURE_REPO, CAP_CUR), _img(CAPTURE_REPO, CAP_OP), _img(CAPTURE_REPO, STALE), _img(CAPTURE_REPO, STALE)]

    plan = pm.plan(host="zcrypto", rows=rows, images=images, containers=[])

    assert [i.short for i in plan.remove] == [STALE]


# --------------------------------------------------------------------------------------------
# Pre-staged digests: resident, unrecorded, attached to no container — indistinguishable from
# stale, and `.claude/skills/zcrypto-rollout-image/SKILL.md`'s `Shared converge mechanics` MANDATES
# pre-staging before a converge.
# --------------------------------------------------------------------------------------------


def test_a_pre_staged_digest_is_removable_unless_named_by_keep():
    rows = pm.parse_pins_table(_pins(ONE_ROW))
    staged = "5a5a5a5a5a5a"
    images = [_img(CAPTURE_REPO, d) for d in (CAP_CUR, CAP_OP, staged)]
    containers = [_container("zcrypto-capture", CAPTURE_REPO, CAP_CUR)]

    exposed = pm.plan(host="zcrypto", rows=rows, images=images, containers=containers)
    assert [i.short for i in exposed.remove] == [staged]

    protected = pm.plan(host="zcrypto", rows=rows, images=images, containers=containers, extra_keep=(staged,))
    assert protected.remove == ()
    assert protected.extra_keep == frozenset({staged})


@pytest.mark.parametrize("bad", ["sha256:5a5a5a5a5a5a", "5a5a5a5a5a5", "5a5a5a5a5a5az", "", "5A5A5A5A5A5A"])
def test_keep_refuses_anything_that_is_not_a_bare_12_hex_digest(bad):
    """A typo'd --keep silently protects nothing — the operand it was meant to save is deleted."""
    rows = pm.parse_pins_table(_pins(ONE_ROW))

    with pytest.raises(pm.PruneError):
        pm.plan(host="zcrypto", rows=rows, images=[], containers=[], extra_keep=(bad,))


# --------------------------------------------------------------------------------------------
# The catastrophic direction: an under-populated keep-set removes an image the file means to
# protect. A dropped row takes its ROLLBACK OPERAND, which no container holds — so every
# unreadable-file shape must refuse loudly rather than compute a smaller answer.
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "break_line",
    [
        "",
        "<!-- the engine leg lands next -->",
        "  | engine | zcrypto | `c3c3c3c3c3c3` | x | `d4d4d4d4d4d4` |",
        "Prose between rows.",
    ],
    ids=["blank line", "html comment", "indented row", "prose"],
)
def test_a_row_stranded_below_a_break_in_the_table_refuses_instead_of_vanishing(break_line):
    """THE silent under-keep. The pins file is hand-edited at every converge and sits outside
    mdformat's reach, so a stray blank line between rows is a realistic edit — and it would drop
    the engine row's operand from the keep-set with the prune reporting a perfectly normal run."""
    text = _pins(f"{ONE_ROW}\n{break_line}\n| engine | zcrypto | `{ENG_CUR}` | 2026-08-23 | `{ENG_OP}` (2026-08-19) |")

    with pytest.raises(pm.PinsError):
        pm.parse_pins_table(text)


def test_prose_below_the_table_carrying_no_digest_row_is_not_mistaken_for_a_stranded_row():
    """The true-negative for that guard: the non-image package table lives under this very heading,
    separated by prose. An always-refusing guard would be as useless as none."""
    packages = "\nSome prose.\n\n| package | host | version |\n| --- | --- | --- |\n| agentboard | zcrypto-ops | `0.4.8` |\n"

    rows = pm.parse_pins_table(_pins(ONE_ROW, after=packages))

    assert [row.service for row in rows] == ["capture"]


def test_the_digest_must_be_the_cells_leading_token_not_merely_the_first_one_found():
    """ "Revisions are 8 hex, serials are 5" is a habit of the file, not an invariant of it. A cell
    whose leading token is a 12-hex REVISION would otherwise be kept as the pin, leaving the real
    pin removable — silently, with the run reporting normally."""
    text = _pins(f"| capture | zcrypto | revision `f54431a6c0de` — `{CAP_CUR}` | 2026-08-23 | `{CAP_OP}` |")

    with pytest.raises(pm.PinsError):
        pm.parse_pins_table(text)


def test_a_trailing_second_digest_in_the_cell_does_not_displace_the_leading_pin():
    rows = pm.parse_pins_table(_pins(f"| capture | zcrypto | `{CAP_CUR}` — supersedes `f54431a6c0de` | 2026-08-23 | `{CAP_OP}` |"))

    assert rows[0].current == CAP_CUR


@pytest.mark.parametrize("marker", ["—", "(none)", "first pin", "n/a"])
def test_a_row_declaring_no_rollback_path_parses_and_keeps_only_its_current(marker):
    """A first-ever pin of a new service has no operand. Refusing that row would disable this script
    FLEET-WIDE — including on the two capture hosts where it is the data-loss guard — and the only
    way to satisfy a stricter parser would be to invent an operand, i.e. write false data into the
    authority file."""
    rows = pm.parse_pins_table(_pins(f"| capture | zcrypto | `{CAP_CUR}` | 2026-08-23 | {marker} |"))

    assert rows[0].operand == ""
    assert set(pm.keep_for_host(rows, "zcrypto")) == {CAP_CUR}


@pytest.mark.parametrize(
    ("name", "text"),
    [
        ("no heading", _pins(ONE_ROW, heading="## Old pins")),
        ("heading but no table", "# Fleet pins\n\n## Current pins\n\nProse only, no table.\n\n## Standing constraints\n"),
        ("header and separator but no rows", "# Fleet pins\n\n## Current pins\n\n" + HEADER + "\n\n## Standing constraints\n"),
        ("digest cell carries no digest", _pins("| capture | zcrypto | pending | x | `b2b2b2b2b2b2` |")),
        ("operand is a typo, neither digest nor marker", _pins("| capture | zcrypto | `a1a1a1a1a1a1` | x | `b2b2b2b2b2b` |")),
        ("row has fewer cells than the header", _pins("| capture | zcrypto | `a1a1a1a1a1a1` | `b2b2b2b2b2b2` |")),
        ("host cell is empty", _pins("| capture |  | `a1a1a1a1a1a1` | x | `b2b2b2b2b2b2` |")),
        (
            "header names no digest column",
            _pins("| capture | zcrypto | x | y | z |", header="| service | host | a | b | c |\n| --- | --- | --- | --- | --- |"),
        ),
    ],
)
def test_an_unreadable_pins_table_refuses_loudly_instead_of_yielding_an_empty_keep_set(name, text):
    with pytest.raises(pm.PinsError):
        pm.parse_pins_table(text)


def test_a_host_no_row_names_refuses_rather_than_planning_against_an_empty_keep_set():
    rows = pm.parse_pins_table(_pins(ONE_ROW))

    with pytest.raises(pm.PinsError):
        pm.keep_for_host(rows, "zcrypto-red")


def test_the_script_never_reaches_for_a_blanket_prune():
    """`docker image prune -a` / `docker system prune` would take the recorded rollback operands —
    exactly the digests this script exists to protect. Removal is one explicit ref at a time.

    Two checks over the AST's non-docstring string constants, because either alone has a hole:
    exact membership misses a whole command spelled as ONE constant, and a bare substring sweep
    cannot tell an argv token from prose (`filesystem` contains `system`). Docstrings are excluded —
    the module's names the blanket forms in order to forbid them, which a raw grep cannot tell from
    a call site.
    """
    tree = ast.parse(SCRIPT.read_text())
    docstrings = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef)
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
        and isinstance(node.body[0].value.value, str)
    }
    constants = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings
    ]
    argv_tokens = {c for c in constants if c and not any(ch.isspace() for ch in c)}

    assert not [c for c in argv_tokens if "prune" in c or "system" in c], argv_tokens
    assert not [c for c in constants if any(p in c for p in ("image prune", "system prune", "prune -a", "prune --all"))]
    assert {"image", "rm"} <= argv_tokens  # the one removal form the script may spell


# --------------------------------------------------------------------------------------------
# `main` over a fake host seam: dry-run-by-default and the exact removal ref are the two
# properties the design turns on, and neither is visible from the planner alone.
# --------------------------------------------------------------------------------------------


class FakeDocker:
    """Stands in for `Docker`. Records every removal so the call SITE is asserted, not just the plan."""

    def __init__(self, images, containers, *, ok=True):
        self.host = "zcrypto"
        self.access = pm.HOSTS["zcrypto"]
        self._images = images
        self._containers = containers
        self._ok = ok
        self.removed: list[str] = []
        self.free_calls = 0

    def containers(self):
        return list(self._containers)

    def images(self):
        return list(self._images)

    def free_bytes(self):
        self.free_calls += 1
        return 10 * 1024**3 + self.free_calls * 1024**3

    def remove_image(self, ref):
        self.removed.append(ref)
        return self._ok, "" if self._ok else "image is referenced in multiple repositories"


def _main_fixture(tmp_path, *, containers, ok=True, rows=ONE_ROW):
    pins = tmp_path / "fleet-pins.md"
    pins.write_text(_pins(rows))
    images = [_img(CAPTURE_REPO, d) for d in (CAP_CUR, CAP_OP, STALE)]
    return pins, FakeDocker(images, containers, ok=ok)


def test_dry_run_is_the_default_and_removes_nothing(tmp_path, monkeypatch, capsys):
    """Even with a removable image AND an unrecorded pin present — the two conditions that make an
    apply-run act and exit non-zero."""
    pins, fake = _main_fixture(tmp_path, containers=[_container("zcrypto-capture", CAPTURE_REPO, "7e7e7e7e7e7e")])
    monkeypatch.setattr(pm, "Docker", lambda host: fake)

    code = pm.main(["zcrypto", "--pins", str(pins)])

    assert code == 0
    assert fake.removed == []
    assert "DRY RUN" in capsys.readouterr().out


def test_apply_removes_each_planned_image_by_its_full_64_hex_digest_ref(tmp_path, monkeypatch):
    """The ref the call site actually passes — a repo-plus-full-digest, never a tag, never a short
    id, never a bare repo (which would take every tag in it)."""
    pins, fake = _main_fixture(tmp_path, containers=[_container("zcrypto-capture", CAPTURE_REPO, CAP_CUR)])
    monkeypatch.setattr(pm, "Docker", lambda host: fake)

    code = pm.main(["zcrypto", "--apply", "--pins", str(pins)])

    assert code == 0
    assert fake.removed == [f"{CAPTURE_REPO}@{_full(STALE)}"]
    (ref,) = fake.removed
    assert re.fullmatch(rf"{re.escape(CAPTURE_REPO)}@sha256:[0-9a-f]{{64}}", ref), ref


def test_apply_exits_non_zero_on_an_unrecorded_pin(tmp_path, monkeypatch):
    """The condition means the pins file is WRONG, and the file's own warning is that a pin recorded
    only on a host is one prune from unrecoverable. A zero exit here would be read as all-clear."""
    pins, fake = _main_fixture(tmp_path, containers=[_container("zcrypto-capture", CAPTURE_REPO, "7e7e7e7e7e7e")])
    monkeypatch.setattr(pm, "Docker", lambda host: fake)

    assert pm.main(["zcrypto", "--apply", "--pins", str(pins)]) == 1


def test_apply_exits_non_zero_when_a_removal_fails(tmp_path, monkeypatch):
    pins, fake = _main_fixture(tmp_path, containers=[_container("zcrypto-capture", CAPTURE_REPO, CAP_CUR)], ok=False)
    monkeypatch.setattr(pm, "Docker", lambda host: fake)

    assert pm.main(["zcrypto", "--apply", "--pins", str(pins)]) == 1


def test_keep_reaches_the_planner_from_the_command_line(tmp_path, monkeypatch):
    pins, fake = _main_fixture(tmp_path, containers=[_container("zcrypto-capture", CAPTURE_REPO, CAP_CUR)])
    monkeypatch.setattr(pm, "Docker", lambda host: fake)

    code = pm.main(["zcrypto", "--apply", "--keep", STALE, "--pins", str(pins)])

    assert code == 0
    assert fake.removed == []


# --------------------------------------------------------------------------------------------
# The thin host seam: the argv it builds, and parsers for what docker and df actually print.
# --------------------------------------------------------------------------------------------


def test_the_container_listing_includes_stopped_containers():
    """A stopped container still holds its image against removal, so omitting it turns a correct
    docker refusal into a spurious FAILED line and a non-zero exit on a healthy prune."""
    calls = []
    docker = pm.Docker("zcrypto")

    def fake_docker(*argv, check=True):
        calls.append(argv)
        return 0, "zcrypto-capture\n" if argv[0] == "ps" else f"{CAPTURE_REPO}@{_full(CAP_CUR)}\n", ""

    docker._docker = fake_docker
    out = docker.containers()

    assert calls[0] == ("ps", "-a", "--format", "{{.Names}}")
    assert [c.container for c in out] == ["zcrypto-capture"]
    assert calls[1] == ("inspect", "--format", "{{.Config.Image}}", "zcrypto-capture")


def test_the_nas_docker_invocation_is_the_absolute_path_under_sudo():
    """A bare `docker` on the NAS is not on a non-interactive ssh PATH, so `docker ps` returns empty
    and reads as "no containers" rather than "command not found" — a keep-set missing every resident
    image."""
    assert pm.HOSTS["nas"].docker == ("sudo", "/usr/local/bin/docker")
    assert pm.HOSTS["zcrypto"].docker == ("docker",)


@pytest.mark.parametrize(
    ("ref", "expected"),
    [
        (f"{CAPTURE_REPO}@{_full(CAP_CUR)}", (CAPTURE_REPO, CAP_CUR)),
        (f"{ALLOY_REPO}@{_full(ALLOY_CUR)}", (ALLOY_REPO, ALLOY_CUR)),
        (f"{CAPTURE_REPO}:latest", (CAPTURE_REPO, "")),
        ("registry.example:5000/team/img:1.2.3", ("registry.example:5000/team/img", "")),
        ("busybox", ("busybox", "")),
    ],
)
def test_split_ref_separates_repo_from_digest(ref, expected):
    assert pm.split_ref(ref) == expected


def test_parse_image_ls_reads_the_tab_separated_form_and_treats_none_as_no_digest():
    out = f"{CAPTURE_REPO}\t{_full(CAP_CUR)}\tf00dcafe0001\t3.25GB\n<none>\t<none>\tf00dcafe0002\t1.1GB\n"

    images = pm.parse_image_ls(out)

    assert [i.repo for i in images] == [CAPTURE_REPO, "<none>"]
    assert images[0].short == CAP_CUR
    assert images[1].digest == ""
    assert images[0].ref == f"{CAPTURE_REPO}@{_full(CAP_CUR)}"


def test_parse_df_reads_the_available_column_in_bytes():
    out = "Filesystem     1024-blocks      Used Available Capacity Mounted on\n/dev/sda1         50268820  45312508   2296112      96% /\n"

    assert pm.parse_df_avail_bytes(out) == 2296112 * 1024


def test_parse_df_refuses_output_with_no_data_line():
    with pytest.raises(pm.PruneError):
        pm.parse_df_avail_bytes("Filesystem 1024-blocks Used Available Capacity Mounted on\n")
