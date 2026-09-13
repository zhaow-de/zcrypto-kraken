export const meta = {
  name: 'pre-read',
  description: 'The author’s prose and message claims graded by a different agent before any read',
  whenToUse: 'Before every review or re-review of a range: one agent grades the range’s prose, re-runs the commands and probes its messages quote, and checks each fix’s class walk. args: {repo, range, tip, reportDir, worktree, model?}',
  phases: [{ title: 'Pre-read', detail: 'one read-only grader over the range’s prose and message claims' }],
}

// --- inputs ------------------------------------------------------------------------------------
const { repo, range, tip, reportDir, worktree, model } = args || {}
if (!repo || !range || !tip || !reportDir || !worktree) throw new Error('args: {repo, range, tip, reportDir, worktree, model?}')

// --- shared with review.js and re-review.js; tests/test_review_workflows.py holds the three copies equal ---
const GRADING = `Critical = a defect that reaches the operator as a traceback, silently degrades a report, refuses something legitimate, instructs the operator to destroy or invalidate data, or changes live-trade-path behaviour no test drives; a count that reads 0 over a set that misses the violation's usual shape; a guard that passes when it should refuse. Important = a claim a commit message makes that does not reproduce with the command it quotes, a probe verdict earned by something other than the guard it names, a number typed rather than pasted from the run it describes, a test that can pass vacuously, or prose that, acted on as written, breaks something no test stops. Minor = everything else in prose: wrong, dead, self-contradictory, naming a site a reader cannot find, or a comment or docstring a reader would not act on.`
const SCOPE = `Re-run a probe only through the case its message records (a \`-k\` case), never a whole test file; re-derive a number only where the range's correctness rests on it; never run the full suite, prose-chars or the whole count list — they are CI's and the author's. About 40 tool calls: when the range is graded, stop and write.`
const COMMON = `Run every git command with \`-C ${repo}\`. READ-ONLY in that checkout: no edits, no commits, no checkout, no stash. A detached worktree at the tip, already synced, is at ${worktree}: run probes and drives there, and never create, remove or check out a worktree. Plain blocking commands only, no background jobs, no subagents. Never run \`docker inspect\`, \`ansible-inventory\` or ssh; the data root under data/ is unversioned and read-only for you.`

// --- schema ------------------------------------------------------------------------------------
const PROSE = {
  type: 'object',
  properties: {
    site: { type: 'string', description: 'path:line at the tip' },
    survives: { type: 'string', enum: ['yes', 'trim', 'cut'] },
    correct: { type: 'boolean' },
    duplicateOf: { type: 'string', description: 'path:line of the sibling that already carries the claim, or empty' },
    ship: { type: 'string', description: 'the text to ship, verbatim — empty when cut' },
  },
  required: ['site', 'survives', 'correct', 'duplicateOf', 'ship'],
}
const CLAIM = {
  type: 'object',
  properties: {
    commit: { type: 'string' },
    claim: { type: 'string', description: 'one claim the message makes, in its words' },
    disposition: { type: 'string', enum: ['reproduces', 'does-not-reproduce', 'not-checkable'] },
    by: { type: 'string', description: 'the command re-run and what it printed, or why it cannot be run' },
  },
  required: ['commit', 'claim', 'disposition', 'by'],
}
const PROBE = {
  type: 'object',
  properties: {
    commit: { type: 'string' },
    command: { type: 'string' },
    mutationParses: { type: 'boolean', description: 'the mutated file compiles (python -m py_compile / bash -n / node --check)' },
    verdictReproduces: { type: 'boolean' },
    killedBy: { type: 'string', description: 'the assertion or error the killed case died on — a collection error or SyntaxError means the verdict is void' },
  },
  required: ['commit', 'command', 'mutationParses', 'verdictReproduces', 'killedBy'],
}
const WALK = {
  type: 'object',
  properties: {
    fix: { type: 'string', description: 'what the commit says it fixed' },
    siblingsLeft: { type: 'array', items: { type: 'string' }, description: 'path:line of each carrier of the same defect the fix did not touch' },
  },
  required: ['fix', 'siblingsLeft'],
}
const REPORT = {
  type: 'object',
  properties: {
    ready: { type: 'boolean', description: 'true when nothing above needs a change before a read' },
    verdict: { type: 'string', description: 'three sentences at most' },
    prose: { type: 'array', items: PROSE },
    claims: { type: 'array', items: CLAIM },
    probes: { type: 'array', items: PROBE },
    classWalk: { type: 'array', items: WALK },
    reportPath: { type: 'string' },
  },
  required: ['ready', 'verdict', 'prose', 'claims', 'probes', 'classWalk', 'reportPath'],
}

// --- the grader --------------------------------------------------------------------------------
const prompt = `You are the pre-reader of \`git log ${range}\` at tip \`${tip}\` in ${repo}, a different agent from the author, run before any review. ${COMMON} ${SCOPE} Grading: ${GRADING}

Four things, each against the tree at the tip, none on trust:

1. PROSE. Every comment, docstring, topic sentence and operator-facing string the range adds or changes — graded as it stands at the tip in the whole docstring or comment block a hunk lands in, plus the module docstring of each touched file, not the added lines alone, because a phrase per commit accretes into repetition. Three questions per site: would a reader do something differently without it (name what)? Is every claim in it correct against the code and data? Does the same claim already stand in the same file, in an error string, in the rule or topic it cites, or in the range's commit messages (quote the sibling with path:line)? Evidence and reasoning for a decision belong in the commit message, never in the code; an operator-facing string may carry an instruction and the one reason that stops the wrong move. For each site return survives yes / trim / cut and the text to ship, verbatim.

2. CLAIMS. Every claim a commit message in the range makes that a command can check — a number, a count, a grep verdict, a citation, a "none left" — re-run with the command the message quotes (or the obvious one when it quotes none) and compared. A claim that does not reproduce is disposition does-not-reproduce with what the command printed.

3. PROBES. Every mutate-probe verdict a message records: apply the quoted mutation to a copy of the file and compile it (python -m py_compile, bash -n, node --check as the file demands) — a mutation that does not parse voids the verdict whatever the script printed; then re-run the probe as quoted in the worktree and read what the killed case died on: a collection error, an import error or a SyntaxError is not a kill by the guard.

4. CLASS WALK. For each defect a commit says it fixed, grep the tree for the same defect's other carriers — sibling spellings, other files carrying the same claim, other branches of the same condition — and list any the fix did not touch.

Write a Markdown report to ${reportDir}/pre-read.md with \`## Verdict\`, \`## Prose\` (a table), \`## Claims\`, \`## Probes\`, \`## Class walk\`, then return the structured output; the report and the structure must agree. Write nothing else to the repo.`

phase('Pre-read')
const report = await agent(prompt, { label: 'pre-read', phase: 'Pre-read', agentType: 'general-purpose', effort: 'high', schema: REPORT, ...(model ? { model } : {}) })
if (!report) throw new Error('the pre-reader returned nothing')
const n = (list, pred) => list.filter(pred).length
log(`prose: ${n(report.prose, (p) => p.survives === 'cut')} cut, ${n(report.prose, (p) => p.survives === 'trim')} trimmed, ${n(report.prose, (p) => !p.correct)} incorrect; claims: ${n(report.claims, (c) => c.disposition === 'does-not-reproduce')} do not reproduce; probes: ${n(report.probes, (p) => !p.mutationParses || !p.verdictReproduces)} void; class walk: ${n(report.classWalk, (w) => w.siblingsLeft.length)} fixes with siblings left; ready: ${report.ready}`)
return report
