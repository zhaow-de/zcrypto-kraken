"""Each prose check trips one unit over its bar and passes at it; `--since` shows only new offenders."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
_SCRIPT = _REPO / "infra" / "scripts" / "prose-tripwire.py"
_spec = importlib.util.spec_from_file_location("prose_tripwire", _SCRIPT)
tw = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = tw
_spec.loader.exec_module(tw)


def _py(prose_lines: list[str], code_lines: int) -> str:
    """Prose lines first, then enough code that only the block check can trip."""
    return "\n".join(prose_lines + [f"x{i} = {i}" for i in range(code_lines)]) + "\n"


def _kinds(offenders) -> list[str]:
    return [o.kind for o in offenders]


class TestCommentBlock:
    def test_python_trips_one_over(self) -> None:
        n = tw.COMMENT_BLOCK_LINES + 1
        offs = tw.offenders_for("a.py", _py(["# c"] * n, 6 * n))
        assert _kinds(offs) == ["comment-block"]
        assert (offs[0].line, offs[0].measured, offs[0].threshold) == (1, n, tw.COMMENT_BLOCK_LINES)

    def test_python_passes_at_threshold(self) -> None:
        n = tw.COMMENT_BLOCK_LINES
        assert tw.offenders_for("a.py", _py(["# c"] * n, 6 * n)) == []

    def test_docstring_trips_one_over(self) -> None:
        n = tw.COMMENT_BLOCK_LINES + 1
        doc = ['"""d'] + ["d"] * (n - 2) + ['"""']
        offs = tw.offenders_for("a.py", _py(doc, 6 * n))
        assert _kinds(offs) == ["comment-block"]
        assert offs[0].measured == n

    def test_docstring_passes_at_threshold(self) -> None:
        n = tw.COMMENT_BLOCK_LINES
        doc = ['"""d'] + ["d"] * (n - 2) + ['"""']
        assert tw.offenders_for("a.py", _py(doc, 6 * n)) == []

    def test_a_blank_line_ends_a_block(self) -> None:
        n = tw.COMMENT_BLOCK_LINES
        src = _py(["# c"] * n + [""] + ["# c"] * n, 12 * n)
        assert tw.offenders_for("a.py", src) == []

    @pytest.mark.parametrize("suffix", [".sh", ".yml", ".yaml"])
    def test_hash_comments_trip_one_over(self, suffix: str) -> None:
        n = tw.COMMENT_BLOCK_LINES + 1
        src = "\n".join(["# c"] * n + ["run: true"]) + "\n"
        offs = tw.offenders_for(f"a{suffix}", src)
        assert _kinds(offs) == ["comment-block"]
        assert offs[0].measured == n

    @pytest.mark.parametrize("suffix", [".sh", ".yml"])
    def test_hash_comments_pass_at_threshold(self, suffix: str) -> None:
        n = tw.COMMENT_BLOCK_LINES
        src = "\n".join(["# c"] * n + ["run: true"]) + "\n"
        assert tw.offenders_for(f"a{suffix}", src) == []

    @pytest.mark.parametrize("suffix", [".sh", ".yml"])
    def test_indented_hash_comments_trip_one_over(self, suffix: str) -> None:
        n = tw.COMMENT_BLOCK_LINES + 1
        src = "\n".join(["top: 1"] + ["  # c"] * n + ["  x: 1"]) + "\n"
        offs = tw.offenders_for(f"a{suffix}", src)
        assert [(o.line, o.kind, o.measured) for o in offs] == [(2, "comment-block", n)]

    def test_a_run_of_trailing_comments_is_not_a_block(self) -> None:
        n = tw.COMMENT_BLOCK_LINES + 1
        src = "\n".join(f"x{i} = {i}  # c" for i in range(n)) + "\n" + "z = 0\n" * (6 * n)
        assert tw.offenders_for("a.py", src) == []

    @pytest.mark.parametrize("opener", ['r"""', "'''"])
    def test_raw_and_single_quote_docstrings_are_blocks(self, opener: str) -> None:
        n = tw.COMMENT_BLOCK_LINES + 1
        doc = [opener + "d"] + ["d"] * (n - 2) + [opener[-3:]]
        offs = tw.offenders_for("a.py", _py(doc, 6 * n))
        assert [(o.kind, o.measured) for o in offs] == [("comment-block", n)]

    def test_the_shebang_is_not_a_comment_line(self) -> None:
        n = tw.COMMENT_BLOCK_LINES
        src = "\n".join(["#!/usr/bin/env bash"] + ["# c"] * n + ["true"]) + "\n"
        assert tw.offenders_for("a.sh", src) == []


class TestTheTokenizer:
    def test_a_docstring_and_a_comment_block_are_separate_blocks(self) -> None:
        half = tw.COMMENT_BLOCK_LINES - 1
        doc = ['"""d'] + ["d"] * (half - 2) + ['"""']
        src = _py(doc + ["# c"] * half, 12 * half)
        blocks = tw.python_blocks(src)
        assert [(b.start, b.end) for b in blocks] == [(1, half), (half + 1, 2 * half)]
        assert tw.offenders_for("a.py", src) == []

    def test_merged_they_would_trip(self) -> None:
        n = 2 * (tw.COMMENT_BLOCK_LINES - 1)
        assert _kinds(tw.offenders_for("a.py", _py(["# c"] * n, 12 * n))) == ["comment-block"]

    def test_a_plain_string_is_code(self) -> None:
        src = 'x = "not prose"\ny = 1\n'
        total, prose, code = tw.measure_python(src)
        assert (total, prose, code) == (2, 0, 2)

    def test_a_triple_quoted_string_is_prose(self) -> None:
        src = 'x = """\nnot code\n"""\ny = 1\n'
        total, prose, code = tw.measure_python(src)
        assert (total, prose, code) == (4, 3, 1)

    def test_a_trailing_comment_counts_as_prose_and_not_code(self) -> None:
        total, prose, code = tw.measure_python("x = 1  # c\ny = 2\n")
        assert (total, prose, code) == (2, 1, 1)


class TestFileProse:
    def _src(self, prose: int, total: int) -> str:
        lines = [f"# c{i}" if i % 2 == 0 and i // 2 < prose else f"x{i} = {i}" for i in range(total)]
        return "\n".join(lines) + "\n"

    def test_trips_one_over(self) -> None:
        total = 100
        offs = tw.offenders_for("a.py", self._src(tw.FILE_PROSE_PERCENT + 1, total))
        assert _kinds(offs) == ["file-prose"]
        assert offs[0].measured == tw.FILE_PROSE_PERCENT + 1

    def test_passes_at_threshold(self) -> None:
        assert tw.offenders_for("a.py", self._src(tw.FILE_PROSE_PERCENT, 100)) == []

    def test_an_unparseable_file_is_skipped_not_reported(self) -> None:
        assert tw.measure_python("def (:\n") is None
        assert tw.offenders_for("a.py", "def (:\n") == []


class TestTableRow:
    def test_trips_one_over(self) -> None:
        row = "|" + "a" * (tw.TABLE_ROW_CHARS - 1)
        offs = tw.offenders_for("a.md", f"# t\n\n{row}|\n")
        assert _kinds(offs) == ["table-row"]
        assert (offs[0].line, offs[0].measured) == (3, tw.TABLE_ROW_CHARS + 1)

    def test_passes_at_threshold(self) -> None:
        row = "|" + "a" * (tw.TABLE_ROW_CHARS - 2) + "|"
        assert tw.offenders_for("a.md", f"# t\n\n{row}\n") == []

    def test_width_is_characters_not_bytes(self) -> None:
        row = "|" + "—" * (tw.TABLE_ROW_CHARS - 2) + "|"
        assert tw.offenders_for("a.md", f"# t\n\n{row}\n") == []

    def test_a_row_inside_a_fence_is_not_a_row(self) -> None:
        row = "|" + "a" * tw.TABLE_ROW_CHARS + "|"
        assert tw.offenders_for("a.md", f"# t\n\n```\n{row}\n```\n") == []


class TestSection:
    def _md(self, body_bytes: int) -> str:
        return "## H\n" + "b" * (body_bytes - len("## H\n") - 1) + "\n"

    def test_trips_one_over(self) -> None:
        offs = tw.offenders_for("a.md", self._md(tw.SECTION_BYTES + 1))
        assert _kinds(offs) == ["section"]
        assert (offs[0].line, offs[0].measured) == (1, tw.SECTION_BYTES + 1)

    def test_passes_at_threshold(self) -> None:
        assert tw.offenders_for("a.md", self._md(tw.SECTION_BYTES)) == []

    def test_a_subsection_is_measured_on_its_own(self) -> None:
        half = tw.SECTION_BYTES // 2 + 10
        src = "## P\n" + "b" * half + "\n### C\n" + "b" * half + "\n"
        assert tw.offenders_for("a.md", src) == []

    def test_a_long_child_trips_at_its_own_line_and_not_at_its_parents(self) -> None:
        big = "b" * tw.SECTION_BYTES
        src = f"## P\nshort\n### C\n{big}\n"
        assert [(o.line, o.kind) for o in tw.offenders_for("a.md", src)] == [(3, "section")]

    def test_text_before_the_first_heading_is_a_body(self) -> None:
        big = "b" * tw.SECTION_BYTES
        assert [(o.line, o.kind) for o in tw.offenders_for("a.md", f"{big}\n## H\nshort\n")] == [(1, "section")]

    def test_a_file_with_no_headings_is_one_body(self) -> None:
        big = "b" * tw.SECTION_BYTES
        assert [(o.line, o.kind) for o in tw.offenders_for("a.md", f"{big}\n")] == [(1, "section")]

    def test_a_sibling_heading_ends_the_section(self) -> None:
        half = tw.SECTION_BYTES // 2 + 10
        src = "## A\n" + "b" * half + "\n## B\n" + "b" * half + "\n"
        assert tw.offenders_for("a.md", src) == []

    def test_a_hash_line_inside_a_fence_is_not_a_heading(self) -> None:
        big = "b" * tw.SECTION_BYTES
        src = f"## A\n```\n# not a heading\n```\n{big}\n"
        offs = tw.offenders_for("a.md", src)
        assert [(o.line, o.kind) for o in offs] == [(1, "section")]

    def test_a_language_tagged_fence_still_opens_and_closes(self) -> None:
        big = "b" * tw.SECTION_BYTES
        src = f"## A\n```bash\n# not a heading\n```\n## B\n{big}\n"
        offs = tw.offenders_for("a.md", src)
        assert [(o.line, o.kind) for o in offs] == [(5, "section")]

    def test_bytes_not_characters(self) -> None:
        body = "é" * (tw.SECTION_BYTES // 2)
        assert _kinds(tw.offenders_for("a.md", f"## H\n{body}\n")) == ["section"]


class TestChangelogEntry:
    PATH = "docs/iterations-history-phase9.md"

    def _entry(self, bullets: int) -> str:
        return "## 2026-01-01 — e\n\n" + "\n".join("- b" for _ in range(bullets)) + "\n"

    def test_trips_one_over(self) -> None:
        offs = tw.offenders_for(self.PATH, self._entry(tw.CHANGELOG_BULLETS + 1))
        assert _kinds(offs) == ["changelog-entry"]
        assert (offs[0].line, offs[0].measured) == (1, tw.CHANGELOG_BULLETS + 1)

    def test_passes_at_threshold(self) -> None:
        assert tw.offenders_for(self.PATH, self._entry(tw.CHANGELOG_BULLETS)) == []

    def test_nested_bullets_are_not_top_level(self) -> None:
        src = "## e\n\n- b\n  - nested\n  - nested\n" + "- b\n" * (tw.CHANGELOG_BULLETS - 1)
        assert tw.offenders_for(self.PATH, src) == []

    def test_a_bullet_right_after_a_fence_is_counted_and_a_fenced_one_is_not(self) -> None:
        n = tw.CHANGELOG_BULLETS
        src = "## e\n\n" + "- b\n" * n + "```\n- fenced\n```\n- b\n"
        offs = tw.offenders_for(self.PATH, src)
        assert [(o.kind, o.measured) for o in offs] == [("changelog-entry", n + 1)]

    def test_only_changelog_files_carry_the_check(self) -> None:
        assert tw.offenders_for("docs/reference/x.md", self._entry(tw.CHANGELOG_BULLETS + 1)) == []


class TestTruePositives:
    def test_a_production_shaped_python_file_is_clean(self) -> None:
        src = '"""One line."""\n\nimport os\n\n\ndef f(x):\n    # why\n    return os.path.join(x, "y")\n' + "z = 0\n" * 12
        assert tw.offenders_for("cli/x.py", src) == []

    def test_a_production_shaped_markdown_file_is_clean(self) -> None:
        src = "# Title\n\nA paragraph.\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n## Section\n\nMore.\n"
        assert tw.offenders_for("docs/reference/x.md", src) == []


class TestScope:
    @pytest.fixture
    def repo(self, tmp_path: Path, monkeypatch) -> Path:
        for rel in (
            "cli/a.py",
            "tests/b.py",
            "infra/c.sh",
            "infra/d.yml",
            "infra/runbooks/e.md",
            "docs/reference/f.md",
            "docs/reference/ops-journal/g.md",
            "docs/universe/h.md",
            "docs/iterations-history-phase1.md",
            "docs/open-topics/T0001-x.md",
            "docs/open-topics/archive/T0000-y.md",
            "docs/specs/00001-z.md",
            "docs/plans/00001-z.md",
            "docs/research/r.md",
            "README.md",
            ".claude/rules/k.md",
            "cli/n.json",
        ):
            (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
            (tmp_path / rel).write_text("# t\n")
        monkeypatch.chdir(tmp_path)
        return tmp_path

    def test_the_default_scope(self, repo: Path) -> None:
        got = sorted(tw.default_paths())
        assert got == [
            "README.md",
            "cli/a.py",
            "docs/iterations-history-phase1.md",
            "docs/open-topics/T0001-x.md",
            "docs/reference/f.md",
            "docs/universe/h.md",
            "infra/c.sh",
            "infra/d.yml",
            "infra/runbooks/e.md",
            "tests/b.py",
        ]

    def test_an_explicit_directory_still_honours_the_exclusions(self, repo: Path) -> None:
        got = sorted(tw.expand_paths(["docs"]))
        assert not any(p.startswith(("docs/specs", "docs/plans", "docs/research")) for p in got)
        assert "docs/reference/ops-journal/g.md" not in got
        assert "docs/open-topics/archive/T0000-y.md" not in got
        assert "docs/reference/f.md" in got

    def test_an_explicit_walk_skips_dot_directories(self, repo: Path) -> None:
        (repo / ".venv").mkdir()
        (repo / ".venv" / "x.py").write_text("x = 1\n")
        got = tw.expand_paths(["."])
        assert ".venv/x.py" not in got
        assert "cli/a.py" in got

    def test_an_explicit_file_is_scanned_as_named(self, repo: Path) -> None:
        assert tw.expand_paths(["docs/specs/00001-z.md"]) == ["docs/specs/00001-z.md"]


class TestTheCommandLine:
    @pytest.fixture
    def tree(self, tmp_path: Path, monkeypatch) -> Path:
        monkeypatch.chdir(tmp_path)
        (tmp_path / "clean.py").write_text("x = 1\n")
        return tmp_path

    def test_clean_exits_zero_with_an_all_zero_summary(self, tree: Path, capsys) -> None:
        assert tw.main(["clean.py"]) == 0
        out = capsys.readouterr().out.splitlines()
        assert out == ["offenders: comment-block=0 file-prose=0 table-row=0 section=0 changelog-entry=0 (total 0)"]

    def test_an_offender_exits_one_and_is_listed_before_the_summary(self, tree: Path, capsys) -> None:
        n = tw.COMMENT_BLOCK_LINES + 1
        (tree / "b.py").write_text(_py(["# c"] * n, 6 * n))
        assert tw.main(["b.py", "clean.py"]) == 1
        out = capsys.readouterr().out.splitlines()
        assert out[0] == f"b.py:1: comment-block {n} > {tw.COMMENT_BLOCK_LINES}"
        assert out[-1].startswith("offenders: comment-block=1 ") and out[-1].endswith("(total 1)")

    def test_output_is_sorted_by_path_then_line(self, tree: Path, capsys) -> None:
        n = tw.COMMENT_BLOCK_LINES + 1
        (tree / "z.py").write_text(_py(["# c"] * n, 6 * n))
        (tree / "a.py").write_text("x = 1\n" + _py(["# c"] * n, 6 * n) + _py(["# d"] * n, 6 * n))
        assert tw.main(["z.py", "a.py"]) == 1
        lines = [ln.split(":")[0:2] for ln in capsys.readouterr().out.splitlines()[:-1]]
        assert lines == sorted(lines, key=lambda p: (p[0], int(p[1])))

    def test_an_absolute_path_is_reported_relative(self, tree: Path, capsys) -> None:
        n = tw.COMMENT_BLOCK_LINES + 1
        (tree / "b.py").write_text(_py(["# c"] * n, 6 * n))
        assert tw.main([str(tree / "b.py")]) == 1
        assert capsys.readouterr().out.splitlines()[0].startswith("b.py:1:")

    def test_large_measures_render_without_an_exponent(self) -> None:
        o = tw.Offender("a.md", 1, "section", 1234567, tw.SECTION_BYTES, "h")
        assert tw.render([o]).splitlines()[0] == f"a.md:1: section 1234567 > {tw.SECTION_BYTES}"

    def test_help_prints_every_threshold(self, capsys) -> None:
        with pytest.raises(SystemExit) as exc:
            tw.main(["--help"])
        assert exc.value.code == 0
        text = capsys.readouterr().out
        for name in ("COMMENT_BLOCK_LINES", "FILE_PROSE_PERCENT", "TABLE_ROW_CHARS", "SECTION_BYTES", "CHANGELOG_BULLETS"):
            assert f"{name}={getattr(tw, name)}" in text


class TestSince:
    @pytest.fixture
    def repo(self, tmp_path: Path, monkeypatch) -> Path:
        monkeypatch.chdir(tmp_path)
        git = ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false"]
        subprocess.run([*git, "init", "-q"], check=True)
        n = tw.COMMENT_BLOCK_LINES + 1
        (tmp_path / "old.py").write_text(_py(["# old"] * n, 6 * n))
        subprocess.run([*git, "add", "old.py"], check=True)
        subprocess.run([*git, "commit", "-q", "-m", "baseline"], check=True)
        return tmp_path

    def test_only_baseline_offenders_means_clean(self, repo: Path, capsys) -> None:
        assert tw.main(["--since", "HEAD", "old.py"]) == 0
        assert capsys.readouterr().out.splitlines()[-1].endswith("(total 0)")

    def test_a_new_offender_is_shown_and_the_old_one_hidden(self, repo: Path, capsys) -> None:
        n = tw.COMMENT_BLOCK_LINES + 1
        (repo / "old.py").write_text(_py(["# old"] * n, 6 * n) + _py(["# new"] * n, 6 * n))
        (repo / "fresh.py").write_text(_py(["# fresh"] * n, 6 * n))
        assert tw.main(["--since", "HEAD", "old.py", "fresh.py"]) == 1
        out = capsys.readouterr().out.splitlines()
        assert [ln.split(" ")[0] for ln in out[:-1]] == ["fresh.py:1:", f"old.py:{6 * n + n + 1}:"]
        assert out[-1].endswith("(total 2)")

    def test_a_moved_offender_is_not_new(self, repo: Path) -> None:
        n = tw.COMMENT_BLOCK_LINES + 1
        (repo / "old.py").write_text("y = 0\ny = 1\ny = 2\n" + _py(["# old"] * n, 6 * n))
        assert tw.main(["--since", "HEAD", "old.py"]) == 0

    def test_a_second_offender_with_the_same_anchor_is_new(self, repo: Path, capsys) -> None:
        n = tw.COMMENT_BLOCK_LINES + 1
        block = _py(["# old"] * n, 6 * n)
        (repo / "old.py").write_text(block + block)
        assert tw.main(["--since", "HEAD", "old.py"]) == 1
        assert capsys.readouterr().out.splitlines()[-1].endswith("(total 1)")

    def test_an_offender_that_grew_is_new(self, repo: Path, capsys) -> None:
        n = tw.COMMENT_BLOCK_LINES + 1
        (repo / "old.py").write_text(_py(["# old"] * (3 * n), 18 * n))
        assert tw.main(["--since", "HEAD", "old.py"]) == 1
        assert capsys.readouterr().out.splitlines()[0] == f"old.py:1: comment-block {3 * n} > {tw.COMMENT_BLOCK_LINES}"

    def test_an_unknown_revision_exits_two_and_says_so(self, repo: Path, capsys) -> None:
        assert tw.main(["--since", "no-such-rev", "old.py"]) == 2
        assert "no-such-rev" in capsys.readouterr().err

    def test_without_since_everything_is_shown(self, repo: Path, capsys) -> None:
        assert tw.main(["old.py"]) == 1
        assert capsys.readouterr().out.splitlines()[-1].endswith("(total 1)")
