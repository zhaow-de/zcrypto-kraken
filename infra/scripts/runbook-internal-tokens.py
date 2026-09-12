#!/usr/bin/env python3
"""One line per runbook bullet or numbered step whose prose carries an internal token.

One line per BULLET, its tokens joined -- the count is bullets, as the entry's name and the rule's
set clause both say, so a bullet carrying three tokens is one finding to fix and not three.

    runbook-internal-tokens.py <page>...

prints `path:line token` per hit and exits 0 whether or not it found any: this is an instrument the
count list reads, not a gate, and a refusal here would block a runbook fix during an incident. A
non-zero count is the finding -- an operator reaching the page from an alert description cannot
resolve `T0160` or `spec 00106`, while a paragraph and a table row may carry one, because provenance
for a claim the tree cannot otherwise re-derive is worth keeping (the owner's ruling of 2026-09-12).
A declaration's `why` is inside its bullet and takes the rule with it.

Neither half of the reading is defined here, and that is the point -- one definition, two readers:

* the TOKEN CLASSES and the path exemption come from `tests/test_internal_terms_not_operator_visible.py`,
  which is the rule's holder for every other surface. They stay in that file rather than moving here
  because `infra/scripts/` is inside the very set that test scans for leaks: its `VERBOSE` pattern
  carries `# T0096` and `# spec 00052` as examples, so a copy of it living under `infra/scripts/`
  would read as an operator-facing leak and turn the test red on its own definition.
* the BULLET, with a wrapped item's continuation lines joined and fenced code set aside, comes from
  `infra/scripts/guidance-guard.py`'s `bullets()` -- the same reader the universal test uses, so
  "inside a bullet" means one thing across both instruments.

Both are loaded by path because neither filename is importable (a hyphen, and a test module outside
any package). A page this cannot read is reported on stderr and exits 2, so a typo in the count
list's glob is loud rather than a zero.
"""

import importlib.util
import pathlib
import sys
import types

_ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
_GUARD = _ROOT / "infra" / "scripts" / "guidance-guard.py"
_VOCABULARY = _ROOT / "tests" / "test_internal_terms_not_operator_visible.py"


def _load(path: pathlib.Path, name: str) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"runbook-internal-tokens: cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module  # a dataclass or an enum in either module resolves its own module by name
    spec.loader.exec_module(module)
    return module


def hits(text: str, guard: types.ModuleType, vocabulary: types.ModuleType) -> list[tuple[int, str]]:
    """One (line, tokens) per offending bullet, its line the item's first and its tokens comma-joined
    in the order they appear, so the caller counts bullets and still reads what each one carries."""
    found = []
    for line, bullet in guard.bullets(text):
        tokens = [token.strip() for token in vocabulary._leaks(bullet)]
        if tokens:
            found.append((line, ", ".join(dict.fromkeys(tokens))))
    return found


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: runbook-internal-tokens.py <page>...", file=sys.stderr)
        return 2
    guard = _load(_GUARD, "guidance_guard")
    vocabulary = _load(_VOCABULARY, "internal_terms_vocabulary")
    for path in argv[1:]:
        try:
            text = pathlib.Path(path).read_text()
        except OSError as exc:
            print(f"runbook-internal-tokens: cannot read {path}: {exc.strerror or exc}", file=sys.stderr)
            return 2
        for line, tokens in hits(text, guard, vocabulary):
            print(f"{path}:{line} {tokens}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
