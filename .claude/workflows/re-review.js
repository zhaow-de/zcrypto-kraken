export const meta = {
  name: 're-review',
  description: 'Read a fix range against a prior review: each prior finding closed at its class, left, or open',
  whenToUse: 'After the fixes a review asked for, before push. args: {repo, range, tip, prior: [{id, severity, path, line, claim}], left, grading, reportDir, model?}',
  phases: [
    { title: 'Re-read', detail: 'one reader over the fix range with the prior findings' },
    { title: 'Refute', detail: 'two independent skeptics per Critical and Important, new or reopened' },
  ],
}

// --- inputs ------------------------------------------------------------------------------------
const { repo, range, tip, prior, left, grading, reportDir, model } = args || {}
if (!repo || !range || !tip || !Array.isArray(prior) || !grading || !reportDir) {
  throw new Error('args: {repo, range, tip, prior: [{id, severity, path, line, claim}], left, grading, reportDir, model?}')
}
for (const p of prior) {
  if (!Number.isInteger(p.id) || !p.severity || !p.path || !Number.isInteger(p.line) || !p.claim) throw new Error(`prior finding needs integer id, severity, path, integer line, claim: ${JSON.stringify(p)}`)
  if (/\n/.test(p.claim)) throw new Error(`prior finding ${p.id}: claim is one line -- the full text stays in the prior review's report, which the reader can open`)
}
if (left && !/#\d+/.test(left)) throw new Error('left names each consciously-left prior by id (#<id>) with its reason')

// --- schemas -----------------------------------------------------------------------------------
const FINDING = {
  type: 'object',
  properties: {
    severity: { type: 'string', enum: ['Critical', 'Important', 'Minor'] },
    path: { type: 'string', description: 'repo-relative path, or a commit sha for a message finding' },
    line: { type: 'integer', description: '1-based line, 0 when the finding has no line' },
    claim: { type: 'string' },
    evidence: { type: 'string' },
    consequence: { type: 'string' },
  },
  required: ['severity', 'path', 'line', 'claim', 'evidence', 'consequence'],
}
const PRIOR = {
  type: 'object',
  properties: {
    id: { type: 'integer' },
    status: { type: 'string', enum: ['closed', 'left', 'open'] },
    by: { type: 'string', description: 'closed: the hunk or commit, the class the finding is an instance of and what was checked beyond the instance, or why it has no class beyond itself; left: the words of the author that leave it, with the reason shown to hold; open: why, a standing sibling or a reason that does not hold included' },
  },
  required: ['id', 'status', 'by'],
}
const CLAIM = {
  type: 'object',
  properties: {
    claim: { type: 'string', description: 'one claim a commit message makes, in its words' },
    disposition: { type: 'string', enum: ['re-measured', 'read', 'declined'] },
    by: { type: 'string', description: 'the command quoted, what was read, or why the range does not rest on it' },
  },
  required: ['claim', 'disposition', 'by'],
}
const REPORT = {
  type: 'object',
  properties: {
    verdict: { type: 'string' },
    prior: { type: 'array', items: PRIOR, description: 'one entry per prior finding, every id accounted for' },
    findings: { type: 'array', items: FINDING, description: 'new findings only' },
    messageClaims: { type: 'array', items: CLAIM, description: 'every claim the messages in the range make, each with its disposition' },
    executed: { type: 'array', items: { type: 'string' } },
    reportPath: { type: 'string' },
  },
  required: ['verdict', 'prior', 'findings', 'messageClaims', 'executed', 'reportPath'],
}
const VERDICT = {
  type: 'object',
  properties: { refuted: { type: 'boolean' }, reason: { type: 'string' } },
  required: ['refuted', 'reason'],
}

// --- prompts -----------------------------------------------------------------------------------
const common = (label) => `Repo: ${repo}, range \`${range}\`, tip \`${tip}\`. Run every git command with \`-C ${repo}\`. READ-ONLY in that checkout: no edits, no commits, no checkout, no stash. To re-run a mutation probe (infra/scripts/mutate-probe.sh refuses a dirty tree and restores by \`git checkout --\`), use a detached worktree of your own at the tip — \`git -C ${repo} worktree add --detach ${reportDir}/wt-${label} ${tip}\` — knowing that its first \`uv run\` builds the worktree its own environment, and remove it with \`git worktree remove --force\` before you finish. Plain blocking commands only, no background jobs, no subagents. Never run \`docker inspect\` or \`ansible-inventory\`. Grading: ${grading}`

const priorList = prior.map((p) => `- #${p.id} [${p.severity}] ${p.path}:${p.line} — ${p.claim}`).join('\n')
const readerPrompt = `You are the scoped second reader, a different agent from the author, of the fix commits \`git log ${range}\`. ${common('re-read')}

The prior review's findings, which these commits answer:
${priorList}

What the author names as consciously left, each by prior id with its reason (the reason is a claim this read rests on: check it against the tree): ${left || 'nothing'}

Read \`git diff ${range}\` first, then each commit message; a claim a message makes is re-measured when the range's correctness rests on it — a mutation verdict re-run with the exact strings the message quotes, a number re-derived by a command you quote; a claim about a file the range does not touch is read, not re-run, and the full suite is CI's to run, not yours; a claim you neither re-measured nor read is named with why the range does not rest on it, so a scoped read is distinguishable from a skipped one. A verdict a message names without the command that produced it has not been shown, and a check whose failure would have looked like success — a probe whose failing output nobody read, a grep whose miss prints nothing, an install whose output was suppressed — has not been run, whatever the message says: each is a finding at the commit, graded as the grading above grades a claim that does not reproduce (Important where it is silent), never a probe of your own choosing. Then walk every prior finding by id: closed (name the hunk or commit, AND name the class the finding is an instance of — the sibling spellings, the other carriers of the same claim, the other branches of the same condition — and say what you checked beyond the instance the finding named; where the finding has no class beyond itself — a wrong number, a dangling reference, a sentence that contradicts its own file — say that instead, and say why nothing else carries it; a hunk that answers the finding as written and leaves a sibling standing has not closed it), left (only when the author's words above name it by id AND the reason holds against the tree; a left whose reason does not hold is open, the reason's failure being why), or open — a prior finding neither closed nor named as left is open; report it in the prior table only, not again under findings, since the workflow carries an open one forward itself. Grade anything else in the diff you would grade as a new finding. Write a Markdown report to ${reportDir}/re-review.md with \`## Counts\`, \`## Verdict\`, \`## Prior findings\` (a table), \`## Findings\`, \`## Claims\` (one row per claim a message makes: re-measured with its command, read with what was read, or declined with why the range does not rest on it) and \`## Executed\`, then return the structured output; the report and the structure must agree.`

const refutePrompt = (f, k) => `You are skeptic ${k + 1} of 2. ${common(`refute-${f.id}-${k + 1}`)}

A reader graded this ${f.severity}: at \`${f.path}:${f.line}\` — ${f.claim}
Its evidence: ${f.evidence}
Its consequence: ${f.consequence}

${f.priorId ? `This row reopens prior #${f.priorId}. Its first grading — ${f.firstGrading} — may well have been answered by the fix and is NOT the claim; what stands is the reader's reason, the evidence above.\n\n` : ''}Try to REFUTE it: reproduce what the evidence claims, and decide whether the claim holds as stated at this tip. Default to refuted=true when you cannot make it hold. Return the structured output; write nothing to the repo.`

// --- Re-read -----------------------------------------------------------------------------------
phase('Re-read')
const opts = (label, phaseName) => ({ label, phase: phaseName, agentType: 'general-purpose', ...(model ? { model } : {}) })
const report = await agent(readerPrompt, { ...opts('re-read', 'Re-read'), schema: REPORT })
if (!report) throw new Error('the reader returned nothing')
const known = new Set(prior.map((p) => p.id))
const unknown = report.prior.filter((p) => !known.has(p.id)).map((p) => p.id)
if (unknown.length) log(`the reader's table names ids the caller never passed, ignored: ${unknown.join(', ')}`)
const seen = new Set()
const doubled = report.prior.filter((p) => known.has(p.id)).map((p) => p.id).filter((id, i, ids) => ids.indexOf(id) !== i)
if (doubled.length) log(`the reader's table lists a prior twice, the first row kept: ${[...new Set(doubled)].join(', ')}`)
report.prior = report.prior.filter((p) => known.has(p.id) && !seen.has(p.id) && seen.add(p.id))  // one row per prior id, the first wins
const accounted = new Set(report.prior.map((p) => p.id))
const unaccounted = prior.map((p) => p.id).filter((id) => !accounted.has(id))
if (unaccounted.length) log(`prior findings the reader did not account for: ${unaccounted.join(', ')} -- carried forward as open`)
const open = [...report.prior.filter((p) => p.status === 'open').map((p) => p.id), ...unaccounted]
const RANK = { Critical: 3, Important: 2, Minor: 1 }
const byId = new Map(prior.map((p) => [p.id, p]))
// A reopened prior goes to the skeptics as the reader's reason it is open -- a standing sibling, a left reason that fails -- not as the instance first graded, which the fix may well have answered.
const reopened = open.filter((id) => byId.has(id)).map((id) => { const why = (report.prior.find((p) => p.id === id) || { by: 'the reader did not account for it' }).by; return { ...byId.get(id), claim: `prior #${id} stands open`, evidence: why, consequence: 'the prior finding stands', priorId: id, firstGrading: byId.get(id).claim } })
const findings = [...report.findings, ...reopened].sort((a, b) => RANK[b.severity] - RANK[a.severity]).map((f, i) => ({ ...f, id: i + 1 }))
const count = (sev, list) => list.filter((f) => f.severity === sev).length
const claimsOf = (kind) => report.messageClaims.filter((c) => c.disposition === kind).length
log(`prior: ${report.prior.filter((p) => p.status === 'closed').length} closed, ${report.prior.filter((p) => p.status === 'left').length} left, ${open.length} open; new: ${count('Critical', findings)} Critical / ${count('Important', findings)} Important / ${count('Minor', findings)} Minor; message claims: ${claimsOf('re-measured')} re-measured, ${claimsOf('read')} read, ${claimsOf('declined')} declined`)

// --- Refute the Criticals and Importants, new or reopened -----------------------------------------------------
phase('Refute')
const graded = (
  await parallel(
    findings.map((f) => () =>
      f.severity === 'Minor'
        ? Promise.resolve({ ...f, refuted: false, skeptics: [] })
        : parallel([0, 1].map((k) => () => agent(refutePrompt(f, k), { ...opts(`refute:${f.id}.${k + 1}`, 'Refute'), schema: VERDICT }))).then((vs) => {
            const skeptics = vs.filter(Boolean)
            if (skeptics.length < 2) log(`finding ${f.id}: ${2 - skeptics.length} skeptic(s) returned nothing; it stands unrefuted`)
            return { ...f, refuted: skeptics.length === 2 && skeptics.every((v) => v.refuted), skeptics, skepticsMissing: 2 - skeptics.length }
          }),
    ),
  )
).filter(Boolean)
const standing = graded.filter((f) => !f.refuted)

return {
  range,
  tip,
  verdict: report.verdict,
  reportPath: report.reportPath,
  executed: report.executed,
  prior: report.prior,
  messageClaims: report.messageClaims,
  unaccounted,
  open,
  counts: { Critical: count('Critical', standing), Important: count('Important', standing), Minor: count('Minor', standing), refuted: graded.length - standing.length },
  findings: graded,
}
