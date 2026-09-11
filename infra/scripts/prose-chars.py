"""Print the mass of comments and docstrings, in characters, under cli/, tests/ and infra/ -- Python docstrings and comments; the full-line comments of YAML, shell, Jinja templates and systemd units; Jinja comment blocks; Ansible `name:` fields -- a number to watch, not a gate."""

import ast
import io
import pathlib
import re
import sys
import tokenize

ROOTS = ("cli", "tests", "infra")
HASHED = {".yml", ".yaml", ".sh", ".j2", ".timer", ".service"}
HASH_COMMENT = re.compile(r"^\s*(#(?!!).*?)\s*$", re.M)  # a full-line comment; a shebang is not prose
NAME_FIELD = re.compile(r"^\s*-?\s*name:\s*(\S.*?)\s*$", re.M)  # an Ansible play or task name
JINJA_COMMENT = re.compile(r"\{#(.*?)#\}", re.S)


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


def hashed_chars(source: str, suffix: str) -> int:
    total = sum(len(m.group(1)) for m in HASH_COMMENT.finditer(source))
    if suffix in {".yml", ".yaml"}:
        total += sum(len(m.group(1)) for m in NAME_FIELD.finditer(source))
    if suffix == ".j2":
        total += sum(len(m.group(1)) for m in JINJA_COMMENT.finditer(source))
    return total


def prose_chars(path: pathlib.Path) -> int:
    source = path.read_text(encoding="utf-8")
    if path.suffix == ".py":
        return python_chars(source)
    if path.suffix in HASHED:
        return hashed_chars(source, path.suffix)
    return 0


def main() -> int:
    repo = pathlib.Path(__file__).resolve().parents[2]
    files = [p for root in ROOTS for p in (repo / root).rglob("*") if p.is_file() and "__pycache__" not in p.parts]
    print(sum(prose_chars(p) for p in files))
    return 0


if __name__ == "__main__":
    sys.exit(main())
