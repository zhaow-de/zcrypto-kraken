export const meta = {
  name: 're-review',
  description: 'Scoped read of a fix range against a prior review: every prior finding closed by a named hunk, consciously left, or open; new findings refuted by two skeptics',
  whenToUse: 'After the fixes a review asked for, before push. args: {repo, range, tip, prior: [{id, severity, path, line, claim}], left, grading, reportDir, model?}',
  phases: [
    { title: 'Re-read', detail: 'one reader over the fix range with the prior findings' },
    { title: 'Refute', detail: 'two independent skeptics per new Critical and Important' },
  ],
}

// --- inputs ------------------------------------------------------------------------------------
const { repo, range, tip, prior, left, grading, reportDir, model } = args || {}
if (!repo || !range || !tip || !Array.isArray(prior) || !grading || !reportDir) {
  throw new Error('args: {repo, range, tip, prior: [{id, severity, path, line, claim}], left, grading, reportDir, model?}')
}
for (const p of prior) {
  if (!Number.isInteger(p.id) || !p.severity || !p.path || !Number.isInteger(p.line) || !p.claim) throw new Error(`prior finding needs integer id, severity, path, integer line, claim: ${JSON.stringify(p)}`)
}

// --- schemas -----------------------------------------------------------------------------------
const FINDING = {
  type: 'object',
  properties: {
    severity: { type: 'string', enum: ['Critical', 'Important', 'Minor'] },
    path: { type: 'string' },
    line: { type: 'integer' },
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
    by: { type: 'string', description: 'the hunk or commit that closed it, the words that leave it, or why it is open' },
  },
  required: ['id', 'status', 'by'],
}
const REPORT = {
  type: 'object',
  properties: {
    verdict: { type: 'string' },
    prior: { type: 'array', items: PRIOR, description: 'one entry per prior finding, every id accounted for' },
    findings: { type: 'array', items: FINDING, description: 'new findings only' },
    executed: { type: 'array', items: { type: 'string' } },
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
const common = (label) => `Repo: ${repo}, range \`${range}\`, tip \`${tip}\`. Run every git command with \`-C ${repo}\`. READ-ONLY in that checkout: no edits, no commits, no checkout, no stash. To re-run a mutation probe (infra/scripts/mutate-probe.sh refuses a dirty tree and restores by \`git checkout --\`), use a detached worktree of your own at the tip — \`git -C ${repo} worktree add --detach ${reportDir}/wt-${label} ${tip}\` — knowing that its first \`uv run\` builds the worktree its own environment, and remove it with \`git worktree remove --force\` before you finish. Plain blocking commands only, no background jobs, no subagents. Never run \`docker inspect\` or \`ansible-inventory\`. Grading: ${grading}`

const priorList = prior.map((p) => `- #${p.id} [${p.severity}] ${p.path}:${p.line} — ${p.claim}`).join('\n')
const readerPrompt = `You are the scoped second reader, a different agent from the author, of the fix commits \`git log ${range}\`. ${common('re-read')}

The prior review's findings, which these commits answer:
${priorList}

What the author names as consciously left: ${left || 'nothing'}

Read \`git diff ${range}\` first, then each commit message; every claim a message makes is checked against the tree — a mutation verdict re-run with its exact strings, a number re-derived by a command you quote. Then walk every prior finding by id: closed (name the hunk or commit), left (only when the author's words above name it), or open — a prior finding neither closed nor named as left is open; report it in the prior table only, not again under findings, since the workflow carries an open one forward itself. Grade anything else in the diff you would grade as a new finding. Write a Markdown report to ${reportDir}/re-review.md with \`## Counts\`, \`## Verdict\`, \`## Prior findings\` (a table), \`## Findings\` and \`## Executed\`, then return the structured output; the report and the structure must agree.`

const refutePrompt = (f, k) => `You are skeptic ${k + 1} of 2. ${common(`refute-${f.id}-${k + 1}`)}

A reader graded this ${f.severity}: at \`${f.path}:${f.line}\` — ${f.claim}
Its evidence: ${f.evidence}
Its consequence: ${f.consequence}

Try to REFUTE it: reproduce what the evidence claims, and decide whether the claim holds as stated at this tip. Default to refuted=true when you cannot make it hold. Return the structured output; write nothing to the repo.`

// --- Re-read -----------------------------------------------------------------------------------
phase('Re-read')
const opts = (label, phaseName) => ({ label, phase: phaseName, agentType: 'general-purpose', ...(model ? { model } : {}) })
const report = await agent(readerPrompt, { ...opts('re-read', 'Re-read'), schema: REPORT })
if (!report) throw new Error('the reader returned nothing')
const accounted = new Set(report.prior.map((p) => p.id))
const unaccounted = prior.map((p) => p.id).filter((id) => !accounted.has(id))
if (unaccounted.length) log(`prior findings the reader did not account for: ${unaccounted.join(', ')}`)
const open = report.prior.filter((p) => p.status === 'open').map((p) => p.id)
const RANK = { Critical: 3, Important: 2, Minor: 1 }
const byId = new Map(prior.map((p) => [p.id, p]))
const reopened = open.filter((id) => byId.has(id)).map((id) => ({ ...byId.get(id), evidence: report.prior.find((p) => p.id === id).by, consequence: 'the prior finding stands', priorId: id }))
const findings = [...report.findings, ...reopened].sort((a, b) => RANK[b.severity] - RANK[a.severity]).map((f, i) => ({ id: i + 1, ...f }))
const count = (sev, list) => list.filter((f) => f.severity === sev).length
log(`prior: ${report.prior.filter((p) => p.status === 'closed').length} closed, ${report.prior.filter((p) => p.status === 'left').length} left, ${open.length} open; new: ${count('Critical', findings)} Critical / ${count('Important', findings)} Important / ${count('Minor', findings)} Minor`)

// --- Refute the new Criticals and Importants -----------------------------------------------------
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
  unaccounted,
  open,
  counts: { Critical: count('Critical', standing), Important: count('Important', standing), Minor: count('Minor', standing), refuted: graded.length - standing.length },
  findings: graded,
}
