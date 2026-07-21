# Decisions log

Per-phase logs `docs/research/<serial>.phase<N>-decisions.md` record **subject-matter research decisions**, appended live and committed with each iteration's closing commit — interactive and unattended modes alike.

**The gate — log iff both hold**: (1) it's about the **subject matter** (research direction, variants, scope, the feature/model/label/universe/knob to try), and (2) you're in a **live research iteration** — an unattended `/zcrypto-auto-exec` iteration, or an interactive session actively designing or running one. Skip everything else — permission, engineering/tooling, process, formatting. Reversible tooling choices are still *decided* autonomously, just not logged.

**Entry format and phase routing are the `iteration-closeout` skill** (`.claude/skills/iteration-closeout/SKILL.md`): load it when logging.
