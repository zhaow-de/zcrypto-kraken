---
status: resolved
---

# Internal development terms leak onto user-facing surfaces

## Context — what

Internal development vocabulary — `Phase <N>`, `T<NNNN>` topics, `iter-<NNN>`, `spec <NNNNN>` (+ D-numbers) — belongs to the repo's traceability convention: specs, plans, decision logs, code comments. It has leaked onto surfaces an **operator sees at runtime without opening the repo**, where it is noise at best and confusion at worst (registered 2026-07-23 grooming; the triggering example was `infra/systemd/zcrypto-engine-shadow.service`'s `Description=zcrypto shadow engine (Phase 6a soak): …`).

Measured inventory (2026-07-23):

- **systemd `Description=` lines — the main surface, ~9 units** (visible in `systemctl status`, `systemctl list-timers`, journalctl headers): the shadow-engine unit ("Phase 6a soak"), `grafana-watchdog` ("T0083"), `panel-materialize` ("spec 00052 D6"), `zcrypto-capture-prune` ("spec 00050 D8"), `verified-replay` / `verify-replay` ("spec 00051 OPS-3"), `archive-pull` ("spec 00054/T0058"), plus the prune/probe timer variants.
- **`README.md` — three spots** (lines ≈136, 233, 237): "spec `docs/specs/00049-…`", "spec 00052 D6 / T0066" twice, inside option-semantics prose the readme-usage rule requires.
- **CLI `--help` strings — clean** (grepped all `help=` in `cli/`).
- **CLI runtime error strings — a measurement blind spot; audited for `T<NNNN>` only, NOT closed for the rest of the vocabulary.** The `help=`-only grep above structurally cannot see a message raised at runtime, and one leaked: `cli/panel/command.py`'s non-EUR `--pair` refusal printed the literal `T0092` to the operator's terminal (found 2026-07-26 by the pre-push review of `feat/t0092-btc-quoted-capture`, which introduced it; fixed in that branch by moving the token to the adjacent comment). Errors raised to a terminal are squarely "visible without opening the repo", so the sweep's grep must cover them — `typer.BadParameter`, `typer.Exit` messages **including those routed through `_abort`** (`cli/panel/command.py:36-39` logs via `logger.error`, and the default handler is `StreamHandler(sys.stdout)` per `cli/logging/config.py:25`, so it prints to the terminal *and* reaches the Alloy log pipeline), and raised exception text — not just `help=`.
  - **Method, and what a too-narrow scan cost.** An AST walk over every `raise` in `cli/`, matching the vocabulary inside the raised message's string literals, is the measurement — a `help=` grep and a plain line-grep both miss these (token and `raise` usually sit on different lines). Scanned first for `T\d{4}` alone, it found a **second** instance: `cli/data/rebuild.py:103`, the universe staleness refusal, ends `...measures past liquidity, not current (T0093).` **That narrow scan then produced a false all-clear** — this entry claimed the surface "closed" while having checked one of the four vocabulary classes (the same over-claim the entry above corrects, one level down; caught 2026-07-26 by the review of the fix commit). Re-run across the full vocabulary (`T\d{4}`, `spec \d{5}`, `Phase \d+`, `iter-\d+`), it found a **third**, of a different class and in the very file the fix touched: `cli/panel/command.py:76`, `_check_generation`'s panel-meta refusal, ends `...must be an explicit regeneration of the whole panel tree (spec 00052 D5), never a silent mix.` Both remaining leaks are left unfixed deliberately — `rebuild.py` is outside the fixing branch, and the `spec 00052` one is pre-existing rather than introduced by it — so both are sweep work, registered here rather than left in a review report.
- **compose container names / labels — clean.**

## Why this matters

These are the surfaces a future operator (or the owner, months later) reads cold: `systemctl status` output should say *what a unit does*, not which internal iteration minted it. The traceability the tokens provide is not lost by removing them — it moves one line up, into the unit file's **comment**, which is repo-internal and already the convention everywhere else. Related precedent: `WP<N>` labels are already banned from git-tracked files outright; this topic draws the (weaker) line for the rest of the vocabulary — internal terms stay out of *runtime-visible/user-facing* strings, while comments and docs keep them deliberately.

## Findings so far

- The boundary that makes the rule cheap to follow: **"visible without opening the repo" = in scope** (README, CLI `--help`, **CLI runtime error/exit messages**, systemd `Description=`, compose container names/labels, and any future UI strings); **source comments, docs/, commit messages = explicitly out of scope** — spec serials in comments are load-bearing internal documentation, and cleansing them would destroy traceability for zero operator benefit.
- Compose is clean and CLI `--help` is clean, but the third CLI surface — runtime error messages — was never measured and holds two known leaks (above), so the rule does more than *pin* the status quo: the sweep is ~9 `Description=` rewordings + 3 README spots + 2 raised-message rewordings, with the done-check a `cli/` AST walk over raised text across the whole vocabulary.
- Log messages were not named in the ruling and are left as a boundary question for the rule's design (operator-visible, but also the primary debugging surface where a `T<NNNN>` pointer can genuinely help — decide, rather than leave implicit).

## Resolution

**Resolved 2026-07-26.** The rule is `.claude/rules/operator-facing-text.md`, the sweep is done, and both are enforced by `tests/test_internal_terms_not_operator_visible.py`.

**Enforced by a test rather than swept once.** A sweep has to be re-run by whoever remembers it exists; a test runs on every PR. That also answers this topic's optional pre-commit-guard question — a hook would add noise for a check the suite already performs.

**Two rounds, and the second was three times the first.** The initial pass found **23** leaks against an estimated 14. Adversarial review then showed the detector itself had blind spots, and widening it found **25 more** — 48 sites, 62 token instances, across eight surfaces. The method was the work; the sweep was mechanical.

**What the review's widening actually closed** — each of these was a false-all-clear waiting to happen:

- **Indirection.** A message built into a variable and echoed later (`text = render_report(...); typer.echo(text)`) is invisible to any call-site walk, and chasing it statically is dataflow analysis. The detector now checks **every non-docstring literal**, sidestepping it — measured cost: four findings, zero false positives, because docstrings are excluded and no `logger.*` literal carries vocabulary.
- **Line wrapping.** Rich wraps the `--help` column at ~46 chars, so `spec 00052` split across a break was invisible to a regex expecting the space. Whitespace is collapsed before matching.
- **A too-greedy path carve-out.** `spec 00054/T0058` is two tokens joined by a slash, not a path — the original pattern excused the second one. A path now needs two separators or a file extension. That exact string was in this repo, in a `Description=` that only failed on its *other* token.
- **Surfaces the rule named but nothing checked**: Prometheus metric HELP text, Grafana alert summaries and panel descriptions, compose `${VAR:?message}` errors, and `infra/scripts/` — the instruments `capture-deploys.md` tells an operator to run.

**Grafana alert summaries turned out to be the strongest case in the rule, not an exception.** The reasoning that excuses log lines — the reader has the repo open — is exactly inverted for an alert: it is read on a phone, in Slack, with nothing open. Ten summaries carried trailing tokens appended to otherwise actionable text; the tokens went, the instructions stayed. Pushed live and read back from the API: 48 rules, zero carrying vocabulary.

**Several leaks were added the same evening**, by the T0021 and T0027 iterations, while this topic sat in the queue. That is the argument for enforcement over a one-time sweep, in one line.

**Boundaries decided rather than left implicit**, now recorded in the rule:

- **Log lines are out of scope** — the primary debugging surface, and its reader has the repo open. Verified rather than assumed: no `logger.*` literal in the scanned packages carries vocabulary, so the carve-out costs nothing today.
- **A token inside a file path is not a leak** — you need the exact name to open the file, which makes it an operand rather than a reference.
- **Semantic content stays, the token moves to the adjacent comment.** Two Descriptions kept the operator-useful half of their parenthetical ("the unit name is historical") while shedding the serial beside it.

Host-side, the reworded Descriptions land at each role's next natural converge — a `Description=` change is cosmetic, so no dedicated deploy. The Grafana half was pushed immediately, since alert text is a deployed artifact.
