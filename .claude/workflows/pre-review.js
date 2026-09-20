export const meta = {
  name: 'pre-review',
  description: 'The author’s prose and message claims graded by a different agent before any review',
  whenToUse: 'Before every review or re-review — over the fix range after the first review: graders grade the range’s prose, re-run the commands and probes its messages quote, and check each fix’s class walk. args: {repo, range, tip, reportDir, worktree?, model?, ranges?, rulings?}',
  phases: [
    { title: 'Pre-review', detail: 'a read-only grader per slice over the range’s prose and message claims' },
    { title: 'Record', detail: 'the row the review that follows checks, written once the read is done' },
  ],
}

// --- inputs ------------------------------------------------------------------------------------
const { repo, range, tip, reportDir, worktree, model, ranges, rulings } = args || {}
// `ranges` fans the read out: one grader per entry, each inside its own budget, over one slice of `range`.
const FAN = Array.isArray(ranges) && ranges.length ? ranges : null
const LABEL = /^[a-z0-9][a-z0-9-]{0,31}$/
// The one recorded row says the whole branch range was read, so the slices are held to a cover of it by their own spelling.
const ends = (r) => String((r && r.range) || r || '').split('..')
const chained = FAN && FAN.every((r, i) => ends(r).length === 2 && ends(r)[0] !== ends(r)[1] && ends(r)[0] === (i ? ends(FAN[i - 1])[1] : ends(range)[0])) && ends(FAN[FAN.length - 1])[1] === ends(range)[1]
const badRanges = ranges != null && (!chained || FAN.some((r) => !LABEL.test(r.label || '')) || new Set(FAN.map((r) => r.label)).size !== FAN.length)
if (!repo || !range || !tip || !reportDir || badRanges) throw new Error('args: {repo, range, tip, reportDir, worktree?, model?, ranges?: [{label, range}] — labels unique, 1 to 32 of lowercase, digits and dashes, none opening with a dash; ranges `a..b` chained from the opening of `range` to its close, none empty —, rulings?}')

// --- shared with review.js and re-review.js; tests/test_review_workflows.py holds GRADING, SCOPE and RULES equal across the three ---
const GRADING = `Critical = a defect that reaches the operator as a traceback, silently degrades a report, refuses something legitimate, instructs the operator to destroy or invalidate data, or changes live-trade-path behaviour no test drives; a count that reads 0 over a set that misses the violation's usual shape; a guard that passes when it should refuse. Important = a claim a commit message makes that does not reproduce with the command it quotes, a probe verdict earned by something other than the guard it names, a number typed rather than pasted from the run it describes, a test that can pass vacuously, prose that, acted on as written, breaks something no test stops, or a change that alters behaviour or a guard's reach whatever its size. Minor = everything else in prose: wrong, dead, self-contradictory, naming a site a reader cannot find, or a comment or docstring a reader would not act on.`
const SCOPE = `Re-run a probe only through the case its message records (a \`-k\` case), never a whole test file; re-derive a number only where the range's correctness rests on it; never run the full suite, prose-chars or the whole count list — they are CI's and the author's. About 40 tool calls: when the range is graded, stop and write.`
const RULES = `READ-ONLY in the repo checkout: no edits, no commits, no checkout, no stash. Plain blocking commands only, no background jobs, no subagents, and no agent tools (\`ListAgents\`, \`SendMessage\`): you read a range, you do not coordinate. Never run \`docker inspect\`, \`ansible-inventory\` or ssh; the data root under data/ is unversioned and read-only for you.`
const OWN_CHECKOUT = (label) => `Run every git command with \`-C ${repo}\` and read files at the tip with \`git -C ${repo} show ${tip}:<path>\`. Other graders read sibling ranges of this branch at the same time, so a probe or a drive that must execute the range's code runs in a detached worktree of your own — \`git -C ${repo} worktree add --detach ${reportDir}/wt-pre-${label} ${tip}\`, removed with \`git worktree remove --force\` before you return — never in the checkout and never in another grader's worktree, and never for reading: a worktree costs a venv sync, and a docs range needs none.`
const CHECKOUT = worktree
  ? `Run every git command with \`-C ${repo}\`. A detached worktree at the tip, already synced, is at ${worktree}: run probes and drives there — you are its only user — and never create, remove or check out a worktree.`
  : `Run every git command with \`-C ${repo}\` and read files at the tip with \`git -C ${repo} show ${tip}:<path>\`. Create a detached worktree only when a probe or a drive must execute the range's code — \`git -C ${repo} worktree add --detach ${repo}/.tmp/reads/pre-review-<tip7> ${tip}\`, removed before you return — and never for reading: a worktree costs a venv sync, and a docs range needs none.`

// --- schema ------------------------------------------------------------------------------------
const PROSE = {
  type: 'object',
  properties: {
    site: { type: 'string', description: 'path:line at the tip; a long site graded paragraph by paragraph returns one row per paragraph, each at its own first line' },
    survives: { type: 'string', enum: ['trim', 'cut', 'fix', 'keep'] },
    correct: { type: 'boolean', description: 'false when a claim in it is false of the tree' },
    duplicateOf: { type: 'string', description: 'path:line of the sibling that already carries the claim, whatever carries it — or empty' },
    ship: { type: 'string', description: 'the text to ship, verbatim — empty when cut; for `keep`, the one line naming what a reader would do differently without that paragraph' },
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
    fix: { type: 'string', description: 'what the commit says it fixed, and in one sentence the invariant the fix restores' },
    siblingsLeft: { type: 'array', items: { type: 'string' }, description: 'one entry per member the fix left, each prefixed `TEXT:` (a carrier, with its path:line) or `SPACE:` (an input or state category the fix still admits, with what you drove or why you could not)' },
  },
  required: ['fix', 'siblingsLeft'],
}
const REPORT = {
  type: 'object',
  properties: {
    ready: { type: 'boolean', description: 'true when nothing above needs a change before a read' },
    verdict: { type: 'string', description: 'three sentences at most' },
    graded: { type: 'integer', description: 'how many prose sites were graded, including the ones that stand' },
    prose: { type: 'array', items: PROSE, description: 'the sites that need a change, plus a `keep` row for every paragraph of a site longer than eight lines that stands' },
    claims: { type: 'array', items: CLAIM },
    probes: { type: 'array', items: PROBE },
    classWalk: { type: 'array', items: WALK },
    reportPath: { type: 'string' },
  },
  required: ['ready', 'verdict', 'graded', 'prose', 'claims', 'probes', 'classWalk', 'reportPath'],
}

// --- the grader --------------------------------------------------------------------------------
const promptFor = (slice) => `You are the pre-reviewer of \`git log ${slice ? slice.range : range}\` at tip \`${tip}\` in ${repo}, a different agent from the author, run before any review.${slice ? ` That range is the slice \`${slice.label}\` of the branch range \`${range}\`; other graders read its other slices now, so grade what THIS slice's commits add or change and leave a site only another slice touches to its grader.` : ''} ${RULES} ${slice ? OWN_CHECKOUT(slice.label) : CHECKOUT} ${SCOPE} Grading: ${GRADING}

Four things, each against the tree at the tip, none on trust:

1. PROSE. Every comment, docstring, topic sentence and operator-facing string the range adds or changes — graded as it stands at the tip in the whole docstring or comment block a hunk lands in, plus the module docstring or header of each touched file, not the added lines alone, because a phrase per commit accretes into repetition. Three questions: would a reader do something differently without it (name what)? Is every claim in it correct against the code and data? Does the same claim already stand elsewhere — in the code the prose describes, in a test that drives it, in an error string, in the rule or topic it cites, or in the range's commit messages (quote the sibling with path:line)? A durable file holds STATE and DECISIONS; an EVENT — what was measured, read, found or corrected — goes to the commit message, never into the code; an operator-facing string may carry an instruction and the one reason that stops the wrong move.

The first question is asked of every PARAGRAPH of every site the range touches, whatever its length — the eight-line bar below decides only which standing paragraphs are LISTED — and it is asked BEFORE the second: a paragraph a reader would not act on is cut without its claims being checked, because correcting a sentence that should not exist is the accretion this grader exists to stop. A site longer than eight lines as a reader sees it, source or rendered, is graded paragraph by paragraph, each owing its own answer, and a paragraph with none is cut whatever the truth of its sentences — a long block of true sentences is the shape that passes a site-level read and fails its reader. Four shapes fail that question on sight, and each is a row: (a) a paragraph that enumerates what a table, a constant, a case list or a function's branches below it already spell out — the code is the list and the prose a copy that goes stale; what may stay is the external fact the code encodes but cannot say, such as why two branches differ or a tool's own asymmetry; (b) a specimen — a literal path, id, count, date or string that came from a measurement over the tree or its history — is an event: cut it and name the commit message as its home; (c) a sentence stating a behaviour a test drives duplicates that test, which is exhaustive and executable where the prose is a sample; (d) a rule restated from the negative side after the positive side gave it ("not X" beside "only Y"). None of the four is cut on sight where a rule names that prose as owed — a guard whose header or docstring \`CLAUDE.md\` requires to state what it refuses is graded on its reader like any other site. A site the range has already rewritten once (\`git log -p ${range} -- <path>\` shows the same paragraph changed in an earlier commit of the range), and that no rule names as owed, is graded cut unless you can ship it correct in one line: a sentence rewritten once and up for rewriting again is the signal that the code or a test states it better.

Return a row for a site that needs a change — \`trim\`, \`cut\`, or \`fix\` when the length stands and a claim in it does not — with the text to ship, verbatim — the WHOLE site as it should read, never a fragment with the rest declared unchanged, because the author replaces the site with it — and never longer than what stands: a fix that lengthens a site is a \`cut\` you have not found yet; and a \`keep\` row for every paragraph of a site longer than eight lines that stands — a \`keep\` whose \`ship\` names no reason a reader would act on is not a keep, and the run reports it as a row you owe. A shorter site that stands as written is counted in \`graded\` and not listed, so the report is the exceptions and \`graded\` is the census.

2. CLAIMS. Every claim a commit message in the range makes that a command can check — a number, a count, a grep verdict, a citation, a "none left" — re-run with the command the message quotes (or the obvious one when it quotes none) and compared. A claim that does not reproduce is disposition does-not-reproduce with what the command printed.${rulings && (!slice || slice === FAN[FAN.length - 1]) ? ` The task loop's rulings are claims too: every line of ${rulings} carrying \`Ruling:\` or \`minor (deferred)\` is re-run like a message's claim, its commit the one it names or \`task-loop\`.` : ''}

3. PROBES. Every mutate-probe verdict a message records: apply the quoted mutation to a copy of the file and compile it (python -m py_compile, bash -n, node --check as the file demands) — a mutation that does not parse voids the verdict whatever the script printed; then re-run the probe as quoted and read what the killed case died on: a collection error, an import error or a SyntaxError is not a kill by the guard.

4. CLASS WALK. For each defect a commit says it fixed, state in one sentence the invariant the fix restores, then walk its class BOTH ways and list every member the fix left. TEXT: the defect's other carriers — sibling spellings, other files carrying the same claim, other branches of the same condition. SPACE: the categories the fixed code's input or state ranges over, each judged against the invariant — only categories this repo produces, driven where you can drive them, named rather than guessed where you cannot. A class walked one way is half walked. Each fix also names, in its \`fix\` sentence, what it DELETED from the sites it touched — a fix over a site this range already rewrote that deletes nothing is the fourth-round shape, and is reported as one.

EARLIER PRE-REVIEWS of this branch are the ${reportDir}/pre-review-*.md files${slice ? ` that do not carry \`${tip}\` in their name: those are sibling slices writing now` : ''} (none on a first read). A site one of them SHIPPED — a row graded trim, cut or fix whose shipped text the range now carries — is graded keep and not re-graded: the grader does not re-grade its own dispositions, and a site graded keep by an earlier pre-review is re-graded only where the range changed it. The one exception is a shipped text that is WRONG, which is a fix like any other, with the earlier report named.

Write a Markdown report to ${reportDir}/pre-review-${tip}${slice ? `-${slice.label}` : ''}.md with \`## Verdict\`, \`## Prose\` (a table of the sites needing a change and of the paragraphs a long site keeps, under a line saying how many were graded), \`## Claims\`, \`## Probes\`, \`## Class walk\`, then return the structured output; the report and the structure must agree. Write nothing else to the repo.`

phase('Pre-review')
const grade = (slice) => agent(promptFor(slice), { label: slice ? `pre-review:${slice.label}` : 'pre-review', phase: 'Pre-review', agentType: 'general-purpose', effort: 'high', schema: REPORT, ...(model ? { model } : {}) })
const parts = FAN ? await parallel(FAN.map((slice) => () => grade(slice))) : [await grade(null)]
if (parts.some((p) => !p)) throw new Error(FAN ? `the pre-reviewers of ${FAN.filter((_, i) => !parts[i]).map((r) => r.label).join(', ')} returned nothing` : 'the pre-reviewer returned nothing')
// A site two slices touched comes back once per slice.
const bySite = new Map()
for (const row of parts.flatMap((p) => p.prose)) bySite.set(row.site, [...(bySite.get(row.site) || []), row])
const asked = (rows) => rows.filter((r, i) => r.survives !== 'keep' && rows.findIndex((o) => o.survives === r.survives && o.ship === r.ship) === i)
const prose = [...bySite.values()].flatMap((rows) => (asked(rows).length ? asked(rows) : rows.slice(0, 1)))
const contested = FAN ? [...bySite.entries()].filter(([, rows]) => asked(rows).length > 1).map(([site]) => site) : []
if (contested.length) log(`CONTESTED: ${contested.length} site(s) carry a different change from more than one slice, all rows returned — ${contested.join(', ')}`)
const report = !FAN
  ? parts[0]
  : {
      ready: parts.every((p) => p.ready),
      verdict: parts.map((p, i) => `[${FAN[i].label}] ${p.verdict}`).join(' '),
      graded: parts.reduce((sum, p) => sum + p.graded, 0),
      prose,
      claims: parts.flatMap((p) => p.claims),
      probes: parts.flatMap((p) => p.probes),
      classWalk: parts.flatMap((p) => p.classWalk),
      reportPath: parts.map((p) => p.reportPath).join(', '),
    }
const n = (list, pred) => list.filter(pred).length
// A reason is judged by what is left of it: the words a placeholder is made of, and the words any sentence
// carries, say nothing on their own, so a ship built only from those is a count wearing a sentence's clothes.
const SAYS_NOTHING = new Set(['none', 'nothing', 'nil', 'na', 'tbd', 'keep', 'kept', 'stand', 'stands', 'write', 'written', 'change', 'changes', 'changed', 'need', 'needed', 'needs', 'same', 'unchanged', 'ok', 'okay', 'fine', 'good', 'correct', 'right', 'already', 'still', 'reads', 'read', 'looks', 'look', 'seems', 'add', 'yes', 'x', 'y'])
const ANY_SENTENCE = new Set(['a', 'an', 'the', 'is', 'are', 'was', 'be', 'been', 'it', 'its', 'this', 'that', 'as', 'to', 'of', 'and', 'or', 'no', 'not', 'here', 'for', 'in', 'on', 'at', 'with', 'without', 'by', 'so'])
const saysNothing = (ship) => {
  const said = new Set(String(ship || '').toLowerCase().split(/[^a-z]+/).filter((w) => w && !SAYS_NOTHING.has(w) && !ANY_SENTENCE.has(w)))
  return said.size < 2
}
const mute = report.prose.filter((p) => p.survives === 'keep' && saysNothing(p.ship)).map((p) => p.site)
if (mute.length) log(`OWED: ${mute.length} \`keep\` row(s) name no reason a reader would act on — ${mute.join(', ')}`)
log(`prose: ${report.graded} graded${FAN ? ' (summed over slices, so a site two slices graded counts twice)' : ''}, ${n(report.prose, (p) => p.survives === 'cut')} cut, ${n(report.prose, (p) => p.survives === 'trim')} trimmed, ${n(report.prose, (p) => p.survives === 'fix')} corrected, ${n(report.prose, (p) => p.survives === 'keep')} keep rows; claims: ${n(report.claims, (c) => c.disposition === 'does-not-reproduce')} do not reproduce; probes: ${n(report.probes, (p) => !p.mutationParses || !p.verdictReproduces)} void; class walk: ${n(report.classWalk, (w) => w.siblingsLeft.length)} fixes with siblings left; ready: ${report.ready}`)
const ledgerPath = `${reportDir}/ledger.jsonl`
const RECORDED = { type: 'object', properties: { appended: { type: 'boolean' } }, required: ['appended'] }

// --- Record -------------------------------------------------------------------------------------
phase('Record')
const recorded = await agent(
  `Bookkeeping only. Append exactly one line to ${ledgerPath}, creating the file if absent: {"kind":"pre-review","range":"${range}","tip":"${tip}","ts":"<date -u +%Y-%m-%dT%H:%M:%SZ>"}. Return appended true once the line is on disk. No other file, no other command.`,
  { label: 'record', phase: 'Record', agentType: 'general-purpose', model: 'sonnet', effort: 'low', schema: RECORDED },
)
if (!recorded || !recorded.appended) log(`${ledgerPath} did not take the row for this pre-review — the next read refuses ${tip} until it carries {"kind":"pre-review","tip":"${tip}"}; append it by hand`)
return { ...report, recorded: Boolean(recorded && recorded.appended) }
