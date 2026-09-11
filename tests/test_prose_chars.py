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


def test_yaml_counts_comments_and_task_names_but_not_module_arguments(tmp_path):
    text = "# top\n- name: install the thing\n  apt:\n    name: pkg\n  # nested\n"
    assert _count(tmp_path, "a.yml", text) == len("# top") + len("install the thing") + len("# nested")
    assert _count(tmp_path, "b.yaml", "- name: a play\n") == len("a play")


def test_a_template_counts_hash_lines_and_jinja_blocks(tmp_path):
    text = "#!/bin/sh\n# rendered comment\n{# a jinja\nblock #}\necho {{ x }}\n"
    assert _count(tmp_path, "a.sh.j2", text) == len("# rendered comment") + len(" a jinja\nblock ")


def test_a_systemd_unit_counts_and_other_kinds_do_not(tmp_path):
    assert _count(tmp_path, "a.timer", "# every hour\n[Timer]\n") == len("# every hour")
    assert _count(tmp_path, "a.service", "# once\n[Service]\n") == len("# once")
    assert _count(tmp_path, "a.json", '{"#": "not a comment"}\n') == 0


def test_an_alloy_config_a_dockerfile_and_a_shebang_script_count(tmp_path):
    assert _count(tmp_path, "config.alloy", "// the stack\nlogging {}\n") == len("// the stack")
    assert _count(tmp_path, "Dockerfile", "# base\nFROM x\n") == len("# base")
    assert _count(tmp_path, "rrsync", "#!/usr/bin/python3\n# a wrapper\n") == len("# a wrapper")
    assert _count(tmp_path, "notes", "# no shebang, no suffix\n") == 0


def test_a_key_or_certificate_reads_as_no_prose(tmp_path):
    path = tmp_path / "deploy_ed25519"
    path.write_bytes(b"#!\xff\xfe binary")
    assert pc.prose_chars(path) == 0
