export const meta = {
  name: 'review',
  description: 'Read a diff range: one reader per lens, two skeptics on every Critical or Important',
  whenToUse: 'The read a different agent from the author owes a branch before push. args: {repo, range, tip, lenses: [{name, brief}], grading, reportDir, model?}',
  phases: [
    { title: 'Read', detail: 'one read-only reader per lens, in parallel' },
    { title: 'Refute', detail: 'two independent skeptics per Critical and Important' },
  ],
}

// --- inputs ------------------------------------------------------------------------------------
const { repo, range, tip, lenses, grading, reportDir, model } = args || {}
if (!repo || !range || !tip || !Array.isArray(lenses) || lenses.length === 0 || !grading || !reportDir) {
  throw new Error('args: {repo, range, tip, lenses: [{name, brief}], grading, reportDir, model?}')
}
for (const l of lenses) {
  if (!l.name || !l.brief || !/^[a-z0-9-]+$/.test(l.name)) throw new Error(`lens needs a slug name and a brief: ${JSON.stringify(l)}`)
}
if (new Set(lenses.map((l) => l.name)).size !== lenses.length) throw new Error(`lens names must be distinct: ${lenses.map((l) => l.name).join(', ')}`)

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
const REPORT = {
  type: 'object',
  properties: {
    verdict: { type: 'string', description: 'three sentences at most, including whether the range is pushable' },
    findings: { type: 'array', items: FINDING },
    executed: { type: 'array', items: { type: 'string' }, description: 'every command relied on, with its summary line' },
    reportPath: { type: 'string' },
  },
  required: ['verdict', 'findings', 'executed', 'reportPath'],
}
const VERDICT = {
  type: 'object',
  properties: {
    refuted: { type: 'boolean', description: 'true when the finding does not hold as claimed; default to true when uncertain' },
    reason: { type: 'string', description: 'the command or reading that decides it' },
  },
  required: ['refuted', 'reason'],
}

// --- prompts -----------------------------------------------------------------------------------
const common = (label) => `Repo: ${repo}, range \`${range}\`, tip \`${tip}\`. Run every git command with \`-C ${repo}\`. READ-ONLY in that checkout: no edits, no commits, no checkout, no stash. To re-run a mutation probe (infra/scripts/mutate-probe.sh refuses a dirty tree and restores by \`git checkout --\`), use a detached worktree of your own at the tip — \`git -C ${repo} worktree add --detach ${reportDir}/wt-${label} ${tip}\` — knowing that its first \`uv run\` builds the worktree its own environment, and remove it with \`git worktree remove --force\` before you finish. Plain blocking commands only, no background jobs, no subagents. Never run \`docker inspect\` or \`ansible-inventory\`. Grading: ${grading}`

const readerPrompt = (lens) => `You are one of ${lenses.length} independent readers, a different agent from the author, of \`git log ${range}\`. ${common(`read-${lens.name}`)}

YOUR LENS — ${lens.name}: ${lens.brief} The other lenses are ${lenses.filter((o) => o.name !== lens.name).map((o) => o.name).join(', ') || 'none'}; leave their ground to them.

Read \`git diff ${range}\` first, then each commit message; a claim a message makes is re-measured when the range's correctness rests on it — a mutation verdict re-run with the exact strings the message quotes, a number re-derived by a command you quote; a message that names a verdict without the command that produced it has not shown it, so grade that claim unmeasured rather than choosing a probe of your own; a claim about a file the range does not touch is read, not re-run, and the full suite is CI's to run, not yours. A check whose failure would have looked like success — a probe whose failing output nobody read, a grep whose miss prints nothing, an install whose output was suppressed — was not run, whatever the message says. Write a Markdown report to ${reportDir}/${lens.name}.md with \`## Counts\`, \`## Verdict\`, \`## Findings\` (one \`### [Severity] path:line — claim\` heading per finding with evidence and a \`Consequence:\` line) and \`## Executed\`, then return the structured output with the same findings; the report and the structure must agree.`

const refutePrompt = (f, k) => `You are skeptic ${k + 1} of 2. ${common(`refute-${f.id}-${k + 1}`)}

A reader graded this ${f.severity}: at \`${f.path}:${f.line}\` — ${f.claim}
Its evidence: ${f.evidence}
Its consequence: ${f.consequence}

Try to REFUTE it: reproduce what the evidence claims, and decide whether the claim holds as stated at this tip. Default to refuted=true when you cannot make it hold. Return the structured output; write nothing to the repo.`

// --- Read: one reader per lens; the union needs all of them, so the barrier is right ------------
phase('Read')
const opts = (label, phaseName) => ({ label, phase: phaseName, agentType: 'general-purpose', ...(model ? { model } : {}) })
const reports = (await parallel(lenses.map((l) => () => agent(readerPrompt(l), { ...opts(`read:${l.name}`, 'Read'), schema: REPORT })))).map((r, i) => (r ? { ...r, lens: lenses[i].name } : null))
const dropped = lenses.filter((_, i) => !reports[i]).map((l) => l.name)
if (dropped.length) log(`readers that returned nothing: ${dropped.join(', ')}`)
const live = reports.filter(Boolean)
if (!live.length) throw new Error('no reader returned a report')

// --- the union: cluster on path:line as the plan-review union does, keep the maximum severity, never re-grade downward; every lens's wording is kept
const RANK = { Critical: 3, Important: 2, Minor: 1 }
const key = (f) => `${f.path}:${f.line}`
const union = new Map()
for (const r of live) {
  for (const f of r.findings) {
    const k = key(f)
    const prev = union.get(k)
    if (!prev) union.set(k, { ...f, lenses: [r.lens], claims: [{ lens: r.lens, severity: f.severity, claim: f.claim }] })
    else {
      prev.lenses.push(r.lens)
      prev.claims.push({ lens: r.lens, severity: f.severity, claim: f.claim })
      if (RANK[f.severity] > RANK[prev.severity]) Object.assign(prev, { severity: f.severity, claim: f.claim, evidence: f.evidence, consequence: f.consequence })
    }
  }
}
const findings = [...union.values()].sort((a, b) => RANK[b.severity] - RANK[a.severity]).map((f, i) => ({ ...f, id: i + 1 }))
const count = (sev, list) => list.filter((f) => f.severity === sev).length
log(`union over ${live.length} lenses: ${count('Critical', findings)} Critical / ${count('Important', findings)} Important / ${count('Minor', findings)} Minor`)

// --- Refute: two skeptics per Critical and Important; a finding dies only when both refute it ------
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
log(`after refutation: ${count('Critical', standing)} Critical / ${count('Important', standing)} Important / ${count('Minor', standing)} Minor standing, ${graded.length - standing.length} refuted, ${graded.filter((f) => f.skepticsMissing).length} with a skeptic missing`)

return {
  range,
  tip,
  lenses: live.map((r) => ({ name: r.lens, verdict: r.verdict, reportPath: r.reportPath, executed: r.executed })),
  droppedLenses: dropped,
  counts: { Critical: count('Critical', standing), Important: count('Important', standing), Minor: count('Minor', standing), refuted: graded.length - standing.length },
  findings: graded,
}
