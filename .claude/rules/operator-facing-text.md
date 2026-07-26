# Operator-facing text

Internal traceability vocabulary — `Phase <N>`, `T<NNNN>`, `iter-<NNN>`, `spec <NNNNN>` and its D-numbers — never appears on a surface visible **without opening the repo**.

- **In scope**: systemd `Description=`, CLI `--help`, CLI runtime messages (raised exceptions, `typer.echo`, `print`), README, compose container names and labels, any future UI string.
- **Out of scope**: source comments, `docs/`, commit messages — there the tokens are load-bearing, and stripping them destroys traceability for no operator gain.
- **Log lines are out of scope too**: they are the primary debugging surface, and whoever reads one has the repo open.
- Keep the semantic content, move the token to the adjacent comment. A `Description=` still says what the unit does; the serial sits on the line above it.
- `WP<N>` is banned from every git-tracked file, not just these — `zcrypto-grooming`'s `references/memo-protocol.md`.

`tests/test_internal_terms_not_operator_visible.py` enforces all of this; it walks the rendered `--help`, not the source, so a command registered in an unusual way is still covered.
