# Skip-gate matcher — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every skip gate under `tests/` matches one of six enumerated forms or is refused, so the rule that no skip is decided by whether a venue answers is held by `infra/scripts/count-list.sh skip-gate-contract` rather than by nothing.

**Architecture:** `tests/test_live_venue_opt_in.py` keeps its gate discovery (the walker) and replaces its expression reducer with a matcher: a guard is matched against five manifest forms (path presence, uid, binary, the opt-in read, collection membership) plus a call into a new registry module, `tests/skip_gates.py`, whose three functions are the declarations for the 22 gates whose guard does not say what it reads. The registry is held closed by one test over its own AST. The 22 gates migrate first, under the reducer that still accepts them; the matcher then lands green; the reducer's resolution code is deleted last.

**Tech Stack:** Python 3.14, `ast`, pytest; `infra/scripts/mutate-probe.sh` for the verdicts; `topic-ops` for the closeout.

**Spec:** `docs/specs/00114-skip-gate-matcher-design.md`

## Global Constraints

- The guard file keeps its name, `tests/test_live_venue_opt_in.py`: `CLAUDE.md:33` and `infra/scripts/count-list.sh:275` name it, and neither is edited here (spec D5).
- Nothing is followed: an environment key is a string literal or a plain top-level `NAME = "<literal>"` assigned once in the module; every other binding is refused (spec D2).
- The registry `tests/skip_gates.py` imports only `shutil`, `subprocess`, `pathlib` and `typing`, calls only into those and builtins, and every public function's body is a single `return` (spec D4).
- No gate's decision moves in the migration: each rewritten guard is equivalent to the one it replaces — with the one
  exception spec D8 names, `tests/test_tape_bars_rest_control.py`'s `day is None` skip, whose input is filtered by
  Kraken's answer and which splits into a local skip and a venue `pytest.fail` (Task 2 Step 4).
- A commit that adds or changes a guard records its `mutate-probe.sh` verdict on that commit: the verdict is earned after the commit exists and recorded by a message-only amend of that commit, the tree frozen.
- Every commit is green over `uv run pytest tests/test_live_venue_opt_in.py tests/test_count_list.py` and the files the task touches; the branch carries no red intermediate commit (spec D8).
- A commit message ends with the `Co-Authored-By` and `Claude-Session` trailers the session reminder gives.

---

## File structure

- Create `tests/skip_gates.py` — the three declared readings.
- Modify `tests/test_live_venue_opt_in.py` — the matcher (`Form`, `_match`, `_plain_literal`, `_plain_collection`, `_key`, `_is_environ`, `_env_read_key`, `_registry_call`) replaces the reducer (`Reading`, `_NOTHING`, `_BODY_READING`, `_reads`, `_refuses`, `_locals_of`, `_classify`, `_fold`, `_owned_class`, `_owned_attribute`, `_classify_call`, `_read_module`, `_resolve`, `_follow`, `_environment_key`, `_PREDICATES`, `_BUILTINS`, `_MAPPING_READS`, `_MAPPING_VIEWS`, `_module_strings`, `_module_functions`, `_module_aliases`, `_module_path`, `_is_local_module`, `_is_environ_expression`, `_environ_aliases`, `_assigned`, `_module_scope`, `_body_expressions`, `_enclosing_function`, `OURS`); `Module` slims to `tree`, `imported`, `os_names`, `label`; `_os_aliases`, `_imported`, `_module`, `_module_of`, `_parents`, `_guards_of`, `_as_expression`, `_pytest_bindings`, `_pytest_modules`, `_skip_helpers`, `_is_pytest_call`, `_gates`, `_labelled`, `_second_flags`, `_unreadable`, `_tree_gates`, `_FIXTURE`, `_FIXTURE_GATES` stay; the module docstring is rewritten to what the file then holds.
- Modify the eight test files that carry the 22 gates: `tests/test_count_list.py`, `tests/test_infra_archive_pull_template.py`, `tests/test_infra_tape_bars_template.py`, `tests/test_infra_verify_replay_template.py`, `tests/test_costmin_drift.py`, `tests/test_engine_venuestate.py`, `tests/test_registry_conformance.py`, `tests/test_tape_bars_rest_control.py`.
- Modify `docs/open-topics/T0190-live-venue-opt-in-flags-disagree.md` (moved to `archive/`), create the topic for the
  registry's unverifiable argument, and re-render `docs/open-topics/README.md` at closeout.

---

### Task 1: The registry and the test that holds it closed

**Files:**
- Create: `tests/skip_gates.py`
- Modify: `tests/test_live_venue_opt_in.py` (constants after `OPT_IN` at line 88; one test after `test_the_tree_holds_the_control_that_keeps_the_one_name_assertion_falsifiable`)
- Test: `tests/test_live_venue_opt_in.py::test_the_registry_reads_nothing_a_form_could_not`

**Interfaces:**
- Produces: `tests.skip_gates.develop_resolves() -> bool`, `tests.skip_gates.no_binary(name: str) -> bool`, `tests.skip_gates.nothing_found(rows: object) -> bool`; in the guard file `REGISTRY = TESTS / "skip_gates.py"`, `REGISTRY_MODULE` derived from it, and `REGISTRY_IMPORTS = frozenset({"shutil", "subprocess", "pathlib", "typing"})`. `REGISTRY` and `REGISTRY_IMPORTS` are read by this task's test alone; `REGISTRY_MODULE` is the dotted name Task 3's `_registry_call` keys on, derived from `REGISTRY` so the path and the module name cannot disagree. Also produces `_call_root(node) -> str`, read by this task's test alone and named in neither column of the File structure, so Task 5 leaves it.

- [ ] **Step 1: Write the failing test**

After `OPT_IN = "ZCRYPTO_LIVE_VENUE_TESTS"`:

```python
REGISTRY = TESTS / "skip_gates.py"
# The dotted name `_registry_call` keys on, derived from the path so the two cannot drift apart.
REGISTRY_MODULE = f"{TESTS.name}.{REGISTRY.stem}"
REGISTRY_IMPORTS = frozenset({"shutil", "subprocess", "pathlib", "typing"})
```

After the control test:

```python
def _call_root(node: ast.AST) -> str:
    """The name a call reaches through: `shutil` in `shutil.which(...)`, `Path` in `Path(x).resolve()`,
    so a chained call is judged by what it started from rather than by its first dotted segment."""
    while isinstance(node, (ast.Attribute, ast.Call, ast.Subscript)):
        node = node.func if isinstance(node, ast.Call) else node.value
    return node.id if isinstance(node, ast.Name) else ast.unparse(node)


def test_the_registry_reads_nothing_a_form_could_not():
    """A call into `tests/skip_gates.py` is a form (spec 00114 D3), so the module is held closed: its
    imports are within the four named, every call reaches a name one of those imports binds or a
    builtin, the one process it may launch is `git`, and every public function it defines anywhere is
    one `return`. A registry that could open a socket would be the reducer's leak, one file over --
    and `subprocess` is on the allowlist, so the launch and the walk are what close that direction."""
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
    allowed = set(bound) | set(dir(builtins))
    assert roots <= allowed, f"the registry calls {sorted(roots - allowed)}"
    for call in calls:
        if _call_root(call.func) != "subprocess":
            continue
        argv = call.args[0] if call.args else None
        launched = isinstance(argv, ast.List) and argv.elts and isinstance(argv.elts[0], ast.Constant) and argv.elts[0].value == "git"
        assert launched, f"a process launch that is not git: {ast.unparse(call)}"
    public = [
        f for f in ast.walk(tree) if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef)) and not f.name.startswith("_")
    ]
    assert {f.name for f in public} == {"develop_resolves", "no_binary", "nothing_found"}
    for f in public:
        body = [s for s in f.body if not (isinstance(s, ast.Expr) and isinstance(s.value, ast.Constant))]
        assert len(body) == 1 and isinstance(body[0], ast.Return), f"{f.name} is more than one return"
```

(`builtins` is already imported at line 78.) `bound` maps each name an import binds to the module it
came from, so the import check and the call check read one dict: a call may reach only a name an
allowlisted import bound, or a builtin. `ast.walk` rather than `tree.body` for the functions, and the
`git` constraint on the launch, are the two clauses that refuse a registry carrying
`if shutil.which("curl"): def venue_answers(): return subprocess.run(["curl", ...])` — which passes
every other clause.

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
    return subprocess.run(["git", "-C", str(REPO), "rev-parse", "--verify", "--quiet", "develop"], capture_output=True).returncode == 0


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

```bash
infra/scripts/mutate-probe.sh --file tests/skip_gates.py --control 's/^def nothing_found/def nothing_seen/' --mutation 's/^import shutil$/import shutil, socket/' -- uv run pytest tests/test_live_venue_opt_in.py -k registry_reads_nothing -q
```

Expected: `KILLED (control proven, tree restored byte-identically)`. Then `git commit --amend` adding one paragraph: `Proven with infra/scripts/mutate-probe.sh on tests/skip_gates.py: the mutation imports socket, the control renames a public function, the probe is -k registry_reads_nothing — KILLED (control proven).`

---

### Task 2: The 22 gates declare their reading

**Files:**
- Modify: `tests/test_count_list.py:62-64` and its eleven call sites (ten `skipif` decorators at :198, :250, :317, :367, :414, :444, :461, :482, :494, :579, and the `assert` at :56); `tests/test_infra_archive_pull_template.py:59-61,100-102,125-127,196-198`; `tests/test_infra_tape_bars_template.py:45-47,101-103`; `tests/test_infra_verify_replay_template.py:337-339`; `tests/test_costmin_drift.py:20-22`; `tests/test_engine_venuestate.py:77-79`; `tests/test_registry_conformance.py:92-94`; `tests/test_tape_bars_rest_control.py:51-53,60-83`.

**Interfaces:**
- Consumes: `develop_resolves`, `no_binary`, `nothing_found` from Task 1.

The reducer still in place reads a call into a module of ours and follows it, so a registry call is clean under it exactly as today's `_develop_resolves()` and `bash is None` are: this commit changes what the gates SAY, not what any of them decides, and the current tree assertion stays green over it.

- [ ] **Step 1: Record the baseline**

Run: `uv run pytest tests/test_live_venue_opt_in.py tests/test_count_list.py tests/test_infra_archive_pull_template.py tests/test_infra_tape_bars_template.py tests/test_infra_verify_replay_template.py tests/test_costmin_drift.py tests/test_engine_venuestate.py tests/test_registry_conformance.py tests/test_tape_bars_rest_control.py -q -rs`
Keep the summary line and the `-rs` skip lines: Step 5 compares against them.

- [ ] **Step 2: Migrate the ten count-list gates**

In `tests/test_count_list.py`: delete `_develop_resolves` (lines 62–64) and `import subprocess` if nothing else in the
file uses it; add `from tests.skip_gates import develop_resolves`; replace every `_develop_resolves()` call with
`develop_resolves()`. There are ELEVEN, not ten: the ten `@pytest.mark.skipif(not _develop_resolves(), ...)` decorators
and the unconditional `assert _develop_resolves(), (...)` at `tests/test_count_list.py:56`, inside
`test_this_checkout_carries_what_the_counts_measure_from`. The spec's gate census counts ten because an `assert` is not
a gate; leaving it behind is a `NameError` on every run of that file.

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

`no_binary("found")` would skip unconditionally on every host, which no run of Step 5 prints a line for.

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

```python
    healed = [d for d in archived if is_heal_complete(index, PAIR, d)]
    if nothing_found(healed):
        pytest.skip(f"no heal-complete {PAIR} day under {PRIMARY_ROOT}")
```

goes directly below the `archived` gate, before `rows = fetch_ohlc(...)`, so the archive-only skip is decided before the
venue is touched. Then `covered` iterates `healed` rather than `archived`, and `day = next(...)` and its skip become:

```python
    if not covered:
        pytest.fail(
            f"Kraken REST reaches {stamps[0].date()}..{stamps[-1].date()} and covers no heal-complete "
            f"{PAIR} day (the archive holds {healed[0]}..{healed[-1]})"
        )
    day = covered[-1]
```

`covered` is ascending, so `covered[-1]` is the newest heal-complete covered day — the same day `next(... reversed(covered) ...)`
picked. Re-true the comment above the `if stamps[-1] - stamps[0] < timedelta(days=1):` check in the same commit (it moves
when the block above it is inserted, so find it by its text): it justified a separate `pytest.fail`
by saying the two cases it could not separate both left `covered` empty, and an empty `covered` is now a fail too; the
check stays for the diagnostic it prints. `is_heal_complete` is now called over every archived day rather than lazily
from the newest — a local index read, on a test that runs only with the opt-in set.

The gate count is unchanged: one skip gate leaves this file and one arrives, so `_tree_gates()` stays at 66 and the
migrated set stays at 22.

- [ ] **Step 5: Run the guard and every touched file**

Run the Step 1 command again.
Expected: the same summary line and the same skip lines as Step 1 recorded, and the guard file green, the reducer
reading each registry call as a helper of ours that reaches nothing remote. The Step 4 split does not move a line
here: without `ZCRYPTO_LIVE_VENUE_TESTS=1`, `test_tape_bars_match_kraken_rest_ohlc` skips at its opt-in gate before
either half is reached, so this run cannot see the one decision that did move — read the diff for that, not the
summary. A line that DOES move is a gate rewritten wrong.

- [ ] **Step 6: Commit**

```bash
git add tests/
git commit -m "test: the 22 skip gates that read a helper, a which() result or a local now say so through tests/skip_gates.py"
```

---

### Task 3: The matcher over the fixture, and the tree assertion

**Files:**
- Modify: `tests/test_live_venue_opt_in.py` — `Gate` (line 100), `Module` (line 110), `_module_of` (line 288), `_gate` (line 791), `_gates` (line 802), the tree assertion at line 878, the five fixture tests from line 1119, three new fixture tests, eight fixture cases appended to `_FIXTURE`.

**Interfaces:**
- Consumes: `REGISTRY_MODULE` from Task 1; `_imported(tree) -> dict[str, str]`, `_os_aliases(tree) -> frozenset[str]`, `_as_expression`, `_guards_of`, `_is_pytest_call` (existing).
- Produces: `Form(name: str, key: str | None = None)`; `_match(guard: ast.AST, module: Module) -> list[Form] | str`; `Gate.forms: tuple[Form, ...]`; `_fixture_span(f) -> tuple[int, int]` and `_fixture_case(gate: Gate) -> str` (the fixture function a gate sits in); `_REFUSAL_REMEDY` rewritten in place.

- [ ] **Step 1: Write the failing fixture tests**

Append to `_FIXTURE`, before its closing `"""`:

```python
from tests.skip_gates import no_binary
import tests.skip_gates as declared
from os import environ
from tests.basket_fixture import *

ANNOTATED: str = "ZCRYPTO_SOMETHING_ELSE"
if True:
    IN_IF = "ZCRYPTO_SOMETHING_ELSE"
try:
    IN_TRY = "ZCRYPTO_SOMETHING_ELSE"
except NameError:
    IN_TRY = ""


class _Keyed:
    KEY = "ZCRYPTO_SOMETHING_ELSE"

    def test_gated_on_a_second_flag_whose_key_is_an_attribute(self):
        if os.environ.get(self.KEY) != "1":
            pytest.skip("a key read off an attribute is not the plain form")


def test_gated_on_the_registry_by_name():
    if no_binary("jq"):
        pytest.skip("the registry is the one helper a guard may call")


def test_gated_on_the_registry_by_module():
    if declared.no_binary("jq"):
        pytest.skip("the module spelling of the same call")


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
```

Spec D2 names five bindings an opt-in key may arrive by and refuses all five; the fixture carried two of them (a
computed key and a constant a function rebinds). The three appended above — a constant bound under a module-level `try`,
a key read as `self.KEY`, and a name arriving by star-import — are the other three, so every binding D2 refuses has a
case that asserts the refusal. `STARRED` is bound by nothing in the fixture, which is the point: `_plain_literal` finds
no `Store` for it and refuses.

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
    return next(f.name for f in _FIXTURE_FUNCTIONS if _fixture_span(f)[0] <= gate.line <= _fixture_span(f)[1])


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
)
```

Replace the five fixture tests from `test_a_second_opt_in_name_is_caught_in_every_spelling_the_language_offers` to `test_a_gate_with_no_venue_dependency_passes_beside_them` with:

```python
def test_every_second_opt_in_spelling_is_caught_by_one_of_the_two_assertions():
    """Twenty-two ways to put a second flag in front of a skip. Ten are READ -- the key is a literal or a
    plain module constant, so the matcher names it and the one-name assertion refuses it; twelve are
    REFUSED -- the mapping or the key is reached some other way, and the matcher follows nothing (spec
    00114 D2), so no form matches and the every-gate-matches assertion refuses it. The two tuples are
    the count: a spelling added to the fixture lands in one of them or nothing checks it."""
    for name in _SECOND_FLAG_NAMED:
        gate = _fixture(name)
        assert gate.env == ("ZCRYPTO_SOMETHING_ELSE",) and gate.opaque == (), f"{name}: {gate}"
    for name in _SECOND_FLAG_REFUSED:
        gate = _fixture(name)
        assert gate.env == () and gate.opaque, f"{name}: {gate}"
    for control in ("test_gated_on_the_flag", "test_fails_rather_than_skips_when_the_opt_in_is_set"):
        assert _fixture(control).env == (OPT_IN,), f"{control}: the one opt-in must be read, or the count above proves nothing"


def test_every_reachability_spelling_is_refused():
    """A venue probe -- inline, in a helper, on a class, through a module of ours that is not the
    registry -- matches no form. `basket_fixture.grids()` is a real helper that reads nothing remote
    and it is refused too: a call is a form only into the registry (spec 00114 D3), and the price of
    following nothing is that a clean helper declares itself there or is rewritten at the gate."""
    for name in _REACHABILITY_REFUSED:
        gate = _fixture(name)
        assert gate.forms == () and gate.opaque, f"{name}: {gate}"


def test_the_registry_is_the_one_call_a_guard_may_make():
    for name in ("test_gated_on_the_registry_by_name", "test_gated_on_the_registry_by_module"):
        gate = _fixture(name)
        assert gate.forms == (Form("registry"),) and gate.opaque == (), f"{name}: {gate}"


def test_the_fixture_carries_every_position_a_skip_can_sit():
    (unchanged: keep the existing body and docstring)


def test_a_gate_with_no_venue_dependency_passes_beside_them():
    """The degeneracy control. A guard that flagged every skip would pass its own fixture and refuse
    the dataset gates that are most of `tests/` -- an absent dataset is not an outage read as coverage."""
    gate = _fixture("test_gated_on_a_local_dataset")
    assert gate.forms == (Form("path"),) and gate.env == () and gate.opaque == (), f"got {gate}"
```

- [ ] **Step 2: Run them and read WHICH failure fired**

Run: `uv run pytest tests/test_live_venue_opt_in.py -k "second_opt_in_spelling or reachability_spelling or one_call_a_guard or no_venue_dependency" -q`
Expected: 4 failed, at RUN time and not at collection — nothing references `Form` at import time, so the module imports.
`test_the_registry_is_the_one_call_a_guard_may_make` and `test_a_gate_with_no_venue_dependency_passes_beside_them` raise
`NameError: name 'Form' is not defined`; `test_every_reachability_spelling_is_refused` raises `AttributeError: 'Gate'
object has no attribute 'forms'`; and `test_every_second_opt_in_spelling_is_caught_by_one_of_the_two_assertions` fails on
the FIRST name of `_SECOND_FLAG_REFUSED` with `gate.env == ('ZCRYPTO_SOMETHING_ELSE',)`, because the reducer FOLLOWS
`_opted_in()` where the matcher will refuse it. Its `_SECOND_FLAG_NAMED` loop passes under the reducer, which is right:
those ten are the spellings both engines read.

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

Replace everything from `_REFUSAL_REMEDY` to `_classify_call`'s end (lines 397–620) with the block below. The span
starts at 397, not at `class Reading` on 402, because the block re-defines `_REFUSAL_REMEDY` and the old one lives at
397 — outside a 402 span, and named in neither column of the File structure, so it would survive to the tip as a
second, contradictory assignment. It has no reader in the file today. The span also takes `_body_expressions` (509),
which the File structure now lists as replaced.

```python
_PRESENCE = ("exists", "is_file", "is_dir")
_ENV_READS = ("get", "getenv")
_REFUSAL_REMEDY = (
    "write the guard as a presence check on a path, `os.geteuid() == 0`, `shutil.which('<name>') is None`, "
    "a read of the one opt-in under a literal or plain module-constant key, membership in a module-level "
    "constant collection of literals, or a call into tests/skip_gates.py"
)


def _assignments(name: str, module: Module) -> list[ast.AST]:
    """Every node that binds `name` anywhere in the module, so a plain constant is one that is bound once."""
    return [n for n in ast.walk(module.tree) if isinstance(n, ast.Name) and n.id == name and isinstance(n.ctx, ast.Store)]


def _plain_literal(name: str, module: Module) -> str | None:
    """`NAME = "<literal>"` at the module's top level, bound nowhere else (spec 00114 D2)."""
    if len(_assignments(name, module)) != 1:
        return None
    for node in module.tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) and node.targets[0].id == name:
            value = node.value
            return value.value if isinstance(value, ast.Constant) and isinstance(value.value, str) else None
    return None


def _plain_collection(name: str, module: Module) -> bool:
    """`NAME = (...)`, `[...]`, `{...}` or `frozenset({...})` of literals at the top level, bound once."""
    if len(_assignments(name, module)) != 1:
        return False
    for node in module.tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name) and node.targets[0].id == name:
            value = node.value
            if isinstance(value, ast.Call) and isinstance(value.func, ast.Name) and value.func.id in ("frozenset", "set", "tuple") and len(value.args) == 1:
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
    """The key of `os.environ.get(K)`, `os.getenv(K)`, `environ.get(K)`, `getenv(K)` or `os.environ[K]`."""
    if isinstance(node, ast.Call) and node.args:
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr in _ENV_READS:
            if _is_environ(func.value, module) or (isinstance(func.value, ast.Name) and func.value.id in module.os_names):
                return node.args[0]
        if isinstance(func, ast.Name) and func.id == "getenv" and module.imported.get("getenv") == "os":
            return node.args[0]
    if isinstance(node, ast.Subscript) and _is_environ(node.value, module):
        return node.slice
    return None


def _registry_call(node: ast.Call, module: Module) -> bool:
    func = node.func
    if isinstance(func, ast.Name):
        return module.imported.get(func.id) == REGISTRY_MODULE
    return isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) and module.imported.get(func.value.id) == REGISTRY_MODULE


def _opt_in(key_node: ast.AST, module: Module) -> list[Form] | str:
    key = _key(key_node, module)
    if key is None:
        return f"an environment key that is not a literal or a plain module constant: {ast.unparse(key_node)}"
    return [Form("opt-in", key)]


def _match(guard: ast.AST, module: Module) -> list[Form] | str:
    """The forms this guard is made of, or why it is refused (spec 00114 D1-D3)."""
    node = guard
    while isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        node = node.operand
    if isinstance(node, ast.BoolOp):
        forms: list[Form] = []
        for value in node.values:
            got = _match(value, module)
            if isinstance(got, str):
                return got
            forms.extend(got)
        return forms
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in _PRESENCE and not node.args and not node.keywords:
        return [Form("path")]
    if isinstance(node, ast.Call) and _registry_call(node, module):
        return [Form("registry")]
    if isinstance(node, ast.Compare) and len(node.ops) == 1:
        left, op, right = node.left, node.ops[0], node.comparators[0]
        if isinstance(op, ast.Eq) and isinstance(left, ast.Call) and ast.unparse(left.func) in {f"{n}.geteuid" for n in module.os_names}:
            if isinstance(right, ast.Constant) and right.value == 0:
                return [Form("uid")]
        if isinstance(op, ast.Is) and isinstance(right, ast.Constant) and right.value is None and isinstance(left, ast.Call):
            if ast.unparse(left.func) == "shutil.which" and len(left.args) == 1 and isinstance(left.args[0], ast.Constant):
                return [Form("binary")]
        if isinstance(op, (ast.Eq, ast.NotEq)) and isinstance(right, ast.Constant) and isinstance(right.value, str):
            key_node = _env_read_key(left, module)
            if key_node is not None:
                return _opt_in(key_node, module)
        if isinstance(op, (ast.In, ast.NotIn)) and _is_environ(right, module):
            return _opt_in(left, module)
        if isinstance(op, (ast.In, ast.NotIn)) and isinstance(right, ast.Name) and _plain_collection(right.id, module):
            return [Form("membership")]
    return f"no form matches {ast.unparse(guard)!r}"
```

Rewrite `_gate` and the two calls to it in `_gates`:

```python
def _gate(line: int, kind: str, guards: list[ast.AST], module: Module, extra=()) -> Gate:
    forms: list[Form] = []
    refusals: list[str] = list(extra)
    for guard in guards:
        got = _match(guard, module)
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

In `_gates`: `out.append(_gate(node.lineno, "skipif", [condition], module, extra))` and `out.append(_gate(node.lineno, "skip-site", guards, module))`; delete the `scope = ...` line and the comment above it. Delete `_module_scope`, `_locals_of` and
`_enclosing_function`, whose only call site is that `scope` line — left behind it is a helper and a docstring nothing
reaches, in the commit that removes the reducer's dead weight.

- [ ] **Step 4: Run the fixture tests to verify they pass**

Run: `uv run pytest tests/test_live_venue_opt_in.py -q -k "not skip_gate_in_tests and not the_tree and not every_environment"`
The three tree assertions carry `skip_gate_in_tests`, `the_tree` and `every_environment`; `not tree` does not deselect
`test_no_skip_gate_in_tests_is_decided_by_something_this_file_cannot_read`, which walks all 66 tree gates and would be
diagnosed here against the fixture's list.
Expected: every fixture test passes. A fixture case whose disposition differs from its tuple is a matcher defect or a wrong tuple: the tuple is right when the case's key is a literal or a once-bound top-level string constant read straight off `os.environ`/`os.getenv`/`environ`, and wrong otherwise — fix the matcher, never move the name.

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
Expected: all passed; `_tree_gates()` returns 66 — the fixture's 38 gates are judged separately, because they live in
the `_FIXTURE` string literal, which no parse of this module sees as code. A tree site the assertion names here is a gate outside the 22 whose key is bound other than as a plain top-level literal, or whose collection is not literal: rewrite that gate to the plain form in this commit and name it in the message.

- [ ] **Step 6: Record what the assertion names against the pre-migration tree**

In a throwaway worktree at `develop` — never the main checkout, whose tree peers share, and never the stash, which is shared too — copy the matcher in and run its tree assertion over the unmigrated gates:

```bash
git worktree add ../wt-premig develop
cp tests/test_live_venue_opt_in.py ../wt-premig/tests/test_live_venue_opt_in.py
( cd ../wt-premig && uv run python -c "import tests.test_live_venue_opt_in as g; [print(f'{l}:{gt.line} [{gt.kind}] {gt.guards}') for l, gt in g._unreadable(g._tree_gates())]" | sort | nl )
git worktree remove --force ../wt-premig
```

Expected: exactly the 22 sites of the spec's census, one numbered line each — `nl`'s last number is the count. The rows
are read off `_unreadable(_tree_gates())` rather than off a failing pytest run because pytest prefixes every line of an
assertion message with `E` and the first with `AssertionError:`, so no line of that output is anchored at `^tests/`.
Quote the count and the files in the commit message. A count other than 22 is a gate the census missed or a form the matcher over-accepts, and it is run down before the commit.

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

A real gate rewritten unmatched:

```bash
infra/scripts/mutate-probe.sh --file tests/test_costmin_drift.py --control 's/^    if nothing_found(snaps):$/    if nothing_found(snaps) or True:/' --mutation 's/^    if nothing_found(snaps):$/    if not snaps:/' -- uv run pytest tests/test_live_venue_opt_in.py -k matches_a_form -q
```

Expected: `KILLED (control proven)` — the mutation restores the bare local and the tree assertion names `tests/test_costmin_drift.py:22` — `Gate.line` for a
skip site is the `pytest.skip` call's line, not the `if` the mutation edits; the control's `or True` is a `BoolOp` whose second value no form matches, so the assertion refuses it too. Amend the commit body with both verdicts, naming the script, the files, the mutations and the selectors.

---

### Task 4: Discovery widened to `unittest`'s decorator and method

**Files:**
- Modify: `tests/test_live_venue_opt_in.py` — `_is_pytest_call` (line 733) and its docstring (739-740), `_gates`, a new
  `_unittest_skip`, `_FIXTURE`, one new test.

- [ ] **Step 1: Write the failing fixture test**

Append to `_FIXTURE`:

```python
import unittest
import unittest as ut
from unittest import skipUnless


class TestOld(unittest.TestCase):
    @unittest.skipIf(not ROOT.exists(), "no data")
    def test_gated_by_a_unittest_decorator(self):
        pass

    @skipUnless(ROOT.exists(), "no data")
    def test_gated_by_a_unittest_decorator_imported_by_name(self):
        pass

    @ut.skipIf(not ROOT.exists(), "no data")
    def test_gated_by_a_unittest_decorator_through_a_module_alias(self):
        pass

    def test_gated_by_a_unittest_method(self):
        if not ROOT.exists():
            self.skipTest("no data")
```

Three decorator spellings, not one: `_pytest_modules` and `_pytest_bindings` make every pytest recognition in this file
alias-tolerant, and a `unittest` arm that matched only the dotted `unittest.skipIf` would leave the two spellings a
`unittest`-style module is ordinarily written with (`from unittest import skipIf`, `import unittest as ut`) invisible to
both tree assertions — a discovery hole no assertion in the file can see, in the construct this task exists to close.

Add after `test_the_registry_is_the_one_call_a_guard_may_make`:

```python
def test_unittests_decorator_and_method_are_gates_the_walker_finds():
    """`@unittest.skipIf`/`skipUnless` and `self.skipTest(...)` are the two `unittest` spellings the
    reducer's docstring listed as passing uncaught (spec 00114 D6). Both are gates now, matched like
    any other, and the decorator is recognised under each name `unittest` can be bound by -- the
    dotted module, a module alias, and the bare name imported from it."""
    for name in (
        "test_gated_by_a_unittest_decorator",
        "test_gated_by_a_unittest_decorator_imported_by_name",
        "test_gated_by_a_unittest_decorator_through_a_module_alias",
    ):
        decorated = _fixture(name)
        assert decorated.kind == "skipif" and decorated.forms == (Form("path"),), f"{name}: {decorated}"
    method = _fixture("test_gated_by_a_unittest_method")
    assert method.kind == "skip-site" and method.forms == (Form("path"),), method
```

`_FIXTURE_FUNCTIONS` already walks the whole fixture tree and spans each function from its first decorator (Task 3), so
these four gates resolve to their cases without a change to it.

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_live_venue_opt_in.py -k unittests_decorator -q`
Expected: FAIL in `_fixture` with `test_gated_by_a_unittest_decorator: 0 gates`.

- [ ] **Step 3: Widen discovery**

Beside `_pytest_modules`, the same recognition for `unittest`'s two decorators:

```python
def _unittest_skip(func: ast.AST, module: Module) -> bool:
    """`skipIf`/`skipUnless` reached through `unittest` under any name it is bound to, or imported from
    it by name -- the alias tolerance `_pytest_modules` and `_pytest_bindings` give pytest's spellings.
    `_imported` keeps the BOUND name, so `import unittest as ut` and `from unittest import skipIf` both
    resolve and a name bound to anything else does not."""
    if isinstance(func, ast.Attribute) and func.attr in ("skipIf", "skipUnless"):
        return isinstance(func.value, ast.Name) and module.imported.get(func.value.id) == "unittest"
    return isinstance(func, ast.Name) and func.id in ("skipIf", "skipUnless") and module.imported.get(func.id) == "unittest"
```

and in `_gates`, a third arm beside the `mark.skipif` one:

```python
        elif isinstance(node, ast.Call) and _unittest_skip(node.func, module) and node.args:
            condition, extra = _as_expression(node.args[0])
            out.append(_gate(node.lineno, "skipif", [condition], module, extra))
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

Expected: `KILLED (control proven)` — the mutation drops the `skipTest` arm and the method case finds no gate; the control renames the fixture case so `_fixture` finds nothing under the asserted name. Amend the commit body with the verdict.

---

### Task 5: The reducer's remains go, and the docstring says what the file holds

**Files:**
- Modify: `tests/test_live_venue_opt_in.py`.

- [ ] **Step 1: Delete every helper the file-structure section lists as replaced**

Run `uv run pytest tests/test_live_venue_opt_in.py -q` after the deletion; a `NameError` names a helper the matcher still needs — keep that one and re-run until green. `functools` goes from the imports if nothing uses it after `_BODY_READING` and `_read_module` are gone.

- [ ] **Step 2: Rewrite the module docstring**

It states, in this order: the one rule (the opt-in) and the two halves this file holds — every environment-keyed gate reads the one name; every gate matches a form, and no form reaches a venue; the six forms by name; the registry and the test that holds it closed; what the file does not hold — gate discovery beyond the fixture's positions, and the provenance of a registry call's arguments; and two sentences of history: the reducer (2026-09-11 to this change) followed calls and read what a helper reached, and the four hand counts of its blind spots were each wrong, which is why a closed set of forms replaced it. Delete the sections "WHAT IT DOES NOT HOLD", "AND WHAT THE TWO SURVIVING CLAIMS THEMSELVES MISS" and "The diagnosis"; the diagnosis goes to the commit message. The control test's docstring drops its "Fifty-five of the tree's sixty-one" — a number that was already stale at 60 of 66 — for "most of the tree's gates are that shape; take the split from a run".

- [ ] **Step 3: Run the count entry and the guard's prose count**

Run: `infra/scripts/count-list.sh skip-gate-contract`
Expected: `skip-gate-contract	<N> passed`, N the file's case count. Run `infra/scripts/count-list.sh prose-chars` before and after and quote both in the commit message.

- [ ] **Step 4: Commit**

```bash
git add tests/test_live_venue_opt_in.py
git commit -m "test(venue): the reducer's resolution goes; the docstring holds what the matcher holds"
```

---

### Task 6: Closeout

**Files:**
- Modify: `docs/open-topics/T0190-live-venue-opt-in-flags-disagree.md` → `docs/open-topics/archive/`,
  `docs/open-topics/README.md` (rendered).
- Create: one topic under `docs/open-topics/`, serial minted by `topic-ops`.

- [ ] **Step 1: Resolve T0190 through `topic-ops`**

The remainder is delivered: flip `status: partial` → `resolved`, delete `ripe_when`, rename `## Done so far` to
`## Resolution` with one closing paragraph naming spec 00114, this branch's commits and the census (the tree's gate
count from `_tree_gates()`, six forms, 22 declarations through the registry), delete `## Suggested next steps`,
`git mv` the file into `docs/open-topics/archive/`.

Then mint, through the same skill and into the same commit, the topic the spec's Out-of-scope entry parks: the
registry's arguments — `nothing_found(rows)` declares a provenance it cannot check, and a scan helper that takes the
path and does the glob itself would. `ripe_when` is an activity: the next branch that adds a `nothing_found` gate.
The archived topic's `## Suggested next steps` is the only live record of that residual today and this step deletes
it, so without the new topic it is parked nowhere and evaluated by no trigger.

Then run `uv run python infra/scripts/topics-index.py` once over both changes, and
`uv run pytest tests/test_open_topics_frontmatter.py -q`.

- [ ] **Step 2: Name the guidance edit as owed**

Two `CLAUDE.md` entries go false when this merges, and the PR body's `## Follow-ups` names all five clauses, so the
owner's guidance branch inherits the list rather than re-deriving it. The edit is the owner's, on its own branch
(spec D5).

`CLAUDE.md:33`, the reachability half:

- "no count command: nothing asserts it" — the count is now `infra/scripts/count-list.sh skip-gate-contract`.
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

Title: `test(venue): every skip gate matches a form; T0190 resolved`. The branch name carries the serial and the title the topic, so the change-index row is owed; the read floor is Opus (no Fable path is touched).
