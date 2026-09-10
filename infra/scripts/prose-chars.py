"""Print the mass of docstrings and comments, in characters, across the Python under cli/, tests/ and infra/ — a number to watch, not a gate."""

import ast
import io
import pathlib
import sys
import tokenize

ROOTS = ("cli", "tests", "infra")


def prose_chars(path: pathlib.Path) -> int:
    source = path.read_text(encoding="utf-8")
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


def main() -> int:
    repo = pathlib.Path(__file__).resolve().parents[2]
    files = [p for root in ROOTS for p in (repo / root).rglob("*.py") if "__pycache__" not in p.parts]
    print(sum(prose_chars(p) for p in files))
    return 0


if __name__ == "__main__":
    sys.exit(main())
