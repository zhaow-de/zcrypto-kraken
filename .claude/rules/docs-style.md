# CLAUDE.md, rules, and markdown style

- **Markdown: one line per paragraph/bullet** — never hard-wrap to a column width; let the renderer wrap.
- **CLAUDE.md and `.claude/rules/*` are operational guidance for Claude, not human-facing docs**: the shortest imperative statement of what to DO / NOT do, one line each where possible; drop human-facing phrasing.
- **No narration in rules** — history, derivations, measurements, dates, and rationale beyond one clause belong in specs/topics.
- **No references except operands.** Cite only what you will actually open and use: a config path, a script you run, a sibling rule or skill you load, a live lookup table. Never spec serials, topic IDs, or code line numbers — a line number rots silently and nothing in the commit gate checks it. If a code pointer is genuinely needed, name the symbol, not the coordinates.
- **Keep the one-clause why** wherever the instruction would otherwise look wrong, so it does not get "corrected" later. That is not a reference.
- **Add to CLAUDE.md only what changes Claude's behavior.** Never duplicate a config's mechanics (globs, regexes, hook scoping) — that knowledge lives in the config file itself.
- **A config's absence from CLAUDE.md is the signal not to touch it** — wait for an explicit instruction before changing configs CLAUDE.md doesn't mention.
