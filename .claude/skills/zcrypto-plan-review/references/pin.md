You are running the contract pin for a spec+plan pair in {WORKTREE} (branch {BRANCH}). You have no prior context.

Read {SPEC} — the binding authority — then {PLAN}.{TOPIC_LINE} Do not read `docs/memo.local.md`. Your cwd resets between commands: prefix each with `cd {WORKTREE} &&`.

## The task

Document review cannot falsify a premise: a pair can be internally consistent around a claim about the world that is simply false. Enumerate every claim the pair makes about something OUTSIDE the two documents — the current tree, a library, a runtime, a venue API, a config, a metric — and verify each **by execution**: run the code, call the function, enumerate the call sites, import the module, collect the tests, render the template. Never by reading a docstring, a type stub, a comment or a name.

The minimum, for every instance the pair contains:

- every symbol the plan says exists — `uv run python -c "import …; print(…)"`, or the search that finds its definition;
- every "X is only called from Y" — enumerate the call sites, then trace whether an unlisted one is reachable on a production path;
- every method the plan's code calls — sync or async by CALLING it in a scratch interpreter, never by `inspect.iscoroutinefunction` (native bindings answer that falsely);
- every `-k` filter, test path and stated collect count — `uv run pytest --collect-only -q <path> -k "<expr>"`;
- every constructor, dataclass or signature the plan extends — the existing construction sites (`grep -rn "<Name>("` across `cli/ tests/ infra/`) and whether the new fields have defaults;
- every fixture the plan's tests request — its precondition, against what the code path under test actually produces;
- every template substitution — which publishing path performs it, and whether the plan's artefact travels through that path;
- every config key, host path, unit name, metric name, alert uid, runbook anchor — present where the plan says, in the current tree;
- every threshold — against the structural range of the metric it compares to.

A claim about a fleet host — a unit, a mount, a running container, a host's config — cannot be checked from here: ssh is blocked in a dispatched agent. **This is about where the COMMAND runs, not what it reports on**: a repo script you can run here that queries a monitoring API is yours to run and grade, however much its subject is a host; only a command that must execute ON the host is a `HOST` line.

**Every path, unit name, container name and host alias inside a `HOST` command is RESOLVED FROM THE REPO before you write it** — `docs/reference/fleet.md` is the register, and you search it for the THING (the container, the dataset, the mount), never for the spelling you expect. A guessed path is worse than no line: it runs, returns nothing, and scores the premise unverifiable when the premise was true. If you cannot resolve one, write the line as `UNVERIFIABLE · <claim> · could not resolve <the path/unit/alias> from the repo — <where you looked>` and let it be a finding; never write a command carrying a value you could not confirm, and never delegate the confirming to whoever runs it. Write it as `HOST · <the claim, quoted> · <the exact read-only command that would check it, scoped per CLAUDE.md's secrets rule — a docker inspect names one field, never .Config or .Config.Env, never docker exec … env>`; do not run it and do not grade it — the orchestrator runs those lines itself.

Write `{REPORT_DIR}/pin-facts.md`: one line per claim — `VERIFIED | REFUTED | UNVERIFIABLE | HOST · <the claim, quoted> · <the command> · <what it returned>`. Each line begins with its grade followed by ` · ` — no list markers, no tables, no bold; a line that does not start with a grade fails the orchestrator's gate. The reviewers that follow receive this file as fact and will not re-verify it, so a line you did not actually run is a lie they will build on.

Every REFUTED claim is a finding in `{OUT}` in the shape below; the Scenario is what happens when an implementer acts on the false premise. Every UNVERIFIABLE claim is a finding at Important, stating what would have to exist for it to be checked.

{COMMON}

Read-only: change nothing in the tree; a scratch interpreter and `--collect-only` are the only execution you perform. Run everything as plain blocking commands; background nothing; no subagents. Do not end your turn before both files exist.
