---
status: open
ripe_when: NOW — an autonomous small iteration (a standing rule + a repo sweep, all reversible edits); the host-side effect of the systemd rewordings lands opportunistically at each role's next converge (a `Description=` change is cosmetic, so no dedicated deploy)
---

# Internal development terms leak onto user-facing surfaces

## Context — what

Internal development vocabulary — `Phase <N>`, `T<NNNN>` topics, `iter-<NNN>`, `spec <NNNNN>` (+ D-numbers) — belongs to the repo's traceability convention: specs, plans, decision logs, code comments. It has leaked onto surfaces an **operator sees at runtime without opening the repo**, where it is noise at best and confusion at worst (registered 2026-07-23 grooming; the triggering example was `infra/systemd/zcrypto-engine-shadow.service`'s `Description=zcrypto shadow engine (Phase 6a soak): …`).

Measured inventory (2026-07-23):

- **systemd `Description=` lines — the main surface, ~9 units** (visible in `systemctl status`, `systemctl list-timers`, journalctl headers): the shadow-engine unit ("Phase 6a soak"), `grafana-watchdog` ("T0083"), `panel-materialize` ("spec 00052 D6"), `zcrypto-capture-prune` ("spec 00050 D8"), `verified-replay` / `verify-replay` ("spec 00051 OPS-3"), `archive-pull` ("spec 00054/T0058"), plus the prune/probe timer variants.
- **`README.md` — three spots** (lines ≈136, 233, 237): "spec `docs/specs/00049-…`", "spec 00052 D6 / T0066" twice, inside option-semantics prose the readme-usage rule requires.
- **CLI `--help` strings — clean** (grepped all `help=` in `cli/`).
- **compose container names / labels — clean.**

## Why this matters

These are the surfaces a future operator (or the owner, months later) reads cold: `systemctl status` output should say *what a unit does*, not which internal iteration minted it. The traceability the tokens provide is not lost by removing them — it moves one line up, into the unit file's **comment**, which is repo-internal and already the convention everywhere else. Related precedent: `WP<N>` labels are already banned from git-tracked files outright; this topic draws the (weaker) line for the rest of the vocabulary — internal terms stay out of *runtime-visible/user-facing* strings, while comments and docs keep them deliberately.

## Findings so far

- The boundary that makes the rule cheap to follow: **"visible without opening the repo" = in scope** (README, CLI `--help`, systemd `Description=`, compose container names/labels, and any future UI strings); **source comments, docs/, commit messages = explicitly out of scope** — spec serials in comments are load-bearing internal documentation, and cleansing them would destroy traceability for zero operator benefit.
- Two surfaces are already clean (CLI help, compose), so the standing rule mostly *pins* the status quo; the sweep itself is ~9 `Description=` rewordings + 3 README spots.
- Log messages were not named in the ruling and are left as a boundary question for the rule's design (operator-visible, but also the primary debugging surface where a `T<NNNN>` pointer can genuinely help — decide, rather than leave implicit).

## Suggested next steps

- **(one small iteration, autonomous)** Write the standing rule in `.claude/rules/` (a `claude`-type commit): the in-scope surface list above, the vocabulary list (`Phase <N>`, `T<NNNN>`, `iter-<NNN>`, `spec <NNNNN>`/D-numbers), the move-to-comment convention for displaced traceability, and the settled log-line decision; cross-reference the existing `WP<N>` ban rather than restating it.
- **(same iteration)** The sweep: reword the ~9 systemd `Description=` lines (semantic content stays, tokens move to the adjacent comment) and the 3 README spots; re-grep all four surfaces afterwards as the done-check. Host-side, the reworded Descriptions take effect at each role's next natural converge — no dedicated deploy.
- **(decide in the rule design, optional)** A pre-commit guard greping the named surfaces for the vocabulary, so the rule enforces itself; weigh against hook noise before adopting.
