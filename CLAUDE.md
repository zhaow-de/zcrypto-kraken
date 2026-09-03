# CLAUDE.md

## Project

`zcrypto-kraken` is a crypto quant trading project targeting Kraken (spot + spot-margin). The research north star is `docs/research/00.master-plan.md` — the phased master plan. The `cli` package (`cli/__main__.py`) is a Typer app exposed as the `zcrypto` console script. Vocabulary: "observability" means the Grafana Cloud telemetry stack, never the healthchecks.io dead-man switches — those are a separate, independent failure domain.

**Sessions.** Four named Claude Code sessions share this repo (`docs/reference/multi-agent-protocol.md`): `zcrypto-main` coordinates and holds the PR, topic, memory and memo-token authorities; `zcrypto-alex` and `zcrypto-bravo` are payload sessions bound by that doc's payload contract; `zcrypto-zebra` is the owner's own and is never assigned. `ListAgents` prints which one you are.

## Repository layout

Standard single-package uv project: `pyproject.toml`, `uv.lock`, `.python-version`, and `ruff.toml` all live at the **repo root**, and every `uv` command runs from the root.

- `cli/` — the application package; run via `uv run python -m cli`.
- `.claude/rules/`, `.claude/skills/` — repo-specific Claude Code rules and skills.
- **CLI subcommands**: each is a sibling package `cli/<name>/` with a `command.py` (library packages like `cli/portfolio` carry no command). Single-command ones register in `cli/__main__.py` via `app.command(name=...)(...)`; multi-command groups expose a Typer sub-app registered via `app.add_typer(...)`. Loggers are named `get_logger("<package>.<module>")`.
- `zcrypto.toml` — the app's config, loaded by `cli/config.py`.
- `docs/` — the knowledge tree, organized into subdirectories: `research/` (master plan + phase reports + phase decisions logs, serial-prefixed and grouped by phase), `reference/` (living cross-phase artifacts that belong to no single phase — fee schedule, data catalogs, the fleet topology + pins maps, the corporate-action ledger, and the append-only `trial-registry.jsonl`), `universe/` (the point-in-time universe's living doc), `open-topics/` (parked follow-ups + index), `specs/` + `plans/` (per `spec-plan-locations.md`). The only Markdown files that live **directly** under `docs/` are the per-phase changelogs `iterations-history-phase<N>.md` (+ the `iterations-history.md` index) and the gitignored `memo.local.md` and `coordination.local.md`. **Do not create new documents directly under `docs/`** — every new doc belongs in a subdirectory (`research/` for phase-specific reports, `reference/` for living reference, `specs/`/`plans/`/`open-topics/` for their kinds).
- `data/` — the gitignored data root (its own `.gitignore` ignores everything inside): the compiled/canonical datasets plus the engine's transactional dirs (`data/engine-store`, `data/engine-journal`) — config defaults, present only where an engine actually runs; the live pair is on the engine host.

## Secrets

*Protected — every edit takes the owner's per-edit sign-off (`zcrypto-refine-rules`).*

**Never print a container's environment on the engine host `zcrypto`** — `docker inspect … {{json .Config.Env}}` / `{{json .Config}}`, `docker exec … env`, `docker compose config`: `zcrypto-engine` carries the live Kraken trade key and the Loki push password as env vars. Scope every inspect to the field you need — `.Mounts`, `.State`, `.Config.Image`, `.Config.Entrypoint`, `.RestartCount` — and **name those fields in a subagent's dispatch prompt**, since an unscoped "gather `docker inspect` evidence" invites the whole-object form. Vault- and deploy-specific hazards (`ansible-inventory --host`/`--list`) are in `fleet-deploys.md`.

## Rules

### 1. Think Before Coding

**Don't assume. Surface tradeoffs. Ask when unclear.**

- State assumptions; mark each *validated / assumed / unknown*.
- Multiple interpretations → present 2–3 with tradeoffs; don't pick silently.
- Name confidence on non-obvious choices (*high / medium / low*).
- Distinguish symptom from root problem.
- Unclear? Stop, name what's confusing, ask.

### 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked. No "while I'm here."
- No abstractions for single-use code.
- No flexibility / configurability / error handling that wasn't requested.
- 200 lines that could be 50? Rewrite it.

### 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- Remove imports / variables / functions that *your* changes made unused.
- Don't delete pre-existing dead code — mention it instead.

The test: every changed line traces directly to the user's request.

### 4. Define Done by Outcome, Not Output

**"Merged" is not "done." Done is "it works and we can tell."**

- Turn vague tasks into verifiable goals: a failing test that reproduces the bug then passes; tests pass identically before/after a refactor; a real flow completes end-to-end.
- Confirm it's observable in production: logs, errors, analytics that show it working (or failing).
- For multi-step work, state a brief plan as `step → verify` lines.

## Tooling

- Package/dependency manager: **uv** (`pyproject.toml` + `uv.lock`). Do not edit `uv.lock` by hand.
- Python is pinned to **3.14**. PEP 758 applies: `except ValueError, IndexError:` — unparenthesized multiple exception types (only without `as`) — is **valid syntax**; do not flag it as an error or "fix" it in review.
- Run all Python through uv so the locked environment is used.

## Commands

```bash
uv sync                          # install/refresh the locked environment (incl. dev group)
uv run zcrypto [args]            # run the CLI via the installed console script

uv run pytest                    # run tests
uv run pytest path/to/test.py::test_name   # run a single test

uv run pre-commit run -a         # full commit gate
uv add <pkg>            # add new deps
uv add --dev <pkg>      # add new dev deps
```

Tests live in `tests/` (pytest + Typer's `CliRunner`).

**The pre-PR full-suite run is CI's — do not duplicate it locally.** `.github/workflows/coverage.yml` runs the whole suite on every PR into `develop` and a failing suite fails that check. Locally run the tests the diff can reach, targeting one with `uv run pytest path::test` while iterating. The full run takes ~19 minutes with both local data sources present.

**Except what CI cannot run.** Tests skip there for want of local data or mounts — `data/ohlc-full`, the engine-journal mount, the gitignored refdata snapshot and universe JSON, the panel and trade-archive mounts, `data/ohlc-15m`, the ops journal mirror. **Run the data-gated tests locally before PR whenever the diff can reach them**, and never assume a skip is coverage: `tests/test_costmin_drift.py` is COSTMIN's only guard, sits on the live trade path, and skips in CI.

**A network-gated test is not data-gated** — one that reaches a live venue endpoint runs in CI, where it is a flake source, and skips silently if the venue ever blocks the runner. Gate such a test on an explicit opt-in env var rather than on reachability, so a skip is a decision and never an outage read as coverage.

**A change to `uv.lock`, `pyproject.toml` or a `conftest.py` reaches everything** — run the suite in full for those.

## Conventions

- **The commit gate is `uv run pre-commit run -a`** — run the full suite before committing, not individual hooks; it runs ruff (lint + format), yamllint, ansible-lint, mdformat, and standard hygiene hooks. A run that rewrites files reports **Failed** and leaves the rewrites **unstaged**: re-run until clean, then **stage everything the hooks rewrote** (re-stage even if you'd staged before) and commit. Semantics: `-a` checks all tracked files, bare `pre-commit run` only the staged set, and a brand-new file is invisible to both until `git add`ed. If the commit-time hook still rewrites something, re-stage and re-commit — never `--no-verify`.
- **Versioning** is commitizen-managed (`.cz.toml`). `cz bump` (run by the `/release` skill) is the source of truth for the version and updates both `pyproject.toml` and the README `Version` badge — don't hand-edit either or they'll drift.
- **Workflow conventions** live in `.claude/rules/`: branch model (`branch-workflow.md`), PR title/body + co-author trailer (`pull-requests.md`), commit messages (`commit-messages.md`), README Usage (`readme-usage.md`), when/where to write specs & plans (`spec-plan-locations.md`), the iterations-history entry every plan must end with (`iterations-history.md`), the open-topics convention for parking follow-up items (`open-topics.md`), and the decisions-log convention for recording subject-matter research decisions in the per-phase `docs/research/<serial>.phase<N>-decisions.md` logs (`decisions-log.md`). Fleet deploy discipline — the canary rule, converge windows for every tier, the alert-rule lifecycle — lives in `fleet-deploys.md`; host access (ssh aliases, the passwordless-sudo deploy user) and the attended-reboot discipline are `docs/reference/fleet.md`; shell/subagent operating lessons in `agent-ops.md`; CLAUDE.md/rules/markdown style in `docs-style.md`; keeping internal traceability vocabulary off operator-visible surfaces in `operator-facing-text.md`. Consult them before branching, opening a PR, or releasing.
