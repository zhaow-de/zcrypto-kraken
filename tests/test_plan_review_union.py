"""Guard for `.claude/skills/zcrypto-plan-review/scripts/union.py`'s two load-bearing claims.

The union keeps the MAXIMUM severity when two reports grade one `path:line` differently, and its
counts come from the parsed headings rather than from any summary line a report carries. Both are
the properties a consolidating agent gets wrong (`docs/research/90.spec-plan-review-protocol.md`),
so both are pinned here with fixtures where the defect and the correct behaviour differ — and a
heading nested one level deeper, indented, or list-prefixed is still a finding, never silently a body line.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
UNION = REPO / ".claude/skills/zcrypto-plan-review/scripts/union.py"

_A = """# lens A
### [Important] · [in-original] · docs/plans/00000-x.md:12
**Quote:** `for: 1h`
**Consequence:** the rule never fires.

### [Minor] · [in-original] · docs/plans/00000-x.md:40
**Quote:** `foo`
counts: Critical 0 · Important 0 · Minor 2
"""

_B = """# lens B
### [Critical] · [last-fix] · docs/plans/00000-x.md:12
**Quote:** `for: 1h`
**Consequence:** the rule never fires and the guard it backs is defeated.

### [Important] · [in-original] · docs/plans/00000-x.md:77
**Quote:** `bar`
"""


def _run(tmp_path: Path, *reports: str) -> tuple[subprocess.CompletedProcess, str]:
    paths = []
    for i, text in enumerate(reports):
        p = tmp_path / f"r{i}.md"
        p.write_text(text, encoding="utf-8")
        paths.append(str(p))
    out = tmp_path / "union.md"
    proc = subprocess.run([sys.executable, str(UNION), str(out), *paths], capture_output=True, text=True)
    return proc, out.read_text(encoding="utf-8")


def test_shared_key_takes_the_maximum_severity_and_the_most_recent_origin(tmp_path):
    proc, text = _run(tmp_path, _A, _B)
    assert proc.returncode == 0, proc.stderr
    assert "### [Critical] · [last-fix] · docs/plans/00000-x.md:12" in text
    assert "### [Important] · [in-original] · docs/plans/00000-x.md:12" not in text
    assert "<!-- r0.md graded Important -->" in text and "<!-- r1.md graded Critical -->" in text


def test_counts_come_from_headings_not_from_a_report_summary_line(tmp_path):
    proc, _ = _run(tmp_path, _A, _B)
    # Report A's own summary line claims "Important 0"; the headings say one Critical (the merged
    # key), one Important (:77) and one Minor (:40) across three distinct keys.
    assert proc.stdout.strip() == (
        "counts (from headings): Critical 1 · Important 1 · Minor 1 · keys 3 · raw findings 4 · unparsed 0"
    )


def test_nested_indented_and_list_prefixed_findings_are_parsed_and_a_bare_title_is_surfaced(tmp_path):
    nested = """### Findings
#### [Critical] · [in-original] · docs/plans/00000-x.md:5
**Quote:** `a`
  ### [Important] · [in-original] · docs/plans/00000-x.md:6
**Quote:** `b`
- ### [Minor] · [in-original] · docs/plans/00000-x.md:7
**Quote:** `c`
"""
    proc, text = _run(tmp_path, nested)
    assert proc.returncode == 2, "the `### Findings` title is heading-shaped and unparsable — it must be surfaced"
    assert "counts (from headings): Critical 1 · Important 1 · Minor 1 · keys 3 · raw findings 3 · unparsed 1" in proc.stdout
    assert "## Unparsed" in text and "r0.md: ### Findings" in text


def test_fences_are_body_blockquotes_are_headings_and_typos_surface_without_truncating(tmp_path):
    text = """### [Important] · [in-original] · docs/plans/00000-x.md:11
**Quote:** `q`
#### Evidence
**Consequence:** kept in the body
```
### [Critical] · [in-original] · docs/plans/00000-x.md:99
```
> ### [Minor] · [in-original] · docs/plans/00000-x.md:12
**Quote:** `r`
###[Important] · [in-original] · docs/plans/00000-x.md:13
####### [Minor] · [in-original] · docs/plans/00000-x.md:14
"""
    proc, out = _run(tmp_path, text)
    assert proc.returncode == 2
    assert "counts (from headings): Critical 0 · Important 1 · Minor 1 · keys 2 · raw findings 2 · unparsed 3" in proc.stdout
    assert "**Consequence:** kept in the body" in out, "a sub-heading inside a finding must not close its body"
    assert out.count("<!-- r0.md graded") == 2, "a fenced heading is body, never its own cluster"
    unparsed = out.split("## Unparsed")[1]
    assert "#### Evidence" in unparsed and "###[Important]" in unparsed and "####### [Minor]" in unparsed


def test_fences_follow_commonmark_and_an_unclosed_one_is_surfaced(tmp_path):
    # A display block holding a fence opener: three fence lines, and the second is an opener with an
    # info string, which CommonMark says cannot close a fence. A toggle would read the trailing Minor as body.
    quoted = "### [Important] · [in-original] · docs/plans/00000-x.md:1\n**Quote:**\n```\n```bash\n```\n### [Minor] · [in-original] · docs/plans/00000-x.md:2\n**Quote:** `z`\n"
    proc, _ = _run(tmp_path, quoted)
    assert proc.returncode == 0 and "Critical 0 · Important 1 · Minor 1 · keys 2" in proc.stdout
    # A tilde fence holding a backtick run — the wrong character cannot close it — and a four-backtick fence
    # holding a three-backtick line: both headings inside are body.
    tilde_and_four = "~~~\n```\n### [Critical] · [in-original] · docs/plans/00000-x.md:9\n~~~\n````\n```\n### [Critical] · [in-original] · docs/plans/00000-x.md:8\n````\n### [Minor] · [in-original] · docs/plans/00000-x.md:3\n**Quote:** `y`\n"
    proc, _ = _run(tmp_path, tilde_and_four)
    assert proc.returncode == 0 and "Critical 0 · Important 0 · Minor 1 · keys 1" in proc.stdout
    # A fence never closed swallows every later heading; that must be said, not silent.
    unclosed = (
        "### [Important] · [in-original] · docs/plans/00000-x.md:4\n```\n### [Critical] · [in-original] · docs/plans/00000-x.md:5\n"
    )
    proc, out = _run(tmp_path, unclosed)
    assert proc.returncode == 2 and "unparsed 1" in proc.stdout
    assert "unclosed fence opened at line 2" in out
    # A fence opened inside a blockquote or a list item closes when that container ends (CommonMark), so the
    # headings after a one-line `> \`\`\`` quote are headings — and a later ```python display block, whose
    # closer cannot close a still-open fence, does not flip the parse into swallowing them.
    contained = (
        "### [Minor] · [in-original] · docs/plans/00000-x.md:1\n**Quote:**\n> ```\n"
        "### [Critical] · [in-original] · docs/plans/00000-x.md:2\n**Quote:** `c`\n"
        "### [Important] · [in-original] · docs/plans/00000-x.md:3\n**Quote:**\n```python\nx = 1\n```\n"
        "### [Minor] · [in-original] · docs/plans/00000-x.md:4\n**Quote:** `m`\n"
    )
    proc, _ = _run(tmp_path, contained)
    assert proc.returncode == 0 and "Critical 1 · Important 1 · Minor 2 · keys 4" in proc.stdout
    listed = "### [Minor] · [in-original] · docs/plans/00000-x.md:5\n- ```\n### [Important] · [in-original] · docs/plans/00000-x.md:6\n**Quote:**\n```\nRun: x\n```\n"
    proc, out = _run(tmp_path, listed)
    assert proc.returncode == 0 and "Important 1 · Minor 1 · keys 2" in proc.stdout and "unclosed" not in out
    # A closer belongs to its container: `> \`\`\`` inside a column-0 display block is content, so the block's
    # real closer still closes it and the headings after it are headings.
    quoted_bq = (
        "### [Minor] · [in-original] · docs/plans/00000-x.md:7\n**Quote:**\n```\n> ```\n> uv run pytest\n> ```\n```\n"
        "### [Critical] · [in-original] · docs/plans/00000-x.md:8\n**Quote:** `c`\n"
        "### [Important] · [in-original] · docs/plans/00000-x.md:9\n**Quote:**\n```python\nx = 1\n```\n"
        "### [Minor] · [in-original] · docs/plans/00000-x.md:10\n**Quote:** `m`\n"
    )
    proc, _ = _run(tmp_path, quoted_bq)
    assert proc.returncode == 0 and "Critical 1 · Important 1 · Minor 2 · keys 4" in proc.stdout
    # A `> - \`\`\`` opener lives in a list item inside a blockquote: a `>` line not indented to the item's content
    # column ends the item and the fence with it, so the blockquoted heading that follows is a heading.
    nested = "### [Minor] · [in-original] · docs/plans/00000-x.md:11\n> - ```\n> ### [Critical] · [in-original] · docs/plans/00000-x.md:12\n### [Important] · [in-original] · docs/plans/00000-x.md:13\n"
    proc, _ = _run(tmp_path, nested)
    assert proc.returncode == 0 and "Critical 1 · Important 1 · Minor 1 · keys 3" in proc.stdout
    # A tab is four columns: a tab-indented closer inside a list-item fence closes it.
    tabbed = "- ```\n\tcode\n\t```\n### [Critical] · [in-original] · docs/plans/00000-x.md:14\n**Quote:** `t`\n"
    proc, out = _run(tmp_path, tabbed)
    assert proc.returncode == 0 and "Critical 1 · Important 0 · Minor 0 · keys 1" in proc.stdout and "unclosed" not in out
    # A tab after the blockquote marker expands from its column: `>\t\`\`\`` is a closer, not content.
    bq_tab = "### [Minor] · [in-original] · docs/plans/00000-x.md:15\n> ```\n> code\n>\t```\n> ### [Critical] · [in-original] · docs/plans/00000-x.md:16\n"
    proc, _ = _run(tmp_path, bq_tab)
    assert proc.returncode == 0 and "Critical 1 · Important 0 · Minor 1 · keys 2" in proc.stdout
    # A display block nested four spaces under a bullet, with no marker on its own line, closes at its own indent.
    under_bullet = "### [Minor] · [in-original] · docs/plans/00000-x.md:17\n- item\n    ```\n    x\n    ```\n### [Important] · [in-original] · docs/plans/00000-x.md:18\n"
    proc, out = _run(tmp_path, under_bullet)
    assert proc.returncode == 0 and "Important 1 · Minor 1 · keys 2" in proc.stdout and "unclosed" not in out
    # An indented marker followed by a tab: the content column is the tab's stop (4), not marker-length past it,
    # so a heading at three spaces ends the item — a column of 2 would keep it inside the fence.
    marker_tab = "### [Minor] · [in-original] · docs/plans/00000-x.md:19\n  -\t```\n    ### [Critical] · [in-original] · docs/plans/00000-x.md:20\n   ### [Important] · [in-original] · docs/plans/00000-x.md:21\n"
    proc, out = _run(tmp_path, marker_tab)
    assert proc.returncode == 0 and "Critical 0 · Important 1 · Minor 1 · keys 2" in proc.stdout and "unclosed" not in out
    # A closer sits within three columns of its container, or no deeper than its opener: a four-space run after a
    # one-space opener is content, so the fence stays open and the file says so instead of flipping parity.
    flip = "### [Minor] · [in-original] · docs/plans/00000-x.md:22\n ```\n    ```\n### [Critical] · [in-original] · docs/plans/00000-x.md:23\n```\n### [Important] · [in-original] · docs/plans/00000-x.md:24\n```\n### [Minor] · [in-original] · docs/plans/00000-x.md:25\n"
    proc, out = _run(tmp_path, flip)
    assert proc.returncode == 2 and "Critical 0 · Important 1 · Minor 1 · keys 2 · raw findings 2 · unparsed 1" in proc.stdout
    assert "unclosed fence opened at line 7" in out


def test_a_heading_without_its_brackets_is_still_a_finding(tmp_path):
    """The template once wrote the shape as `[Critical|Important|Minor]`, which every reviewer read as
    choose-one notation and rendered bare. A parser keyed on literal brackets then counted a real
    Critical as zero — measured on this skill's own first live run, eleven findings, `unparsed 11`."""
    bare = (
        "### Critical · in-original · docs/plans/00000-x.md:30\n**Quote:** `a`\n"
        "### Important · last-fix · docs/plans/00000-x.md:31\n**Quote:** `b`\n"
    )
    proc, out = _run(tmp_path, bare)
    assert proc.returncode == 0, "a bare heading is a finding, not an unparsed line"
    assert "Critical 1 · Important 1 · Minor 0 · keys 2 · raw findings 2 · unparsed 0" in proc.stdout
    # Mixed forms across two reports still cluster on one key and take the maximum severity.
    proc, out = _run(tmp_path, "### Minor · in-original · docs/plans/00000-x.md:30\n**Quote:** `a`\n", bare)
    assert "Critical 1 · Important 1 · Minor 0 · keys 2" in proc.stdout


def test_a_finding_written_at_section_level_is_surfaced_not_swallowed(tmp_path):
    """A severity heading at one or two hashes is a typo of the required form. It matches the section
    pattern, so before this guard it closed the open block and vanished at exit 0 — the silent drop the
    script exists to prevent, and the one failure mode its counts cannot survive."""
    text = (
        "### [Important] · [in-original] · docs/plans/00000-x.md:40\n**Quote:** `q`\n"
        "## [Critical] · [in-original] · docs/plans/00000-x.md:41\n**Quote:** `r`\n"
        "# [Minor] · [in-original] · docs/plans/00000-x.md:42\n"
    )
    proc, out = _run(tmp_path, text)
    assert proc.returncode == 2, "a finding at section level must not pass silently"
    assert "Critical 0 · Important 1 · Minor 0 · keys 1 · raw findings 1 · unparsed 2" in proc.stdout
    unparsed = out.split("## Unparsed")[1]
    assert "## [Critical]" in unparsed and "# [Minor]" in unparsed
    # A real section heading still just closes the block, without being surfaced.
    proc, out = _run(tmp_path, "### [Minor] · [in-original] · docs/plans/00000-x.md:43\n**Quote:** `s`\n## Skips upheld\n- none\n")
    assert proc.returncode == 0 and "unparsed 0" in proc.stdout


def test_an_unparsable_heading_is_listed_and_exits_2(tmp_path):
    proc, text = _run(tmp_path, _A, "### Important — docs/plans/00000-x.md:99\nprose\n")
    assert proc.returncode == 2
    assert "## Unparsed" in text and "### Important — docs/plans/00000-x.md:99" in text
    assert "unparsed 1" in proc.stdout
