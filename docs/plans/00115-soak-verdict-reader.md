# The soak verdict row and the engine read shapes — implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `ops-daily.py report` prints one `soak verdict` row decided from a `soak-check` run over the journal alone, and the daily-ops classifier judges each `zcrypto engine` read subcommand against that subcommand's own options.

**Architecture:** Both halves live in `infra/scripts/ops_daily.py`. The classifier's one generated shape for six subcommands becomes a flag table per subcommand, held to the Typer app's real options by a test. The report gains `read_soak_verdict`, a runner-seamed check like the two that already follow `read_verdict`: its runner `soak_run` copies the newest success record's twelve `240` snapshots into a temporary store-shaped directory, runs `uv run zcrypto engine soak-check --json` over it from the repo root, and returns the payload, which the check reduces to `PASS`, `FAIL` or `unreadable:`.

**Tech Stack:** Python 3.14, pytest, Typer/Click introspection, polars through the repo's own `to_frame`/`write_parquet`; `infra/scripts/mutate-probe.sh` for the guard verdicts; `topic-ops` for the closeout.

**Spec:** `docs/specs/00115-soak-verdict-reader-design.md`

## Global Constraints

- No source file under `cli/` changes (spec D2): no image is rolled and the NAS gate cache's fingerprint does not move. The one `cli`-side edit is a test, `tests/test_engine_soak_command.py`.
- No file under `.claude/` changes (spec D7).
- Three real options stay OUT of the classifier's shapes (spec D5): `soak-check --json` writes the path it names; `soak-check --registry` and `tracking-report --ledger-export` name a file whose reader echoes content when it refuses it.
- The reduction order is fixed (spec D4): no payload or no canonical dataset is `unreadable:`; any other non-empty `void_reasons` is `FAIL` and is read BEFORE any verdict; then `panel.n_outside >= 3` is `FAIL`; otherwise `PASS`. The row never keys off one metric's `inconsistent`.
- `read_soak_verdict` takes its runner keyword-only with no default, as `read_unattended_upgrades` and `read_agentboard_cgroup` do.
- No string literal in `infra/scripts/ops_daily.py` carries a topic id, a spec serial or a decision number: `tests/test_internal_terms_not_operator_visible.py` walks that file. Provenance goes in the commit message.
- A commit that adds or changes a guard records its `infra/scripts/mutate-probe.sh` verdict on that commit: the verdict is earned after the commit exists and recorded by a message-only amend of that commit, the tree frozen, before the push.
- Every commit is green over `uv run pytest tests/test_ops_daily.py tests/test_engine_soak_command.py -q` and `uv run pre-commit run -a`.
- No step of Tasks 1, 2 or 4 reaches a host, a venue or a mount. Task 3's last step reads the read-only NAS journal mount and is run by the controller, not by a dispatched subagent.
- A new Markdown paragraph or list item is one line: no column wrap, no filler blank lines.
- A commit message ends with these two trailers:

```
Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01VpmFzSn7FrFTiq8hphvCaY
```

---

## File structure

- Modify `infra/scripts/ops_daily.py` — the per-sub flag table `_ZCRYPTO_READ_FLAGS` replaces `_ZCRYPTO_READ_SUBS` and its one generated shape (Task 1); `SOAK_*` constants and `read_soak_verdict` (Task 2); `derive_soak_store`, `soak_run`, two imports and one line of `main` (Task 3).
- Modify `tests/test_ops_daily.py` — the classifier fixtures and the table-against-CLI test (Task 1); the reduction tests (Task 2); the derived-store, runner and wiring tests, and one added line in each of the three existing tests that drive `main(["report"])` to a verdict (Task 3).
- Modify `tests/test_engine_soak_command.py` — one test pinning the payload keys the reduction reads (Task 2).
- Modify `docs/open-topics/T0210-soak-check-gating-verdicts-have-no-scheduled-reader.md` (resolved, moved to `archive/`), `docs/open-topics/T0184-soak-hhi-aggregate-averages-a-sentinel.md`, `docs/open-topics/T0201-store-type-door-cannot-see-a-wrong-instant.md`, and re-render `docs/open-topics/README.md` (Task 4).

---

### Task 1: The classifier judges each engine read sub by its own options

**Files:**
- Modify: `infra/scripts/ops_daily.py` (the block that begins ``# `zcrypto engine <sub>`: `exec-status` reads,`` and ends at the blank line above `# Pipeline filters.`)
- Test: `tests/test_ops_daily.py` (append at the end of the file)

**Interfaces:**
- Consumes: `_Shape`, `_FIRST_STAGE_SHAPES`, `_PATH`, `_FILEREF`, `_SINCE`, `_INT`, `_NAME` from `infra/scripts/ops_daily.py`; `classify_action`, `Tier`, and the test file's `_identity` resolver.
- Produces: `ops_daily._ZCRYPTO_READ_FLAGS: dict[str, dict[str, str | None]]` — sub name to its flag table, `None` meaning a valueless flag. `_ZCRYPTO_READ_SUBS` is removed; nothing else reads it.

- [ ] **Step 1: Append the failing tests to `tests/test_ops_daily.py`**

```python
# --- the `zcrypto engine` read shapes: one flag table per sub, held to the CLI's own options ---------------------

_ENGINE_READS = [
    "zcrypto engine exec-status --state-dir /var/lib/zcrypto-engine",
    "zcrypto engine report --journal-dir /mnt/zhao-crypto/engine-journal",
    "zcrypto engine decompose --journal-dir /mnt/zhao-crypto/engine-journal --since 2026-09-01 --until 2026-09-19 --json",
    "zcrypto engine accum-replay --minimums data/refdata/pairs.json --nav 10000.5 --json",
    "zcrypto engine tracking-report --gate-from 2026-W37 --simulated-fills --json",
    "zcrypto engine soak-check --journal-dir /mnt/zhao-crypto/engine-journal --store-dir /tmp/soak/store"
    " --canonical-dir /srv/ohlc-full --fee-per-side 0.006 --band 0.9 --floor 30 --null both --path fast",
    "sudo docker exec zcrypto-engine zcrypto engine soak-check",
]


@pytest.mark.parametrize("cmd", _ENGINE_READS)
def test_each_engine_read_sub_is_autonomous_with_its_own_options(cmd):
    assert ops_daily.classify_action(cmd, host="zcrypto", resolve=_identity) is ops_daily.Tier.AUTONOMOUS


# Every real option the table leaves out, with the reason it is out. A new CLI option lands in neither place and
# fails `test_the_engine_read_shapes_are_the_clis_own_options`, so someone decides which side it belongs on.
_ENGINE_OPTIONS_LEFT_OUT = {
    "soak-check": {
        "--json": "writes the path it names",
        "--registry": "`_load_registry_record` prints a line that is JSON but not an object",
    },
    "tracking-report": {"--ledger-export": "`read_ledger_export` prints the header line of the file it refuses"},
}


@pytest.mark.parametrize(
    "cmd",
    [
        "zcrypto engine soak-check --json /tmp/out.json",
        "zcrypto engine soak-check --json=/tmp/out.json",
        "zcrypto engine soak-check --json /var/lib/zcrypto-engine/exec/armed",
        # The CLI refuses a valueless `--json` here; a shape that admitted it would vouch for a form that cannot run.
        "zcrypto engine soak-check --json",
        "zcrypto engine soak-check --registry /etc/zcrypto-ops/alloy/alloy-secrets.env",
        "zcrypto engine tracking-report --ledger-export /opt/zcrypto-capture/logship-secrets.env",
        # Options of a sibling sub, which one shared shape used to admit everywhere.
        "zcrypto engine report --since 24h",
        "zcrypto engine report --date 2026-09-19 --pair XBTEUR",
        "zcrypto engine exec-status --journal-dir /mnt/zhao-crypto/engine-journal",
        "zcrypto engine decompose --nav 10000",
        # Not reads at all, so no table names them.
        "zcrypto engine cycle --at 2026-09-19T12:00:00+00:00 --replace",
        "zcrypto engine gate-export --textfile /tmp/gate.prom",
    ],
)
def test_an_engine_write_a_content_echoing_file_and_a_foreign_option_stay_prepared(cmd):
    assert ops_daily.classify_action(cmd, host="zcrypto", resolve=_identity) is ops_daily.Tier.PREPARED


def _engine_cli_options() -> dict[str, dict[str, bool]]:
    """`{sub: {option: is_flag}}` for every `zcrypto engine` command, read off the Typer app itself."""
    import typer

    from cli.engine.command import engine_app

    group = typer.main.get_command(engine_app)
    return {
        name: {opt: param.is_flag for param in sub.params if param.param_type_name == "option" for opt in param.opts}
        for name, sub in group.commands.items()
    }


def test_the_engine_read_shapes_are_the_clis_own_options():
    """The table and the CLI are two hand-written lists of the same options: every flag the table admits exists on
    that sub and takes a value exactly when the CLI's does, and every option it leaves out is left out by name."""
    real = _engine_cli_options()
    assert set(ops_daily._ZCRYPTO_READ_FLAGS) <= set(real), set(ops_daily._ZCRYPTO_READ_FLAGS) - set(real)
    for sub, flags in ops_daily._ZCRYPTO_READ_FLAGS.items():
        assert set(flags) <= set(real[sub]), (sub, set(flags) - set(real[sub]))
        for flag, spec in flags.items():
            assert (spec is None) == real[sub][flag], (sub, flag, spec, real[sub][flag])
        assert set(real[sub]) - set(flags) == set(_ENGINE_OPTIONS_LEFT_OUT.get(sub, {})), (sub, set(real[sub]) - set(flags))
```

- [ ] **Step 2: Run them and watch them fail**

Run: `uv run pytest tests/test_ops_daily.py -q -k "engine_read or engine_write"`
Expected: FAIL — `test_the_engine_read_shapes_are_the_clis_own_options` with `AttributeError: module 'ops_daily' has no attribute '_ZCRYPTO_READ_FLAGS'`; the `_ENGINE_READS` cases for `exec-status --state-dir`, `accum-replay … --nav 10000.5`, `tracking-report --gate-from …` and the long `soak-check` form, each classified `PREPARED`; and the prepared cases `soak-check --json`, `report --since 24h`, `report --date … --pair …`, `exec-status --journal-dir …` and `decompose --nav 10000`, each classified `AUTONOMOUS`. The other cases pass already, and stay pinned.

- [ ] **Step 3: Replace the generated shape with the per-sub table**

In `infra/scripts/ops_daily.py`, replace exactly this block:

```python
# `zcrypto engine <sub>`: `exec-status` reads, `cycle --replace` deletes a boundary's record, and
# `gate-export` writes a textfile. The read subcommands are named one by one for the same reason.
_ZCRYPTO_READ_SUBS = ("exec-status", "report", "tracking-report", "decompose", "accum-replay", "soak-check")
_FIRST_STAGE_SHAPES += tuple(
    _Shape(
        ("zcrypto", "engine", sub),
        {
            "--journal-dir": _PATH,
            "--since": _SINCE,
            "--until": _SINCE,
            "--nav": _INT,
            "--minimums": _FILEREF,
            "--path": _NAME,
            "--date": _SINCE,
            "--pair": _NAME,
            "--json": None,
        },
    )
    for sub in _ZCRYPTO_READ_SUBS
)
```

with:

```python
# `zcrypto engine <sub>`, one flag table per read subcommand; `cycle --replace` deletes a boundary's record
# and `gate-export` writes a textfile, so neither is here. Three real options stay out on purpose:
# `soak-check --json` WRITES the path it names, and `soak-check --registry` and `tracking-report
# --ledger-export` name a file whose reader echoes content when it refuses it.
# `tests/test_ops_daily.py::test_the_engine_read_shapes_are_the_clis_own_options` holds this table to the CLI.
_FLOAT = r"\d{1,9}(?:\.\d{1,9})?"
_ISOWEEK = r"\d{4}-W\d{2}"
_ENGINE_WINDOW = {"--journal-dir": _PATH, "--since": _SINCE, "--until": _SINCE}
_ENGINE_SIZING = {"--minimums": _FILEREF, "--nav": _FLOAT}
_ZCRYPTO_READ_FLAGS: dict[str, dict[str, str | None]] = {
    "exec-status": {"--state-dir": _PATH},
    "report": {"--journal-dir": _PATH},
    "decompose": {**_ENGINE_WINDOW, "--json": None},
    "accum-replay": {**_ENGINE_WINDOW, **_ENGINE_SIZING, "--json": None},
    "tracking-report": {**_ENGINE_WINDOW, **_ENGINE_SIZING, "--gate-from": _ISOWEEK, "--simulated-fills": None, "--json": None},
    "soak-check": {
        "--journal-dir": _PATH,
        "--store-dir": _PATH,
        "--canonical-dir": _PATH,
        "--fee-per-side": _FLOAT,
        "--band": _FLOAT,
        "--floor": _INT,
        "--null": _NAME,
        "--path": _NAME,
    },
}
_FIRST_STAGE_SHAPES += tuple(_Shape(("zcrypto", "engine", sub), flags) for sub, flags in _ZCRYPTO_READ_FLAGS.items())
```

- [ ] **Step 4: Run the file**

Run: `uv run pytest tests/test_ops_daily.py -q`
Expected: PASS, every test. The two runbook-corpus tests in this file classify every command the runbooks spell, so a read the old shape admitted and the new table refuses would fail there by name.

- [ ] **Step 5: Lint and commit**

```bash
uv run ruff check infra/scripts/ops_daily.py tests/test_ops_daily.py && uv run ruff format infra/scripts/ops_daily.py tests/test_ops_daily.py
git add infra/scripts/ops_daily.py tests/test_ops_daily.py
git commit -F - <<'EOF'
fix(ops): the daily-ops classifier reads each engine sub by its own options

One shape was generated for six `zcrypto engine` subcommands, so it
admitted `--date` and `--pair`, which no sub has, refused each sub's own
options (`exec-status --state-dir`, `tracking-report --gate-from` and
`--simulated-fills`, a float `--nav`, and `soak-check`'s store, canonical,
band, floor, null and fee options), and admitted a valueless
`soak-check --json` the CLI itself refuses. A flag table per sub replaces
it. Three real options stay out by name, each pinned PREPARED:
`soak-check --json` writes the path it names, and `--registry` and
`--ledger-export` name a file whose reader echoes content on a refusal.
A test reads the Typer app's options and holds the table to them.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01VpmFzSn7FrFTiq8hphvCaY
EOF
```

- [ ] **Step 6: Prove the new guard, and record the verdict on the commit**

```bash
infra/scripts/mutate-probe.sh --file infra/scripts/ops_daily.py \
  --control 's/"report": {"--journal-dir": _PATH},/"report": {"--journal-dir": _PATH, "--date": _SINCE},/' \
  --mutation 's/        "--path": _NAME,/        "--path": _NAME,\n        "--json": None,/' \
  -- uv run pytest tests/test_ops_daily.py -q -x -k "engine_read_shapes or stay_prepared"
```

Expected: `mutate-probe: KILLED (control proven, tree restored byte-identically)`. The control gives `report` an option it does not have; the mutation re-admits the valueless `soak-check --json`. Then amend the message only — `git commit --amend -F -` with the same message plus one paragraph before the trailers: ``Probe: `infra/scripts/mutate-probe.sh` over the table, control an option `report` lacks, mutation a valueless `soak-check --json` re-admitted: KILLED, control proven.`` — and push.

---

### Task 2: The reduction — one payload, one row

**Files:**
- Modify: `infra/scripts/ops_daily.py` (insert directly above `def read_deploys(`)
- Test: `tests/test_ops_daily.py` (append), `tests/test_engine_soak_command.py` (insert directly above `def test_soak_check_exits_non_zero_when_the_null_reconciliation_fails(`)

**Interfaces:**
- Consumes: `Check(name, expr, ok, value)` and `_UNREACHABLE` from `infra/scripts/ops_daily.py`; in the soak test file, the existing helpers `_patch_config`, `_patch_canonical_pipeline`, `_mk_journal_and_store`, `_soak_args` and the module constant `_CLOSES`.
- Produces: `ops_daily.read_soak_verdict(*, runner) -> Check`, where `runner(journal_dir: Path) -> dict` returns a `soak-check --json` payload or raises; constants `SOAK_CHECK = "soak verdict"`, `SOAK_JOURNAL = Path("/mnt/zhao-crypto/engine-journal")`, `SOAK_EXPR`, `SOAK_OUTSIDE_FAILS_AT = 3`. Test helpers `_soak_payload(*, n_outside=1, void=(), outside=("governor_engagement",), both=())` and `_soak_answering(payload)`, which Task 3's tests reuse.

- [ ] **Step 1: Append the failing reduction tests to `tests/test_ops_daily.py`**

```python
# --- the soak verdict: the scheduled reader of `soak-check`'s gating verdicts ------------------------------------


def _soak_payload(*, n_outside=1, void=(), outside=("governor_engagement",), both=()):
    """The fields `read_soak_verdict` reduces, shaped as `soak-check --json` writes them; the pin that the CLI
    still writes them is `tests/test_engine_soak_command.py::test_soak_check_json_carries_the_fields_the_daily_pass_reduces`."""
    verdicts = {}
    for metric in ("gross", "net", "active_frac", "turnover", "hhi", "governor_engagement", "cap_breach"):
        label = "inconsistent" if metric in outside or metric in both else "consistent"
        primary = "inconsistent" if metric in both else ("n/a" if metric in outside else "consistent")
        verdicts[metric] = {"verdict": label, "dual": {"primary": primary, "secondary": label, "verdict": label}}
    return {
        "void_reasons": list(void),
        "panel": {
            "n_outside": n_outside,
            "n_metrics": 7,
            "line": f"{n_outside} of 7 outside band (~0.7 expected by chance at 90%)",
        },
        "provenance": {"L": 424, "window_bound": "journal"},
        "gating_verdicts": verdicts,
        "realized_no_book_bars": 0,
        "realized_total_bars": 424,
    }


def _soak_answering(payload):
    return lambda journal_dir: payload


def test_one_metric_outside_is_the_count_chance_expects_and_passes():
    check = ops_daily.read_soak_verdict(runner=_soak_answering(_soak_payload()))
    assert check.ok, check.value
    assert check.value == (
        "1 of 7 outside band (~0.7 expected by chance at 90%); L=424, window_bound=journal; "
        "outside: governor_engagement (one construction); no-book bars 0 of 424; hhi consistent"
    )


def test_the_row_fails_at_the_provisional_count_and_not_one_below_it():
    assert ops_daily.SOAK_OUTSIDE_FAILS_AT == 3
    two = _soak_payload(n_outside=2, outside=("governor_engagement",), both=("hhi",))
    three = _soak_payload(n_outside=3, outside=("governor_engagement",), both=("hhi", "gross"))
    assert ops_daily.read_soak_verdict(runner=_soak_answering(two)).ok
    failed = ops_daily.read_soak_verdict(runner=_soak_answering(three))
    assert not failed.ok and not failed.value.startswith("unreadable:")
    assert "gross (both constructions)" in failed.value and "hhi inconsistent" in failed.value


def test_a_void_run_fails_on_its_reasons_and_never_reads_the_verdicts_beside_them():
    """`soak-check --json` writes populated verdicts beside a non-empty `void_reasons`; a reader that looked at
    the panel first would pass a run whose instrument failed its own self-test."""
    payload = _soak_payload(n_outside=0, outside=(), void=("self-test VOID: identity_ok=False",))
    check = ops_daily.read_soak_verdict(runner=_soak_answering(payload))
    assert not check.ok
    assert check.value == "void: self-test VOID: identity_ok=False"


def test_a_void_run_whose_analysis_never_ran_still_names_its_reason():
    payload = {"void_reasons": ["no journaled cycles found"], "panel": None, "provenance": None, "gating_verdicts": None}
    check = ops_daily.read_soak_verdict(runner=_soak_answering(payload))
    assert not check.ok and check.value == "void: no journaled cycles found"


def test_no_canonical_dataset_is_a_source_the_pass_could_not_read():
    payload = _soak_payload(void=("canonical absent — null unavailable",))
    check = ops_daily.read_soak_verdict(runner=_soak_answering(payload))
    assert not check.ok and check.value == "unreadable: canonical absent — null unavailable"


@pytest.mark.parametrize(
    "fault",
    [
        FileNotFoundError("no cycle record under /mnt/zhao-crypto/engine-journal"),
        subprocess.TimeoutExpired(cmd="uv", timeout=900),
        RuntimeError("soak-check exited 1 and wrote no payload: read_store_series: cannot read x"),
        json.JSONDecodeError("Expecting value", "", 0),
    ],
)
def test_a_run_that_produced_no_payload_is_unreadable_and_never_a_verdict_on_the_book(fault):
    def refuse(journal_dir):
        raise fault

    check = ops_daily.read_soak_verdict(runner=refuse)
    assert not check.ok and check.value.startswith("unreadable:"), check.value


def test_a_payload_missing_a_field_the_reduction_reads_is_unreadable():
    payload = _soak_payload()
    del payload["panel"]
    check = ops_daily.read_soak_verdict(runner=_soak_answering(payload))
    assert not check.ok and check.value.startswith("unreadable:"), check.value


def test_the_soak_reader_takes_its_runner_and_never_defaults_one():
    runner = inspect.signature(ops_daily.read_soak_verdict).parameters["runner"]
    assert runner.kind is inspect.Parameter.KEYWORD_ONLY and runner.default is inspect.Parameter.empty
    with pytest.raises(TypeError):
        ops_daily.read_soak_verdict()
```

- [ ] **Step 2: Insert the payload pin into `tests/test_engine_soak_command.py`**

Directly above `def test_soak_check_exits_non_zero_when_the_null_reconciliation_fails(`:

```python
def test_soak_check_json_carries_the_fields_the_daily_pass_reduces(tmp_path, monkeypatch):
    """`read_soak_verdict` in `infra/scripts/ops_daily.py` reduces this payload to one row of the daily report and
    reads these keys by name, so a rename here is a reader that goes `unreadable` every morning."""
    _patch_config(monkeypatch, tmp_path)
    _patch_canonical_pipeline(monkeypatch)
    journal_dir, store_dir = _mk_journal_and_store(tmp_path, _CLOSES)
    json_out = tmp_path / "report.json"

    result = runner.invoke(app, _soak_args(journal_dir, store_dir, tmp_path / "fake-canonical", json_out))

    assert result.exit_code == 0, result.output
    payload = json.loads(json_out.read_text())
    assert payload["void_reasons"] == []
    panel = payload["panel"]
    assert isinstance(panel["n_outside"], int) and isinstance(panel["n_metrics"], int)
    assert panel["line"].startswith(f"{panel['n_outside']} of {panel['n_metrics']} outside band")
    assert {"L", "window_bound"} <= set(payload["provenance"])
    assert isinstance(payload["realized_no_book_bars"], int) and isinstance(payload["realized_total_bars"], int)
    assert "hhi" in payload["gating_verdicts"]
    for metric, row in payload["gating_verdicts"].items():
        assert isinstance(row["verdict"], str), metric
        assert {"primary", "secondary", "verdict"} <= set(row["dual"]), (metric, row["dual"])
```

- [ ] **Step 3: Run both and read the failures**

Run: `uv run pytest tests/test_ops_daily.py tests/test_engine_soak_command.py -q -k "soak_reader or metric_outside or provisional_count or void_run or canonical_dataset or no_payload or missing_a_field or daily_pass_reduces"`
Expected: the `tests/test_ops_daily.py` cases FAIL with `AttributeError: module 'ops_daily' has no attribute 'read_soak_verdict'` (or `SOAK_OUTSIDE_FAILS_AT`); `test_soak_check_json_carries_the_fields_the_daily_pass_reduces` PASSES already — it pins what `cli/engine/soak.py` writes today, and Step 6's probe is what shows it can fail.

- [ ] **Step 4: Insert the constants and the reader into `infra/scripts/ops_daily.py`**

Directly above `def read_deploys(`, followed by two blank lines:

```python
SOAK_CHECK = "soak verdict"
SOAK_JOURNAL = Path("/mnt/zhao-crypto/engine-journal")
SOAK_EXPR = "zcrypto engine soak-check over the newest journaled 240 snapshots"
# PROVISIONAL. At a 90% band one metric outside is the count chance expects, so one never fails the row. Seven
# independent looks at 10% reach three under 3% of the time; the seven are correlated, which loosens that bound,
# and the number is re-derived once there is a history of rows to derive it from.
SOAK_OUTSIDE_FAILS_AT = 3
_SOAK_CANONICAL_ABSENT = "canonical absent"


def read_soak_verdict(*, runner) -> Check:
    """The scheduled reader of `soak-check`'s gating verdicts: one row, decided in this order.

    A run that produced no payload, or one with no canonical dataset to judge against, is `unreadable` -- the
    pass could not look, which says nothing about the book. `void_reasons` is read BEFORE any verdict because
    the payload carries populated verdicts beside a non-empty one. Then the panel's own multiplicity count
    decides, never one metric's `inconsistent`.

    Keyword-only `runner`, no default: an injection default is a live call site, not a seam.
    """
    try:
        payload = runner(SOAK_JOURNAL)
        void = list(payload["void_reasons"])
        if any(_SOAK_CANONICAL_ABSENT in reason for reason in void):
            return Check(SOAK_CHECK, SOAK_EXPR, ok=False, value=f"unreadable: {'; '.join(void)}")
        if void:
            return Check(SOAK_CHECK, SOAK_EXPR, ok=False, value=f"void: {'; '.join(void)}")
        panel, provenance, verdicts = payload["panel"], payload["provenance"], payload["gating_verdicts"]
        outside = []
        for metric, row in verdicts.items():
            dual = row.get("dual") or {}
            if dual.get("verdict", row["verdict"]) == "inconsistent":
                calls = [dual.get("primary"), dual.get("secondary")].count("inconsistent")
                outside.append(f"{metric} ({'both constructions' if calls == 2 else 'one construction'})")
        value = (
            f"{panel['line']}; L={provenance['L']}, window_bound={provenance['window_bound']}; "
            f"outside: {', '.join(outside) or 'none'}; "
            f"no-book bars {payload['realized_no_book_bars']} of {payload['realized_total_bars']}; hhi {verdicts['hhi']['verdict']}"
        )
        return Check(SOAK_CHECK, SOAK_EXPR, ok=int(panel["n_outside"]) < SOAK_OUTSIDE_FAILS_AT, value=value)
    except (*_UNREACHABLE, subprocess.SubprocessError, TypeError, AttributeError, RuntimeError) as exc:
        return Check(SOAK_CHECK, SOAK_EXPR, ok=False, value=f"unreadable: {exc}")
```

- [ ] **Step 5: Run, lint and commit**

Run: `uv run pytest tests/test_ops_daily.py tests/test_engine_soak_command.py -q`
Expected: PASS, every test.

```bash
uv run ruff check infra/scripts/ops_daily.py tests/test_ops_daily.py tests/test_engine_soak_command.py && uv run ruff format infra/scripts/ops_daily.py tests/test_ops_daily.py tests/test_engine_soak_command.py
git add infra/scripts/ops_daily.py tests/test_ops_daily.py tests/test_engine_soak_command.py
git commit -F - <<'EOF'
feat(ops): a soak-check payload reduces to one verdict row

`read_soak_verdict` turns a `soak-check --json` payload into a `Check`:
no payload, or no canonical dataset to judge against, is `unreadable:`;
any other `void_reasons` fails and is read before any verdict, because
the payload carries populated verdicts beside a non-empty one; then the
panel's outside count fails the row at a PROVISIONAL three, never one
metric's `inconsistent`, which at a 90% band is the count chance expects.
The value carries the panel line, the scored-bar count, the window bound,
each outside metric with how many null constructions called it, the
no-book bar count and the hhi verdict. Not wired into the report yet: the
runner that produces the payload is the next commit. A test in
`tests/test_engine_soak_command.py` pins the payload keys the reduction
reads by name.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01VpmFzSn7FrFTiq8hphvCaY
EOF
```

- [ ] **Step 6: Prove both guards, and record the verdicts on the commit**

```bash
infra/scripts/mutate-probe.sh --file infra/scripts/ops_daily.py \
  --control 's/^SOAK_OUTSIDE_FAILS_AT = 3/SOAK_OUTSIDE_FAILS_AT = 9/' \
  --mutation 's/^        if void:/        if False:/' \
  -- uv run pytest tests/test_ops_daily.py -q -x -k "void_run or provisional_count"
infra/scripts/mutate-probe.sh --file cli/engine/soak.py \
  --control 's/        "void_reasons": list(void_reasons),/        "void_reason": list(void_reasons),/' \
  --mutation 's/    payload\["realized_no_book_bars"\] = realized_flat/    payload["realized_flat_bars"] = realized_flat/' \
  -- uv run pytest tests/test_engine_soak_command.py -q -x -k "daily_pass_reduces"
```

Expected: `KILLED (control proven, tree restored byte-identically)` twice. The first mutation lets a void run fall through to its verdicts; the second renames a payload key the reduction reads. Amend the message only, adding before the trailers: ``Probes: `infra/scripts/mutate-probe.sh` over the reduction, control the threshold moved to nine, mutation the void arm disabled: KILLED, control proven. Over `cli/engine/soak.py`, control `void_reasons` renamed, mutation `realized_no_book_bars` renamed: KILLED, control proven.`` Then push.

---

### Task 3: The runner, and the row in the report

**Files:**
- Modify: `infra/scripts/ops_daily.py` (two imports; one constant below `SOAK_OUTSIDE_FAILS_AT = 3`; two functions directly above `def read_soak_verdict(`; one line in `main`)
- Test: `tests/test_ops_daily.py` (append; and one line added in each of `test_the_upgrade_check_reaches_the_verdict_the_pass_prints`, `test_the_cgroup_check_reaches_the_verdict_the_pass_prints` and `test_an_uncapped_bridge_moves_the_pass_to_attention`)

**Interfaces:**
- Consumes: from Task 2, `read_soak_verdict(*, runner)`, `SOAK_CHECK`, `SOAK_JOURNAL`, and the test helpers `_soak_payload(...)` and `_soak_answering(payload)`; from the module, `REPO_ROOT` and `ssh_read`; from the test file, `_host_answering(**fields)`.
- Produces: `ops_daily.derive_soak_store(journal_dir: Path, root: Path) -> Path` (returns `root / "store"`; raises `FileNotFoundError` when the journal holds no `*/cycle-*.json`, `ValueError` when the newest record journals no `240` snapshot); `ops_daily.soak_run(journal_dir: Path) -> dict` (raises `RuntimeError` when `soak-check` wrote no payload); `main` appends `read_soak_verdict(runner=soak_run)` to the verdict list.

- [ ] **Step 1: Append the failing tests to `tests/test_ops_daily.py`**

```python
def _journal_a_cycle_from(store_dir: Path, journal_dir: Path, cycle_ts: datetime) -> None:
    """One success record written the way `run_cycle` writes it: the store is read, union-aligned and journaled
    by the engine's own functions, so the snapshots are what a real cycle leaves, not a test's idea of them."""
    from cli.engine.cycle import _journal_snapshots, _union_align
    from cli.engine.journal import CycleRecord, to_json
    from cli.engine.store import GRID_INTERVALS, PAIR_KEYS, read_store_series

    raw = {
        (symbol, interval): read_store_series(store_dir, symbol, interval) for symbol in PAIR_KEYS for interval in GRID_INTERVALS
    }
    entries = _journal_snapshots(journal_dir, cycle_ts, {interval: _union_align(raw, interval) for interval in GRID_INTERVALS})
    record = CycleRecord(
        schema_version=2,
        cycle_ts=cycle_ts,
        snapshots=entries,
        final_targets=dict.fromkeys(PAIR_KEYS, 0.0),
        started_at=cycle_ts,
        completed_at=cycle_ts + timedelta(minutes=1),
        code_version="test",
        builder_path="fast",
    )
    day_dir = journal_dir / f"{cycle_ts:%Y-%m-%d}"
    day_dir.mkdir(parents=True, exist_ok=True)
    (day_dir / f"cycle-{cycle_ts:%H}.json").write_text(to_json(record) + "\n")


def _a_twelve_leg_store(store_dir: Path, last: datetime, *, short_leg: str) -> None:
    """Both grids for every basket pair, closes distinct per leg and per bar; `short_leg`'s 240 series lacks the
    stamp before `last`, so the union-aligned snapshot carries a `None` there."""
    from cli.engine.store import GRID_INTERVALS, PAIR_KEYS
    from cli.ohlc.dataset import to_frame, write_parquet

    for k, symbol in enumerate(PAIR_KEYS):
        base, quote = symbol.split("/")
        for interval in GRID_INTERVALS:
            step = timedelta(minutes=interval)
            stamps = [last - step * n for n in range(5, -1, -1)]
            if symbol == short_leg and interval == 240:
                stamps.remove(last - step)
            rows = [[int(t.timestamp()), *[str(100.0 + k + n / 7)] * 5, "1.0", 1] for n, t in enumerate(stamps)]
            (store_dir / base / quote).mkdir(parents=True, exist_ok=True)
            write_parquet(to_frame(rows), store_dir / base / quote / f"{interval}.parquet")


def test_the_journal_derived_store_carries_every_close_the_real_store_does(tmp_path):
    """The claim the soak row rests on. A snapshot differs from its store leg only by a `None` close at a stamp
    the leg lacks and another leg has, and `realized_series` skips a `None` close exactly as it skips an absent
    stamp -- so the comparison drops them and demands equality on the rest, leg by leg."""
    from cli.engine.store import PAIR_KEYS, read_store_series

    last = datetime(2026, 9, 19, 12, tzinfo=timezone.utc)
    store, journal = tmp_path / "store", tmp_path / "journal"
    _a_twelve_leg_store(store, last, short_leg="SOL/EUR")
    _journal_a_cycle_from(store, journal, last + timedelta(hours=4))

    derived = ops_daily.derive_soak_store(journal, tmp_path / "scratch")

    assert derived == tmp_path / "scratch" / "store"
    for symbol in PAIR_KEYS:
        real = dict(zip(*read_store_series(store, symbol, 240)))
        copy = dict(zip(*read_store_series(derived, symbol, 240)))
        assert {t: c for t, c in copy.items() if c is not None} == real, symbol
    padded = dict(zip(*read_store_series(derived, "SOL/EUR", 240)))
    assert padded[last - timedelta(hours=4)] is None, "the fixture no longer exercises the union's None"
    assert not list(derived.rglob("1440.parquet")), "only the 240 grid is read by soak-check"


def test_the_derived_store_is_the_newest_success_records_and_a_failed_cycle_is_not_a_record(tmp_path):
    last = datetime(2026, 9, 19, 12, tzinfo=timezone.utc)
    store, journal = tmp_path / "store", tmp_path / "journal"
    _a_twelve_leg_store(store, last - timedelta(hours=4), short_leg="SOL/EUR")
    _journal_a_cycle_from(store, journal, last)
    _a_twelve_leg_store(store, last, short_leg="SOL/EUR")
    _journal_a_cycle_from(store, journal, last + timedelta(hours=4))
    # Sorts after every `cycle-*.json` of its day, and carries no snapshots: the glob must not take it.
    (journal / "2026-09-19" / "failed-cycle-20.json").write_text('{"reason": "stale_pair"}\n')

    from cli.engine.store import read_store_series

    derived = ops_daily.derive_soak_store(journal, tmp_path / "scratch")
    assert read_store_series(derived, "BTC/EUR", 240)[0][-1] == last


def test_a_journal_with_no_record_and_a_record_with_no_240_snapshot_both_refuse(tmp_path):
    with pytest.raises(FileNotFoundError, match="no cycle record"):
        ops_daily.derive_soak_store(tmp_path, tmp_path / "scratch")
    day = tmp_path / "2026-09-19"
    day.mkdir()
    (day / "cycle-16.json").write_text(json.dumps({"snapshots": [{"grid": "1440", "pair": "BTC/EUR", "path": "x"}]}))
    with pytest.raises(ValueError, match="no 240 snapshot"):
        ops_daily.derive_soak_store(tmp_path, tmp_path / "scratch")


def test_the_soak_run_hands_soak_check_the_derived_store_and_returns_what_it_wrote(tmp_path, monkeypatch):
    last = datetime(2026, 9, 19, 12, tzinfo=timezone.utc)
    store, journal = tmp_path / "store", tmp_path / "journal"
    _a_twelve_leg_store(store, last, short_leg="SOL/EUR")
    _journal_a_cycle_from(store, journal, last + timedelta(hours=4))
    seen = {}

    def fake_run(command, **kwargs):
        seen["command"], seen["kwargs"] = command, kwargs
        handed = Path(command[command.index("--store-dir") + 1])
        seen["legs"] = sorted(p.relative_to(handed).as_posix() for p in handed.rglob("*.parquet"))
        Path(command[command.index("--json") + 1]).write_text('{"void_reasons": []}')
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(ops_daily.subprocess, "run", fake_run)
    assert ops_daily.soak_run(journal) == {"void_reasons": []}
    assert seen["command"][:7] == ("uv", "run", "zcrypto", "engine", "soak-check", "--journal-dir", str(journal))
    assert seen["kwargs"]["cwd"] == ops_daily.REPO_ROOT and seen["kwargs"]["timeout"] == 900
    assert len(seen["legs"]) == 12 and "BTC/EUR/240.parquet" in seen["legs"]
    assert not Path(seen["command"][seen["command"].index("--store-dir") + 1]).exists(), "the scratch store outlived the run"


def test_a_soak_check_that_wrote_no_payload_raises_its_last_line(tmp_path, monkeypatch):
    last = datetime(2026, 9, 19, 12, tzinfo=timezone.utc)
    store, journal = tmp_path / "store", tmp_path / "journal"
    _a_twelve_leg_store(store, last, short_leg="SOL/EUR")
    _journal_a_cycle_from(store, journal, last + timedelta(hours=4))
    aborted = lambda command, **kwargs: subprocess.CompletedProcess(
        command, 1, stdout="", stderr="warming up\nError: read_store_series: cannot read x\n"
    )
    monkeypatch.setattr(ops_daily.subprocess, "run", aborted)
    with pytest.raises(RuntimeError, match="exited 1 and wrote no payload: Error: read_store_series: cannot read x"):
        ops_daily.soak_run(journal)


def test_the_soak_row_reaches_the_verdict_the_pass_prints(monkeypatch, capsys):
    monkeypatch.setattr(ops_daily.grafana_auth, "vault_var", lambda name: "tok")
    monkeypatch.setattr(ops_daily, "read_alerts", lambda *a, **k: ops_daily.AlertsRead())
    monkeypatch.setattr(ops_daily, "read_logs", lambda *a, **k: ops_daily.LogsRead())
    monkeypatch.setattr(ops_daily, "read_deadmen", lambda *a, **k: ops_daily.DeadmenRead(via_prometheus=0.0))
    monkeypatch.setattr(ops_daily, "read_verdict", lambda *a, **k: [])
    monkeypatch.setattr(ops_daily, "read_deploys", lambda *a, **k: [])
    monkeypatch.setattr(ops_daily, "read_reminders", lambda *a, **k: ops_daily.RemindersRead())
    monkeypatch.setattr(ops_daily, "ssh_read", _host_answering(StampEpoch=str(int(datetime.now(timezone.utc).timestamp()))))
    monkeypatch.setattr(ops_daily, "soak_run", _soak_answering(_soak_payload()))
    assert ops_daily.main(["report"]) == 0
    assert f"- PASS {ops_daily.SOAK_CHECK}: 1 of 7 outside band" in capsys.readouterr().out

    monkeypatch.setattr(ops_daily, "soak_run", _soak_answering(_soak_payload(void=("cap-breach inconsistent",))))
    assert ops_daily.main(["report"]) == 1
    assert f"- FAIL {ops_daily.SOAK_CHECK}: void: cap-breach inconsistent" in capsys.readouterr().out

    def unmounted(journal_dir):
        raise FileNotFoundError(f"no cycle record under {journal_dir}")

    monkeypatch.setattr(ops_daily, "soak_run", unmounted)
    assert ops_daily.main(["report"]) == 2
    assert f"- {ops_daily.SOAK_CHECK} could not be read: no cycle record under {ops_daily.SOAK_JOURNAL}" in capsys.readouterr().out
```

- [ ] **Step 2: Run them and watch them fail**

Run: `uv run pytest tests/test_ops_daily.py -q -k "derived or journal_with_no or soak_run or wrote_no_payload or soak_row"`
Expected: FAIL with `AttributeError: module 'ops_daily' has no attribute 'derive_soak_store'` (and `'soak_run'`).

- [ ] **Step 3: Add the runner to `infra/scripts/ops_daily.py`**

In the import block, add `import shutil` directly above `import subprocess` and `import tempfile` directly below `import sys`. Directly below `SOAK_OUTSIDE_FAILS_AT = 3` add:

```python
_SOAK_TIMEOUT_SECONDS = 900
```

Directly above `def read_soak_verdict(`, followed by two blank lines:

```python
def derive_soak_store(journal_dir: Path, root: Path) -> Path:
    """A store-shaped directory holding the newest success record's 240 snapshots, which is every close
    `soak-check` reads from the engine's store: each cycle journals the store series it read, and the engine
    host's store has no replica to read instead."""
    records = sorted(journal_dir.glob("*/cycle-*.json"))
    if not records:
        raise FileNotFoundError(f"no cycle record under {journal_dir}")
    legs = [entry for entry in json.loads(records[-1].read_text())["snapshots"] if entry["grid"] == "240"]
    if not legs:
        raise ValueError(f"{records[-1]} journals no 240 snapshot")
    store = root / "store"
    for entry in legs:
        base, quote = entry["pair"].split("/")
        leg = store / base / quote / "240.parquet"
        leg.parent.mkdir(parents=True)
        shutil.copyfile(journal_dir / entry["path"], leg)
    return store


def soak_run(journal_dir: Path) -> dict:
    """The payload of one `soak-check` run over `derive_soak_store`, from the checkout this script sits in: the
    canonical dataset and the trial registry are read at their repo-relative defaults."""
    with tempfile.TemporaryDirectory(prefix="zcrypto-soak-") as scratch:
        root = Path(scratch)
        out = root / "soak.json"
        command = ("uv", "run", "zcrypto", "engine", "soak-check", "--journal-dir", str(journal_dir))
        command += ("--store-dir", str(derive_soak_store(journal_dir, root)), "--json", str(out))
        done = subprocess.run(command, cwd=REPO_ROOT, capture_output=True, text=True, timeout=_SOAK_TIMEOUT_SECONDS)
        if not out.exists():
            last = (done.stderr.strip() or done.stdout.strip() or "no output").splitlines()[-1]
            raise RuntimeError(f"soak-check exited {done.returncode} and wrote no payload: {last}")
        return json.loads(out.read_text())
```

In `main`, directly below `    verdict.append(read_agentboard_cgroup(runner=ssh_read))`, add:

```python
    verdict.append(read_soak_verdict(runner=soak_run))
```

- [ ] **Step 4: Keep the three existing report tests off the live runner**

`main` now runs `soak_run`, which would start a real `soak-check` from inside the suite. In `test_the_upgrade_check_reaches_the_verdict_the_pass_prints` and `test_the_cgroup_check_reaches_the_verdict_the_pass_prints`, directly below `    monkeypatch.setattr(ops_daily, "ssh_read", fresh)`, and in `test_an_uncapped_bridge_moves_the_pass_to_attention`, directly below `    monkeypatch.setattr(ops_daily, "ssh_read", uncapped)`, add this one line:

```python
    monkeypatch.setattr(ops_daily, "soak_run", _soak_answering(_soak_payload()))
```

- [ ] **Step 5: Run, lint and commit**

Run: `uv run pytest tests/test_ops_daily.py tests/test_engine_soak_command.py tests/test_internal_terms_not_operator_visible.py -q`
Expected: PASS, every test. A failure in one of the three tests of Step 4 with exit code 2 means its added line is missing.

```bash
uv run ruff check infra/scripts/ops_daily.py tests/test_ops_daily.py && uv run ruff format infra/scripts/ops_daily.py tests/test_ops_daily.py
git add infra/scripts/ops_daily.py tests/test_ops_daily.py
git commit -F - <<'EOF'
feat(ops): the daily report runs soak-check from the journal and prints its verdict

`soak-check` reads the engine's store at one call, the realized series'
read of each leg's 240 parquet, and every successful cycle journals that
same series. `derive_soak_store` copies the newest success record's 240
snapshots into a store-shaped temporary directory and `soak_run` hands it
to `uv run zcrypto engine soak-check --json` from the repo root, so the
row needs the journal mount, the canonical dataset and the registry, and
no host. A fixture writes a twelve-leg store, journals a cycle from it
with the engine's own `_union_align` and `_journal_snapshots`, and holds
the derived store to every close the real one carries, the union's `None`
at a stamp one leg lacks excepted. `main` appends the row; the three
existing tests that drive `main` to a verdict stub the runner.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01VpmFzSn7FrFTiq8hphvCaY
EOF
```

- [ ] **Step 6: Prove the derived-store guard, and record the verdict on the commit**

```bash
infra/scripts/mutate-probe.sh --file infra/scripts/ops_daily.py \
  --control 's/if entry\["grid"\] == "240"\]/if entry["grid"] == "1440"]/' \
  --mutation 's#journal_dir.glob("\*/cycle-\*.json")#journal_dir.glob("*/*cycle-*.json")#' \
  -- uv run pytest tests/test_ops_daily.py -q -x -k "derived_store or journal_derived"
```

Expected: `KILLED (control proven, tree restored byte-identically)`. The control derives the wrong grid; the mutation lets a `failed-cycle-*.json` be taken for the newest record. Amend the message only, adding before the trailers: ``Probe: `infra/scripts/mutate-probe.sh` over the derived store, control the 1440 grid copied instead, mutation the record glob widened to take a failed cycle: KILLED, control proven.`` Then push.

- [ ] **Step 7: Live acceptance — the controller runs this, never a dispatched subagent**

The branch worktree has no `data/ohlc-full`, so the row reads `unreadable:` there, which is the first half of the acceptance. The second half needs the canonical dataset, symlinked for the length of one command and unlinked before anything else happens in the worktree (`CLAUDE.md`: a scratch worktree that symlinks a canonical dataset unlinks it before `git worktree remove`, and the main checkout's `data/` listing is read afterwards).

```bash
uv run python -c "
import importlib.util, sys
spec = importlib.util.spec_from_file_location('ops_daily', 'infra/scripts/ops_daily.py'); m = importlib.util.module_from_spec(spec); sys.modules['ops_daily'] = m; spec.loader.exec_module(m)
c = m.read_soak_verdict(runner=m.soak_run); print(c.ok, '|', c.value)"
```

Expected without the symlink: `False | unreadable: canonical absent — null unavailable`. Then:

```bash
ln -s /home/zhaow/Projects/zcrypto-kraken/data/ohlc-full data/ohlc-full
# the same python command again
unlink data/ohlc-full && ls -la data/ && ls /home/zhaow/Projects/zcrypto-kraken/data/
```

Expected with the symlink: `True | N of 7 outside band (~0.7 expected by chance at 90%); L=<several hundred>, window_bound=journal; outside: …; no-book bars 0 of <L>; hhi consistent`, in well under a minute. After the unlink, `data/` lists `.gitignore` alone and the main checkout's `data/` still lists `ohlc-full`. The values go in the PR body's test plan, not in any file.

---

### Task 4: Closeout — the topic resolves, and its two dependents say what the row does for them

**Files:**
- Modify: `docs/open-topics/T0210-soak-check-gating-verdicts-have-no-scheduled-reader.md`, then `git mv` it to `docs/open-topics/archive/`
- Modify: `docs/open-topics/T0184-soak-hhi-aggregate-averages-a-sentinel.md`, `docs/open-topics/T0201-store-type-door-cannot-see-a-wrong-instant.md`
- Modify: `docs/open-topics/README.md` (rendered, never hand-edited)

**Interfaces:**
- Consumes: the merged behaviour of Tasks 1–3 and PR #572's number.
- Produces: nothing a later task reads.

- [ ] **Step 1: Load `topic-ops` and record the heading sets**

```bash
for f in docs/open-topics/T0210-*.md docs/open-topics/T0184-*.md docs/open-topics/T0201-*.md; do echo "== $f"; grep -n '^#' "$f"; done
```

- [ ] **Step 2: Resolve T0210**

In `docs/open-topics/T0210-soak-check-gating-verdicts-have-no-scheduled-reader.md`: set `status: resolved`; delete the whole `ripe_when:` line; replace the `## Suggested next steps` heading and every bullet under it with:

```markdown
## Resolution

Resolved by PR #572 under spec `00115` and its plan. `ops-daily.py report` now prints a `soak verdict` row: `read_soak_verdict` in `infra/scripts/ops_daily.py` runs `soak-check` over a store derived from the newest journaled 240 snapshots and reduces the payload to `PASS`, `FAIL` or `unreadable`, reading `void_reasons` before any verdict and failing on the panel's outside count at a PROVISIONAL three, never on one metric's `inconsistent`. The daily pass is therefore the scheduled reader, sited on the workstation, with no timer, no host change and no store replica. The three shapes this topic listed are costed in the spec's Alternatives tables; the metric with an alert rule is what paging between passes would cost, and the spec leaves it out of scope.

The last next step — re-read `governor_engagement` once the null has power — is dropped as a separate action: the row names every outside metric, and how many null constructions called it, on every pass, so the re-read happens daily and needs no trigger of its own. [[T0184]]'s two operands are printed by the same row; [[T0201]]'s trigger cannot be evaluated from a journal-derived store; both topics record that.
```

Then:

```bash
git mv docs/open-topics/T0210-soak-check-gating-verdicts-have-no-scheduled-reader.md docs/open-topics/archive/
grep -rn "open-topics/T0210-" --include=*.md --include=*.py --include=*.sh . | grep -v "^./docs/open-topics/README.md\|^./docs/plans/00115-\|^./.tmp/"
```

Expected from the grep: no line — this plan's own steps, which name the path the file is moved FROM, are filtered out. A hit is a path citation the move broke; re-point it at `docs/open-topics/archive/`.

- [ ] **Step 3: Say in T0184 and T0201 what the row does for each trigger**

In `docs/open-topics/T0184-soak-hhi-aggregate-averages-a-sentinel.md`, append one bullet at the end of the `## Findings so far` list (directly above the blank line before `## Done so far`):

```markdown
- The daily pass prints this trigger's two operands on every pass: the `soak verdict` row of `ops-daily.py report` carries the realized no-book bar count and the `hhi` verdict, from a `soak-check` run over a store derived from the journal (spec `00115`). `zcrypto-daily-ops` still names an evaluation statement unevaluated; letting it decide one from a report row is a guidance change that spec leaves to its own branch.
```

In `docs/open-topics/T0201-store-type-door-cannot-see-a-wrong-instant.md`, replace the line `Nothing investigated since registration: what PR #514 (T0193) measured is the sections above.` with:

```markdown
What PR #514 (T0193) measured is the sections above.

**The daily pass's `soak verdict` row cannot evaluate this trigger.** Spec `00115` runs `soak-check` over a store derived from the newest journaled 240 snapshots, whose last bar is that cycle's own `last_ts` and so sits on a 4h boundary by construction. An off-boundary `store last bar` can only come from a run over the engine host's own store, which has no replica (`docs/reference/fleet.md`).
```

- [ ] **Step 4: Re-render the index, compare the heading sets, run the guards**

```bash
uv run python infra/scripts/topics-index.py
for f in docs/open-topics/archive/T0210-*.md docs/open-topics/T0184-*.md docs/open-topics/T0201-*.md; do echo "== $f"; grep -n '^#' "$f"; done
uv run pytest tests/test_open_topics_frontmatter.py tests/test_topics_index.py tests/test_guidance_refs_resolve.py tests/test_change_index.py -q
```

Expected: T0184's and T0201's heading sets are unchanged from Step 1; T0210's differs in exactly one heading, `## Suggested next steps` now `## Resolution`; the index lists T0210 under `## Resolved` with its link pointing into `archive/`; every test passes.

- [ ] **Step 5: Commit and push**

```bash
git add docs/open-topics/
git commit -F - <<'EOF'
docs(topics): T0210 resolves on the daily pass's soak verdict row

T0210 asked who reads `soak-check`'s gating verdicts on a schedule. The
answer landed on this branch: `ops-daily.py report` prints a row decided
from a run over the journal alone. The topic's deferred last step, a
re-read of `governor_engagement`, is dropped with its reason in the
Resolution: the row names every outside metric and its construction count
on every pass. T0184 records that the row prints its trigger's two
operands daily; T0201 records that a journal-derived store puts the store
last bar on a boundary by construction, so the row cannot evaluate its
trigger. No topic is registered.

Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01VpmFzSn7FrFTiq8hphvCaY
EOF
git push
```

- [ ] **Step 6: Re-true the PR body through `open-pr`**

`## Spec / Plan` names the plan beside the spec; `## Changes` is derived per file from `git diff develop...HEAD -- <path>`; `## Test plan` carries Task 3 Step 7's two live readings; the README `## Usage` box is `N/A — no CLI option moved`, which `git diff develop...HEAD --name-only | grep '^cli/'` printing nothing confirms. The change-index row for #572 already carries `00115` and `T0210`.
