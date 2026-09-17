export const meta = {
  name: 're-review',
  description: 'The single-lens review of a fix range: every prior closed, left, or open',
  whenToUse: 'After the fixes a review asked for, each fix its own commit and never an amend, so the range exists; after their pre-read; at most two per branch — a Critical or Important still open after the second goes to the owner. Priors are open Critical/Important only. args: {repo, range, tip, prior: [{id, severity, path, line, claim}], reportDir, left?, reported?, drive?, model?}',
  phases: [
    { title: 'Ledger', detail: 'the order of reviews, refused rather than remembered' },
    { title: 'Re-read', detail: 'one reader over the fix range with the open priors' },
    { title: 'Refute', detail: 'one skeptic per Critical and Important, new or reopened' },
    { title: 'Record', detail: 'the row that says this re-review happened, written once it has' },
  ],
}

// --- inputs ------------------------------------------------------------------------------------
const { repo, range, tip, prior, reportDir, left, reported, drive, model } = args || {}
if (!repo || !range || !tip || !Array.isArray(prior) || !reportDir) {
  throw new Error('args: {repo, range, tip, prior: [{id, severity, path, line, claim}], reportDir, left?, reported?, drive?, model?}')
}
for (const p of prior) {
  if (!Number.isInteger(p.id) || !p.severity || !p.path || !Number.isInteger(p.line) || !p.claim) throw new Error(`prior finding needs integer id, severity, path, integer line, claim: ${JSON.stringify(p)}`)
  if (!['Critical', 'Important'].includes(p.severity)) throw new Error(`prior #${p.id} is ${p.severity}: a Minor is never a prior -- pass it in \`reported\` as context, fixed or left with its reason`)
  if (/\n/.test(p.claim)) throw new Error(`prior finding ${p.id}: claim is one line -- the full text stays in the prior review's report, which the reader can open`)
}
if (left && !/#\d+/.test(left)) throw new Error('left names each consciously-left prior by id (#<id>) with its reason')
if (drive && drive.length > 400) throw new Error(`drive is ${drive.length} characters, at most 400: one sentence naming what the standing brief does not cover — cut every clause that names a figure, a path or a command, the brief re-measures those itself`)

// --- shared with pre-read.js and review.js; tests/test_review_workflows.py holds GRADING, SCOPE and RULES equal across the three ---
const GRADING = `Critical = a defect that reaches the operator as a traceback, silently degrades a report, refuses something legitimate, instructs the operator to destroy or invalidate data, or changes live-trade-path behaviour no test drives; a count that reads 0 over a set that misses the violation's usual shape; a guard that passes when it should refuse. Important = a claim a commit message makes that does not reproduce with the command it quotes, a probe verdict earned by something other than the guard it names, a number typed rather than pasted from the run it describes, a test that can pass vacuously, prose that, acted on as written, breaks something no test stops, or a change that alters behaviour or a guard's reach whatever its size. Minor = everything else in prose: wrong, dead, self-contradictory, naming a site a reader cannot find, or a comment or docstring a reader would not act on.`
const SCOPE = `Re-run a probe only through the case its message records (a \`-k\` case), never a whole test file; re-derive a number only where the range's correctness rests on it; never run the full suite, prose-chars or the whole count list — they are CI's and the author's. About 40 tool calls: when the range is graded, stop and write.`
const RULES = `READ-ONLY in the repo checkout: no edits, no commits, no checkout, no stash. Plain blocking commands only, no background jobs, no subagents, and no agent tools (\`ListAgents\`, \`SendMessage\`): you read a range, you do not coordinate. Never run \`docker inspect\`, \`ansible-inventory\` or ssh; the data root under data/ is unversioned and read-only for you.`
const CHECKOUT = (label) => `Run every git command with \`-C ${repo}\`. Probes and drives run in a detached worktree of your own at the tip — \`git -C ${repo} worktree add --detach ${reportDir}/wt-${label} ${tip}\`, whose first \`uv run\` syncs it (about two minutes) — never in the checkout and never in another agent's worktree: a sibling's mutation probe rewrites its tree while it runs. Remove yours with \`git worktree remove --force\` before you finish.`

// --- schemas -----------------------------------------------------------------------------------
const FINDING = {
  type: 'object',
  properties: {
    severity: { type: 'string', enum: ['Critical', 'Important', 'Minor'] },
    path: { type: 'string', description: 'repo-relative path, or a commit sha for a message finding' },
    line: { type: 'integer', description: '1-based line, 0 when the finding has no line' },
    claim: { type: 'string', description: 'one sentence, the defect as a claim' },
    evidence: { type: 'string', description: 'what was run or read, and what it showed' },
    consequence: { type: 'string', description: 'what goes wrong if the claim stands' },
  },
  required: ['severity', 'path', 'line', 'claim', 'evidence', 'consequence'],
}
const PRIOR = {
  type: 'object',
  properties: {
    id: { type: 'integer' },
    status: { type: 'string', enum: ['closed', 'left', 'open'] },
    by: { type: 'string', description: 'closed: the hunk or commit, the class the finding is an instance of — its text carriers AND the categories its input or state ranges over — and what was checked beyond the instance, or why it has no class beyond itself; left: the words of the author that leave it, with the reason shown to hold; open: why, a standing sibling or a reason that does not hold included' },
  },
  required: ['id', 'status', 'by'],
}
const REPORT = {
  type: 'object',
  properties: {
    verdict: { type: 'string', description: 'three sentences at most' },
    prior: { type: 'array', items: PRIOR, description: 'one entry per prior finding, every id accounted for' },
    findings: { type: 'array', items: FINDING, description: 'new findings in the range; a Minor is listed, never carried forward' },
    executed: { type: 'array', items: { type: 'string' }, description: 'every command relied on, with its summary line' },
    reportPath: { type: 'string' },
  },
  required: ['verdict', 'prior', 'findings', 'executed', 'reportPath'],
}
const VERDICT = {
  type: 'object',
  properties: { refuted: { type: 'boolean' }, reason: { type: 'string' } },
  required: ['refuted', 'reason'],
}

// --- prompts -----------------------------------------------------------------------------------
const priorList = prior.map((p) => `- #${p.id} [${p.severity}] ${p.path}:${p.line} — ${p.claim}`).join('\n')
const readerPrompt = `You are the scoped second reader, a different agent from the author, of the fix commits \`git log ${range}\` at tip \`${tip}\` in ${repo}. ${RULES} ${CHECKOUT('re-read')} ${SCOPE} Grading: ${GRADING}

The prior read's open findings, which these commits answer:
${priorList}

What the author names as consciously left, each by prior id with its reason (the reason is a claim this read rests on: check it against the tree): ${left || 'nothing'}
Minors the prior read reported, fixed or left with their reasons — context, not priors: ${reported || 'none'}

The pre-read has already graded the range's prose and re-run its message claims: grade prose only where acting on it as written breaks something, and re-measure a claim only where the range's correctness rests on it.${drive ? ` Beyond the standing brief, drive this: ${drive}` : ''}

Read \`git diff ${range}\` first, then each commit message. Then walk every prior finding by id: closed (name the hunk or commit, AND name the class the finding is an instance of, both ways — the text (sibling spellings, other carriers of the same claim, other branches of the same condition) and the space (the categories the fixed code's input or state ranges over, judged against the invariant the fix restores) — and say what you checked beyond the instance the finding named; where the finding has no class beyond itself say that instead; a hunk that answers the finding as written and leaves a sibling standing has not closed it), left (only when the author's words above name it by id AND the reason holds against the tree), or open — a prior finding neither closed nor named as left is open; report it in the prior table only, since the workflow carries an open one forward itself. Grade anything else in the diff you would grade as a new finding; a Minor you list is context for the author's next pre-read, not a row for the next read. Write a Markdown report to ${reportDir}/re-review.md with \`## Verdict\`, \`## Prior findings\` (a table), \`## Findings\` and \`## Executed\`, then return the structured output; the report and the structure must agree.`

const refutePrompt = (f) => `You are the skeptic. ${RULES} ${CHECKOUT(`refute-${f.id}`)} ${SCOPE}

A reader graded this ${f.severity}: at \`${f.path}:${f.line}\` — ${f.claim}
Its evidence: ${f.evidence}
Its consequence: ${f.consequence}

${f.priorId === undefined ? '' : `This row reopens prior #${f.priorId}. Its first grading — ${f.firstGrading} — may well have been answered by the fix and is NOT the claim; what stands is why the reader left it open, the evidence above.\n\n`}Try to REFUTE it: reproduce what the evidence claims, and decide whether the claim holds as stated at this tip — including whether its consequence follows (a test that stops it, a pre-branch behaviour that was no better). Default to refuted=true when you cannot make it hold. Return the structured output; write nothing to the repo.`

// --- ledger: the order of reviews is refused, not remembered; a row is written once the read is done ---
const LEDGER_ENTRY = {
  type: 'object',
  properties: {
    kind: { type: 'string' }, range: { type: 'string' }, tip: { type: 'string' }, ts: { type: 'string' },
    coversTip: { type: 'boolean', description: 'true when this entry\'s tip is the current tip or an ancestor of it' },
  },
  required: ['kind', 'range', 'tip', 'ts', 'coversTip'],
}
const LEDGER = { type: 'object', properties: { entries: { type: 'array', items: LEDGER_ENTRY } }, required: ['entries'] }
const RECORDED = { type: 'object', properties: { appended: { type: 'boolean' } }, required: ['appended'] }
const ledgerPath = `${reportDir}/ledger.jsonl`
phase('Ledger')
const ledger = await agent(
  `Bookkeeping only. Read ${ledgerPath} if it exists — one JSON object per line, {kind, range, tip, ts}; a missing file is an empty ledger. For each entry set coversTip true when \`git -C ${repo} merge-base --is-ancestor <entry.tip> ${tip}\` exits 0. Return the entries. Write nothing; no other command.`,
  { label: 'ledger', phase: 'Ledger', agentType: 'general-purpose', model: 'sonnet', effort: 'low', schema: LEDGER },
)
if (!ledger) throw new Error(`re-review refuses ${tip}: the ledger agent returned nothing — a failed bookkeeping step, not a missing pre-read; retry`)
const entries = ledger.entries || []
const covered = (kind) => entries.some((e) => e.kind === kind && e.coversTip)
if (!entries.some((e) => e.kind === 'review')) throw new Error(`re-review refuses ${tip}: ${ledgerPath} records no review of this branch — a fix range follows a whole-branch review, never replaces it`)
if (!covered('pre-read')) throw new Error(`re-review refuses ${tip}: ${ledgerPath} records no pre-read of this tip or an ancestor — run pre-read on the fix range first`)

// --- Re-read -----------------------------------------------------------------------------------
phase('Re-read')
const opts = (label, phaseName, effort) => ({ label, phase: phaseName, agentType: 'general-purpose', effort, ...(model ? { model } : {}) })
const report = await agent(readerPrompt, { ...opts('re-read', 'Re-read', 'high'), schema: REPORT })
if (!report) throw new Error('the reader returned nothing')
const known = new Set(prior.map((p) => p.id))
const unknown = report.prior.filter((p) => !known.has(p.id)).map((p) => p.id)
if (unknown.length) log(`the reader's table names ids the caller never passed, ignored: ${unknown.join(', ')}`)
const seen = new Set()
report.prior = report.prior.filter((p) => known.has(p.id) && !seen.has(p.id) && seen.add(p.id))  // one row per prior id, the first wins
const accounted = new Set(report.prior.map((p) => p.id))
const unaccounted = prior.map((p) => p.id).filter((id) => !accounted.has(id))
if (unaccounted.length) log(`prior findings the reader did not account for: ${unaccounted.join(', ')} -- carried forward as open`)
const open = [...report.prior.filter((p) => p.status === 'open').map((p) => p.id), ...unaccounted]
const RANK = { Critical: 3, Important: 2, Minor: 1 }
const byId = new Map(prior.map((p) => [p.id, p]))
// A reopened prior goes to the skeptic as the reader's reason it is open -- a standing sibling, a left reason that fails -- not as the instance first graded, which the fix may well have answered.
const reopened = open.filter((id) => byId.has(id)).map((id) => { const why = (report.prior.find((p) => p.id === id) || { by: 'no reason given: the reader\'s table did not account for this prior, so nothing here says why it stands' }).by; return { ...byId.get(id), claim: `prior #${id} stands open`, evidence: why, consequence: 'the prior finding stands', priorId: id, firstGrading: byId.get(id).claim } })
const findings = [...report.findings, ...reopened].sort((a, b) => RANK[b.severity] - RANK[a.severity]).map((f, i) => ({ ...f, id: i + 1 }))
const count = (sev, list) => list.filter((f) => f.severity === sev).length
log(`prior: ${report.prior.filter((p) => p.status === 'closed').length} closed, ${report.prior.filter((p) => p.status === 'left').length} left, ${open.length} open; new: ${count('Critical', report.findings)} Critical / ${count('Important', report.findings)} Important / ${count('Minor', report.findings)} Minor, plus ${reopened.length} reopened`)

// --- Refute the Criticals and Importants, new or reopened: one skeptic each ---------------------------
phase('Refute')
const graded = (
  await parallel(
    findings.map((f) => () =>
      f.severity === 'Minor'
        ? Promise.resolve({ ...f, refuted: false, skeptic: null })
        : agent(refutePrompt(f), { ...opts(`refute:${f.id}`, 'Refute', 'medium'), schema: VERDICT }).then((v) => {
            if (!v) log(`finding ${f.id}: the skeptic returned nothing; it stands unrefuted`)
            return { ...f, refuted: Boolean(v && v.refuted), skeptic: v }
          }),
    ),
  )
).filter(Boolean)
const standing = graded.filter((f) => !f.refuted)
log(`after refutation: ${count('Critical', standing)} Critical / ${count('Important', standing)} Important standing, ${count('Minor', standing)} Minor reported, ${graded.length - standing.length} refuted`)

// --- Record: the row that says this re-review happened, written once it has -------------------------
phase('Record')
const recorded = await agent(
  `Bookkeeping only. Append exactly one line to ${ledgerPath}, creating the file if absent: {"kind":"re-review","range":"${range}","tip":"${tip}","ts":"<date -u +%Y-%m-%dT%H:%M:%SZ>"}. Return appended true once the line is on disk. No other file, no other command.`,
  { label: 'record', phase: 'Record', agentType: 'general-purpose', model: 'sonnet', effort: 'low', schema: RECORDED },
)
if (!recorded || !recorded.appended) log(`${ledgerPath} did not take the row for this re-review — the next read refuses ${tip} until it carries {"kind":"re-review","tip":"${tip}"}; append it by hand`)

return {
  range,
  tip,
  recorded: Boolean(recorded && recorded.appended),
  verdict: report.verdict,
  reportPath: report.reportPath,
  executed: report.executed,
  prior: report.prior,
  unaccounted,
  open,
  counts: { Critical: count('Critical', standing), Important: count('Important', standing), Minor: count('Minor', standing), refuted: graded.length - standing.length },
  findings: graded,
}
