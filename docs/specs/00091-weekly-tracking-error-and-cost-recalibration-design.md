# 00091 — the weekly tracking-error report and cost recalibration from real fills

The fourth of [[T0018]]'s five-spec decomposition to be written, at the serial that decomposition reserved for it in 2026-08-11 — `00088`, `00089`, `00090` and `00094` all landed at their own reserved serials, so `00091` is a held gap rather than the next free number. Read-only, no money at risk, no fleet surface.

It produces the two numbers rung 3's go/no-go reads: how far realized execution drifted from the model, weekly, against the floor the venue's order minimums impose; and what the cost basis actually costs, measured from real fills. It is **evidence for a decision, not an operational signal** — it does not gate, alert, page, or mutate anything.

## The measured basis

Verified against the repo, 2026-08-22:

- **The edge is already pinned, so the report's shape is mostly determined, not open.** [[T0116]]'s amendment states it as *"the p95 of the per-cycle drift floor against that week's mean drift, over ≥3 COMPLETE ISO weeks"*. A review of its first draft found it named no edge at all, and on the very data the band was derived from a median edge fails two of four weeks while a p95 edge passes all four — so the choice flips the gate, and it is not this spec's to revisit.
- **The floor half already exists and is validated.** `accumulation_payload` (spec `00081`) computes per-cycle drift at each NAV. Re-run 2026-08-22, it reproduces [[T0118]]'s registered curve to within a decimal on every cell (136 cycles against 138). A second implementation would be a second thing to be wrong.
- **The realized half has a data source.** Exec-ledger `fill` events carry `qty`, `px`, `fee`, `fee_currency`, **`liquidity`** (`maker`/`taker`), `trade_id` and `at` — `executor.py::_fill_payload`, shared by the in-flight and detached paths so an adopted order's fill is recorded in identical terms.
- **The cost half closes a named open item.** [[T0090]]'s third next-step: *"Derive the realized maker/taker blend from real fills and re-price against it. Until then the quoted baseline is the **range 0.51–0.91 conditional**, not a point."*
- **Rung 2's tracking error is NOT a gate input** — ratified with the ladder's shape: concentration fixes entry placeability, not delta placeability, so the number measures something adjacent to the deployable.
- **No fills exist yet.** No order has ever been submitted; `exec_armed` renders false. Everything below is built before its input exists, which is the central risk this spec designs against.

## Decisions

### D1 — one reader, two aggregations

Both outputs land in one spec and one pass over the journal. They share the fill ledger as input and rung 3's go/no-go inherits both; splitting them would mean two passes over one ledger and two specs whose only difference is which column they aggregate.

The floor half **reuses `accumulation_payload` rather than re-deriving it**, for the reason above.

### D2 — a workstation command, and the timer is a registered follow-up

`zcrypto engine tracking-report`, reading the NAS-pulled engine journal exactly as `accum-replay` does (`--journal-dir`, `--since`, `--until`, `--nav` repeatable, `--json`). No timer, no unit, no ops converge, no keep-regex, no alert-rule question, **no canary bake owed** — it ships when it merges. The cadence is weekly and attended, and the consumer is a human reading a decision.

**A scheduled run is deliberately deferred and gets a registered topic at closeout** — the owner chose "command now, timer later", and prose is not registration. The topic's trigger is the condition that would prove the manual cadence unreliable: a rung-3 week that closes with no report produced.

### D3 — the weekly table, and the one thing it must refuse to conflate

Per **complete ISO week**: mean realized drift (bps of NAV), the floor's p95 over those cycles, and the verdict. Partial weeks print marked and are excluded from every verdict — `accum-replay`'s own precedent (*"a p95 over four points is the maximum wearing a percentile's name"*), and the gate needs ≥3 complete weeks.

**Each week is labelled with the rung its cycles came from, and rung-2 weeks are marked measured-but-not-gate-eligible.** Averaging them into a verdict would corrupt the exact number the go/no-go reads, against a ratified decision. This is stricter than [[T0116]] requires — it forbids in code what T0116 forbids in prose.

Realized drift per cycle is `Σ|target·NAV − held| ÷ NAV` in bps, from the cycle journal's `final_targets` and a `held` accumulated **from the ledger's own fills** — not from `zcrypto_exec_position` and not from the venue record. The report reads a pulled journal offline, so the fills are the only source present in its input; and using the engine's own position gauge would make the report agree with the engine by construction, which is precisely the divergence `_reconcile_terminal` exists to doubt.

### D4 — the cost basis is PROPOSED, never applied

The report emits the realized maker share, the blended per-side cost it implies, the registered constant, and the proposal — with `n`, the maker/taker split, and the per-fill realized cost's **min/median/max** — a spread, not a standard deviation, because a handful of probe-scale fills cannot support a parametric dispersion and quoting one would dress up a sample of tens. It writes nothing.

`fee_per_side` is an input registry record 47 was validated under. Re-pricing it changes what the deployable IS, which is re-ratification territory, not a side effect of reading a number — and a go/no-go that reads a constant which moved under it is reading two things at once.

### D5 — it fails closed rather than reporting a number it cannot stand behind

- **A week with no fills reads _no data_, never zero drift.** An empty result is not an absent event; this repo has already booked a `[30d]` selector over a series that had not lived that long ([[T0129]]), and made the same error again on 2026-08-22 quoting a 30-day flatness over ~14 days of retention.
- **A fill whose `liquidity` is neither `maker` nor `taker` aborts the cost half.** `str()` on the pinned library's enum yields `"1"`, not `"MAKER"` — this repo shipped exactly that bug into the forensic ledger once. A skewed blend is worse than no blend.
- **A `fee_currency` other than EUR aborts** rather than summing mixed units.
- The venue-minimums snapshot stamp is quoted in the output, as `accum-replay` does: *"these floors move, so a band quoted from an older table is stale, not conservative."*

### D6 — proving it before its input exists

Constructed fixtures pin the arithmetic — known fills to known drift, known blend — with each refusal in D5 constructed and seen to trip.

Then the **true-positive**, which is what makes this more than fixtures: `--simulated-fills` takes `accumulation_payload`'s simulated placements as the fill source, so the reader runs end-to-end over the **256 real journal cycles** available today and emits a real-shaped number before rung 1 funds anything. Without it an always-zero or always-refusing report ships green, and its first real invocation would be inside the decision window it exists to inform.

The simulated source is explicitly **not** a substitute for the real one: it exercises the pipeline, not the measurement. The report labels any run using it.

### D7 — the surfaces that move with it

- **`README.md` `## Usage`** — a new subcommand is documented in the same change (`readme-usage.md`).
- **`infra/runbooks/engine.md`'s sleeve-composition alert, step 3** — it currently tells the operator to re-derive *"the model-consistency band the gate compares realized performance against"* and names only `accum-replay`, which is the **floor** half. Once the realized half exists that step sends someone to half the comparison; it gains the second command.
- **A `## engine-tracking-report — PROCEDURE` section is deliberately NOT written here.** The procedure that uses this instrument is rung 3's go/no-go, which has not run and is not this spec's scope; documenting it now would describe something nobody can execute. It is owed by rung 3.
- The decisions-log entry (phase 6) records D2's and D4's choices.

## Verification

- Each D5 refusal constructed and seen to trip, and a healthy production-shaped input that must pass — both halves, per the guard-proving rule.
- The floor figures the report quotes match `accum-replay`'s for the same window and NAV, asserted rather than assumed: one implementation, two callers.
- A rung-2-labelled week is proven excluded from the verdict by a constructed case, not by reading the code.
- Partial ISO weeks are proven excluded from every verdict and marked in the output.
- `--simulated-fills` produces a non-degenerate number over the real journal — a run that emits zero drift across 256 cycles fails the test rather than passing it.

## Out of scope

- Any scheduled/unattended execution (D2's registered follow-up).
- Applying the re-priced constant (D4).
- Rung 3's go/no-go procedure and its runbook section.
- Re-deriving the band itself — that is `accum-replay`'s job and [[T0116]]'s trigger, whose ≥3-complete-ISO-weeks basis now lives on the operating surface at `infra/runbooks/engine.md`'s sleeve-alert step 3.
