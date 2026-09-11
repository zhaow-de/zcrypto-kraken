"""Print the mass of comments and docstrings, in characters, over the tracked files under cli/, tests/ and infra/ -- Python docstrings and comments; the full-line comments of YAML, shell, Jinja templates, systemd units, Dockerfiles, Alloy configs and shebang scripts; Jinja and Go-template comment blocks; Ansible play and task names -- a number to watch, not a gate."""

import ast
import io
import pathlib
import re
import subprocess
import sys
import tokenize

ROOTS = ("cli", "tests", "infra")
HASHED = {".yml", ".yaml", ".sh", ".zsh", ".j2", ".timer", ".service", ".cfg"}
HASH_COMMENT = re.compile(r"^\s*(#(?!!).*?)\s*$", re.M)  # a full-line comment; a shebang is not prose
SLASH_COMMENT = re.compile(r"^\s*(//.*?)\s*$", re.M)  # Alloy's comment
NAME_FIELD = re.compile(r"^\s*- name:\s*(\S.*?)\s*$", re.M)  # an Ansible play or task name -- a list item, never a module argument
JINJA_COMMENT = re.compile(r"\{#(.*?)#\}", re.S)
GO_COMMENT = re.compile(r"\{\{-?\s*/\*(.*?)\*/\s*-?\}\}", re.S)  # a Go template's comment, the notification templates' kind


def python_chars(source: str) -> int:
    total = 0
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return 0
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            doc = ast.get_docstring(node, clean=False)
            if doc:
                total += len(doc)
    for tok in tokenize.generate_tokens(io.StringIO(source).readline):
        if tok.type == tokenize.COMMENT:
            total += len(tok.string)
    return total


def hashed_chars(source: str, suffix: str, name: str = "") -> int:
    total = sum(len(m.group(1)) for m in HASH_COMMENT.finditer(source))
    if suffix in {".yml", ".yaml"} and name != "requirements.yml":  # a galaxy requirement's name is a collection, not a task
        total += sum(len(m.group(1)) for m in NAME_FIELD.finditer(source))
    if suffix == ".j2":
        total += sum(len(m.group(1)) for m in JINJA_COMMENT.finditer(source))
    return total


def prose_chars(path: pathlib.Path) -> int:
    try:
        source = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return 0  # a key, a certificate: no prose
    if path.suffix == ".py":
        return python_chars(source)
    if path.suffix in HASHED or path.name == "Dockerfile":
        return hashed_chars(source, path.suffix, path.name)
    if path.suffix == ".alloy":
        return sum(len(m.group(1)) for m in SLASH_COMMENT.finditer(source))
    if path.suffix == ".tmpl":
        return sum(len(m.group(1)) for m in GO_COMMENT.finditer(source))
    if not path.suffix and source.startswith("#!"):
        return hashed_chars(source, "")  # a script named without a suffix, its comments the shebang's language's
    return 0


def main() -> int:
    repo = pathlib.Path(__file__).resolve().parents[2]
    listed = subprocess.run(["git", "-C", str(repo), "ls-files", "-z", "--", *ROOTS], capture_output=True, text=True, check=True)
    files = [repo / rel for rel in listed.stdout.split("\0") if rel]  # tracked files alone, so a reading is a property of a commit
    print(sum(prose_chars(p) for p in files if p.is_file()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
