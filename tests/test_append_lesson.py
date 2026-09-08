"""The lesson-append helper: it refuses before it writes, and it writes to the main checkout's inbox."""

import importlib.util
import json
import pathlib
import subprocess

import pytest

_ROOT = pathlib.Path(__file__).resolve().parents[1]
_SCRIPT = _ROOT / "infra" / "scripts" / "append-lesson.py"
_CHECKER = _ROOT / "infra" / "scripts" / "check-agent-lessons.py"


def _load(path: pathlib.Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    import sys

    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


al = _load(_SCRIPT, "append_lesson")
NOW = "2026-09-07T09:00:00Z"
OK = dict(session="zcrypto-bravo", branch="fix/x", kind="self-correction", what="a thing", why="a reason")


def _argv(**over) -> list[str]:
    fields = {**OK, **over}
    return [f"--{k}={v}" for k, v in fields.items()]


@pytest.fixture
def checkout(tmp_path: pathlib.Path) -> pathlib.Path:
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / ".local" / "agent-lessons").mkdir(parents=True)
    return tmp_path


def _inbox(checkout: pathlib.Path) -> pathlib.Path:
    return checkout / ".local" / "agent-lessons" / "zcrypto-bravo.jsonl"


class TestTheHappyPath:
    def test_a_valid_record_appends_and_revalidates(self, checkout: pathlib.Path) -> None:
        assert al.run(_argv(cites="a.md,b.py"), cwd=checkout, now=NOW) == 0
        written = [json.loads(line) for line in _inbox(checkout).read_text().splitlines()]
        assert written == [{"ts": NOW, "cites": ["a.md", "b.py"], **OK}]
        checker = _load(_CHECKER, "check_agent_lessons_revalidate")
        assert checker.check(str(_inbox(checkout))) == 0

    def test_a_second_append_adds_one_line(self, checkout: pathlib.Path) -> None:
        assert al.run(_argv(), cwd=checkout, now=NOW) == 0
        assert al.run(_argv(what="another"), cwd=checkout, now=NOW) == 0
        assert len(_inbox(checkout).read_text().splitlines()) == 2

    def test_no_cites_is_an_empty_list_not_an_empty_string(self, checkout: pathlib.Path) -> None:
        assert al.run(_argv(), cwd=checkout, now=NOW) == 0
        assert json.loads(_inbox(checkout).read_text())["cites"] == []

    def test_the_stamp_it_writes_itself_is_utc_and_zulu(self, checkout: pathlib.Path) -> None:
        assert al.run(_argv(), cwd=checkout) == 0
        import datetime as dt

        stamp = json.loads(_inbox(checkout).read_text())["ts"]
        assert stamp.endswith("Z")
        assert "." not in stamp  # whole seconds, the shape every existing inbox record uses
        assert dt.datetime.fromisoformat(stamp).tzinfo == dt.UTC


class TestARefusalWritesNothing:
    @pytest.mark.parametrize(
        "over, reason",
        [
            ({"kind": "invented"}, "kind"),
            ({"what": ""}, "what"),
            ({"why": "   "}, "why"),
            ({"session": ""}, "session"),
            ({"branch": ""}, "branch"),
            ({"cites": " , "}, "cites"),
        ],
        ids=["bad-kind", "empty-what", "blank-why", "empty-session", "empty-branch", "empty-cite"],
    )
    def test_each_invalid_field_refuses_with_nothing_written(self, checkout: pathlib.Path, capsys, over: dict, reason: str) -> None:
        inbox = _inbox(checkout)
        inbox.write_text("")
        before = inbox.stat().st_size
        assert al.run(_argv(**over), cwd=checkout, now=NOW) == 1
        assert inbox.stat().st_size == before
        assert reason in capsys.readouterr().err

    def test_a_refusal_leaves_an_existing_inbox_byte_identical(self, checkout: pathlib.Path) -> None:
        inbox = _inbox(checkout)
        assert al.run(_argv(), cwd=checkout, now=NOW) == 0
        before = inbox.read_bytes()
        assert al.run(_argv(kind="invented"), cwd=checkout, now=NOW) == 1
        assert inbox.read_bytes() == before


class TestItResolvesTheMainCheckout:
    def test_a_worktree_cwd_resolves_to_the_main_checkout(self, checkout: pathlib.Path, tmp_path: pathlib.Path) -> None:
        subprocess.run(
            [
                "git",
                "-C",
                str(checkout),
                "-c",
                "user.name=zcrypto-test",
                "-c",
                "user.email=zcrypto-test@example.invalid",
                "commit",
                "-q",
                "--allow-empty",
                "-m",
                "x",
            ],
            check=True,
        )
        wt = tmp_path / "wt"
        subprocess.run(["git", "-C", str(checkout), "worktree", "add", "-q", "--detach", str(wt)], check=True)
        assert al.main_checkout(wt) == checkout.resolve()
        assert al.run(_argv(), cwd=wt, now=NOW) == 0
        assert _inbox(checkout).exists()
        assert not (wt / ".local").exists()

    def test_a_missing_inbox_directory_refuses_rather_than_creating_one(self, checkout: pathlib.Path, capsys) -> None:
        (checkout / ".local" / "agent-lessons").rmdir()
        assert al.run(_argv(), cwd=checkout, now=NOW) == 2
        assert "does not exist" in capsys.readouterr().err


class TestTheSessionNamesOneFileInTheInbox:
    """A session that is not a plain name is refused before any path is built from it."""

    @pytest.mark.parametrize(
        "session",
        ["../../evil", "../..", "..", "team/bravo", "/etc/passwd", ".hidden", "a b"],
        ids=["up-into-root", "up-twice", "dotdot", "separator", "absolute", "leading-dot", "space"],
    )
    def test_a_session_that_is_not_a_plain_name_refuses(self, checkout: pathlib.Path, session: str, capsys) -> None:
        assert al.run(_argv(session=session), cwd=checkout, now=NOW) == 2
        assert "is not a session name" in capsys.readouterr().err

    def test_an_empty_session_is_the_validators_refusal_not_the_names(self, checkout: pathlib.Path, capsys) -> None:
        """The record check runs first, so an empty session is a malformed record (1), not a bad name (2)."""
        assert al.run(_argv(session=""), cwd=checkout, now=NOW) == 1
        assert "session must be a non-empty string" in capsys.readouterr().err

    def test_traversal_writes_nothing_anywhere_under_the_checkout(self, checkout: pathlib.Path) -> None:
        before = sorted(str(p.relative_to(checkout)) for p in checkout.rglob("*") if p.is_file())
        assert al.run(_argv(session="../../evil"), cwd=checkout, now=NOW) == 2
        assert sorted(str(p.relative_to(checkout)) for p in checkout.rglob("*") if p.is_file()) == before


class TestItCannotResolveTheCheckout:
    def test_outside_a_checkout_it_refuses_legibly_and_not_as_a_validation_failure(self, tmp_path: pathlib.Path, capsys) -> None:
        """Exit 2, not 1: a caller must tell 'not a git repo' from 'your record is malformed'."""
        outside = tmp_path / "nowhere"
        outside.mkdir()
        assert al.run(_argv(), cwd=outside, now=NOW) == 2
        assert "cannot resolve the main checkout" in capsys.readouterr().err

    def test_a_checkout_path_with_a_space_is_parsed_whole(self, tmp_path: pathlib.Path) -> None:
        spaced = tmp_path / "my repo"
        spaced.mkdir()
        subprocess.run(["git", "init", "-q", str(spaced)], check=True)
        (spaced / ".local" / "agent-lessons").mkdir(parents=True)
        assert al.main_checkout(spaced) == spaced.resolve()
        assert al.run(_argv(), cwd=spaced, now=NOW) == 0


class TestTheValidatorIsTheCheckers:
    def test_narrowing_the_checkers_kind_set_makes_the_helper_refuse_too(
        self, checkout: pathlib.Path, tmp_path: pathlib.Path, monkeypatch
    ) -> None:
        """One kind set, one home."""
        fake = tmp_path / "scripts"
        fake.mkdir()
        patched = _CHECKER.read_text().replace('"self-correction", ', "")
        (fake / "check-agent-lessons.py").write_text(patched)
        monkeypatch.setattr(al, "_CHECKER", fake / "check-agent-lessons.py")
        assert al.run(_argv(), cwd=checkout, now=NOW) == 1
        assert not _inbox(checkout).exists()


class TestASubstitutedFieldIsRefused:
    """A backticked symbol name in a DOUBLE-quoted shell argument runs as command substitution.

    The output is spliced into the field, so what lands is multi-line and every other check passes:
    it is a non-empty string of the right type. A newline is the tell no legitimate field carries."""

    SPLICED = "derive the list from CHANGELOG.md\nCLAUDE.md\ncli\ndocs/ output rather than typing it"

    # `session` belongs in the arm: `record_errors` runs before the `re.fullmatch` on `args.session`,
    # so a newline-bearing session is refused here and the name check never sees it.
    @pytest.mark.parametrize("field", ["what", "why", "branch", "session"])
    def test_a_field_carrying_substituted_output_refuses(self, checkout: pathlib.Path, capsys, field: str) -> None:
        inbox = _inbox(checkout)
        inbox.write_text("")
        before = inbox.stat().st_size
        assert al.run(_argv(**{field: self.SPLICED}), cwd=checkout, now=NOW) == 1
        assert inbox.stat().st_size == before
        err = capsys.readouterr().err
        assert field in err
        assert "single-quote" in err  # the refusal must say what to do, not only what is wrong

    def test_a_cite_carrying_substituted_output_refuses(self, checkout: pathlib.Path, capsys) -> None:
        assert al.run(_argv(cites="cli/tick/read.py\nCLAUDE.md"), cwd=checkout, now=NOW) == 1
        assert "single-quote" in capsys.readouterr().err

    def test_the_harvest_refuses_a_stored_record_too(self, tmp_path: pathlib.Path, capsys) -> None:
        """The arm has to hold when `check()` reads a record it did not write, carrying the newline
        escaped inside one physical line as a JSON-serialising writer stores it."""
        stored = tmp_path / "zcrypto-x.jsonl"
        rec = dict(
            ts="2026-09-08T00:00:00Z", session="zcrypto-x", branch="fix/x", kind="miscount", cites=[], what="a\nb", why="fine"
        )
        stored.write_text(json.dumps(rec) + "\n")
        chk = _load(_CHECKER, "chk_harvest")
        assert chk.check(str(stored)) == 1
        # WHICH refusal: a later one this fixture happens to trip would keep this green with the arm gone.
        assert "must be one line" in capsys.readouterr().out

    def test_a_legitimate_one_line_lesson_still_writes(self, checkout: pathlib.Path) -> None:
        """The true positive: the guard must not refuse the records it exists to protect."""
        assert (
            al.run(_argv(what="backticks in a double-quoted arg run", why="so pass prose single-quoted"), cwd=checkout, now=NOW)
            == 0
        )
        assert json.loads(_inbox(checkout).read_text())["what"] == "backticks in a double-quoted arg run"
