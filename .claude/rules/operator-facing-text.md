# Operator-facing text

Internal traceability vocabulary — `Phase <N>`, `T<NNNN>`, `iter-<NNN>`, `spec <NNNNN>` and its D-numbers — never appears on a surface visible **without opening the repo**.

- **In scope**: systemd `Description=`, CLI `--help`, runtime output from `cli/` and `infra/` (Python *and* shell — a textfile exporter's `# HELP` lines are printed by `printf`), Prometheus metric HELP text, Grafana alert summaries and panel titles/descriptions, Grafana notification templates (`infra/grafana/notification-templates/*.tmpl`), compose `${VAR:?message}` errors, README. A new operator-visible surface joins this list **and** the test together.
- **Out of scope**: source comments, docstrings, `docs/`, commit messages — there the tokens are load-bearing, and stripping them destroys traceability for no operator gain.
- **Log lines are out of scope too**: they are the primary debugging surface, and whoever reads one has the repo open. An **alert summary is the opposite** — read on a phone, in Slack, with nothing open — so it is in scope.
- Keep the semantic content, move the token to the adjacent comment. A `Description=` still says what the unit does; the serial sits on the line above it.
- `WP<N>` is banned from every git-tracked file, not just these — `zcrypto-grooming`'s `references/memo-protocol.md`, which also records the one historical exception; don't add more, and don't "fix" the recorded exception away. The ban is enforced repo-wide by the same test (two-way allowlist).

`tests/test_internal_terms_not_operator_visible.py` enforces every surface listed above. It checks each **non-docstring** literal rather than only the ones inside a `raise`/`echo` — a message built into a variable and printed later is invisible to a call-site walk.
