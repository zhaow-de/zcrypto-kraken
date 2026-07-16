# CLAUDE.md, rules, and markdown style

- **Markdown: one line per paragraph/bullet** — never hard-wrap to a column width; let the renderer wrap.
- **CLAUDE.md and `.claude/rules/*` are operational guidance for Claude, not human-facing docs**: the shortest imperative statement of what to DO / NOT do, one line each where possible; drop human-facing phrasing.
- **No narration in rules** — history, derivations, measurements, and rationale beyond one clause belong in specs/topics; a rule keeps the standing instruction plus a pointer to the doc holding the why.
- **Add to CLAUDE.md only what changes Claude's behavior.** Never duplicate a config's mechanics (globs, regexes, hook scoping) — that knowledge lives in the config file itself.
- **A config's absence from CLAUDE.md is the signal not to touch it** — wait for an explicit instruction before changing configs CLAUDE.md doesn't mention.
