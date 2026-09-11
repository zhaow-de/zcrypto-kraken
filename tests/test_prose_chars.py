"""prose-chars.py: the comment mass of each file kind the count names, measured on fixtures whose answer is known."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SCRIPT = REPO / "infra" / "scripts" / "prose-chars.py"


def _load():
    spec = importlib.util.spec_from_file_location("prose_chars_under_test", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


pc = _load()


def _count(tmp_path: Path, name: str, text: str) -> int:
    path = tmp_path / name
    path.write_text(text)
    return pc.prose_chars(path)


def test_python_counts_docstrings_and_comments(tmp_path):
    assert _count(tmp_path, "a.py", '"""doc"""\nx = 1  # note\n') == len("doc") + len("# note")


def test_a_shell_script_counts_its_comments_but_not_the_shebang(tmp_path):
    assert _count(tmp_path, "a.sh", "#!/usr/bin/env bash\n# why\nrun  # trailing is not counted\n") == len("# why")


def test_yaml_counts_comments_and_ansible_names(tmp_path):
    text = "# top\n- name: install the thing\n  apt:\n    name: pkg\n  # nested\n"
    assert _count(tmp_path, "a.yml", text) == len("# top") + len("install the thing") + len("pkg") + len("# nested")


def test_a_template_counts_hash_lines_and_jinja_blocks(tmp_path):
    text = "#!/bin/sh\n# rendered comment\n{# a jinja\nblock #}\necho {{ x }}\n"
    assert _count(tmp_path, "a.sh.j2", text) == len("# rendered comment") + len(" a jinja\nblock ")


def test_a_systemd_unit_counts_and_other_kinds_do_not(tmp_path):
    assert _count(tmp_path, "a.timer", "# every hour\n[Timer]\n") == len("# every hour")
    assert _count(tmp_path, "a.json", '{"#": "not a comment"}\n') == 0
