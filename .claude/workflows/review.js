export const meta = {
  name: 'review',
  description: 'The wide review of a whole branch: two lenses, one skeptic per Critical or Important',
  whenToUse: 'The wide review a branch owes once it is complete, after its pre-read; again only when a fix adds a door, a guard or files outside the first read’s range. args: {repo, range, tip, reportDir, lenses?, drive?, model?}',
  phases: [
    { title: 'Ledger', detail: 'the order of reviews, refused rather than remembered' },
    { title: 'Read', detail: 'one read-only reader per lens, in parallel' },
    { title: 'Refute', detail: 'one skeptic per Critical and Important' },
    { title: 'Record', detail: 'the row that says this review happened, written once it has' },
  ],
}

// --- inputs ------------------------------------------------------------------------------------
const { repo, range, tip, reportDir, drive, model } = args || {}
if (!repo || !range || !tip || !reportDir) throw new Error('args: {repo, range, tip, reportDir, lenses?, drive?, model?}')
if (drive && drive.length > 400) throw new Error(`drive is ${drive.length} characters, at most 400: one sentence naming what the standing brief does not cover — cut every clause that names a figure, a path or a command, the brief re-measures those itself`)
const DEFAULT_LENSES = [
  { name: 'behaviour', brief: 'What the range changes, driven: each door, refusal, count or guard the messages claim, exercised with the input it names on every grid or path it applies to; anything legitimate now refused; any live-path behaviour changed where no test drives it; every citation of a spec, rule or topic read as written.' },
  { name: 'guards', brief: 'Every test and assertion the range adds or changes: does it refuse what its door refuses, can it pass vacuously (an absence, a substring, a double that never runs), does each probe verdict a message records reproduce through the case it names with a mutation that parses, and is every test double the engine suite must classify classified.' },
]
const lenses = Array.isArray(args.lenses) && args.lenses.length ? args.lenses : DEFAULT_LENSES
for (const l of lenses) {
  if (!l.name || !l.brief || !/^[a-z0-9-]+$/.test(l.name)) throw new Error(`lens needs a slug name and a brief: ${JSON.stringify(l)}`)
}
if (new Set(lenses.map((l) => l.name)).size !== lenses.length) throw new Error(`lens names must be distinct: ${lenses.map((l) => l.name).join(', ')}`)

// --- shared with pre-read.js and re-review.js; tests/test_review_workflows.py holds GRADING, SCOPE and RULES equal across the three ---
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
const readerPrompt = (lens) => `You are one of ${lenses.length} independent readers, a different agent from the author, of \`git log ${range}\` at tip \`${tip}\` in ${repo}. ${RULES} ${CHECKOUT(`read-${lens.name}`)} ${SCOPE} Grading: ${GRADING}

YOUR LENS — ${lens.name}: ${lens.brief} The other lenses are ${lenses.filter((o) => o.name !== lens.name).map((o) => o.name).join(', ') || 'none'}; leave their ground to them. The pre-read has already graded the range's prose and re-run its message claims: grade prose only where acting on it as written breaks something, and re-measure a claim only where the range's correctness rests on it.${drive ? ` Beyond the standing brief, drive this: ${drive}` : ''}

Read \`git diff ${range}\` first, then each commit message. Write a Markdown report to ${reportDir}/${lens.name}.md with \`## Verdict\`, \`## Findings\` (one \`### [Severity] path:line — claim\` heading per finding with evidence and a \`Consequence:\` line) and \`## Executed\`, then return the structured output with the same findings; the report and the structure must agree.`

const refutePrompt = (f) => `You are the skeptic. ${RULES} ${CHECKOUT(`refute-${f.id}`)} ${SCOPE}

A reader graded this ${f.severity}: at \`${f.path}:${f.line}\` — ${f.claim}
Its evidence: ${f.evidence}
Its consequence: ${f.consequence}

Try to REFUTE it: reproduce what the evidence claims, and decide whether the claim holds as stated at this tip — including whether its consequence follows (a test that stops it, a pre-branch behaviour that was no better). Default to refuted=true when you cannot make it hold. Return the structured output; write nothing to the repo.`

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
if (!ledger) throw new Error(`review refuses ${tip}: the ledger agent returned nothing — a failed bookkeeping step, not a missing pre-read; retry`)
const entries = ledger.entries || []
const covered = (kind) => entries.some((e) => e.kind === kind && e.coversTip)
if (!covered('pre-read')) throw new Error(`review refuses ${tip}: ${ledgerPath} records no pre-read of this tip or an ancestor — run pre-read on it first`)

// --- Read: one reader per lens; the union needs all of them, so the barrier is right ------------
phase('Read')
const opts = (label, phaseName, effort) => ({ label, phase: phaseName, agentType: 'general-purpose', effort, ...(model ? { model } : {}) })
const reports = (await parallel(lenses.map((l) => () => agent(readerPrompt(l), { ...opts(`read:${l.name}`, 'Read', 'high'), schema: REPORT })))).map((r, i) => (r ? { ...r, lens: lenses[i].name } : null))
const dropped = lenses.filter((_, i) => !reports[i]).map((l) => l.name)
if (dropped.length) log(`readers that returned nothing: ${dropped.join(', ')}`)
const live = reports.filter(Boolean)
if (!live.length) throw new Error('no reader returned a report')

// --- the union: cluster on path:line, keep the maximum severity, never re-grade downward; every lens's wording is kept
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

// --- Refute: one skeptic per Critical and Important; a finding dies when the skeptic refutes it ------
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
log(`after refutation: ${count('Critical', standing)} Critical / ${count('Important', standing)} Important / ${count('Minor', standing)} Minor standing, ${graded.length - standing.length} refuted`)

// --- Record: the row that says this review happened, written once it has -------------------------
phase('Record')
const recorded = await agent(
  `Bookkeeping only. Append exactly one line to ${ledgerPath}, creating the file if absent: {"kind":"review","range":"${range}","tip":"${tip}","ts":"<date -u +%Y-%m-%dT%H:%M:%SZ>"}. Return appended true once the line is on disk. No other file, no other command.`,
  { label: 'record', phase: 'Record', agentType: 'general-purpose', model: 'sonnet', effort: 'low', schema: RECORDED },
)
if (!recorded || !recorded.appended) log(`${ledgerPath} did not take the row for this review — the next read refuses ${tip} until it carries {"kind":"review","tip":"${tip}"}; append it by hand`)

return {
  range,
  tip,
  recorded: Boolean(recorded && recorded.appended),
  lenses: live.map((r) => ({ name: r.lens, verdict: r.verdict, reportPath: r.reportPath, executed: r.executed })),
  droppedLenses: dropped,
  counts: { Critical: count('Critical', standing), Important: count('Important', standing), Minor: count('Minor', standing), refuted: graded.length - standing.length },
  findings: graded,
}
