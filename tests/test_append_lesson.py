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
        subprocess.run(["git", "-C", str(checkout), "commit", "-q", "--allow-empty", "-m", "x"], check=True)
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
