# Skip-gate matcher — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every skip gate under `tests/` matches one of six enumerated forms or is refused, so the rule that no skip is decided by whether a venue answers is held by `infra/scripts/count-list.sh skip-gate-contract` rather than by nothing. Thirty-two gates are rewritten to reach that, each of them deciding whether a real test runs or skips in CI and in the nightly data-gated run, so a rewrite that moves one decision silently skips — or fails — that test on every run from then on; Task 2's recorded baseline and its re-run over the same fifteen files are what hold each decision still.

**Architecture:** `tests/test_live_venue_opt_in.py` keeps its gate discovery (the walker) and replaces its expression reducer with a matcher: a guard is matched against five manifest forms (path presence, uid, binary, the opt-in read, collection membership) plus a call into a new registry module, `tests/skip_gates.py`, whose three functions are the declarations for the 27 gates whose guard does not say what it reads. The registry is held closed by one test over its own AST. The 32 gates migrate first, under the reducer that still accepts them; the matcher then lands green; the reducer's resolution code is deleted last.

**Tech Stack:** Python 3.14, `ast`, pytest; `infra/scripts/mutate-probe.sh` for the verdicts; `topic-ops` for the closeout.

**Spec:** `docs/specs/00114-skip-gate-matcher-design.md`

## Global Constraints

- The guard file keeps its name, `tests/test_live_venue_opt_in.py`: `CLAUDE.md:33` and `infra/scripts/count-list.sh:275` name it. `CLAUDE.md` is not edited here (spec D5); the count entry at :275 is not edited either, but the COMMENT above it (`infra/scripts/count-list.sh:272-274`) describes the reducer in the same three clauses `CLAUDE.md:32` does, and Task 5 re-trues it — a comment that stays has to be correct, and unlike the guidance line it is not the owner's to write.
- Nothing is followed: an environment key is a string literal or a plain top-level `NAME = "<literal>"` assigned once in the module; every other binding is refused (spec D2).
- The registry `tests/skip_gates.py` imports only `shutil`, `subprocess`, `pathlib` and `typing`, calls only into those and builtins, and every public function's body is a single `return` (spec D4).
- No gate's decision moves in the migration: each rewritten guard is equivalent to the one it replaces — with two
  exceptions, both named in spec D8. `tests/test_tape_bars_rest_control.py`'s `day is None` skip, whose input is
  filtered by Kraken's answer, splits into a local skip and a venue `pytest.fail` (Task 2 Step 4); and
  `tests/test_config_selectors_are_parsed.py`'s `path.name in _GRANDFATHERED` skip, decided by a committed literal
  list, moves from the gate into the parametrize, so the same files go unchecked and one fewer skip line is printed
  (Task 2 Step 5). The tree's gate count therefore ends at 65, not 66.
- A commit that adds or changes a guard records its `mutate-probe.sh` verdict on that commit: the verdict is earned after the commit exists and recorded by a message-only amend of that commit, the tree frozen.
- Every commit is green over `uv run pytest tests/test_live_venue_opt_in.py tests/test_count_list.py` and the files the task touches; the branch carries no red intermediate commit (spec D8).
- A commit message ends with the `Co-Authored-By` and `Claude-Session` trailers the session reminder gives.

---

## File structure

- Create `tests/skip_gates.py` — the three declared readings.
- Modify `tests/test_live_venue_opt_in.py` — the matcher (`Form`, `_match`, `_plain_literal`, `_plain_collection`, `_key`, `_is_environ`, `_env_read_key`, `_bound_to_module`, `_registry_call`, and the receiver rule `_bindings`, `_rooted`, `_unrooted`) replaces the reducer (`Reading`, `_NOTHING`, `_reads`, `_refuses`, `_locals_of`, `_classify`, `_fold`, `_owned_class`, `_owned_attribute`, `_classify_call`, `_read_module`, `_resolve`, `_follow`, `_environment_key`, `_PREDICATES`, `_BUILTINS`, `_MAPPING_READS`, `_MAPPING_VIEWS`, `_module_strings`, `_module_functions`, `_module_aliases`, `_module_path`, `_is_local_module`, `_is_environ_expression`, `_environ_aliases`, `_assigned`, `_module_scope`, `_body_expressions`, `OURS`); `Module` slims to `tree`, `imported`, `os_names`, `label`; `_os_aliases`, `_imported`, `_module`, `_module_of`, `_parents`, `_guards_of`, `_as_expression`, `_pytest_bindings`, `_pytest_modules`, `_skip_helpers`, `_is_pytest_call`, `_enclosing_function`, `_gates`, `_labelled`, `_second_flags`, `_unreadable`, `_tree_gates`, `_FIXTURE`, `_FIXTURE_GATES` stay — `_enclosing_function` because `_rooted` resolves a receiver's root in the gate's own function; the module docstring is rewritten to what the file then holds.
- Modify the thirteen test files that carry the 32 gates: the eight of the 22 — `tests/test_count_list.py`, `tests/test_infra_archive_pull_template.py`, `tests/test_infra_tape_bars_template.py`, `tests/test_infra_verify_replay_template.py`, `tests/test_costmin_drift.py`, `tests/test_engine_venuestate.py`, `tests/test_registry_conformance.py`, `tests/test_tape_bars_rest_control.py` — and the five of the ten D2's receiver rule adds: `tests/test_record43_book.py`, `tests/test_record44_legs.py`, `tests/test_derivatives_oi.py`, `tests/test_derivatives_funding.py`, `tests/test_config_selectors_are_parsed.py` (`tests/test_tape_bars_rest_control.py` carries one of those ten too).
- Modify `docs/open-topics/T0190-live-venue-opt-in-flags-disagree.md` (moved to `archive/`), create FOUR topics — the
  registry's unverifiable argument, gate discovery beyond the fixture's positions, the guidance clauses this branch
  falsifies, and the venue answer a `/` join carries past the receiver rule — and re-render
  `docs/open-topics/README.md` at closeout.
- Modify `infra/scripts/count-list.sh` — the comment above `c_skip_gate_contract` (:272-274), re-trued in Task 5.

---

### Task 1: The registry and the test that holds it closed

**Files:**
- Create: `tests/skip_gates.py`
- Modify: `tests/test_live_venue_opt_in.py` (constants after `OPT_IN` at line 88; one test after `test_the_tree_holds_the_control_that_keeps_the_one_name_assertion_falsifiable`)
- Test: `tests/test_live_venue_opt_in.py::test_the_registry_reads_nothing_a_form_could_not`

**Interfaces:**
- Produces: `tests.skip_gates.develop_resolves() -> bool`, `tests.skip_gates.no_binary(name: str) -> bool`, `tests.skip_gates.nothing_found(rows: object) -> bool`; in the guard file `REGISTRY = TESTS / "skip_gates.py"`, `REGISTRY_MODULE` derived from it, and `REGISTRY_IMPORTS = frozenset({"shutil", "subprocess", "pathlib", "typing"})`. `REGISTRY` and `REGISTRY_IMPORTS` are read by this task's test alone; `REGISTRY_MODULE` is the dotted name Task 3's `_registry_call` keys on, derived from `REGISTRY` so the path and the module name cannot disagree. Also produces `_receiver_root(node) -> ast.AST` and `_call_root(node) -> str`, the chain walk and the text spelling of its answer: `_call_root` is read by this task's test, `_receiver_root` by spec 00114 Task 3's `_rooted`. Neither is named in either column of the File structure, so Task 5 leaves both.

- [ ] **Step 1: Write the failing test**

After `OPT_IN = "ZCRYPTO_LIVE_VENUE_TESTS"`:

```python
REGISTRY = TESTS / "skip_gates.py"
# The dotted name `_registry_call` keys on, derived from the path so the two cannot drift apart.
REGISTRY_MODULE = f"{TESTS.name}.{REGISTRY.stem}"
REGISTRY_IMPORTS = frozenset({"shutil", "subprocess", "pathlib", "typing"})
# The builtins the registry may call: NONE -- its three functions call only what their imports bind.
# An allowlist and not a blocklist of the importing ones, because no blocklist holds:
# `__import__("socket")` is an `ast.Call` and not an `ast.Import`, so the import allowlist below never
# sees it, and `globals()["__builtins__"]["__import__"]` reaches it without naming it.
REGISTRY_BUILTINS: frozenset[str] = frozenset()
# Every word `develop_resolves()`'s argv may carry, each of them a literal. `git` is itself a network
# client, so its name at argv[0] constrains nothing: `ls-remote`, `fetch` and a
# `-c protocol.ext.allow=<transport>` all reach a remote under it, and a skip would then be decided by
# whether that remote answers. The checkout the launch runs in is `cwd=REPO` and no word of the argv.
REGISTRY_GIT_ARGV = frozenset({"git", "rev-parse", "--verify", "--quiet", "develop"})
```

After the control test:

```python
def _receiver_root(node: ast.AST) -> ast.AST:
    """The leftmost operand of an attribute, call, subscript or `/` chain -- `Path` in
    `Path(x).resolve()`, `p` in `(p / "x").parent`. What a chain reads is decided there and nowhere
    else, which is what both readers below ask: the registry test through `_call_root`, and the
    receiver rule of spec 00114 Task 3, which walks `/` as well because a path is built with it."""
    while isinstance(node, (ast.Attribute, ast.Subscript, ast.Call)) or (
        isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div)
    ):
        node = node.func if isinstance(node, ast.Call) else node.left if isinstance(node, ast.BinOp) else node.value
    return node


def _call_root(node: ast.AST) -> str:
    """The name a call reaches through, as text for a refusal message: `shutil` in
    `shutil.which(...)`, so a chained call is judged by what it started from rather than by its first
    dotted segment."""
    root = _receiver_root(node)
    return root.id if isinstance(root, ast.Name) else ast.unparse(root)


def test_the_registry_reads_nothing_a_form_could_not():
    """A call into `tests/skip_gates.py` is a form (spec 00114 D3), so the module is held closed: its
    imports are within the four named, every call reaches a name one of those imports binds or a
    builtin it is allowlisted for, the one process it may launch is a `git` every word of whose argv
    is a literal on the allowlist -- the checkout it runs in is handed to `cwd`, never written as a
    word -- and every function it defines anywhere -- private ones too -- is one `return`. A registry
    that could open a socket would be the reducer's leak, one file over -- and `subprocess` is on the
    allowlist, so the launch and the walk are what close that direction."""
    tree = ast.parse(REGISTRY.read_text(), str(REGISTRY))
    bound = {
        (alias.asname or alias.name).split(".")[0]: (node.module if isinstance(node, ast.ImportFrom) else alias.name).split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    imported = set(bound.values())
    assert imported <= REGISTRY_IMPORTS, f"the registry imports {sorted(imported - REGISTRY_IMPORTS)}"
    calls = [call for call in ast.walk(tree) if isinstance(call, ast.Call)]
    roots = {_call_root(call.func) for call in calls}
    allowed = set(bound) | REGISTRY_BUILTINS
    assert roots <= allowed, f"the registry calls {sorted(roots - allowed)}"
    for call in calls:
        if bound.get(_call_root(call.func)) != "subprocess":
            continue
        argv = call.args[0] if call.args else None
        launched = (
            isinstance(argv, ast.List) and argv.elts and isinstance(argv.elts[0], ast.Constant) and argv.elts[0].value == "git"
        )
        assert launched, f"a process launch that is not git: {ast.unparse(call)}"
        literals = all(isinstance(e, ast.Constant) and isinstance(e.value, str) for e in argv.elts)
        assert literals, f"a git argv word that is not a string literal: {ast.unparse(argv)}"
        words = {e.value for e in argv.elts}
        assert words <= REGISTRY_GIT_ARGV, f"a git that may leave this repo: {sorted(words - REGISTRY_GIT_ARGV)}"
    defined = [f for f in ast.walk(tree) if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef))]
    assert {f.name for f in defined if not f.name.startswith("_")} == {"develop_resolves", "no_binary", "nothing_found"}
    for f in defined:
        body = [s for s in f.body if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant))]
        assert len(body) == 1 and isinstance(body[0], ast.Return), f"{f.name} is more than one return"
```

`bound` maps each name an import binds to the module it came from, so the import check and the call
check read one dict: a call may reach only a name an allowlisted import bound, or a builtin on an
allowlist that is empty. EVERY clause here resolves through `bound` rather than through a literal
name, and that is the point of the dict: measured against the plan's own registry with one line
changed, `import subprocess as sp` with `sp.run(["curl", ...])` and `from subprocess import run` with
`run(["curl", ...])` both pass a launch clause keyed on the literal root `subprocess`. `ast.walk`
rather than `tree.body` for the functions, and the `git` constraint on the launch, are the two clauses
that refuse a registry carrying
`if shutil.which("curl"): def venue_answers(): return subprocess.run(["curl", ...])` — which passes
every other clause; walking every `FunctionDef` rather than only the public ones is what stops a
private helper from carrying a loop, a retry or a probe the three public names may not.

Two clauses are allowlists where a blocklist is the obvious shape, each because the blocklist was
measured not to hold. `REGISTRY_BUILTINS` over `dir(builtins)` minus the four importing names: `return not
globals()["__builtins__"]["__import__"]("socket").create_connection(...)` reaches the module through a
dict key, so neither a roots check over `dir(builtins)` nor a `Name`-load check of those four ever
sees it, and it passed every clause. `REGISTRY_GIT_ARGV` over `argv[0] == "git"`: `git ls-remote
--exit-code origin refs/heads/develop` is the natural repair for the very failure
`develop_resolves()`'s docstring names, and under a head-only clause it passes and the ten
`tests/test_count_list.py` gates then skip whenever the remote is unreachable.

The element clause runs FIRST and admits a literal and nothing else, so `words` is built over every
element rather than over the `Constant` ones among them and no word is judged by nothing. Five
spellings reached a remote while the element shape was unpinned, each measured against the plan's own
registry with one line changed: a splat of a module-level list (`*_REMOTE`, `_REMOTE = ["ls-remote",
"origin"]`), a concatenation (`"ls-" + "remote"`), an f-string (`f"ls-remote"`), a bare name (`_VERB =
"ls-remote"`), and a call whose root was allowlisted (`str("ls-remote")`). The first FOUR pass every
other clause and this one refuses them naming the argv; the fifth is a call, and with the builtin
allowlist empty the roots clause now reaches it first (`the registry calls ['str']`, measured), which
is why Step 6's fourth probe is written as an f-string.

The clause can be literals-only because the launch names this checkout with `cwd=REPO` rather than
with a `git -C str(REPO)` in the argv. An element clause that admitted that one word by its TEXT
judged neither what `REPO` was bound to nor where in the argv the word sat, so a registry whose
`REPO = "ls-remote"` and whose argv was `["git", str(REPO)]` passed every clause it then had --
measured, and the reason the path moved to `cwd` rather than the clause growing a second arm. What no
clause PINS is the shape of the launch's keywords -- though the roots clause judges any call written
in one, `cwd=_venue_dir()` refused as a call the registry may not make (measured) -- so what `cwd` may
name is a literal path or the `pathlib` expression `REPO` binds: a directory, the reading the path
form already allows, and never a remote.

- [ ] **Step 2: Run it and read WHICH failure fired**

Run: `uv run pytest tests/test_live_venue_opt_in.py -k registry_reads_nothing -q`
Expected: FAIL with `FileNotFoundError` on `REGISTRY.read_text()` — the module does not exist yet.

- [ ] **Step 3: Write the registry**

Create `tests/skip_gates.py`:

```python
"""Declared readings for skip gates whose guard does not say what it reads.

A skip gate's guard matches one of `tests/test_live_venue_opt_in.py`'s forms, and a call into this
module is one of them: the call is the declaration, made where a reviewer greps for it. A function
here reads the filesystem, the repo, or the value it is handed, and nothing else --
`test_the_registry_reads_nothing_a_form_could_not` holds the module to that.
"""

import shutil
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def develop_resolves() -> bool:
    """`develop` is a ref this checkout can resolve; a shallow CI clone may lack it."""
    return subprocess.run(["git", "rev-parse", "--verify", "--quiet", "develop"], cwd=REPO, capture_output=True).returncode == 0


def no_binary(name: str) -> bool:
    """The named executable is not on PATH."""
    return shutil.which(name) is None


def nothing_found(rows: object) -> bool:
    """A local scan -- a glob, an index read, a registry filter -- found nothing. The caller declares
    the scan was local; this function only says whether it was empty."""
    return not rows
```

- [ ] **Step 4: Run it to verify it passes**

Run: `uv run pytest tests/test_live_venue_opt_in.py -q`
Expected: every case passes, the new one included; `_tree_gates()` still walks 66 gates (the registry module carries no skip).

- [ ] **Step 5: Commit**

```bash
git add tests/skip_gates.py tests/test_live_venue_opt_in.py
git commit -m "test(venue): the skip-gate registry, held closed by its own test"
```

- [ ] **Step 6: Prove the guard bites, then amend the body with the verdict**

The import allowlist:

```bash
infra/scripts/mutate-probe.sh --file tests/skip_gates.py --control 's/^def nothing_found/def nothing_seen/' --mutation 's/^import shutil$/import shutil, socket/' -- uv run pytest tests/test_live_venue_opt_in.py -k registry_reads_nothing -q
```

The escape past it, which is the clause spec D4 rests on and the one an import allowlist cannot hold:

```bash
infra/scripts/mutate-probe.sh --file tests/skip_gates.py --control 's/^def nothing_found/def nothing_seen/' --mutation 's|^    return not rows$|    return not __import__("socket").create_connection(("api.kraken.com", 443), timeout=2)|' -- uv run pytest tests/test_live_venue_opt_in.py -k registry_reads_nothing -q
```

The git that leaves the repository, which is the clause D4 rests on and the one `argv[0] == "git"`
cannot hold:

```bash
infra/scripts/mutate-probe.sh --file tests/skip_gates.py --control 's/^def nothing_found/def nothing_seen/' --mutation 's/"rev-parse"/"ls-remote"/' -- uv run pytest tests/test_live_venue_opt_in.py -k registry_reads_nothing -q
```

The same `ls-remote` written as something other than a literal, which is the clause the word
allowlist cannot hold on its own — `words` never sees the word:

```bash
infra/scripts/mutate-probe.sh --file tests/skip_gates.py --control 's/^def nothing_found/def nothing_seen/' --mutation 's/"rev-parse"/f"ls-remote"/' -- uv run pytest tests/test_live_venue_opt_in.py -k registry_reads_nothing -q
```

Expected, each: `KILLED (control proven, tree restored byte-identically)` — the first mutation adds an
import the allowlist refuses, the second adds none and is caught by the builtin allowlist alone, the
third leaves a `git` whose argv the word allowlist refuses, and the fourth a `git` whose `ls-remote`
is an f-string rather than a literal, which only the element clause sees -- an f-string and not a
`str("ls-remote")` because the builtin allowlist is empty, so a CALL in the argv is refused by the
roots clause too and the probe would no longer be about the element clause; the control renames a
public function, which the name assertion catches. `"rev-parse"` appears once in the registry, so the
third and fourth mutations' `sed`s each match one line. Then `git commit --amend` adding one paragraph: `Proven with infra/scripts/mutate-probe.sh on tests/skip_gates.py: the mutations import socket, reach it through __import__, turn the local rev-parse into an ls-remote and then into an f"ls-remote" the word allowlist cannot see, the control renames a public function, the probe is -k registry_reads_nothing — KILLED (control proven) four times.`

---

### Task 2: The 32 gates say what they read

**Files:**
- Modify, for the 22 whose SHAPE names no form: `tests/test_count_list.py:62-64` and its eleven call sites (ten `skipif` decorators at :198, :250, :317, :367, :414, :444, :461, :482, :494, :579, and the `assert` at :56); `tests/test_infra_archive_pull_template.py:59-61,100-102,125-127,196-198`; `tests/test_infra_tape_bars_template.py:45-47,101-103`; `tests/test_infra_verify_replay_template.py:337-339`; `tests/test_costmin_drift.py:20-22`; `tests/test_engine_venuestate.py:77-79`; `tests/test_registry_conformance.py:92-94`; `tests/test_tape_bars_rest_control.py:19-22,51-53,60-83`; `tests/test_data_gated_run.py:137`.
- Modify, for the ten whose RECEIVER or operand is bound to something D2's rule refuses (Step 5): `tests/test_record43_book.py:12,149,197,214`; `tests/test_record44_legs.py:11,45`; `tests/test_derivatives_oi.py:443,458,469,482`; `tests/test_derivatives_funding.py:248,256`; `tests/test_tape_bars_rest_control.py:22,47`; `tests/test_config_selectors_are_parsed.py:313,315-316`.

**Interfaces:**
- Consumes: `develop_resolves`, `no_binary`, `nothing_found` from Task 1.

The reducer still in place reads a call into a module of ours and follows it, so a registry call is clean under it exactly as today's `_develop_resolves()` and `bash is None` are: this commit changes what the gates SAY, not what any of them decides, and the current tree assertion stays green over it. Measured over the whole restructured tree with the SHIPPED reducer — every module under `tests/` re-walked through `_gates`, with `tests/skip_gates.py` in place — 65 gates, none opaque, one environment key. Step 5's ten are clean under it for the same reason: four become plain `pathlib` reads the reducer already accepts, five become `nothing_found(...)` over a local it follows, and the tenth stops being a gate.

- [ ] **Step 1: Record the baseline**

Run: `uv run pytest tests/test_live_venue_opt_in.py tests/test_count_list.py tests/test_infra_archive_pull_template.py tests/test_infra_tape_bars_template.py tests/test_infra_verify_replay_template.py tests/test_costmin_drift.py tests/test_engine_venuestate.py tests/test_registry_conformance.py tests/test_tape_bars_rest_control.py tests/test_data_gated_run.py tests/test_record43_book.py tests/test_record44_legs.py tests/test_derivatives_oi.py tests/test_derivatives_funding.py tests/test_config_selectors_are_parsed.py -q -rs`
Fifteen files: the fourteen this task's two Files lines name, and the guard itself. `tests/test_data_gated_run.py` is among them because Step 4 rewrites `_DATA_ABSENT_REASONS`'s entry at :137, which `tests/test_data_gated_run.py:159-161` parametrises — a wrong entry is a RED test, and Step 6 re-runs this command, so the one file whose edit is a bare string literal is checked by the step that commits it. On a data-bearing workstation the last five are minutes rather than seconds, because their gates OPEN there; that is the price of holding ten decisions still, and on a bare checkout they skip and the run is as fast as the other ten.
Keep the summary line and the `-rs` skip lines: Step 6 compares against them.

- [ ] **Step 2: Migrate the ten count-list gates**

In `tests/test_count_list.py`: delete `_develop_resolves` (lines 62–64) and `import subprocess` if nothing else in the
file uses it; add `from tests.skip_gates import develop_resolves`; replace every `_develop_resolves()` call with
`develop_resolves()`. There are ELEVEN, not ten: the ten `@pytest.mark.skipif(not _develop_resolves(), ...)` decorators
and the unconditional `assert _develop_resolves(), (...)` at `tests/test_count_list.py:56`, inside
`test_this_checkout_carries_what_the_counts_measure_from`. The spec's gate census counts ten because an `assert` is not
a gate; leaving it behind is a `NameError` on every run of that file. That `assert`'s own message says "the nine gates
below skip" (`tests/test_count_list.py:58`) and there are ten — `grep -c 'skipif(not _develop_resolves'` returns 10 —
so the word changes to "ten" in the same edit that rewrites the call two lines above it.

- [ ] **Step 3: Migrate the seven `shutil.which` gates**

In each of the three template test files, keep the local (`bash = shutil.which("bash")` feeds the run below it) and
rewrite ONLY the `if` line's condition — the reason string and the trailing `# pragma: no cover` comment stay:

```python
    bash = shutil.which("bash")
    if no_binary("bash"):  # pragma: no cover - bash is present on every dev and CI image we run
        pytest.skip("bash not available")
```

with `from tests.skip_gates import no_binary` at the top of each file. `"bash not available"` and `"sed not available"`
are entries of `tests/test_data_gated_run.py`'s `_OWN_GATE_REASONS`, the corpus
`infra/scripts/data-gated-run.py`'s `is_data_absence` is tested against; nothing derives that list from the tree, so a
rewritten reason would leave two of its entries naming no gate and no step here could notice.

Every coordinate in the table below and in Step 4's is PRE-IMPORT — the line as the file holds it before this step's
own `from tests.skip_gates import ...` lands. How far each gate then moves depends on where the import is written and
on what `uv run ruff check --select I --fix` does with it — measured, the same three files shift by one when the import
is written straight under `import pytest` and by two when ruff has to open a first-party block for it — so there is no
single offset that repairs the table. Rewrite the `if` lines FIRST and add the import after; the coordinates hold until
it lands and not one line longer. Three of `tests/test_infra_archive_pull_template.py`'s four rows are the identical
text `if bash is None:`, so the coordinate is the only thing telling them apart.

The ARGUMENT is the binary, never the local's name — the seven `if` lines and what each takes, because at one of them
the two differ:

| gate line | local | rewritten condition |
| --- | --- | --- |
| `tests/test_infra_archive_pull_template.py:60` | `bash` | `no_binary("bash")` |
| `tests/test_infra_archive_pull_template.py:101` | `sed` | `no_binary("sed")` |
| `tests/test_infra_archive_pull_template.py:126` | `bash` | `no_binary("bash")` |
| `tests/test_infra_archive_pull_template.py:197` | `bash` | `no_binary("bash")` |
| `tests/test_infra_tape_bars_template.py:46` | `found` | `no_binary("bash")` |
| `tests/test_infra_tape_bars_template.py:102` | `sed` | `no_binary("sed")` |
| `tests/test_infra_verify_replay_template.py:338` | `bash` | `no_binary("bash")` |

`no_binary("found")` would skip unconditionally on every host, which no run of Step 6 prints a line for.

- [ ] **Step 4: Migrate the five collection gates — four declare, the fifth splits**

Four are local scans and `nothing_found(...)` is true of them. The coordinate is the `if` line, not the binding a line
above it:

| gate line | binding above it | rewritten condition |
| --- | --- | --- |
| `tests/test_costmin_drift.py:21` | `snaps = sorted(glob.glob(...))` | `if nothing_found(snaps):` |
| `tests/test_engine_venuestate.py:78` | `snapshots = sorted(_SNAPSHOTS.glob(...))` | `if nothing_found(snapshots):` |
| `tests/test_registry_conformance.py:93` | `records = [... TrialRegistry ...]` | `if nothing_found(records):` |
| `tests/test_tape_bars_rest_control.py:52` | `archived = sorted({...index...})` | `if nothing_found(archived):` |

each file with `from tests.skip_gates import nothing_found`.

The fifth, `tests/test_tape_bars_rest_control.py:79`'s `if day is None:`, is NOT declared: `day` is a `next(...)` over
`covered`, and `covered` is filtered by `stamps`, which is sorted off `rows = fetch_ohlc(...)` — Kraken's live REST
answer. `nothing_found(day)` would declare a local scan over a value the venue decides, on the one gate spec D3 cites as
what a matcher would have refused on day one. Split it instead (spec D8): the local half becomes a fifth declaration and
the venue half a `pytest.fail`, beside the two the file already carries.

Beside `PAIR_KEY`, the reach the split turns on:

```python
# Kraken's REST answer is 720 candles, and `now - <that window>` is at most (today - 7) 12:00 at 15m
# whatever hour a run starts at -- so every one of the last REST_REACH_DAYS whole days is wholly inside
# a full-length window. The bound is read off the CALENDAR and never off `stamps`, which is why an
# empty `covered` below is a statement about Kraken's answer rather than about the archive, and it is
# computed from the interval this file already imports so a change to it cannot leave the 6 behind.
REST_REACH_DAYS = 720 * BASE_INTERVAL_MINUTES // (60 * 24) - 1
```

and, directly below the `archived` gate and before `rows = fetch_ohlc(...)`, so the archive-only skip is decided before
the venue is touched:

```python
    recent = [d for d in archived if d >= datetime.now(UTC).date() - timedelta(days=REST_REACH_DAYS)]
    healed = [d for d in recent if is_heal_complete(index, PAIR, d)]
    if nothing_found(healed):
        pytest.skip(f"no heal-complete {PAIR} day in the last {REST_REACH_DAYS} days under {PRIMARY_ROOT}")
```

That expression is 6 at today's `BASE_INTERVAL_MINUTES` of 15 — 720 x 15m is 7.5 days, whose whole-day
floor less one is the number of days a window of that length covers end to end whatever hour it starts
at — and it is a floor, so a shorter interval narrows the scan rather than over-claiming the reach.

`recent`, not `archived`: `is_heal_complete` is not an index read but `pl.read_parquet` over each of the day's hourly
segments plus a neighbour each side, fed to `detect` (`cli/tick/materialize.py:112`), which raises `TradeBackfillError`
on a null `trade_id` (`cli/trades/gaps.py:51`). Unbounded it would read the whole archive — 72 BTC/EUR days on this
workstation and one more every day — before the test touches Kraken, and fail on a defect in a day the REST window can
never reach; the production sweep bounds the same loop for the same reason (`cli/tick/materialize.py:191`, "Bounded
candidate range"). Measured on this workstation's archive: 72 days take 5.0s and the last 6 take 0.3s, and `healed` is
5 days, 2026-09-12..2026-09-16.

Then `covered` iterates `healed` rather than `archived`, and `day = next(...)` and its skip become:

```python
    if not covered:
        pytest.fail(
            f"Kraken REST reaches {stamps[0].date()}..{stamps[-1].date()} and covers none of the "
            f"heal-complete {PAIR} days {healed[0]}..{healed[-1]}"
        )
    day = covered[-1]
```

`covered` is ascending, so `covered[-1]` is the newest heal-complete covered day — the same day `next(... reversed(covered) ...)`
picked. The message names `healed`, not "the archive holds": `is_heal_complete` is False whenever no segment follows the
day (`cli/tick/materialize.py:109-110`), so the live edge is never heal-complete and `healed[-1]` understates the
archive's newest day by at least one on every run — measured, `archived` ends 2026-09-17 and `healed` 2026-09-16.

The fail is venue-only, which is what the bound buys: every day in `healed` is inside `recent`, and every day of `recent`
but today is wholly inside a full-length window, so `covered` can be empty only if Kraken's window is shorter than its
documented reach. Without the bound the same empty `covered` means an archive that has fallen behind — a local
condition, whose skip reason `infra/scripts/data-gated-run.py` books under `data_gated_skipped` and whose fail it books
under `failed`.

Re-true the comment above the `if stamps[-1] - stamps[0] < timedelta(days=1):` check in the same commit (it moves when
the block above it is inserted, so find it by its text): it justified that separate `pytest.fail` by saying the two
cases it could not separate both left `covered` empty, and under the bound above they ARE separated — an old archive
skips at `nothing_found(healed)` and never reaches it. The check stays for the sharper diagnostic it prints; what its
last two sentences become is that `covered` below is now a venue statement too.

Replace `tests/test_data_gated_run.py:137` in the same commit. It is verbatim the reason string of the skip this step
turns into a `pytest.fail` ("no heal-complete BTC/EUR day inside the REST window (REST reaches ...; archive holds ...)"),
and nothing derives `_DATA_ABSENT_REASONS` from the tree — the same hazard Step 3 flags for `_OWN_GATE_REASONS`, one
list over. The new entry is the new reason as a run prints it, `no heal-complete BTC/EUR day in the last 6 days under
/mnt/zhao-crypto/capture-segments`; `is_data_absence` returns True for it, verified by call.

This file's gate count is unchanged: one skip gate leaves it and one arrives. Measured over the restructured source,
its four gates are `opt-in`, `path` (the `PRIMARY_ROOT` presence Step 5 rewrites), `registry` (`nothing_found(archived)`)
and `registry` (`nothing_found(healed)`).

- [ ] **Step 5: Rewrite the ten gates whose receiver or operand D2's binding rule refuses**

These ten match a form's SHAPE and are refused for what their root is bound to (spec D2): a receiver is literal-rooted
or it is not a form, and the remedy is never to hoist, because the line above is read too. Three kinds, and the third
is not a rewrite but a removal.

The GATE line is what the tree assertion prints — `Gate.line`, the decorator for a `skipif` and the `pytest.skip` call
for a skip site — and for the last two that is not the line to edit:

| gate line | what is edited | rewritten condition |
| --- | --- | --- |
| `tests/test_record43_book.py:149` | the import list at :12, and a new module-top binding | `not DATA_ROOT.exists()`, unchanged |
| `tests/test_record43_book.py:197` | (the same one binding) | `not DATA_ROOT.exists()`, unchanged |
| `tests/test_record43_book.py:214` | (the same one binding) | `not DATA_ROOT.exists()`, unchanged |
| `tests/test_record44_legs.py:45` | the import list at :11, and a new module-top binding | `not DATA_ROOT.exists()`, unchanged |
| `tests/test_derivatives_oi.py:458` | :458, and `_OI_PRESENT` beside :443 | `nothing_found(_OI_PRESENT)` |
| `tests/test_derivatives_oi.py:469` | :469 | `nothing_found(_OI_PRESENT)` |
| `tests/test_derivatives_oi.py:482` | :482 | `nothing_found(_OI_PRESENT)` |
| `tests/test_derivatives_funding.py:256` | :256, and `_FUNDING_PRESENT` beside :248 | `nothing_found(_FUNDING_PRESENT)` |
| `tests/test_tape_bars_rest_control.py:48` | the `if` at :47, and `_PRIMARY_PRESENT` beside :22 | `if nothing_found(_PRIMARY_PRESENT):` |
| `tests/test_config_selectors_are_parsed.py:316` | the parametrize at :313 and the `if` at :315 | the gate goes |

**Four import the root.** `tests/test_record43_book.py:149,197,214` and `tests/test_record44_legs.py:45` gate on
`not DATA_ROOT.exists()` with `DATA_ROOT` taken from `cli/portfolio/`'s import list, and an imported name is refused
however its own module binds it. Drop `DATA_ROOT,` from each file's `from cli.portfolio.record4*_* import (...)` list
and bind it at the file's own top level instead:

```python
DATA_ROOT = Path(__file__).resolve().parents[1] / "data" / "ohlc-full"
```

with `from pathlib import Path` beside the other imports. The value is the same expression `cli/portfolio/record44_legs.py:23-24`
writes (`_REPO_ROOT = Path(__file__).resolve().parents[2]`, then `_REPO_ROOT / "data" / "ohlc-full"`), re-rooted for a
file one directory under the repo rather than two, and it is the spelling `tests/test_crossfreq_system.py:408` and
`tests/test_portfolio_builder.py:104` already use for the same root. Neither file reads `DATA_ROOT` anywhere but at
its gates — `grep -n DATA_ROOT` over the two returns the import line and the four `skipif` lines and nothing else — so
no body changes. What this costs is a constant restated: if `cli`'s `DATA_ROOT` ever names a different directory, these
two gates keep reading the old one and skip where they should run. That is the trade the rule forces, and the loud half
of it is that the same two files still import `load_union` and `REGISTRY_PATH` from the module, so a module that MOVES
breaks them at import rather than at the gate.

**Five take the root from the local config.** `tests/test_derivatives_oi.py:458,469,482` and
`tests/test_derivatives_funding.py:256` gate on `not _OI_ROOT.is_dir()` / `not _FUNDING_ROOT.is_dir()`, where
`_substrate_root(name)` is `resolve_hot_source(load_config()) / name` with a `Path("data") / name` fallback; and
`tests/test_tape_bars_rest_control.py`'s `if` at :47 gates on `not PRIMARY_ROOT.exists()`, where `PRIMARY_ROOT` is
`load_config().nfs_mount_dir / "capture-segments"`. No literal replaces these without pinning a mount `zcrypto.toml`
owns, and the day the config names another one the gate would skip for ever — the outage-read-as-coverage failure with
the config in the venue's place. Each declares the presence it already computes instead. Beside each root:

```python
_OI_PRESENT = [_OI_ROOT] if _OI_ROOT.is_dir() else []
```

and the same one line for `_FUNDING_PRESENT` beside `_FUNDING_ROOT` and `_PRIMARY_PRESENT` beside `PRIMARY_ROOT`
(`.exists()` there, matching the gate it replaces). The three decorators become
`@pytest.mark.skipif(nothing_found(_OI_PRESENT), reason="derivatives-oi substrate absent")` and
`@pytest.mark.skipif(nothing_found(_FUNDING_PRESENT), reason="derivatives-funding substrate absent")`, and the
tape-bars gate becomes `if nothing_found(_PRIMARY_PRESENT):` — reason strings untouched, so
`tests/test_data_gated_run.py`'s two corpora keep naming gates that exist. The decision is the same expression:
`nothing_found([r] if r.is_dir() else [])` is `not r.is_dir()` for the same `r`. The declaration hides no environment
read — `cli/config.py`'s `load_config` reads `zcrypto.toml` and nothing else, `grep -n 'environ\|getenv' cli/config.py`
being empty — and no venue read; what it declares is that the scan was local, which a config read and an `is_dir()`
both are. `from tests.skip_gates import nothing_found` goes into the two derivatives files; `tests/test_tape_bars_rest_control.py`
already has it from Step 4.

**The tenth stops being a gate.** `tests/test_config_selectors_are_parsed.py`'s `if path.name in _GRANDFATHERED:` at
:315 is the tree's one membership gate, and its operand is the parametrize value — a parameter, which the rule refuses
wherever it stands. A skip decided by a committed literal list is an exclusion rather than a gate, so the list filters
the parametrize and the two gate lines go:

```python
@pytest.mark.parametrize("path", sorted(p for p in TESTS.glob("test_*.py") if p.name not in _GRANDFATHERED), ids=lambda p: p.name)
def test_no_substring_selector_over_a_hand_edited_config(path: Path) -> None:
    bad = _violations(path.read_text(), path.name)
```

The same five files go unchecked and `_GRANDFATHERED` stays the one place that says which. What moves is the report:
`pytest -q -rs` over this file alone reads `261 passed, 5 skipped` with one summary line,
`SKIPPED [5] tests/test_config_selectors_are_parsed.py:316: pre-existing; see _GRANDFATHERED`, and afterwards reads
`261 passed` with no summary line at all — measured both ways. `_tree_gates()` goes from 66 to 65. `"pre-existing; see
_GRANDFATHERED"` STAYS in `tests/test_data_gated_run.py`'s `_OWN_GATE_REASONS` at :145: that list is the corpus
`is_data_absence` is tested against, not a census of the tree, and the string is still a reason a suite may write.

- [ ] **Step 6: Run the guard and every touched file**

Run the Step 1 command again.
Expected: the guard file green, the reducer reading each registry call as a helper of ours that reaches nothing remote,
and the same summary line and skip lines as Step 1 recorded EXCEPT for one, the
`SKIPPED [5] tests/test_config_selectors_are_parsed.py:316: pre-existing; see _GRANDFATHERED` line Step 5 removes: five
fewer collected, five fewer skipped, that one line gone, nothing else moved. The Step 4 split does not move a line here
either: without `ZCRYPTO_LIVE_VENUE_TESTS=1`,
`test_tape_bars_match_kraken_rest_ohlc` skips at its opt-in gate before either half is reached, so this run cannot see
the one decision that did move — read the diff for that, not the summary. Any OTHER line that moves is a gate
rewritten wrong.

- [ ] **Step 7: Commit**

```bash
git add tests/
git commit -m "test: the 32 skip gates that read a helper, a which() result, a local or an unrooted receiver now say so"
```

---

### Task 3: The matcher over the fixture, and the tree assertion

**Files:**
- Modify: `tests/test_live_venue_opt_in.py` — `Gate` (line 100), `Module` (line 110), `_module_of` (line 288), `_gate` (line 791), `_gates` (line 802), the tree assertion at line 878, the five fixture tests from line 1119, four new fixture tests, twenty fixture gates appended to `_FIXTURE` in twenty-three functions — the three extra are the two call sites of the skip helpers and `_live`, the environment-read helper the second of those helpers reads through, and carry no gate of their own, which is the point of those cases.
- EVERY line number in this task and in Task 4 is as of `develop` BEFORE Task 1, which is where they were read. Task 1 Step 1 inserts a constants block after `OPT_IN` at :88 and a helper and a test below the control test, and Task 3's own rewrite then moves what Task 4 names, so each coordinate is low by the time its step runs. Locate every span by the names beside it and never by the number — the warning Task 2 Step 3 carries for its own two tables, which holds within one task where this one holds across them.

**Interfaces:**
- Consumes: `REGISTRY_MODULE` and `_call_root` from Task 1; `_imported(tree) -> dict[str, str]`, `_os_aliases(tree) -> frozenset[str]`, `_as_expression`, `_guards_of`, `_is_pytest_call` (existing).
- Produces: `Form(name: str, key: str | None = None)`; `_match(guard: ast.AST, module: Module, function: ast.AST | None) -> list[Form] | str`; `_bound_to_module(module, dotted) -> frozenset[str]`; the receiver rule, `_bindings(name, where) -> list[ast.AST | None]` and `_rooted(node, module, function, seen=frozenset()) -> str | None`, with `_unrooted(node, module, function) -> str | None` over it, read by the path arm and by the membership arm; `Gate.forms: tuple[Form, ...]`; `_fixture_span(f) -> tuple[int, int]` and `_fixture_case(gate: Gate) -> str` (the fixture function a gate sits in); `_REFUSAL_REMEDY` rewritten in place. `_bound_to_module` is read by `_registry_call` here and by Task 4's `_unittest_skip`, so it is written once. `_rooted` calls `_receiver_root`, which Task 1 adds further DOWN the file; a module-level name resolves at call time, so that is not a forward reference, and `_receiver_root` sits below `_classify_call` so the deletion span in Step 3 does not reach it. `_enclosing_function` is the one reducer helper the rule keeps: `_rooted` needs the gate's own function to resolve a local, so Step 3 leaves it where it is and the File structure lists it as staying.

- [ ] **Step 1: Write the failing fixture tests**

Append to `_FIXTURE`, before its closing `"""`:

```python
from tests.skip_gates import no_binary
import tests.skip_gates as declared
from tests import skip_gates
import tests.skip_gates
from os import environ
from tests.basket_fixture import *

ANNOTATED: str = "ZCRYPTO_SOMETHING_ELSE"
if True:
    IN_IF = "ZCRYPTO_SOMETHING_ELSE"
try:
    IN_TRY = "ZCRYPTO_SOMETHING_ELSE"
except NameError:
    IN_TRY = ""
_LITERAL_LOCAL_ROOT = Path("data") / "snapshots"
_DOWN_STATES = ("maintenance", "cancel_only")
_TRUTHY = ("1", "true")
_SKIPPABLE = ("data", "scratch")


class _Keyed:
    KEY = "ZCRYPTO_SOMETHING_ELSE"

    def test_gated_on_a_second_flag_whose_key_is_an_attribute(self):
        if os.environ.get(self.KEY) != "1":
            pytest.skip("a key read off an attribute is not the plain form")


def _skip_unless_opted():
    if os.environ.get(OTHER) != "1":
        pytest.skip("the read is inside the skip helper, not at the call site")


def _live():
    return os.environ.get(OTHER) == "1"


def _skip_unless_live():
    if not _live():
        pytest.skip("the skip helper reads through a second helper")


def test_gated_on_the_registry_by_name():
    if no_binary("jq"):
        pytest.skip("the registry is the one helper a guard may call")


def test_gated_on_the_registry_by_module():
    if declared.no_binary("jq"):
        pytest.skip("the module spelling of the same call")


def test_gated_on_the_registry_through_the_package():
    if skip_gates.no_binary("jq"):
        pytest.skip("`from tests import skip_gates` is this suite's idiom for a tests/ helper")


def test_skips_on_a_sibling_reached_through_the_package_name():
    if tests.venue_is_up():
        pytest.skip("a plain `import tests.skip_gates` binds the PACKAGE, not the registry")


def test_skips_on_a_presence_read_of_what_a_call_returned():
    if not _venue_answers().exists():
        pytest.skip("a presence method on a call's result reads the call, not the filesystem")


def test_gated_on_a_second_flag_read_inside_the_skip_helper():
    _skip_unless_opted()


def test_gated_on_a_second_flag_two_helpers_from_the_condition():
    _skip_unless_live()


def test_gated_on_a_second_flag_through_an_annotated_constant():
    if os.environ.get(ANNOTATED) != "1":
        pytest.skip("an annotated assignment is not the plain form")


def test_gated_on_a_second_flag_through_a_constant_bound_under_an_if():
    if os.environ.get(IN_IF) != "1":
        pytest.skip("a binding under an `if` is not top level")


def test_gated_on_a_second_flag_through_a_constant_bound_under_a_try():
    if os.environ.get(IN_TRY) != "1":
        pytest.skip("a binding under a `try` is not top level either")


def test_gated_on_a_second_flag_whose_key_arrived_by_star_import():
    if os.environ.get(STARRED) != "1":
        pytest.skip("a name this module never binds cannot be a plain constant")


def test_gated_on_a_second_flag_through_environ_imported_by_name():
    if environ.get(OTHER) != "1":
        pytest.skip("`from os import environ` is the mapping under its own name")


def test_skips_on_a_membership_of_what_a_call_returned():
    if _venue_answers() in _DOWN_STATES:
        pytest.skip("membership names an operator, so its left operand is where a venue read hides")


def test_gated_on_a_second_flag_read_by_membership_in_a_constant():
    if os.environ.get(OTHER) not in _TRUTHY:
        pytest.skip("an environment read on the left is the opt-in form, key and all")


def test_gated_on_a_membership_of_a_module_constant():
    if ROOT.name in _SKIPPABLE:
        pytest.skip("a call-free left operand against a module-level constant collection")


def test_skips_on_a_presence_read_hoisted_to_the_line_above():
    marker = _venue_answers()
    if not marker.exists():
        pytest.skip("hoisting the call off the receiver does not make the receiver a path")


def test_gated_on_a_local_bound_once_to_a_literal_path():
    local = _LITERAL_LOCAL_ROOT / "kraken-refdata.json"
    if not local.exists():
        pytest.skip("a local bound once to a literal-rooted path is the accepting direction")


def test_skips_on_a_presence_read_of_a_fixture_parameter(tmp_path):
    if not tmp_path.exists():
        pytest.skip("a parameter is a value this file never sees bound")


def test_skips_on_a_presence_read_of_an_imported_root():
    if not basket_fixture.exists():
        pytest.skip("an imported name is not followed across a module boundary")
```

Spec D2 names six shapes an opt-in key may arrive by and refuses all six; the fixture carried none of them. The
five appended above — an annotated constant, a constant bound under a module-level `if`, one under a `try`, a key read
as `self.KEY`, and a name arriving by star-import — are every BINDING among the six, D2's `if` and `try` being one shape
with a case each. Its other two are not bindings and have no case here: a subscript key and a call key are refused by
`_key`, which answers for a string literal and for a plain-constant name and for nothing else.
(`test_gated_on_a_computed_key` and `test_gated_on_a_constant_a_function_rebinds`, which the fixture does carry, are a
run-time-assembled key and a rebound name, neither of them one of the five.) `STARRED` is bound by nothing in the
fixture, which is the point: `_plain_literal` finds no `Store` for it and refuses.

The four after them are D2's receiver rule in each direction, one case per answer the rule can give: a call
HOISTED to the line above (refused at the binding, which is the whole point of the rule — the remedy the rule replaced
said to hoist), a local bound once to a literal-rooted path (accepted, and the only accepting case for a receiver that
is not written at the gate), a fixture parameter (refused: a value this file never sees bound, and a fixture may read a
venue), and an imported name (refused: nothing is followed across a module boundary, spec 00114 D2). Without the
accepting one the rule could be narrowed to `return "no"` and pass; without the hoisted one it could be deleted and
pass, which Step 8's third probe measures.

The other eight cases are the dispositions D3, D2 and D7 claim and nothing asserted:

- `..._through_the_package` and `..._sibling_reached_through_the_package_name` are the two halves of the registry's
  module spelling. `from tests import skip_gates` is how `test_engine_feeders.py`, `test_engine_soak.py`,
  `test_engine_tracking.py` and the guard's own fixture already import a `tests/` helper, and a bound-name lookup keys
  it as `skip_gates -> "tests"`, so an arm comparing that against `"tests.skip_gates"` refuses the repo's own idiom
  while a plain `import tests.skip_gates` keys `tests -> "tests.skip_gates"` and blesses every `tests.<name>()` call.
  One case asserts each direction.
- `..._presence_read_of_what_a_call_returned` is the path form with a venue read in the receiver. `_venue_answers()` is
  the fixture's own reachability helper, so the case is the reachability refusal written in the one form whose name
  fixes only the method.
- `_skip_unless_opted` and `_skip_unless_live` are the helper-hidden read, which D7 lists among the planted defects and
  no task planted. The gate is the HELPER's own `pytest.skip` — the call site carries no condition and yields no gate —
  so the first is a READ (`env == ("ZCRYPTO_SOMETHING_ELSE",)`) and only the second, one helper further out, is a
  refusal. Both dispositions are what the matcher already produces; the cases are what keeps them produced.
- The three `membership` cases are the arm's three answers, and the fixture carried none of them in either direction.
  `membership` is the second form whose operand rather than whose callee carries the reading (spec D2), so its left is
  where a venue read hides: `..._membership_of_what_a_call_returned` is the refusal, `..._read_by_membership_in_a_constant`
  is an environment read on the left, which the arm hands to the opt-in form so the key reaches the one-name assertion,
  and `..._membership_of_a_module_constant` is the accepting direction, without which the arm could be NARROWED to its
  two refusing answers and pass every fixture case. Deleting it outright is caught either way:
  `..._read_by_membership_in_a_constant` routes through the same arm and reads `env=()` without it, which the
  named-spelling loop fails on.

Add, after `_FIXTURE_GATES = _labelled(_gates(_FIXTURE), "fixture")`:

```python
# Every function the fixture defines, methods included, each spanned from its FIRST DECORATOR: a
# `skipif` mark's gate line is the decorator's, which sits above the `def`, so a span starting at
# `FunctionDef.lineno` matches none of the fixture's decorator-written gates.
_FIXTURE_FUNCTIONS = [f for f in ast.walk(ast.parse(_FIXTURE)) if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef))]


def _fixture_span(f: ast.AST) -> tuple[int, int]:
    return (f.decorator_list[0].lineno if f.decorator_list else f.lineno), f.end_lineno


def _fixture_case(gate: Gate) -> str:
    """The fixture function a gate sits in, so a disposition can be asserted by the case's name."""
    found = next((f.name for f in _FIXTURE_FUNCTIONS if _fixture_span(f)[0] <= gate.line <= _fixture_span(f)[1]), None)
    assert found is not None, f"fixture gate at line {gate.line} sits in no function: {gate.guards}"
    return found


def _fixture(name: str) -> Gate:
    hits = [g for _, g in _FIXTURE_GATES if _fixture_case(g) == name]
    assert len(hits) == 1, f"{name}: {len(hits)} gates"
    return hits[0]


# Every spelling of a second opt-in the fixture carries, each caught by exactly one of the two tree
# assertions: NAMED, the matcher read the second key and the one-name assertion refuses it; REFUSED,
# no form matched and the every-gate-matches assertion refuses it.
_SECOND_FLAG_NAMED = (
    "test_gated_on_a_second_flag",
    "test_gated_on_a_second_flag_through_marks",
    "test_gated_on_a_second_flag_written_as_a_string",
    "test_gated_on_a_second_flag_read_by_subscript",
    "test_gated_on_a_second_flag_read_by_bare_getenv",
    "test_gated_on_a_second_flag_read_by_membership",
    "test_gated_on_a_second_flag_through_a_module_alias",
    "test_skips_through_a_name_bound_to_pytests_skip",
    "test_skips_through_the_bare_name_imported_from_pytest",
    "test_gated_on_a_second_flag_through_environ_imported_by_name",
    "test_gated_on_a_second_flag_read_by_membership_in_a_constant",
    "_skip_unless_opted",
)
_SECOND_FLAG_REFUSED = (
    "test_gated_on_a_second_flag_one_call_away_from_the_condition",
    "test_gated_on_a_second_flag_a_function_handed_back",
    "test_gated_on_a_second_flag_held_on_one_of_our_classes",
    "test_gated_on_a_second_flag_read_through_an_alias_of_the_mapping",
    "test_gated_on_a_second_flag_read_through_a_copy_of_the_mapping",
    "test_gated_on_a_computed_key",
    "test_gated_on_a_constant_a_function_rebinds",
    "test_gated_on_a_second_flag_through_an_annotated_constant",
    "test_gated_on_a_second_flag_through_a_constant_bound_under_an_if",
    "test_gated_on_a_second_flag_through_a_constant_bound_under_a_try",
    "test_gated_on_a_second_flag_whose_key_is_an_attribute",
    "test_gated_on_a_second_flag_whose_key_arrived_by_star_import",
    "_skip_unless_live",
)
_REACHABILITY_REFUSED = (
    "test_skips_through_a_reachability_helper",
    "test_skips_on_a_reachability_read_written_inline",
    "test_skips_below_the_condition_rather_than_directly_under_it",
    "test_skips_in_the_else_rather_than_the_body",
    "test_skips_in_an_except_handler_with_no_condition_anywhere",
    "test_skips_on_a_probe_reached_through_a_class",
    "test_skips_on_a_probe_reached_through_an_instance",
    "test_skips_from_a_match_subject_with_no_condition_anywhere",
    "test_gated_on_a_module_of_ours_that_resolves",
    "test_gated_on_a_module_of_ours_that_cannot_be_read",
    "test_gated_on_a_helper_this_file_cannot_read",
    "test_skips_on_a_sibling_reached_through_the_package_name",
    "test_skips_on_a_presence_read_of_what_a_call_returned",
    "test_skips_on_a_membership_of_what_a_call_returned",
    "test_skips_on_a_presence_read_hoisted_to_the_line_above",
    "test_skips_on_a_presence_read_of_a_fixture_parameter",
    "test_skips_on_a_presence_read_of_an_imported_root",
)
_REGISTRY_MATCHED = (
    "test_gated_on_the_registry_by_name",
    "test_gated_on_the_registry_by_module",
    "test_gated_on_the_registry_through_the_package",
)
# The gates that must NOT be refused for the assertions above to mean anything: the one opt-in read
# twice, a dataset gate, and a membership of a module constant -- the last two the accepting direction
# of the two forms whose operand rather than whose callee carries the reading: without `_LOCAL_DATASET`
# the path arm could be deleted outright and pass, and without `_MEMBERSHIP_MATCHED` the membership arm
# could be narrowed to its refusals and pass. spec 00114 Task 4 extends `_DISPOSED` with two tuples when it
# appends its cases.
_OPT_IN_READ = ("test_gated_on_the_flag", "test_fails_rather_than_skips_when_the_opt_in_is_set")
_LOCAL_DATASET = ("test_gated_on_a_local_dataset", "test_gated_on_a_local_bound_once_to_a_literal_path")
_MEMBERSHIP_MATCHED = ("test_gated_on_a_membership_of_a_module_constant",)
_DISPOSED = (
    _SECOND_FLAG_NAMED
    + _SECOND_FLAG_REFUSED
    + _REACHABILITY_REFUSED
    + _REGISTRY_MATCHED
    + _OPT_IN_READ
    + _LOCAL_DATASET
    + _MEMBERSHIP_MATCHED
)
```

Replace the five fixture tests from `test_a_second_opt_in_name_is_caught_in_every_spelling_the_language_offers` to `test_a_gate_with_no_venue_dependency_passes_beside_them` with (five out, six in):

```python
def test_every_second_opt_in_spelling_is_caught_by_one_of_the_two_assertions():
    """Every way to put a second flag in front of a skip that this fixture carries, each caught by one
    assertion or the other. `_SECOND_FLAG_NAMED` is READ -- the key is a literal or a plain module
    constant, so the matcher names it and the one-name assertion refuses it; `_SECOND_FLAG_REFUSED` is
    REFUSED -- the mapping or the key is reached some other way, and the matcher follows nothing
    (spec 00114 D2), so no form matches and the every-gate-matches assertion refuses it. The two tuples
    are the count; take it from them rather than from a number written here."""
    for name in _SECOND_FLAG_NAMED:
        gate = _fixture(name)
        assert gate.env == ("ZCRYPTO_SOMETHING_ELSE",) and gate.opaque == (), f"{name}: {gate}"
    for name in _SECOND_FLAG_REFUSED:
        gate = _fixture(name)
        assert gate.env == () and gate.opaque, f"{name}: {gate}"
    for control in _OPT_IN_READ:
        assert _fixture(control).env == (OPT_IN,), f"{control}: the one opt-in must be read, or the tuples above prove nothing"


def test_every_fixture_case_carries_a_disposition():
    """The tuples are the count the fixture used to carry as a number. A case appended to `_FIXTURE`
    and named in none of them is passed to `_fixture()` by nothing, so the harness would silently stop
    covering a spelling it holds -- which is the failure the number it replaces existed to prevent."""
    carried = sorted({_fixture_case(gate) for _, gate in _FIXTURE_GATES})
    assert carried == sorted(_DISPOSED), (
        f"undisposed: {sorted(set(carried) - set(_DISPOSED))}; stale: {sorted(set(_DISPOSED) - set(carried))}; "
        f"repeated: {sorted(n for n in set(_DISPOSED) if _DISPOSED.count(n) > 1)}"
    )


def test_every_reachability_spelling_is_refused():
    """A venue probe -- inline, in a helper, on a class, through a module of ours that is not the
    registry, worn as a form by putting the call in an `.exists()` receiver or on the left of an `in`,
    or HOISTED off the receiver to the line above, where the binding is read too -- matches no form.
    The last three are the receiver rule's refusing answers (spec 00114 D2): the hoisted call, a
    fixture parameter, and an imported name, each a value this file cannot root in a literal and each
    a value a venue may have decided. The `..._module_of_ours_that_resolves` case is the price of
    following nothing: a call is a form only into the registry (spec 00114 D3), so a sibling module
    declares itself there or is rewritten at the gate, whatever that module happens to read."""
    for name in _REACHABILITY_REFUSED:
        gate = _fixture(name)
        assert gate.forms == () and gate.opaque, f"{name}: {gate}"


def test_the_registry_is_the_one_call_a_guard_may_make():
    """The three spellings D3 accepts -- a name imported from the registry, an alias of the module, and
    the `from tests import skip_gates` idiom this suite uses for every other `tests/` helper. The two
    it refuses are in `_REACHABILITY_REFUSED` and in the tree assertion's remedy, not here."""
    for name in _REGISTRY_MATCHED:
        gate = _fixture(name)
        assert gate.forms == (Form("registry"),) and gate.opaque == (), f"{name}: {gate}"


def test_the_fixture_carries_every_position_a_skip_can_sit():
    (unchanged: keep the existing body and docstring)


def test_a_gate_with_no_venue_dependency_passes_beside_them():
    """The degeneracy control. A guard that flagged every skip would pass its own fixture and refuse
    the dataset gates that are most of `tests/` -- an absent dataset is not an outage read as coverage.
    `_LOCAL_DATASET`'s two are the accepting answers of the path form's receiver rule: one written at
    the gate, one a local bound once to a literal-rooted path, without which the rule could answer
    "not rooted" to everything and pass. The membership case is that control for the other form whose
    operand carries its reading: without an accepting case, the `membership` arm could be narrowed to
    its refusals and nothing here would fail. The tuples are the count; take it from them."""
    for name in _LOCAL_DATASET:
        gate = _fixture(name)
        assert gate.forms == (Form("path"),) and gate.env == () and gate.opaque == (), f"{name}: {gate}"
    member = _fixture(_MEMBERSHIP_MATCHED[0])
    assert member.forms == (Form("membership"),) and member.env == () and member.opaque == (), f"got {member}"
```

- [ ] **Step 2: Run them and read WHICH failure fired**

Run: `uv run pytest tests/test_live_venue_opt_in.py -k "second_opt_in_spelling or reachability_spelling or one_call_a_guard or no_venue_dependency or fixture_case_carries" -q`
Expected: 1 passed, 4 failed, at RUN time and not at collection — nothing references `Form` at import time, so the
module imports. All three of `test_the_registry_is_the_one_call_a_guard_may_make`,
`test_a_gate_with_no_venue_dependency_passes_beside_them` and `test_every_reachability_spelling_is_refused` raise
`AttributeError: 'Gate' object has no attribute 'forms'`: each evaluates `gate.forms` as a comparison's LEFT operand, so
the reducer's `Gate` raises before `Form` is ever looked up and the `NameError` is unreachable.
`test_every_second_opt_in_spelling_is_caught_by_one_of_the_two_assertions` fails on
the FIRST name of `_SECOND_FLAG_REFUSED`, `test_gated_on_a_second_flag_one_call_away_from_the_condition`, with
`gate.env == ('ZCRYPTO_SOMETHING_ELSE',)`, because the reducer FOLLOWS
`_opted_in()` where the matcher will refuse it. Its `_SECOND_FLAG_NAMED` loop passes under the reducer, which is right:
those twelve are the spellings both engines read, the membership-in-a-constant case included — the reducer reads it as
`env=('ZCRYPTO_SOMETHING_ELSE',)` and so does the matcher, by a different arm. The one that PASSES is
`test_every_fixture_case_carries_a_disposition` — it reads the walker and the tuples and not the matcher, and it is run
here so a case name mistyped in Step 1 is caught before the matcher lands. Under the reducer the fixture yields 50
gates in 50 distinct cases, which is what that test compares against `_DISPOSED`.

- [ ] **Step 3: Write the matcher**

Rewrite `Gate` and `Module`:

```python
class Gate(NamedTuple):
    """One skip site: where it is, the forms its guards matched, the opt-in keys those read, and what was refused."""

    line: int
    kind: str
    forms: tuple[Form, ...]
    env: tuple[str, ...]
    opaque: tuple[str, ...]
    guards: str


class Module(NamedTuple):
    """A parsed module and the two lookups a guard is read against: what its imports bind, and which
    names are the `os` module."""

    tree: ast.Module
    imported: dict[str, str]
    os_names: frozenset[str]
    label: str
```

with `_module_of` building only those four fields. Above `Gate`:

```python
class Form(NamedTuple):
    """One recognised guard shape and, for the opt-in form, the key it read."""

    name: str
    key: str | None = None
```

Replace everything from `_REFUSAL_REMEDY`'s assignment to `_classify_call`'s last line with the block below, locating
both ends by those two names: the numbers they carry on `develop` — 397 and 620 — are what Task 1 has already moved, and
deleting 397–620 of the file this task actually finds cuts from inside `_PREDICATES` to inside `_classify_call`, leaving
a truncated dict literal above the replacement block and the tail of `_classify_call` below it. The span starts at
`_REFUSAL_REMEDY` and not at `class Reading` below it because the block re-defines `_REFUSAL_REMEDY`, and the old
assignment is named in neither column of the File structure, so it would otherwise survive to the tip as a second,
contradictory one. It has no reader in the file today. The span also takes `_body_expressions`, which the File structure
now lists as replaced.

```python
_PRESENCE = ("exists", "is_file", "is_dir")
_ENV_READS = ("get", "getenv")
_REFUSAL_REMEDY = (
    "write the guard as a presence check whose RECEIVER is LITERAL-ROOTED -- a `Path('<literal>')` "
    "chain, a `/` join of one, or a name bound once, at this module's top level or in this function, "
    "to one of those -- `os.geteuid() == 0`, `shutil.which('<name>') is None`, a read of the one "
    "opt-in under a literal or plain module-constant key and with NO default, COMPARED to a string "
    "literal, spelled `<key> in os.environ`, or tested against a module-level constant collection of "
    "literals, membership of a CALL-FREE literal-rooted expression in such a collection, or a call "
    "into tests/skip_gates.py -- `no_binary(...)` under `from tests.skip_gates import no_binary`, or "
    "`<name>.no_binary(...)` under `from tests import skip_gates` or `import tests.skip_gates as "
    "<name>`. Do NOT hoist the receiver's call to the line above: the binding is read there too. "
    "And a call that reaches a VENUE is neither hoisted nor declared -- a reachability probe fails a "
    "test, it never skips it"
)


def _assignments(name: str, module: Module) -> list[ast.AST]:
    """Every `Store` of `name` anywhere in the module, so a plain constant is one that is bound once."""
    return [n for n in ast.walk(module.tree) if isinstance(n, ast.Name) and n.id == name and isinstance(n.ctx, ast.Store)]


def _plain_literal(name: str, module: Module) -> str | None:
    """`NAME = "<literal>"` at the module's top level, bound nowhere else (spec 00114 D2)."""
    if len(_assignments(name, module)) != 1:
        return None
    for node in module.tree.body:
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == name
        ):
            value = node.value
            return value.value if isinstance(value, ast.Constant) and isinstance(value.value, str) else None
    return None


def _plain_collection(name: str, module: Module) -> bool:
    """`NAME = (...)`, `[...]`, `{...}` or `frozenset({...})` of literals at the top level, bound once."""
    if len(_assignments(name, module)) != 1:
        return False
    for node in module.tree.body:
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and node.targets[0].id == name
        ):
            value = node.value
            if (
                isinstance(value, ast.Call)
                and isinstance(value.func, ast.Name)
                and value.func.id in ("frozenset", "set", "tuple")
                and len(value.args) == 1
            ):
                value = value.args[0]
            return isinstance(value, (ast.Tuple, ast.List, ast.Set)) and all(isinstance(e, ast.Constant) for e in value.elts)
    return False


def _key(node: ast.AST, module: Module) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name):
        return _plain_literal(node.id, module)
    return None


def _is_environ(node: ast.AST, module: Module) -> bool:
    """`os.environ` under any name the module binds `os` to, or `environ` imported from os under its
    own name (`_imported` keeps the bound name only, so `from os import environ as e` is refused)."""
    if isinstance(node, ast.Attribute) and node.attr == "environ" and isinstance(node.value, ast.Name):
        return node.value.id in module.os_names
    return isinstance(node, ast.Name) and node.id == "environ" and module.imported.get("environ") == "os"


def _env_read_key(node: ast.AST, module: Module) -> ast.AST | None:
    """The key of `os.environ.get(K)`, `os.getenv(K)`, `environ.get(K)`, `getenv(K)` or `os.environ[K]`
    -- of a read with NO default, positional or keyword: the key is `args[0]` and a default is read by
    nothing, so `os.environ.get(K, _venue_up())` would be a venue call written inside a form whose
    reading this matcher declares fixed -- the whole-call pinning `_match` requires of every arm that
    judges a call at the gate."""
    if isinstance(node, ast.Call) and len(node.args) == 1 and not node.keywords:
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr in _ENV_READS:
            if _is_environ(func.value, module) or (isinstance(func.value, ast.Name) and func.value.id in module.os_names):
                return node.args[0]
        if isinstance(func, ast.Name) and func.id == "getenv" and module.imported.get("getenv") == "os":
            return node.args[0]
    if isinstance(node, ast.Subscript) and _is_environ(node.value, module):
        return node.slice
    return None


def _bound_to_module(module: Module, dotted: str) -> frozenset[str]:
    """Every name this module binds to the MODULE `dotted` by import and rebinds nowhere:
    `import <dotted> as n`, and `from <package> import <leaf>` under its own name or an alias -- this
    suite's idiom for a `tests/` helper. `_imported` keys on the bound name and maps the `from`
    spelling to the PACKAGE, so a receiver that names a module is resolved here instead: a plain
    `import tests.skip_gates` binds `tests`, which is the package and not the registry, and yields
    nothing. An import any `Store` of that name rebinds yields nothing either, at any scope --
    nothing here tracks scopes, so a local of that name in an unrelated function is enough: the
    once-bound discipline `_plain_literal` applies to a key, applied to a module over the same
    whole-tree walk. A `Store` is what `_assignments` collects, so a `def`, a `class` or a second
    `import ... as` of the receiver is a rebinding this does not see. A rebound name falls to `no form
    matches`, whose remedy prints the spelling the author already wrote."""
    package, _, leaf = dotted.rpartition(".")
    bound: set[str] = set()
    for node in ast.walk(module.tree):
        if isinstance(node, ast.ImportFrom) and node.module == package:
            bound |= {a.asname or a.name for a in node.names if a.name == leaf}
        elif isinstance(node, ast.Import):
            bound |= {a.asname for a in node.names if a.asname and a.name == dotted}
    return frozenset(n for n in bound if not _assignments(n, module))


def _bindings(name: str, where: ast.AST) -> list[ast.AST | None]:
    """Every expression `where` -- a module, or the gate's own function -- binds `name` to, a parameter
    contributing `None`. `_assignments` counts the STORES of a name anywhere in the module, which is
    the once-bound test `_plain_literal` rides on; this answers the other question, what the ONE scope
    that binds a receiver's root binds it to, so a local bound once inside its own function is not
    refused for a namesake in another."""
    out: list[ast.AST | None] = [None for a in ast.walk(where) if isinstance(a, ast.arg) and a.arg == name]
    for node in ast.walk(where):
        if isinstance(node, ast.Assign):
            out += [node.value for t in node.targets if isinstance(t, ast.Name) and t.id == name]
        elif isinstance(node, (ast.AnnAssign, ast.NamedExpr)) and isinstance(node.target, ast.Name):
            if node.target.id == name and node.value is not None:
                out.append(node.value)
    return out


def _rooted(node: ast.AST, module: Module, function: ast.AST | None, seen: frozenset[str] = frozenset()) -> str | None:
    """`None` when this expression is LITERAL-ROOTED, else the binding that is not (spec 00114 D2).

    Literal-rooted is a chain whose root is a string literal, `__file__`, a name this module imported
    from `pathlib`, or a name bound exactly once -- in the gate's own function, else at the module's
    top level -- to another such expression. That is `_plain_literal`'s discipline given to a receiver
    instead of a key, and it is what stops `marker = _venue_reads()` one line above the gate from
    reading as the local it is written as. A parameter, an imported name, a name no assignment binds,
    a name bound from any other call, and a name bound more than once are each refused BY NAME, so the
    message says what was seen rather than that something was; `seen` refuses a name bound through
    itself rather than following it round. What is NOT judged is what sits beside the root -- a `/`
    join's right operand, a `pathlib` method's argument -- which spec 00114 D5 states as the residual.
    """
    root = _receiver_root(node)
    if isinstance(root, ast.Constant):
        return None if isinstance(root.value, str) else f"{ast.unparse(root)}, which is not a string literal"
    if not isinstance(root, ast.Name):
        return f"{ast.unparse(root)}, which is neither a name nor a literal"
    if root.id == "__file__" or module.imported.get(root.id, "").split(".")[0] == "pathlib":
        return None
    if root.id in module.imported:
        return f"{root.id}, imported from {module.imported[root.id]}"
    if root.id in seen:
        return f"{root.id}, bound through itself"
    found = _bindings(root.id, function) if function is not None else []
    where = function.name if found else module.label
    found = found or _bindings(root.id, module.tree)
    if not found:
        return f"{root.id}, which no assignment in {module.label} binds"
    if len(found) > 1:
        return f"{root.id}, bound {len(found)} times in {where}"
    if found[0] is None:
        return f"{root.id}, a parameter of {where}"
    return _rooted(found[0], module, function, seen | {root.id})


def _unrooted(node: ast.AST, module: Module, function: ast.AST | None) -> str | None:
    """Why a path receiver or a membership operand is not a filesystem read, or `None` when it is.
    The uid, binary and registry forms name their CALLEE, so the form fixes what they read; `exists`
    names only a method and `in` only an operator, so `not fetch_ohlc(PAIR).exists()` and a `marker`
    bound to that call a line above would both otherwise be venue reads matched as path checks. Every
    call written AT the gate is rooted first and then the expression itself, so a `pathlib` method on
    a literal-rooted name passes and the same method on a fixture value or an import does not. The
    call walk stops here and is not carried into `_rooted`'s recursion: a BINDING may hold a call or a
    parameter the root does not reach -- `_ROOT / "data" / named.group(1)` and `_DATA / name` are two
    the tree carries -- and judging those would refuse three more of its own path gates (spec 00114
    D5's residual).
    """
    for inner in ast.walk(node):
        if isinstance(inner, ast.Call):
            why = _rooted(inner.func, module, function)
            if why is not None:
                return why
    return _rooted(node, module, function)


def _registry_call(node: ast.Call, module: Module) -> bool:
    """Whether this call reaches `tests/skip_gates.py` (spec 00114 D3): a name imported from it, or an
    attribute on a name bound to the module. BOTH spellings require the name to be that import's
    alone, so a module-level `no_binary = lambda n: venue_up()` under the registry's own import is a
    rebinding and not a declaration. The dict lookup stays in front of `_assignments`, which walks the
    whole module: only a name the import bound pays for that walk."""
    func = node.func
    if isinstance(func, ast.Name):
        return module.imported.get(func.id) == REGISTRY_MODULE and not _assignments(func.id, module)
    return (
        isinstance(func, ast.Attribute)
        and isinstance(func.value, ast.Name)
        and func.value.id in _bound_to_module(module, REGISTRY_MODULE)
    )


def _opt_in(key_node: ast.AST, module: Module) -> list[Form] | str:
    key = _key(key_node, module)
    if key is None:
        return f"an environment key that is not a literal or a plain module constant: {ast.unparse(key_node)}"
    return [Form("opt-in", key)]


def _match(guard: ast.AST, module: Module, function: ast.AST | None) -> list[Form] | str:
    """The forms this guard is made of, or why it is refused (spec 00114 D1-D3).

    No arm below matches a CALL whose shape it has not pinned -- the positional count exact,
    `keywords` empty, a splat resolving to nothing a form can read -- because a form declares what it
    reads and an argument nothing judges is where a venue read sits: `shutil.which('bash',
    path=_nas_bin())` reads a mount and not PATH. The registry arm is the one exception, by design:
    its argument is the claim the call site makes, which no shape of it can check (spec 00114 D3). The two arms whose OPERAND rather than
    whose callee carries the reading take `function` as well, the function the gate sits in, because a
    receiver that is a name is judged at its binding and a local binds in there (`_rooted`)."""
    node = guard
    while isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        node = node.operand
    if isinstance(node, ast.BoolOp):
        forms: list[Form] = []
        for value in node.values:
            got = _match(value, module, function)
            if isinstance(got, str):
                return got
            forms.extend(got)
        return forms
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in _PRESENCE
        and not node.args
        and not node.keywords
    ):
        stray = _unrooted(node.func.value, module, function)
        if stray is None:
            return [Form("path")]
        return f"a path-presence method whose receiver is rooted in {stray}: {ast.unparse(guard)!r}"
    if isinstance(node, ast.Call) and _registry_call(node, module):
        return [Form("registry")]
    if isinstance(node, ast.Compare) and len(node.ops) == 1:
        left, op, right = node.left, node.ops[0], node.comparators[0]
        if (
            isinstance(op, ast.Eq)
            and isinstance(left, ast.Call)
            and not left.args
            and not left.keywords
            and ast.unparse(left.func) in {f"{n}.geteuid" for n in module.os_names}
        ):
            if isinstance(right, ast.Constant) and right.value == 0:
                return [Form("uid")]
        if isinstance(op, ast.Is) and isinstance(right, ast.Constant) and right.value is None and isinstance(left, ast.Call):
            if (
                ast.unparse(left.func) == "shutil.which"
                and len(left.args) == 1
                and isinstance(left.args[0], ast.Constant)
                and not left.keywords
            ):
                return [Form("binary")]
        if isinstance(op, (ast.Eq, ast.NotEq)) and isinstance(right, ast.Constant) and isinstance(right.value, str):
            key_node = _env_read_key(left, module)
            if key_node is not None:
                return _opt_in(key_node, module)
        if isinstance(op, (ast.In, ast.NotIn)) and _is_environ(right, module):
            return _opt_in(left, module)
        if isinstance(op, (ast.In, ast.NotIn)) and isinstance(right, ast.Name) and _plain_collection(right.id, module):
            key_node = _env_read_key(left, module)
            if key_node is not None:
                return _opt_in(key_node, module)
            stray = _unrooted(left, module, function)
            if stray is not None:
                return f"a membership test whose left operand is rooted in {stray}: {ast.unparse(guard)!r}"
            return [Form("membership")]
    return f"no form matches {ast.unparse(guard)!r}"
```

FIVE arms judge a call, and each pins its own shape beside its own callee rather than through a shared
resolver: the presence method takes nothing at all, `os.geteuid` nothing, `shutil.which` one
positional literal, the environment read one positional key and no keyword (`_env_read_key`), and the
registry call whatever the call site declares -- the one arm whose arguments are free, because D3
makes a registry call's argument a claim rather than a reading. A `len(args)` count alone leaves two
slots open, both measured on these fences: `shutil.which("bash", path=_venue_bin()) is None` matched
`binary` and `os.geteuid(*_venue_up()) == 0` matched `uid`, while `os.geteuid(1)` is a run-time
`TypeError` and a second POSITIONAL `which` argument was refused already -- so the keyword slot and
the splat are what `not left.keywords` and `not left.args` close, and `shutil.which`'s real signature
(`(cmd, mode=1, path=None)`) is why the keyword slot is the one that matters.

Rewrite `_gate` and the two calls to it in `_gates`:

```python
def _gate(line: int, kind: str, guards: list[ast.AST], module: Module, function: ast.AST | None, extra=()) -> Gate:
    forms: list[Form] = []
    refusals: list[str] = list(extra)
    for guard in guards:
        got = _match(guard, module, function)
        (refusals.append if isinstance(got, str) else forms.extend)(got)
    return Gate(
        line=line,
        kind=kind,
        forms=tuple(forms),
        env=tuple(sorted({f.key for f in forms if f.name == "opt-in" and f.key is not None})),
        opaque=tuple(refusals),
        guards=" ; ".join(ast.unparse(g) for g in guards)[:300],
    )
```

In `_gates`: `out.append(_gate(node.lineno, "skipif", [condition], module, None, extra))` and
`out.append(_gate(node.lineno, "skip-site", guards, module, _enclosing_function(node, parents)))`; delete the
`scope = ...` line and the comment above it. `None` for the `skipif` arm and not the decorated function: a decorator's
condition is evaluated at import in MODULE scope, and `_enclosing_function` walking up from a decorator reaches the
function it decorates, whose locals are not in scope where the condition runs.

`_enclosing_function` STAYS — `_rooted` resolves a receiver's root in the gate's own function, which is where four of
the tree's path receivers are bound. Delete `_module_scope` and `_locals_of`, whose remaining call sites are the
`scope` line above, the `skipif` arm's `scope` argument, and the reducer bodies this step's replacement span already
takes (`_owned_class` at :544 and :556, `_classify` at :498, `_classify_call` at :584 and :611) — measured on
`develop`, `grep -n '_module_scope(\|_locals_of('` returns those eight and nothing else.

- [ ] **Step 4: Run the fixture tests to verify they pass**

Run: `uv run pytest tests/test_live_venue_opt_in.py -q -k "not skip_gate_in_tests and not the_tree and not every_environment"`
The three tree assertions carry `skip_gate_in_tests`, `the_tree` and `every_environment`; `not tree` does not deselect
`test_no_skip_gate_in_tests_is_decided_by_something_this_file_cannot_read`, which walks all 65 tree gates — Task 2
migrated them, so the count is 65 and not `develop`'s 66 — and would be diagnosed here against the fixture's list.
Expected: every fixture test passes, `test_every_fixture_case_carries_a_disposition` over all 50 cases included. A fixture case whose disposition differs from its tuple is a matcher defect or a wrong tuple: the tuple is right when the case's key is a literal or a once-bound top-level string constant read straight off `os.environ`/`os.getenv`/`environ` with no default, and wrong otherwise — fix the matcher, never move the name.

- [ ] **Step 5: Rewrite the tree assertion**

Replace `test_no_skip_gate_in_tests_is_decided_by_something_this_file_cannot_read` (line 878) with:

```python
def test_every_skip_gate_in_tests_matches_a_form():
    """A guard is one of six forms or it is refused (spec 00114 D1). The forms are the only things a
    skip may be decided by and none of them reaches a venue: that is how the rule's second half -- no
    skip decided by whether the venue answers -- is held, by a closed set rather than by a reading."""
    unmatched = [(label, gate, why) for label, gate in _unreadable(_tree_gates()) for why in gate.opaque]
    assert not unmatched, "\n".join(
        f"{label}:{gate.line} [{gate.kind}] {why}: {gate.guards} -- {_REFUSAL_REMEDY}" for label, gate, why in unmatched
    )
```

Run: `uv run pytest tests/test_live_venue_opt_in.py -q`
Expected: all passed; `_tree_gates()` returns 65 — the tree is migrated by now, and the fixture's 50 gates are judged
separately, because they live in the `_FIXTURE` string literal, which no parse of this module sees as code. A tree site
the assertion names here is a gate outside the 32 whose key is bound other than as a plain top-level literal, whose
collection is not literal, or whose receiver Task 2 Step 5 left unrooted: rewrite that gate to the plain form in this
commit and name it in the message.

- [ ] **Step 6: Record what the assertion names against the pre-migration tree**

In a throwaway worktree at `develop` — never the main checkout, whose tree peers share, and never the stash, which is shared too — copy the matcher in and run its tree assertion over the unmigrated gates. `--detach` is not optional: `develop` is the main checkout's resting state, a branch cannot be checked out in two worktrees, and without it the `add` fails, the `cp` then fails on a directory that was never created, and the count this step exists to record is never measured.

```bash
git worktree add --detach ../wt-premig develop
cp tests/test_live_venue_opt_in.py ../wt-premig/tests/test_live_venue_opt_in.py
( cd ../wt-premig && uv run python -c "import tests.test_live_venue_opt_in as g; [print(f'{l}:{gt.line} [{gt.kind}] {gt.guards}') for l, gt in g._unreadable(g._tree_gates())]" | sort | nl )
git worktree remove --force ../wt-premig
```

Expected: exactly the 32 sites of the spec's census, one numbered line each — `nl`'s last number is the count. Twenty-two
are the shape refusals and ten are the receivers and operands D2's binding rule refuses, which name the binding they saw
(`DATA_ROOT, imported from cli.portfolio.record43_book`; `_substrate_root, which no assignment ... binds`; `path, a
parameter of test_no_substring_selector_over_a_hand_edited_config`). The rows are read off `_unreadable(_tree_gates())`
rather than off a failing pytest run because pytest prefixes every line of an assertion message with `E` and the first
with `AssertionError:`, so no line of that output is anchored at `^tests/`.
Quote the count and the files in the commit message. A count other than 32 is a gate the census missed or a form the matcher over-accepts, and it is run down before the commit.

- [ ] **Step 7: Commit**

```bash
git add tests/test_live_venue_opt_in.py
git commit -m "test(venue): a guard matches one of six forms or is refused; the fixture carries each disposition"
```

- [ ] **Step 8: Prove the guard bites twice, then amend the body with both verdicts**

The form widened to accept any guard:

```bash
infra/scripts/mutate-probe.sh --file tests/test_live_venue_opt_in.py --control 's/^    if isinstance(node, ast.Call) and _registry_call(node, module):$/    if False:/' --mutation 's/^    return f"no form matches {ast.unparse(guard)!r}"$/    return [Form("path")]/' -- uv run pytest tests/test_live_venue_opt_in.py -k "reachability_spelling or one_call_a_guard" -q
```

Expected: `KILLED (control proven, tree restored byte-identically)` — the mutation reads every unmatched guard as a path check, which the reachability cases catch; the control refuses the registry form, which the registry case catches.

The receiver rule deleted, leaving the call walk `_unrooted` already had:

```bash
infra/scripts/mutate-probe.sh --file tests/test_live_venue_opt_in.py --control 's/^    if isinstance(node, ast.Call) and _registry_call(node, module):$/    if False:/' --mutation 's/^    return _rooted(node, module, function)$/    return None/' -- uv run pytest tests/test_live_venue_opt_in.py -k "reachability_spelling or one_call_a_guard" -q
```

Expected: `KILLED (control proven)` — `_unrooted`'s last line is the binding check, and without it a receiver that is a
bare NAME is rooted by nothing. Three cases catch it and each on its own would:
`test_skips_on_a_presence_read_hoisted_to_the_line_above` (the case the rule exists for — the remedy it replaced told
the author to write exactly this), `..._of_a_fixture_parameter` and `..._of_an_imported_root`. The one case this
mutation does NOT reach is `test_skips_on_a_presence_read_of_what_a_call_returned`, whose receiver carries the call and
is caught by the loop above the mutated line — which is why the two halves of `_unrooted` need two probes and not one.
`    return _rooted(node, module, function)` is the only line of that text in the file: `_rooted`'s own tail line reads
`    return _rooted(found[0], module, function, seen | {root.id})`, so the `sed` matches once.

A real gate rewritten unmatched:

```bash
infra/scripts/mutate-probe.sh --file tests/test_costmin_drift.py --control 's/^    if nothing_found(snaps):$/    if nothing_found(snaps) or True:/' --mutation 's/^    if nothing_found(snaps):$/    if not snaps:/' -- uv run pytest tests/test_live_venue_opt_in.py -k matches_a_form -q
```

Expected: `KILLED (control proven)` — the mutation restores the bare local and the tree assertion names `tests/test_costmin_drift.py:23` — `Gate.line` for a
skip site is the `pytest.skip` call's line, not the `if` the mutation edits, and this probe runs after Task 2, whose `from tests.skip_gates import nothing_found` ruff places beside `import pytest` and one line above the gate; the control's `or True` is a `BoolOp` whose second value no form matches, so the assertion refuses it too. Amend the commit body with both verdicts, naming the script, the files, the mutations and the selectors.

---

### Task 4: Discovery widened to `unittest`'s decorator and method

**Files:**
- Modify: `tests/test_live_venue_opt_in.py` — `_is_pytest_call` (line 733) and its docstring (739-740), `_gates`, a new
  `_unittest_skip` and `_UNITTEST_SKIPS`, `_FIXTURE`, two new tuples beside `_REGISTRY_MATCHED` with `_DISPOSED` extended
  by them, one new test.

- [ ] **Step 1: Write the failing fixture test**

Append to `_FIXTURE`:

```python
import unittest
import unittest as ut
from unittest import skipUnless
from unittest import skipIf as skip_if


class TestOld(unittest.TestCase):
    @unittest.skipIf(not ROOT.exists(), "no data")
    def test_gated_by_a_unittest_decorator(self):
        pass

    @skipUnless(ROOT.exists(), "no data")
    def test_gated_by_a_unittest_decorator_imported_by_name(self):
        pass

    @skip_if(not ROOT.exists(), "no data")
    def test_gated_by_a_unittest_decorator_imported_under_an_alias(self):
        pass

    @ut.skipIf(not ROOT.exists(), "no data")
    def test_gated_by_a_unittest_decorator_through_a_module_alias(self):
        pass

    def test_gated_by_a_unittest_method(self):
        if not ROOT.exists():
            self.skipTest("no data")
```

Four decorator spellings, not one: `_pytest_modules` and `_pytest_bindings` make every pytest recognition in this file
alias-tolerant, and a `unittest` arm that matched only the dotted `unittest.skipIf` would leave the three spellings a
`unittest`-style module is ordinarily written with (`from unittest import skipIf`, that import under an alias, and
`import unittest as ut`) invisible to both tree assertions — a discovery hole no assertion in the file can see, in the
construct this task exists to close. The aliased import is the one a bound-name lookup cannot reach at all:
`_imported` keys `from unittest import skipIf as skip_if` as `skip_if -> "unittest"` and loses `skipIf`, so a membership
test against `("skipIf", "skipUnless")` refuses it.

Beside `_REGISTRY_MATCHED`, the two tuples that give these cases a disposition, with `_DISPOSED`'s sum extended by both
in the same edit — the partition assertion Task 3 added is over every case the fixture carries, so a case appended
without a tuple is red at this step rather than silent:

```python
_UNITTEST_DECORATED = (
    "test_gated_by_a_unittest_decorator",
    "test_gated_by_a_unittest_decorator_imported_by_name",
    "test_gated_by_a_unittest_decorator_imported_under_an_alias",
    "test_gated_by_a_unittest_decorator_through_a_module_alias",
)
_UNITTEST_METHOD = ("test_gated_by_a_unittest_method",)
```

Add after `test_the_registry_is_the_one_call_a_guard_may_make`:

```python
def test_unittests_decorator_and_method_are_gates_the_walker_finds():
    """`@unittest.skipIf`/`skipUnless` and `self.skipTest(...)` are the two `unittest` spellings the
    reducer's docstring listed as passing uncaught (spec 00114 D6). Both are gates now, matched like
    any other, and the decorator is recognised under each name `unittest` can be bound by -- the
    dotted module, a module alias, and the name imported from it under its own name or an alias."""
    for name in _UNITTEST_DECORATED:
        decorated = _fixture(name)
        assert decorated.kind == "skipif" and decorated.forms == (Form("path"),), f"{name}: {decorated}"
    method = _fixture(_UNITTEST_METHOD[0])
    assert method.kind == "skip-site" and method.forms == (Form("path"),), method
```

`_FIXTURE_FUNCTIONS` already walks the whole fixture tree and spans each function from its first decorator (Task 3), so
these five gates resolve to their cases without a change to it, and the fixture goes from 50 gates to 55.

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_live_venue_opt_in.py -k unittests_decorator -q`
Expected: FAIL in `_fixture` with `test_gated_by_a_unittest_decorator: 0 gates`. A run of the whole file is red twice
over at this point — `test_every_fixture_case_carries_a_disposition` too, because the five cases just appended are in
`_DISPOSED` and carry no gate until Step 3 widens discovery. Both go green there.

- [ ] **Step 3: Widen discovery**

Beside `_pytest_modules`, the same recognition for `unittest`'s two decorators:

```python
_UNITTEST_SKIPS = ("skipIf", "skipUnless")


def _unittest_skip(func: ast.AST, module: Module) -> bool:
    """`skipIf`/`skipUnless` reached through `unittest` under any name it is bound to, or imported from
    it under any name -- the alias tolerance `_pytest_modules` and `_pytest_bindings` give pytest's
    spellings. `_imported` keeps the BOUND name and loses the imported one, so the bare form is
    resolved off the import nodes through `_bound_to_module` (spec 00114 Task 3) rather than that dict:
    `from unittest import skipIf as skip_if` is a fourth spelling of the construct, and a name bound
    to anything else is not one of them. `module.imported` is asked first and answers in one lookup:
    every name the walk below can bless is one that dict maps to `unittest`, and this function runs
    for every bare-name call in every module walked."""
    if isinstance(func, ast.Attribute) and func.attr in _UNITTEST_SKIPS:
        return isinstance(func.value, ast.Name) and module.imported.get(func.value.id) == "unittest"
    if not (isinstance(func, ast.Name) and module.imported.get(func.id) == "unittest"):
        return False
    return any(func.id in _bound_to_module(module, f"unittest.{n}") for n in _UNITTEST_SKIPS)
```

The `module.imported` precondition is the difference between a walk and a hang. `_bound_to_module`
re-walks the whole module tree, twice — once per name in `_UNITTEST_SKIPS` — and without the
precondition that pair of walks runs for every bare-name `ast.Call` under `tests/`. Measured over the
248 modules the walker reads, timing the arm alone over the 36499 `ast.Call` nodes a walk of them
visits, 22613 of them bare names: 146s with the arm as a bare `any(...)`, 0.25s with the dict lookup in
front of it. Those two are the ARM's own cost and not the walk's — the file reads `8 passed` in 9s
today, with three tests that each call `_tree_gates()` — so what the missing precondition looks like at
Step 4 is a run of minutes where seconds are expected. `_registry_call` makes the same call from
`_match` alone, over the migrated tree's 65 guards rather than over every call node, which is why Task 3 does not pay
it and needs no precondition.

and in `_gates`, a third arm beside the `mark.skipif` one:

```python
        elif isinstance(node, ast.Call) and _unittest_skip(node.func, module) and node.args:
            condition, extra = _as_expression(node.args[0])
            out.append(_gate(node.lineno, "skipif", [condition], module, None, extra))
```

In `_is_pytest_call`, before its final `return False`:

```python
    if isinstance(func, ast.Attribute) and func.attr == "skipTest" and isinstance(func.value, ast.Name) and func.value.id == "self":
        return attribute == "skip"
```

and rewrite that function's docstring: its last paragraph (739-740) says `@unittest.skipIf(...)` and `self.skipTest(...)`
"produce no gate, so a gate spelled either way is outside both assertions", which this step inverts. It becomes the
reach the function now has — `self.skipTest(...)` is a skip here, `skipIf`/`skipUnless` are gates through `_gates`' third
arm, and the receiver `self.skipTest` is recognised on is the name `self` alone.

- [ ] **Step 4: Run the file**

Run: `uv run pytest tests/test_live_venue_opt_in.py -q`
Expected: all passed; the tree's gate count is unchanged (no test module under `tests/` uses `unittest`'s skip).

- [ ] **Step 5: Commit**

```bash
git add tests/test_live_venue_opt_in.py
git commit -m "test(venue): unittest's decorator and method are gates the walker finds"
```

- [ ] **Step 6: Prove the guard bites, then amend the body with the verdict**

```bash
infra/scripts/mutate-probe.sh --file tests/test_live_venue_opt_in.py --control 's/^    def test_gated_by_a_unittest_method(self):$/    def test_gated_by_a_unittest_method_renamed(self):/' --mutation 's/^        return attribute == "skip"$/        return False/' -- uv run pytest tests/test_live_venue_opt_in.py -k unittests_decorator -q
```

Expected: `KILLED (control proven)` — the mutation drops the `skipTest` arm and the method case finds no gate; the control renames the fixture case so `_fixture` finds nothing under the asserted name. Amend the commit body with the verdict, naming the script, the file, the mutation and the selector, as Task 1 Step 6 and Task 3 Step 8 do: a message carrying `KILLED (control proven)` without `mutate-probe` in it is what `infra/scripts/count-list.sh probe-verdicts-without-the-script` counts, over develop's history plus this branch, and once the PR merges the count has no way back.

---

### Task 5: The reducer's remains go, and the docstring says what the file holds

**Files:**
- Modify: `tests/test_live_venue_opt_in.py`, `infra/scripts/count-list.sh:272-274`.

- [ ] **Step 1: Delete every helper the file-structure section lists as replaced**

Run `uv run pytest tests/test_live_venue_opt_in.py -q` after the deletion; a `NameError` names a helper the matcher still needs — keep that one and re-run until green. `builtins` goes from the imports once `_read_module` and the rest of the resolution are gone: it is read only there, the registry test reading `REGISTRY_BUILTINS` instead. `functools` STAYS — `@functools.cache` decorates `_module`, which the file-structure section keeps.

- [ ] **Step 2: Re-true the count entry's comment, then rewrite the module docstring**

Re-true `infra/scripts/count-list.sh`'s comment above `c_skip_gate_contract` (:272-274) in the same commit. It carries
the same three reducer clauses `CLAUDE.md:32` does — "a computed key, or a call it can neither resolve in this repo nor
attribute to a library, refused; a library call attributed, not walked. The guard is the count; its docstring lists what
passes it uncaught -- five binding shapes, two `unittest` forms." Under D2/D3 every call but a registry call is refused,
resolvable and library calls included, and Task 3 and Task 4 close the five bindings and the `unittest` forms; what the
comment becomes is the six forms and the refusal of everything else. The count entry at :275 does not change. The
guidance line is the owner's and rides its own branch (Task 6 Step 2); this comment is not, and a comment that stays has
to be correct.

Then rewrite the module docstring. It states, in this order: the one rule (the opt-in) and the two halves this file holds — every environment-keyed gate reads the one name; every gate matches a form, and no form reaches a venue; the six forms by name; the registry and the test that holds it closed; what the file does not hold — gate discovery beyond the fixture's positions, the provenance of a registry call's arguments, and a venue answer joined into a literal-rooted path with `/`, which the receiver rule roots past (spec D5); and two sentences of history: the reducer (2026-09-11 to this change) followed calls and read what a helper reached, and the four hand counts of its blind spots were each wrong, which is why a closed set of forms replaced it. Delete the sections "WHAT IT DOES NOT HOLD", "AND WHAT THE TWO SURVIVING CLAIMS THEMSELVES MISS" and "The diagnosis"; the diagnosis goes to the commit message.

The control test's docstring is replaced WHOLE rather than edited for its number. It carries "Fifty-five of the tree's
sixty-one" twice — already stale at 60 of 66 on `develop`, and 59 of 65 once Task 2 lands — and a mechanism claim that is false under the matcher: "a guard that
refused every gate would still pass its own fixture while turning all fifty-five red", when `plain` filters on
`gate.env`, so a matcher that refused every gate leaves `env` empty everywhere, `plain` non-empty and this test GREEN.
What it becomes:

```python
    """The one-name assertion passes on an empty set, so it needs a live counter-shape: a skip gate
    that reads no environment at all and must keep passing. Most of the tree's gates are that shape;
    take the split from a run. What this holds is the EMPTY-set degeneracy alone -- a matcher that read
    the opt-in at every gate would leave `plain` empty and fail here. The other direction, a matcher
    that refused every gate, leaves `plain` untouched and is held by
    `test_every_skip_gate_in_tests_matches_a_form` instead."""
```

- [ ] **Step 3: Run the count entry and the guard's prose count**

Run: `infra/scripts/count-list.sh skip-gate-contract`
Expected: `skip-gate-contract	<N> passed`, N the file's case count. Then run `infra/scripts/count-list.sh prose-chars`
and quote that one number in the commit message. There is no honest "before" to pair it with by the time this step
runs: Step 1 has already deleted the reducer's helpers and Step 2 has already rewritten two docstrings, which are the
whole of this task's effect on that count, and recovering the earlier figure would take a second worktree at Task 4's
tip that no step here makes.

- [ ] **Step 4: Commit**

```bash
git add tests/test_live_venue_opt_in.py infra/scripts/count-list.sh
git commit -m "test(venue): the reducer's resolution goes; the docstring holds what the matcher holds"
```

---

### Task 6: Closeout

**Files:**
- Modify: `docs/open-topics/T0190-live-venue-opt-in-flags-disagree.md` → `docs/open-topics/archive/`,
  `docs/open-topics/README.md` (rendered).
- Create: three topics under `docs/open-topics/`, serials minted by `topic-ops`.

- [ ] **Step 1: Resolve T0190 through `topic-ops`**

The remainder is delivered: flip `status: partial` → `resolved`, delete `ripe_when`, rename `## Done so far` to
`## Resolution` with one closing paragraph naming spec 00114, this branch's commits and the census (the tree's gate
count from `_tree_gates()`, six forms, 27 declarations through the registry), delete `## Suggested next steps`,
`git mv` the file into `docs/open-topics/archive/`.

Then mint, through the same skill and into the same commit, FOUR topics. `## Suggested next steps` is where the
DISCOVERY residual is recorded, and this step deletes it along with the `ripe_when` that fires on any change to
`tests/test_live_venue_opt_in.py`; the other three are recorded only in this branch's own spec, which is a statement of
scope and not a queue anything evaluates. A residual this step does not park is parked nowhere and evaluated by no
trigger.
Each `ripe_when` is an activity.

1. **The registry's arguments** — `nothing_found(rows)` declares a provenance it cannot check, and a scan helper that
   takes the path and does the glob itself would. Ripe on the next branch that adds a `nothing_found` gate. It is the
   residual the spec's Out-of-scope entry parks (`docs/specs/00114-skip-gate-matcher-design.md:72`).
2. **Gate discovery beyond the fixture's positions** — the residual T0190's second `## Suggested next steps` bullet
   now defers rather than states: read at `origin/develop`, that bullet is one sentence, "**What the two surviving
   assertions miss** is listed, planted shape by planted shape, in `tests/test_live_venue_opt_in.py`'s module
   docstring" (PR #562 cut the four clauses it used to carry). Task 5 Step 2 deletes the two sections of that docstring
   it points at, so the pointer and the text it points at both go in this branch and the residual would be recorded
   nowhere. The residual itself: gate DISCOVERY is asserted by nothing and cannot be asserted from inside the guard,
   because any set it computes to check the walker is computed by the walker. D6 and the spec's Out-of-scope entry
   state the limit, which is a statement of scope and not a queued follow-up. Ripe on the next branch that adds a skip
   in a position `_FIXTURE` does not already carry, or the next change to `_gates`. The spec's `## Out of scope`
   already parks this residual in the words entry 1 uses (`docs/specs/00114-skip-gate-matcher-design.md:70`), and
   neither entry carries a serial, so nothing is edited there — which is why this task's Files line and its `git add`
   reach `docs/open-topics/` and nothing else.
3. **The guidance clauses this branch falsifies** — the five `CLAUDE.md` clauses Step 2 quotes, carried in the topic
   rather than in the PR body. Ripe on the owner's next guidance branch.
4. **A venue answer joined into a literal-rooted path** — the receiver rule roots a chain and refuses every call
   written at the gate, and judges neither a `/` join's right operand nor a `pathlib` method's argument, so
   `s = _venue_name()` then `not (ROOT / s).exists()` matches `path` (spec D2, stated as the residual in D5). Rooting
   every operand instead refuses three of the tree's own parametrized dataset gates, which is why it was not done here.
   Ripe on the next branch that writes a `/` join over a name the gate's own function binds.

Then run `uv run python infra/scripts/topics-index.py` once over all five changes, and
`uv run pytest tests/test_open_topics_frontmatter.py -q`.

- [ ] **Step 2: Name the guidance edit as owed**

Two `CLAUDE.md` entries go false when this merges. The five clauses below are the text of topic 3, and the PR body's
`## Follow-ups` references that `T<NNNN>` and carries none of them: `.claude/skills/open-pr/SKILL.md:42` is explicit
that `## Follow-ups` may only reference a registered topic, because a PR description is never re-read after merge. The
edit itself is the owner's, on its own branch (spec D5). The sixth clause, the same three reducer sentences in
`infra/scripts/count-list.sh:272-274`, is NOT here: it is a comment rather than guidance and Task 5 Step 2 re-trues it.

`CLAUDE.md:33`, the reachability half:

- "no count command: nothing asserts it" — the count is now `infra/scripts/count-list.sh skip-gate-contract`, over
  what a gate is written and bound to: spec D5 names the one reading it does not reach, a venue answer joined into a
  literal-rooted path, and topic 4 below carries it.
- "`tests/test_live_venue_opt_in.py`'s docstring records that it takes a static analyser" — Task 5 Step 2 rewrites
  that docstring and it no longer says so.

`CLAUDE.md:32`, the one-name half — this branch is the count entry behind it, and three of its clauses describe the
reducer:

- "its gate a plain module-level reading the guard reduces" — the guard matches a form; it reduces nothing.
- "a computed key, or a call it can neither resolve in this repo nor attribute to a library, refused; a library call
  attributed, not walked" — under D2/D3 every call but a registry call is refused, a resolvable local call and a
  library call included. A session reading this clause would gate a test on a helper in its own file and meet a red
  count with no line telling it why.
- "its docstring lists the five binding shapes and two `unittest` forms that pass it uncaught and unrefused" — D2
  refuses the five, D6 makes the two `unittest` forms gates, and Task 5 Step 2 deletes the sections that listed them.

- [ ] **Step 3: Commit**

```bash
git add docs/open-topics/
git commit -m "docs(topics): T0190 resolved — the reachability half is held by the matcher"
```

- [ ] **Step 4: Open the PR through `open-pr`**

Title: `test(venue): every skip gate matches a form; T0190 resolved`. The branch name carries the serial and the title the topic, so the change-index row is owed; the read floor is Opus (no Fable path is touched). `## Follow-ups` names the four serials Step 1 minted and nothing else: the deferral sweep the skill runs before every create refuses a caveat that is not a registered topic or an explicit drop.
