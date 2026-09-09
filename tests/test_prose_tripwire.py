"""Each prose check trips one unit over its bar and passes at it; `--since` and the baseline ratchet report only offenders the recorded past does not cover."""

from __future__ import annotations

import importlib.util
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
import yaml

_REPO = Path(__file__).resolve().parents[1]
_BASELINE = "infra/scripts/prose-tripwire-baseline.txt"
_SCRIPT = _REPO / "infra" / "scripts" / "prose-tripwire.py"
_spec = importlib.util.spec_from_file_location("prose_tripwire", _SCRIPT)
tw = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = tw
_spec.loader.exec_module(tw)


def _py(prose_lines: list[str], code_lines: int) -> str:
    """Prose lines first, then enough code that only the block check can trip."""
    return "\n".join(prose_lines + [f"x{i} = {i}" for i in range(code_lines)]) + "\n"


def _summary(new: int = 0, grown: int = 0, rewritten: int = 0, shrunk: int = 0, retired: int = 0) -> str:
    """The check's last line, built rather than transcribed, so a new counter is one edit here."""
    return f"new: {new} grown: {grown} rewritten: {rewritten} shrunk: {shrunk} retired: {retired}"


def _kinds(offenders) -> list[str]:
    return [o.kind for o in offenders]


class TestCommentMass:
    """The character bar under the line bar: a block wide enough to evade the line count."""

    def test_one_line_over_the_char_bar_trips(self) -> None:
        wide = "# " + "x" * tw.COMMENT_BLOCK_CHARS
        offs = tw.offenders_for("a.py", _py([wide], 24))
        assert _kinds(offs) == ["comment-mass"]
        assert (offs[0].line, offs[0].measured, offs[0].threshold) == (1, len(wide), tw.COMMENT_BLOCK_CHARS)

    def test_a_block_at_the_char_bar_passes(self) -> None:
        wide = "#" + "x" * (tw.COMMENT_BLOCK_CHARS - 1)
        assert len(wide) == tw.COMMENT_BLOCK_CHARS
        assert tw.offenders_for("a.py", _py([wide], 24)) == []

    def test_a_wide_docstring_on_one_line_trips(self) -> None:
        wide = '"""' + "d" * tw.COMMENT_BLOCK_CHARS + '"""'
        offs = tw.offenders_for("a.py", _py([wide], 24))
        assert _kinds(offs) == ["comment-mass"]

    def test_mass_accumulates_across_lines_under_the_line_bar(self) -> None:
        third = "# " + "x" * (tw.COMMENT_BLOCK_CHARS // 2)
        offs = tw.offenders_for("a.py", _py([third, third], 24))
        assert _kinds(offs) == ["comment-mass"]
        assert offs[0].measured == 2 * len(third)

    def test_a_block_over_both_bars_is_reported_once_as_a_line_offender(self) -> None:
        wide = "# " + "x" * tw.COMMENT_BLOCK_CHARS
        n = tw.COMMENT_BLOCK_LINES + 1
        offs = tw.offenders_for("a.py", _py([wide] * n, 6 * n))
        assert _kinds(offs) == ["comment-block"]
        assert offs[0].measured == n

    def test_a_normal_block_under_both_bars_passes(self) -> None:
        body = ["# a sentence that says what the code cannot, and stops there."] * tw.COMMENT_BLOCK_LINES
        assert tw.offenders_for("a.py", _py(body, 24)) == []

    def test_a_hash_file_is_measured_the_same_way(self) -> None:
        wide = "# " + "x" * tw.COMMENT_BLOCK_CHARS
        offs = tw.offenders_for("a.sh", wide + "\necho hi\n")
        assert _kinds(offs) == ["comment-mass"]


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

    def test_a_triple_quoted_string_outside_a_docstring_position_is_code(self) -> None:
        src = 'x = """\nnot code\n"""\ny = 1\n'
        total, prose, code = tw.measure_python(src)
        assert (total, prose, code) == (4, 0, 4)

    def test_a_triple_quoted_string_in_a_docstring_position_is_prose(self) -> None:
        src = '"""d\nd\n"""\ny = 1\n'
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


class TestTheFileProseFloor:
    def _src(self, code: int) -> str:
        """Two comment lines (under the block bar) over `code` code lines — over the percentage at both sizes."""
        return "# a\n# b\n" + "".join(f"x{i} = {i}\n" for i in range(code))

    def test_the_percentage_bar_starts_at_the_floor(self) -> None:
        offs = tw.offenders_for("a.py", self._src(tw.FILE_PROSE_FLOOR))
        assert _kinds(offs) == ["file-prose"]

    def test_a_file_one_code_line_under_the_floor_is_not_measured(self) -> None:
        src = self._src(tw.FILE_PROSE_FLOOR - 1)
        assert tw.measure_python(src)[1] * 100 > tw.FILE_PROSE_PERCENT * tw.measure_python(src)[0]
        assert tw.offenders_for("a.py", src) == []

    def test_a_one_class_module_with_its_one_sentence_docstring_is_not_reported(self) -> None:
        assert tw.offenders_for("cli/x/errors.py", 'class E(Exception):\n    """One sentence."""\n') == []


class TestStringLiterals:
    """A triple-quoted literal counts as prose only where the AST puts a docstring."""

    N = 5

    def _lines(self, opener: str, closer: str) -> list[str]:
        return [opener] + ["d"] * (self.N - 2) + [closer]

    def test_a_module_docstring_over_the_bar_is_a_block(self) -> None:
        offs = tw.offenders_for("a.py", _py(self._lines('"""d', '"""'), 6 * self.N))
        assert [(o.kind, o.measured) for o in offs] == [("comment-block", self.N)]

    def test_an_assigned_literal_of_the_same_size_is_code(self) -> None:
        assert tw.offenders_for("a.py", _py(self._lines('SQL = """', '"""'), 6 * self.N)) == []

    def test_an_argument_literal_of_the_same_size_is_code(self) -> None:
        assert tw.offenders_for("a.py", _py(self._lines('f("""', '""")'), 6 * self.N)) == []

    def test_a_function_docstring_is_a_block_and_a_literal_in_its_body_is_not(self) -> None:
        body = "\n".join("    " + line for line in self._lines('BODY = """', '"""'))
        doc = "\n".join("    " + line for line in self._lines('"""d', '"""'))
        offs = tw.offenders_for("a.py", f"def g():\n{doc}\n{body}\n    return 1\n" + "z = 0\n" * (12 * self.N))
        assert [(o.line, o.kind, o.measured) for o in offs] == [(2, "comment-block", self.N)]

    def test_a_literal_does_not_push_a_file_over_the_prose_percentage(self) -> None:
        src = 'BLOB = """\n' + "d\n" * 60 + '"""\n' + "x = 1\n" * 20
        assert tw.offenders_for("a.py", src) == []


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


class TestTheOpenTopicsSectionExemption:
    """A topic file and its index grow a section per registration, so only the section bar is dropped."""

    def _section(self) -> str:
        return "## H\n" + "b" * tw.SECTION_BYTES + "\n"

    def test_a_long_section_in_a_reference_page_trips(self) -> None:
        assert _kinds(tw.offenders_for("docs/reference/x.md", self._section())) == ["section"]

    @pytest.mark.parametrize("path", ["docs/open-topics/T0001-x.md", "docs/open-topics/README.md"])
    def test_the_same_section_under_open_topics_does_not(self, path: str) -> None:
        assert tw.offenders_for(path, self._section()) == []

    def test_the_table_row_bar_still_applies_there(self) -> None:
        row = "|" + "a" * tw.TABLE_ROW_CHARS + "|"
        assert _kinds(tw.offenders_for("docs/open-topics/T0001-x.md", f"# t\n\n{row}\n")) == ["table-row"]

    def test_a_nested_path_that_only_looks_like_it_is_not_exempt(self) -> None:
        assert _kinds(tw.offenders_for("docs/open-topics/sub/x.md", self._section())) == ["section"]


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


class TestVaultContent:
    PATH = "infra/ansible/group_vars/all/vault.yml"

    def _header(self) -> str:
        return "\n".join(["# c"] * (tw.COMMENT_BLOCK_LINES + 1))

    def test_a_comment_block_in_a_plain_yaml_file_is_reported(self) -> None:
        """The true positive at the same path: the skip is by content, so a non-vault file still trips."""
        assert _kinds(tw.offenders_for(self.PATH, self._header() + "\nkey: value\n")) == ["comment-block"]

    def test_a_per_value_vault_blob_takes_the_file_out_of_scope(self) -> None:
        src = self._header() + "\nkey: !vault |\n          $ANSIBLE_VAULT;1.1;AES256\n          6162636465\n"
        assert tw.offenders_for(self.PATH, src) == []

    def test_a_whole_file_vault_blob_is_out_of_scope(self) -> None:
        assert tw.offenders_for("a.yml", "$ANSIBLE_VAULT;1.1;AES256\n6162636465\n" + self._header() + "\n") == []

    def test_a_line_opening_with_the_vault_password_variable_is_not_vault_content(self) -> None:
        """The blob's header ends in `;`: an `$ANSIBLE_VAULT`-prefixed variable at a line's start is not one."""
        src = "$ANSIBLE_VAULT_PASSWORD_FILE=vault-pass.sh\n" + self._header() + "\ntrue\n"
        assert _kinds(tw.offenders_for("infra/ansible/scripts/run.sh", src)) == ["comment-block"]


_GIT = ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false"]


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
            "infra/README.md",
            "infra/runbooks/README.md",
            "infra/nas/README.md",
            "infra/ops/README.md",
            "infra/ansible/files/README.md",
            "infra/external-systems.md",
            "infra/nas/ledger-correction-20260714-link-eur.md",
            "docs/open-topics/README.md",
            ".claude/rules/k.md",
            "cli/n.json",
        ):
            (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
            (tmp_path / rel).write_text("# t\n")
        monkeypatch.chdir(tmp_path)
        subprocess.run([*_GIT, "init", "-q"], check=True)
        subprocess.run([*_GIT, "add", "-A", "-f", "."], check=True)
        return tmp_path

    def test_the_default_scope(self, repo: Path) -> None:
        got = sorted(tw.default_paths())
        assert got == [
            "README.md",
            "cli/a.py",
            "docs/iterations-history-phase1.md",
            "docs/open-topics/README.md",
            "docs/open-topics/T0001-x.md",
            "docs/reference/f.md",
            "docs/universe/h.md",
            "infra/README.md",
            "infra/ansible/files/README.md",
            "infra/c.sh",
            "infra/d.yml",
            "infra/external-systems.md",
            "infra/nas/README.md",
            "infra/ops/README.md",
            "infra/runbooks/README.md",
            "infra/runbooks/e.md",
            "tests/b.py",
        ]

    def test_a_research_report_stays_out(self, repo: Path) -> None:
        """Point-in-time reports are out of the default scope, as `docs/specs` and `docs/plans` are."""
        assert "docs/research/r.md" not in tw.default_paths()

    def test_a_dated_record_beside_a_readme_stays_out(self, repo: Path) -> None:
        """`infra/` is walked for READMEs, not for every page: a dated record is point-in-time."""
        assert "infra/nas/ledger-correction-20260714-link-eur.md" not in tw.default_paths()

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


class TestTheIndexIsTheDefaultScope:
    """The index supplies the path set, so an untracked file cannot refuse a commit that leaves it out."""

    @pytest.fixture
    def repo(self, tmp_path: Path, monkeypatch) -> Path:
        monkeypatch.chdir(tmp_path)
        subprocess.run([*_GIT, "init", "-q"], check=True)
        (tmp_path / "cli").mkdir()
        (tmp_path / "cli" / "kept.py").write_text("x = 1\n")
        subprocess.run([*_GIT, "add", "-f", "cli/kept.py"], check=True)
        assert tw.main(["--write-baseline", "base.txt"]) == 0
        return tmp_path

    def test_an_untracked_offender_passes_and_the_same_file_staged_fails(self, repo: Path, capsys) -> None:
        n = tw.COMMENT_BLOCK_LINES + 1
        (repo / "cli" / "fresh.py").write_text(_py(["# fresh"] * n, 6 * n))
        assert tw.main(["--check-baseline", "base.txt"]) == 0
        assert capsys.readouterr().out.splitlines() == [_summary()]
        subprocess.run([*_GIT, "add", "-f", "cli/fresh.py"], check=True)
        assert tw.main(["--check-baseline", "base.txt"]) == 1
        assert capsys.readouterr().out.splitlines()[0] == f"fail new: cli/fresh.py:1: comment-block {n} > {tw.COMMENT_BLOCK_LINES}"

    def test_a_tracked_file_deleted_from_disk_is_reported_not_opened(self, repo: Path, capsys) -> None:
        """The bytes come from the worktree, so a deletion the index still lists is a keep retired, never a read."""
        n = tw.COMMENT_BLOCK_LINES + 1
        (repo / "cli" / "gone.py").write_text(_py(["# gone"] * n, 6 * n))
        subprocess.run([*_GIT, "add", "-f", "cli/gone.py"], check=True)
        assert tw.main(["--write-baseline", "base.txt"]) == 0
        assert (repo / "base.txt").read_text().startswith("cli/gone.py:1: comment-block")
        (repo / "cli" / "gone.py").unlink()
        assert tw.main(["--check-baseline", "base.txt"]) == 0
        out = capsys.readouterr().out.splitlines()
        assert out == [out[0], _summary(retired=1)]  # exactly one line, and it is the retired row
        assert out[0].startswith("note retired: cli/gone.py: comment-block")

    def test_a_named_path_is_scanned_tracked_or_not(self, repo: Path, capsys) -> None:
        """An explicit argument is the caller's word, not the index's."""
        n = tw.COMMENT_BLOCK_LINES + 1
        (repo / "cli" / "fresh.py").write_text(_py(["# fresh"] * n, 6 * n))
        assert tw.main(["--check-baseline", "base.txt", "cli/fresh.py"]) == 1
        assert capsys.readouterr().out.splitlines()[0] == f"fail new: cli/fresh.py:1: comment-block {n} > {tw.COMMENT_BLOCK_LINES}"


class TestADefaultScopeThatCannotBeRead:
    """The default scope is the whole index: where it cannot be read as such, the run refuses rather than scanning nothing."""

    def _offender(self) -> str:
        n = tw.COMMENT_BLOCK_LINES + 1
        return _py(["# c"] * n, 6 * n)

    @pytest.fixture
    def outside(self, tmp_path: Path, monkeypatch) -> Path:
        monkeypatch.chdir(tmp_path)
        (tmp_path / "cli").mkdir()
        (tmp_path / "cli" / "a.py").write_text(self._offender())
        return tmp_path

    @pytest.fixture
    def repo(self, outside: Path) -> Path:
        subprocess.run([*_GIT, "init", "-q"], check=True)
        subprocess.run([*_GIT, "add", "-f", "cli/a.py"], check=True)
        (outside / "base.txt").write_text("")
        return outside

    def test_outside_a_checkout_it_refuses_and_names_the_remedy(self, outside: Path, capsys) -> None:
        assert tw.main([]) == 2
        assert capsys.readouterr().err.splitlines() == ["not a git checkout — name paths explicitly"]

    def test_outside_a_checkout_a_named_path_is_still_scanned(self, outside: Path, capsys) -> None:
        assert tw.main(["cli/a.py"]) == 1
        assert capsys.readouterr().out.splitlines()[0].startswith("cli/a.py:1: comment-block")

    def test_from_the_root_the_staged_offender_is_named(self, repo: Path, capsys) -> None:
        assert tw.main(["--check-baseline", str(repo / "base.txt")]) == 1
        assert capsys.readouterr().out.splitlines()[0].startswith("fail new: cli/a.py:1: comment-block")

    def test_from_a_subdirectory_it_refuses_rather_than_calling_that_tree_clean(self, repo: Path, monkeypatch, capsys) -> None:
        """`git ls-files` prints paths relative to cwd, so the roots below the root match nothing."""
        monkeypatch.chdir(repo / "cli")
        assert tw.main(["--check-baseline", str(repo / "base.txt")]) == 2
        assert "the repository root" in capsys.readouterr().err


class TestTheCommandLine:
    @pytest.fixture
    def tree(self, tmp_path: Path, monkeypatch) -> Path:
        monkeypatch.chdir(tmp_path)
        (tmp_path / "clean.py").write_text("x = 1\n")
        return tmp_path

    def test_clean_exits_zero_with_an_all_zero_summary(self, tree: Path, capsys) -> None:
        assert tw.main(["clean.py"]) == 0
        out = capsys.readouterr().out.splitlines()
        assert out == ["offenders: " + " ".join(f"{k}=0" for k in tw.KINDS) + " (total 0)"]

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

    def test_the_char_bar_is_the_line_bar_at_ruffs_own_width(self) -> None:
        """A hard-coded 528 whose comment claims a derivation: this is what binds it to both operands."""
        import tomllib

        width = tomllib.loads((_REPO / "ruff.toml").read_text())["line-length"]
        assert tw.COMMENT_BLOCK_CHARS == tw.COMMENT_BLOCK_LINES * width

    def test_help_prints_every_threshold(self, capsys) -> None:
        with pytest.raises(SystemExit) as exc:
            tw.main(["--help"])
        assert exc.value.code == 0
        text = "".join(capsys.readouterr().out.split())  # argparse wraps the epilog and breaks long words
        for name in tw.THRESHOLDS:
            assert f"{name}={getattr(tw, name)}" in text
        # THRESHOLDS derives itself, so iterating it cannot notice an omission: pin the set instead.
        assert set(tw.THRESHOLDS) == {n for n, v in vars(tw).items() if n.isupper() and type(v) is int}

    def test_help_prints_the_whole_description_sentence(self, capsys) -> None:
        """One assertion per test: a regression here and in the thresholds must redden separately."""
        with pytest.raises(SystemExit):
            tw.main(["--help"])
        text = " ".join(capsys.readouterr().out.split())  # argparse re-wraps the description to $COLUMNS
        assert "long changelog entries." in text


def _commit(*paths: str) -> None:
    subprocess.run([*_GIT, "add", *paths], check=True)
    subprocess.run([*_GIT, "commit", "-q", "-m", "baseline"], check=True)


class TestSince:
    @pytest.fixture
    def repo(self, tmp_path: Path, monkeypatch) -> Path:
        monkeypatch.chdir(tmp_path)
        subprocess.run([*_GIT, "init", "-q"], check=True)
        n = tw.COMMENT_BLOCK_LINES + 1
        (tmp_path / "old.py").write_text(_py(["# old"] * n, 6 * n))
        _commit("old.py")
        return tmp_path

    def test_two_same_anchor_blocks_reordered_are_not_new(self, repo: Path, capsys) -> None:
        n = tw.COMMENT_BLOCK_LINES + 1
        small, big = _py(["# old"] * n, 6 * n), _py(["# old"] * (n + 2), 6 * n)
        (repo / "two.py").write_text(big + small)
        _commit("two.py")
        (repo / "two.py").write_text(small + big)
        assert tw.main(["--since", "HEAD", "two.py"]) == 0
        assert capsys.readouterr().out.splitlines()[-1].endswith("(total 0)")

    def test_two_shrunken_same_anchor_blocks_are_not_new(self, repo: Path, capsys) -> None:
        n = tw.COMMENT_BLOCK_LINES + 1
        big, small = _py(["# old"] * (n + 4), 6 * n), _py(["# old"] * (n + 2), 6 * n)
        (repo / "shrunk.py").write_text(big + small)
        _commit("shrunk.py")
        (repo / "shrunk.py").write_text(_py(["# old"] * (n + 1), 6 * n) + _py(["# old"] * (n + 3), 6 * n))
        assert tw.main(["--since", "HEAD", "shrunk.py"]) == 0
        assert capsys.readouterr().out.splitlines()[-1].endswith("(total 0)")

    def test_the_reported_line_is_the_new_block_not_the_unchanged_one(self, repo: Path, capsys) -> None:
        n = tw.COMMENT_BLOCK_LINES + 1
        old = "y = 0\n" * 3 + _py(["# old"] * (n + 2), 6 * n)
        (repo / "id.py").write_text(old)
        _commit("id.py")
        (repo / "id.py").write_text(_py(["# old"] * n, 6 * n) + old)
        assert tw.main(["--since", "HEAD", "id.py"]) == 1
        out = capsys.readouterr().out.splitlines()
        assert out[0] == f"id.py:1: comment-block {n} > {tw.COMMENT_BLOCK_LINES}"
        assert out[-1].endswith("(total 1)")

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


class TestTheBaselineRatchet:
    """The ratchet fails on an offender the baseline does not record at that size or larger, never on a keep."""

    N = 5

    @pytest.fixture
    def tree(self, tmp_path: Path, monkeypatch) -> Path:
        monkeypatch.chdir(tmp_path)
        (tmp_path / "kept.py").write_text(_py(["# kept"] * self.N, 6 * self.N))
        assert tw.main(["--write-baseline", "base.txt", "kept.py"]) == 0
        return tmp_path

    def test_the_baseline_is_one_line_per_offender_carrying_its_anchor(self, tree: Path) -> None:
        expected = f"kept.py:1: comment-block {self.N} > {tw.COMMENT_BLOCK_LINES}\t# kept"
        assert (tree / "base.txt").read_text().splitlines() == [expected]

    def test_an_anchorless_offender_leaves_no_trailing_whitespace_for_a_hook_to_strip(self, tree: Path) -> None:
        (tree / "kept.py").write_text("# a\n# b\n" + "".join(f"x{i} = {i}\n" for i in range(tw.FILE_PROSE_FLOOR)))
        assert tw.main(["--write-baseline", "base.txt", "kept.py"]) == 0
        written = (tree / "base.txt").read_text()
        assert written.splitlines() == ["kept.py:1: file-prose 33.3 > 20"]
        assert written == written.rstrip() + "\n"

    def test_a_moved_offender_passes(self, tree: Path, capsys) -> None:
        (tree / "kept.py").write_text("y = 0\n" * 10 + _py(["# kept"] * self.N, 6 * self.N))
        assert tw.main(["--check-baseline", "base.txt", "kept.py"]) == 0
        assert capsys.readouterr().out.splitlines() == [_summary()]

    def test_a_rewritten_keep_still_over_the_bar_passes_as_a_rewrite(self, tree: Path, capsys) -> None:
        """The anchor changed and the block shrank: a rewrite consuming its retired row, not a new offender."""
        (tree / "kept.py").write_text(_py(["# rewritten"] + ["# kept"] * (self.N - 1), 6 * self.N))
        assert tw.main(["--check-baseline", "base.txt", "kept.py"]) == 0
        out = capsys.readouterr().out.splitlines()
        assert out[0] == f"note rewritten: kept.py:1: comment-block {self.N} > {tw.COMMENT_BLOCK_LINES} recorded {self.N}"
        assert out[-1] == _summary(rewritten=1)

    def test_a_re_anchored_block_is_covered_by_a_larger_retired_sibling(self, tree: Path, capsys) -> None:
        """Per (path, kind), not per block: a grown block passes when a larger sibling retires, and what
        still cannot happen is a file's prose growing in total, since each offender consumes a distinct row."""
        (tree / "kept.py").write_text(_py(["# alpha"] * 6 + ["x = 0", ""] + ["# beta"] * 22, 40 * self.N))
        assert tw.main(["--write-baseline", "base.txt", "kept.py"]) == 0
        (tree / "kept.py").write_text(_py(["# alpha rewritten"] + ["# alpha"] * 9, 40 * self.N))
        assert tw.main(["--check-baseline", "base.txt", "kept.py"]) == 0
        assert capsys.readouterr().out.splitlines()[-1] == _summary(rewritten=1, retired=1)

    def test_two_possible_sources_are_named_as_two_rather_than_guessed(self, tree: Path, capsys) -> None:
        """The anchor that identified the row is what a rewrite changes, so any candidate could be its own."""
        body = ["# kept"] * 22 + ["x = 0", ""] + ["# sibling"] * 6
        (tree / "kept.py").write_text(_py(body, 40 * self.N))
        assert tw.main(["--write-baseline", "base.txt", "kept.py"]) == 0
        (tree / "kept.py").write_text(_py(["# rewritten"] + ["# kept"] * 5, 40 * self.N))
        assert tw.main(["--check-baseline", "base.txt", "kept.py"]) == 0
        out = capsys.readouterr().out.splitlines()
        assert out[0] == f"note rewritten: kept.py:1: comment-block 6 > {tw.COMMENT_BLOCK_LINES} recorded one of 6, 22"
        assert out[-1] == _summary(rewritten=1, retired=1)

    def test_one_possible_source_is_named_exactly(self, tree: Path, capsys) -> None:
        (tree / "kept.py").write_text(_py(["# kept"] * 22, 40 * self.N))
        assert tw.main(["--write-baseline", "base.txt", "kept.py"]) == 0
        (tree / "kept.py").write_text(_py(["# rewritten"] + ["# kept"] * 5, 40 * self.N))
        assert tw.main(["--check-baseline", "base.txt", "kept.py"]) == 0
        out = capsys.readouterr().out.splitlines()
        assert out[0] == f"note rewritten: kept.py:1: comment-block 6 > {tw.COMMENT_BLOCK_LINES} recorded 22"
        assert out[-1] == _summary(rewritten=1)

    def test_the_smallest_candidate_is_still_the_one_consumed(self, tree: Path, capsys) -> None:
        """Order decides the GATE: give the 6-block the 22 and the 22-block has nothing left to take. The rows
        are RECORDED largest first, so the pool is not already sorted and dropping the sort cannot hide."""
        (tree / "kept.py").write_text(_py(["# kept"] * 22 + ["x = 0", ""] + ["# sibling"] * 6, 40 * self.N))
        assert tw.main(["--write-baseline", "base.txt", "kept.py"]) == 0
        (tree / "kept.py").write_text(_py(["# A"] * 6 + ["x = 0", ""] + ["# B"] * 22, 40 * self.N))
        assert tw.main(["--check-baseline", "base.txt", "kept.py"]) == 0
        assert capsys.readouterr().out.splitlines()[-1] == _summary(rewritten=2)

    def test_every_offender_names_the_rows_that_stood_before_any_was_matched(self, tree: Path, capsys) -> None:
        """Consuming left to right would leave the last offender naming one row as fact; all three could be its own."""
        body = ["# a"] * 6 + ["x = 0", ""] + ["# b"] * 10 + ["y = 0", ""] + ["# c"] * 22
        (tree / "kept.py").write_text(_py(body, 60 * self.N))
        assert tw.main(["--write-baseline", "base.txt", "kept.py"]) == 0
        (tree / "kept.py").write_text(_py(["# A"] * 6 + ["x = 0", ""] + ["# B"] * 6 + ["y = 0", ""] + ["# C"] * 6, 60 * self.N))
        assert tw.main(["--check-baseline", "base.txt", "kept.py"]) == 0
        out = capsys.readouterr().out.splitlines()
        assert [o.split(" recorded ")[1] for o in out[:3]] == ["one of 6, 10, 22"] * 3

    def test_a_row_already_claimed_by_its_own_anchor_is_not_offered_as_a_source(self, tree: Path, capsys) -> None:
        """The snapshot is taken AFTER the anchor-keyed matches: those rows were identified, not guessed at."""
        (tree / "kept.py").write_text(_py(["# a"] * 10 + ["x = 0", ""] + ["# b"] * 22, 60 * self.N))
        assert tw.main(["--write-baseline", "base.txt", "kept.py"]) == 0
        live = ["# a"] * 10 + ["x = 0", ""] + ["# B"] * 6
        (tree / "kept.py").write_text(_py(live, 60 * self.N))
        assert tw.main(["--check-baseline", "base.txt", "kept.py"]) == 0
        out = capsys.readouterr().out.splitlines()
        assert out[0].endswith("recorded 22")  # not "one of 10, 22": the 10 is `# a`'s, matched by its anchor
        assert out[-1] == _summary(rewritten=1)

    def test_candidates_of_one_size_name_it_rather_than_offering_a_choice(self, tree: Path, capsys) -> None:
        """Two same-size rows: which one was the source does not change what was recorded."""
        (tree / "kept.py").write_text(_py(["# a"] * 6 + ["x = 0", ""] + ["# b"] * 6, 40 * self.N))
        assert tw.main(["--write-baseline", "base.txt", "kept.py"]) == 0
        (tree / "kept.py").write_text(_py(["# A"] * 6 + ["x = 0", ""] + ["# B"] * 6, 40 * self.N))
        assert tw.main(["--check-baseline", "base.txt", "kept.py"]) == 0
        out = capsys.readouterr().out.splitlines()
        assert all(o.endswith("recorded 6") for o in out[:2])

    def test_a_rewritten_keep_that_grew_with_nothing_larger_to_absorb_it_fails(self, tree: Path, capsys) -> None:
        (tree / "kept.py").write_text(_py(["# rewritten"] + ["# kept"] * self.N, 6 * self.N))
        assert tw.main(["--check-baseline", "base.txt", "kept.py"]) == 1
        assert capsys.readouterr().out.splitlines()[-1] == _summary(new=1, retired=1)

    def test_one_retired_row_absorbs_one_offender_and_no_more(self, tree: Path, capsys) -> None:
        """The count is what the gate reads: a rewrite beside a genuinely new block still fails."""
        body = ["# rewritten"] + ["# kept"] * (self.N - 1) + ["x = 0", ""] + ["# brand new"] * self.N
        (tree / "kept.py").write_text(_py(body, 14 * self.N))  # code enough that only the block bars can trip
        assert tw.main(["--check-baseline", "base.txt", "kept.py"]) == 1
        assert capsys.readouterr().out.splitlines()[-1] == _summary(new=1, rewritten=1)

    def test_a_retired_row_of_another_kind_does_not_absorb_it(self, tree: Path, capsys) -> None:
        """The recorded row is LARGER than the offender's measure, so only the kind guard can refuse it."""
        (tree / "kept.py").write_text(_py(["# kept"] * 40, 6 * 40))
        assert tw.main(["--write-baseline", "base.txt", "kept.py"]) == 0
        (tree / "kept.py").write_text("# a\n# b\n" + "".join(f"x{i} = {i}\n" for i in range(tw.FILE_PROSE_FLOOR)))
        assert tw.main(["--check-baseline", "base.txt", "kept.py"]) == 1
        assert capsys.readouterr().out.splitlines()[-1] == _summary(new=1, retired=1)

    def test_a_retired_row_in_another_file_does_not_absorb_it(self, tree: Path, capsys) -> None:
        (tree / "kept.py").unlink()
        (tree / "other.py").write_text(_py(["# kept"] * self.N, 6 * self.N))
        assert tw.main(["--check-baseline", "base.txt", "other.py"]) == 1
        assert capsys.readouterr().out.splitlines()[-1] == _summary(new=1, retired=1)

    def test_a_block_that_grew_by_a_line_fails_and_is_counted_grown(self, tree: Path, capsys) -> None:
        """The anchor matched and the size rose: one grown block, not one new offender beside one retired keep."""
        (tree / "kept.py").write_text(_py(["# kept"] * (self.N + 1), 6 * self.N))
        assert tw.main(["--check-baseline", "base.txt", "kept.py"]) == 1
        out = capsys.readouterr().out.splitlines()
        assert out[0] == f"fail grown: kept.py:1: comment-block {self.N + 1} > {tw.COMMENT_BLOCK_LINES} recorded {self.N}"
        assert out[-1] == _summary(grown=1)

    def test_the_recorded_block_unchanged_passes(self, tree: Path, capsys) -> None:
        assert tw.main(["--check-baseline", "base.txt", "kept.py"]) == 0
        assert capsys.readouterr().out.splitlines() == [_summary()]

    def test_a_block_that_shrank_but_is_still_over_the_bar_fails_until_it_is_banked(self, tree: Path, capsys) -> None:
        """A cut is the improvement the ratchet exists to allow, and it FAILS until the row comes down
        with it: while the row keeps the old size it licenses the way back, silently."""
        big = tw.COMMENT_BLOCK_LINES + 3
        (tree / "kept.py").write_text(_py(["# kept"] * big, 6 * big))
        assert tw.main(["--write-baseline", "base.txt", "kept.py"]) == 0
        (tree / "kept.py").write_text(_py(["# kept"] * (big - 1), 6 * big))
        assert tw.main(["--check-baseline", "base.txt", "kept.py"]) == 1
        assert capsys.readouterr().out.splitlines() == [
            f"fail shrunk: kept.py:1: comment-block {big - 1} > {tw.COMMENT_BLOCK_LINES} recorded {big}",
            _summary(shrunk=1),
        ]
        assert tw.main(["--write-baseline", "base.txt", "kept.py"]) == 0
        assert tw.main(["--check-baseline", "base.txt", "kept.py"]) == 0  # banked: the ceiling came down

    def test_a_second_offender_in_a_recorded_file_fails_and_names_it(self, tree: Path, capsys) -> None:
        block = _py(["# kept"] * self.N, 6 * self.N)
        (tree / "kept.py").write_text(block + _py(["# other"] * self.N, 6 * self.N))
        assert tw.main(["--check-baseline", "base.txt", "kept.py"]) == 1
        out = capsys.readouterr().out.splitlines()
        assert out[0] == f"fail new: kept.py:{7 * self.N + 1}: comment-block {self.N} > {tw.COMMENT_BLOCK_LINES}"
        assert out[-1] == _summary(new=1)

    def test_a_duplicate_of_the_recorded_offender_is_new_and_not_the_keep_grown(self, tree: Path, capsys) -> None:
        """The recorded entry is consumed by the first block, so the second has nothing smaller to have grown from."""
        block = _py(["# kept"] * self.N, 6 * self.N)
        (tree / "kept.py").write_text(block + block)
        assert tw.main(["--check-baseline", "base.txt", "kept.py"]) == 1
        out = capsys.readouterr().out.splitlines()
        assert out[0] == f"fail new: kept.py:{7 * self.N + 1}: comment-block {self.N} > {tw.COMMENT_BLOCK_LINES}"
        assert out[-1] == _summary(new=1)

    def test_an_offender_in_an_unrecorded_file_fails_and_is_printed(self, tree: Path, capsys) -> None:
        (tree / "fresh.py").write_text(_py(["# fresh"] * self.N, 6 * self.N))
        assert tw.main(["--check-baseline", "base.txt", "kept.py", "fresh.py"]) == 1
        out = capsys.readouterr().out.splitlines()
        assert out[0] == f"fail new: fresh.py:1: comment-block {self.N} > {tw.COMMENT_BLOCK_LINES}"
        assert out[-1] == _summary(new=1)

    def test_a_cleaned_offender_passes_and_is_reported_retired(self, tree: Path, capsys) -> None:
        (tree / "kept.py").write_text("y = 0\n")
        assert tw.main(["--check-baseline", "base.txt", "kept.py"]) == 0
        assert capsys.readouterr().out.splitlines() == [
            f"note retired: kept.py: comment-block {self.N} recorded -- # kept",
            _summary(retired=1),
        ]

    def test_a_failing_check_names_the_remedy_on_stderr(self, tree: Path, capsys) -> None:
        (tree / "fresh.py").write_text(_py(["# fresh"] * self.N, 6 * self.N))
        assert tw.main(["--check-baseline", "base.txt", "kept.py", "fresh.py"]) == 1
        assert "--write-baseline base.txt" in capsys.readouterr().err

    def test_a_passing_check_says_nothing_on_stderr(self, tree: Path, capsys) -> None:
        assert tw.main(["--check-baseline", "base.txt", "kept.py"]) == 0
        assert capsys.readouterr().err == ""

    def test_a_missing_baseline_exits_two_and_says_so(self, tree: Path, capsys) -> None:
        assert tw.main(["--check-baseline", "no-such.txt", "kept.py"]) == 2
        assert "no-such.txt" in capsys.readouterr().err


def test_the_pre_commit_hook_runs_the_check_against_the_committed_baseline() -> None:
    """The ratchet is inert unless .pre-commit-config.yaml wires it over the script's own scope."""
    config = yaml.safe_load((_REPO / ".pre-commit-config.yaml").read_text())
    hooks = [h for repo in config["repos"] if repo["repo"] == "local" for h in repo["hooks"]]
    hook = next(h for h in hooks if h["id"] == "prose-tripwire")
    assert "--check-baseline" in hook["entry"]
    assert _BASELINE in hook["entry"]
    assert hook["always_run"] is True and hook["pass_filenames"] is False
    assert (_REPO / _BASELINE).is_file(), "the hook names a baseline that is not committed"


class TestAScopedWriteBaselineWillNotTruncateTheRest:
    """`--write-baseline` opens its target truncating, so a scoped scan replaces every other file's
    recorded keeps with nothing. It refuses instead of writing (T0195)."""

    @pytest.fixture
    def repo(self, tmp_path: Path, monkeypatch) -> Path:
        monkeypatch.chdir(tmp_path)
        subprocess.run([*_GIT, "init", "-q"], check=True)
        (tmp_path / "cli").mkdir()
        n = tw.COMMENT_BLOCK_LINES + 1
        for name in ("one.py", "two.py"):
            (tmp_path / "cli" / name).write_text(_py([f"# {name}"] * n, 6 * n))
            subprocess.run([*_GIT, "add", "-f", f"cli/{name}"], check=True)
        assert tw.main(["--write-baseline", "base.txt"]) == 0
        recorded = (tmp_path / "base.txt").read_text().splitlines()
        assert len(recorded) == 2, recorded  # the selection, asserted before anything depends on it
        return tmp_path

    def test_a_scoped_write_over_a_broader_baseline_refuses_and_leaves_it_whole(self, repo: Path, capsys) -> None:
        before = (repo / "base.txt").read_text()

        assert tw.main(["--write-baseline", "base.txt", "cli/one.py"]) == 2

        assert (repo / "base.txt").read_text() == before, "the baseline was rewritten by a refused run"
        assert "cli/two.py" in capsys.readouterr().err  # WHICH keep the write would have dropped

    def test_an_unscoped_write_still_rewrites_the_whole_baseline(self, repo: Path) -> None:
        """The true positive: refusing every write would be an always-refusing guard shipping green."""
        (repo / "cli" / "one.py").write_text("x = 1\n")

        assert tw.main(["--write-baseline", "base.txt"]) == 0

        assert [r.split(":")[0] for r in (repo / "base.txt").read_text().splitlines()] == ["cli/two.py"]

    def test_a_scoped_write_covering_every_recorded_path_is_written(self, repo: Path) -> None:
        """Nothing is lost when the scan spans the baseline, so the shape itself is not the defect."""
        assert tw.main(["--write-baseline", "base.txt", "cli/one.py", "cli/two.py"]) == 0
        assert len((repo / "base.txt").read_text().splitlines()) == 2

    def test_a_scoped_write_to_a_baseline_that_does_not_exist_yet_is_written(self, repo: Path) -> None:
        """A first write discards nothing, which is what every scoped call in this file relies on."""
        assert tw.main(["--write-baseline", "fresh.txt", "cli/one.py"]) == 0
        assert [r.split(":")[0] for r in (repo / "fresh.txt").read_text().splitlines()] == ["cli/one.py"]

    def test_an_unscoped_write_reports_the_keeps_it_drops_rather_than_refusing(self, repo: Path, capsys) -> None:
        """The remedy the refusal prescribes is itself narrowing when a recorded file has left the
        worktree, so it says so and writes -- refusing here would dead-end the only route left."""
        (repo / "cli" / "two.py").unlink()  # still in the index; `default_paths` scans what is on disk

        assert tw.main(["--write-baseline", "base.txt"]) == 0

        assert [r.split(":")[0] for r in (repo / "base.txt").read_text().splitlines()] == ["cli/one.py"]
        assert "cli/two.py" in capsys.readouterr().err  # WHICH keep went with the write

    def test_a_target_that_is_not_a_baseline_is_refused_rather_than_parsed(self, repo: Path, capsys) -> None:
        """A mistyped target is prose, not rows; it is refused whole rather than raising mid-parse."""
        before = (repo / "cli" / "one.py").read_text()

        assert tw.main(["--write-baseline", "cli/one.py", "cli/one.py"]) == 2

        assert (repo / "cli" / "one.py").read_text() == before
        assert "not a baseline" in capsys.readouterr().err


class TestAShrinkSpendsItsCeilingInTheOpen:
    """A recorded size is a ceiling, not a fact about the tree, so a shrink leaves headroom behind it.
    The check reports every shape of that rather than writing: the write is `--write-baseline`'s."""

    RECORDED = 7
    SHRUNK = 5

    @pytest.fixture
    def tree(self, tmp_path: Path, monkeypatch) -> Path:
        monkeypatch.chdir(tmp_path)
        assert self.SHRUNK != self.RECORDED, "equal sizes pass under the defect and prove nothing"
        assert self.SHRUNK > tw.COMMENT_BLOCK_LINES, "the shrunk block must still trip, or this is the retired case"
        (tmp_path / "kept.py").write_text(_py(["# kept"] * self.RECORDED, 6 * self.RECORDED))
        assert tw.main(["--write-baseline", "base.txt", "kept.py"]) == 0
        return tmp_path

    def _shrink(self, tree: Path) -> None:
        (tree / "kept.py").write_text(_py(["# kept"] * self.SHRUNK, 6 * self.RECORDED))

    def test_a_shrink_that_still_trips_fails_rather_than_being_swallowed(self, tree: Path, capsys) -> None:
        self._shrink(tree)

        failed = tw.main(["--check-baseline", "base.txt", "kept.py"])

        out = capsys.readouterr().out.splitlines()
        assert failed == 1
        assert out[0] == (
            f"fail shrunk: kept.py:1: comment-block {self.SHRUNK} > {tw.COMMENT_BLOCK_LINES} recorded {self.RECORDED}"
        )
        assert out[-1] == _summary(shrunk=1)

    def test_a_regrowth_to_the_recorded_size_fails_once_the_shrink_was_banked(self, tree: Path, capsys) -> None:
        """The ceiling actually comes down: banked at the shrunk size, growing back to what the
        baseline once recorded is a `grown` failure -- which under the old ratchet passed silently."""
        self._shrink(tree)
        assert tw.main(["--write-baseline", "base.txt", "kept.py"]) == 0
        capsys.readouterr()

        (tree / "kept.py").write_text(_py(["# kept"] * self.RECORDED, 6 * self.RECORDED))

        assert tw.main(["--check-baseline", "base.txt", "kept.py"]) == 1
        assert capsys.readouterr().out.splitlines()[0] == (
            f"fail grown: kept.py:1: comment-block {self.RECORDED} > {tw.COMMENT_BLOCK_LINES} recorded {self.SHRUNK}"
        )

    def test_a_keep_at_the_size_the_baseline_records_still_passes(self, tree: Path, capsys) -> None:
        """The true-positive control for the arm above: enforcement refusing an unchanged keep would
        refuse every commit in the repo."""
        assert tw.main(["--check-baseline", "base.txt", "kept.py"]) == 0
        assert capsys.readouterr().out.splitlines() == [_summary()]

    def test_a_keep_still_at_its_recorded_size_reports_nothing(self, tree: Path, capsys) -> None:
        """The true positive: a report that fired on an unchanged keep would fire on every commit."""
        tw.main(["--check-baseline", "base.txt", "kept.py"])
        assert capsys.readouterr().out.splitlines() == [_summary()]

    def test_a_retired_row_is_named_and_not_only_counted(self, tree: Path, capsys) -> None:
        """A row whose block no longer trips can never fail again, so a reader has to be able to find it."""
        (tree / "kept.py").write_text(_py(["# kept"] * tw.COMMENT_BLOCK_LINES, 6 * self.RECORDED))

        tw.main(["--check-baseline", "base.txt", "kept.py"])

        out = capsys.readouterr().out.splitlines()
        assert out[0] == f"note retired: kept.py: comment-block {self.RECORDED} recorded -- # kept"
        assert out[-1] == _summary(retired=1)

    def test_only_the_lines_that_fail_the_gate_carry_the_marker(self, tree: Path, capsys) -> None:
        """A wrapped line's continuation renders flush left whatever its first row did, so the column
        cannot carry this and the marker does. Absence of `fail` is what says a line is not one."""
        self._shrink(tree)
        (tree / "grown.py").write_text(_py(["# grown"] * (self.RECORDED + 1), 6 * self.RECORDED))
        assert tw.main(["--write-baseline", "grown-base.txt", "grown.py"]) == 0
        (tree / "grown.py").write_text(_py(["# grown"] * (self.RECORDED + 2), 6 * self.RECORDED))

        failed = tw.main(["--check-baseline", "base.txt", "kept.py", "grown.py"])

        out = capsys.readouterr().out.splitlines()
        assert failed == 1
        assert sorted(line for line in out if line.startswith("fail ")) == [
            f"fail new: grown.py:1: comment-block {self.RECORDED + 2} > {tw.COMMENT_BLOCK_LINES}",
            f"fail shrunk: kept.py:1: comment-block {self.SHRUNK} > {tw.COMMENT_BLOCK_LINES} recorded {self.RECORDED}",
        ]
        assert [line for line in out if line.startswith("note ")] == []
        assert out[-1] == _summary(new=1, shrunk=1)  # and the summary carries neither marker

    def test_a_retired_anchor_is_budgeted_so_the_line_does_not_wrap(self, tree: Path, capsys) -> None:
        """An anchor is a whole first line, so an unbudgeted one wraps and its continuation is a row
        the marker cannot reach -- the one place a reader could still misread a report as a failure."""
        long_first = "# " + "z" * 200
        (tree / "wide.py").write_text(_py([long_first] + ["# kept"] * self.RECORDED, 6 * self.RECORDED))
        assert tw.main(["--write-baseline", "wide-base.txt", "wide.py"]) == 0
        (tree / "wide.py").write_text("y = 0\n")

        tw.main(["--check-baseline", "wide-base.txt", "wide.py"])

        retired = [line for line in capsys.readouterr().out.splitlines() if line.startswith("note retired: ")]
        assert len(retired) == 1, retired
        assert retired[0].endswith("...") and len(retired[0]) < len(long_first)


class TestNoLineTheCheckEmitsCanWrap:
    """`fail` means something only if no emitted line reaches a second row: a continuation can begin
    with the marker by accident, since an anchor is arbitrary repo prose and a path is not sanitisable."""

    def test_the_budget_is_narrower_than_the_narrowest_width_claimed(self) -> None:
        """The parameter itself, pinned: a guard that survives its own budget being wrong is not one."""
        assert tw._report_width <= 120

    @pytest.mark.parametrize("width", [80, 100, 120])
    def test_no_row_in_the_committed_baseline_renders_past_the_budget(self, width: int) -> None:
        rows = tw.read_baseline(str(_REPO / _BASELINE))
        total = sum(len(pool) for pool in rows.values())
        assert total > 1000, f"the committed baseline, not a sample: {total} rows"
        over, marked = [], []
        for (path, kind, anchor), pool in rows.items():
            for measured in pool:
                line = tw._retired_line(path, kind, measured, anchor)
                if len(line) > tw._report_width:
                    over.append(line)
                if any(c.startswith(("fail ", "note ")) for c in textwrap.wrap(line, width)[1:]):
                    marked.append(line)
        assert over == [], f"{len(over)} of {total} rows render past the budget"
        assert marked == [], f"{len(marked)} of {total} wrap onto a row that wears a marker at {width}"

    def test_a_long_anchor_and_a_long_path_are_both_clamped(self) -> None:
        """Both halves, because budgeting the anchor alone left a 164-character line the path made."""
        line = tw._retired_line("infra/" + "d/" * 40 + "x.py", "comment-block", 7, "# " + "z" * 300)
        assert len(line) == tw._report_width and line.endswith("...")


class TestTheFailureNoteArrivesAfterTheLinesItNames:
    """pre-commit merges both streams into one pipe, where stdout is block buffered and stderr is not,
    so an unflushed note is delivered before the lines it tells the reader to cut."""

    def test_the_note_follows_the_lines_when_both_streams_share_a_pipe(self, tmp_path: Path) -> None:
        (tmp_path / "kept.py").write_text(_py(["# kept"] * 5, 30))
        script = _REPO / "infra" / "scripts" / "prose-tripwire.py"
        subprocess.run([sys.executable, str(script), "--write-baseline", "base.txt", "kept.py"], cwd=tmp_path, check=True)
        (tmp_path / "fresh.py").write_text(_py(["# fresh"] * 9, 30))

        merged = subprocess.run(
            [sys.executable, str(script), "--check-baseline", "base.txt", "kept.py", "fresh.py"],
            cwd=tmp_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        ).stdout.splitlines()

        assert any(line.startswith("fail new: fresh.py") for line in merged), merged
        note = next(i for i, line in enumerate(merged) if line.startswith("cut the lines marked"))
        first_fail = next(i for i, line in enumerate(merged) if line.startswith("fail "))
        assert note > first_fail, f"the note arrived at {note}, before the lines at {first_fail}: {merged}"
