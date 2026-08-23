# 00091 — the tracking-error report, cost recalibration, ledger-export ingestion, and the tracking-error trip

The fourth of [[T0018]]'s five-spec decomposition to be written, at the serial that decomposition reserved for it — `00088`, `00089` and `00090` all landed at their own reserved serials, so `00091` is a held gap rather than the next free number. (`00094` is *not* one of the five; it was slotted ahead of `00090` by the 2026-08-14 sequencing ruling.)

**Three components, three risk tiers — stated up front because they do not ship alike.** [[T0018]] registers all three to this serial and an earlier draft of this spec carried only the first, silently dropping the other two:

| # | component | risk | ships via |
| --- | --- | --- | --- |
| A | the weekly tracking-error report + cost recalibration | **none** — read-only, writes nothing | merge; no converge, no bake |
| B | automated Kraken ledger-export ingestion | **none** — read-only over an owner-supplied export | merge; no converge, no bake |
| C | the tracking-error **kill-switch trip** | **live trade path** — latches the kill file, cancels resting orders, refuses every further intent, pages | engine converge behind the canary gate |

A and B are evidence for a decision. **C is not**: it is an automatic trip in the executor, and per `spec-plan-locations.md` its review floor is Fable and its deploy is a canary-gated engine converge. Conflating them is how a read-only framing smuggles a mutating guard onto the live path.

## The measured basis

Verified against the repo, 2026-08-22:

- **The edge is already pinned, so the report's shape is mostly determined, not open.** [[T0116]]'s amendment states it as *"the p95 of the per-cycle drift floor against that week's mean drift, over ≥3 COMPLETE ISO weeks"*. A review of its first draft found it named no edge at all, and on the very data the band was derived from a median edge fails two of four weeks while a p95 edge passes all four — so the choice flips the gate, and it is not this spec's to revisit.
- **The floor half already exists and is validated.** `accumulation_payload` (spec `00081`) computes per-cycle drift at each NAV. Re-run 2026-08-22 it reproduces [[T0118]]'s registered curve to within a decimal on every cell **except W31**, whose mean moves 32.4 → 31.1 because this window's two extra cycles complete that week (136 cycles against 138). The conclusion — the floor half is validated, do not re-derive it — survives that exception; the claim of an exact match does not. A second implementation would be a second thing to be wrong.
- **The realized half has a data source.** Exec-ledger `fill` events carry `qty`, `px`, `fee`, `fee_currency`, **`liquidity`** (`maker`/`taker`), `trade_id` and `at` — `executor.py::_fill_payload`, shared by the in-flight and detached paths so an adopted order's fill is recorded in identical terms.
- **The cost half builds the instrument that closes a named open item; the number itself is owed at first fills.** Zero fills exist today, so this branch ships a reader that can only answer *no euro-denominated fills in the window*. The instrument is the deliverable; the measurement is discharged when rung 1 produces fills, and [[T0090]]'s next-step records exactly that split rather than reading as closed. [[T0090]]'s third next-step: *"Derive the realized maker/taker blend from real fills and re-price against it. Until then the quoted baseline is the **range 0.51–0.91 conditional**, not a point."*
- **Rung 2's tracking error is NOT a gate input** — ratified with the ladder's shape: concentration fixes entry placeability, not delta placeability, so the number measures something adjacent to the deployable.
- **No fills exist yet.** No order has ever been submitted; `exec_armed` renders false. Everything below is built before its input exists, which is the central risk this spec designs against.

## Decisions

### D1 — one reader, two aggregations

Both outputs land in one spec and one pass over the journal. They share the fill ledger as input and rung 3's go/no-go inherits both; splitting them would mean two passes over one ledger and two specs whose only difference is which column they aggregate.

The floor half **reuses `accumulation_payload` rather than re-deriving it**, for the reason above.

### D2 — a workstation command, and no timer at all

`zcrypto engine tracking-report`, reading the NAS-pulled engine journal exactly as `accum-replay` does (`--journal-dir`, `--since`, `--until`, `--nav` repeatable, `--json`). No timer, no unit, no ops converge, no keep-regex, no alert-rule question, **no canary bake owed** — it ships when it merges. The cadence is weekly and attended, and the consumer is a human reading a decision.

**No scheduled run, and the missed-week risk is closed by procedure rather than parked.** The owner chose "command now, timer later": a weekly attended reading whose consumer is a human does not earn an ops unit, a converge, telemetry, an alert-rule decision and a regeneration story. The cost of that choice is that nothing notices a week nobody ran it for — no artifact is missing, because none was ever expected. So the cadence becomes a **step in the probe-window procedure** (D7), where the operator already is, instead of automation nobody built. The timer is dropped, not deferred: if the manual cadence ever proves unreliable, the evidence for building it will be a week the procedure recorded as unread.

### D3 — the weekly table, and the realized half measured in the SAME quantity as the floor

Per **complete ISO week**: mean realized drift (bps of NAV), the floor's p95 over those cycles, and the verdict. Partial weeks print marked and are excluded from every verdict; the gate needs ≥3 complete weeks.

**The realized half must be the same quantity the floor is, and an earlier draft of this spec got that wrong.** It defined realized `held` as `Σ qty·px` — EUR at fill price — which `accumulation_payload`'s own docstring names as the anti-pattern by name: *"Held state is carried in BASE UNITS, never EUR (spec D4) … A EUR-denominated held state would instead compare a price-stale `held` against a freshly priced `target`, and would report zero drift across a pure price move that placed no order."* Four properties are therefore load-bearing, and each fixes a way the two halves would otherwise merely share a name:

- **Base units, never EUR.** Realized `held` accumulates **signed base quantity** — `+qty` on a `buy`, `−qty` on a `sell`, the side read from the row's `intent["side"]`. It is marked to the same close the floor marks to, never to the fill price.
- **Base-keyed, never symbol-keyed — and the two `/BTC` legs are EXCLUDED, not contracted.** `target_qty` is keyed `BTC`; a fill's `intent["symbol"]` is a basket symbol. An earlier draft said the realized side "contracts symbols to base keys through the same `select_model_inputs` contraction" — that is false about that function: `cycle._MODEL_SYMBOLS` is `tuple(s for s in BASKET if s.endswith("/EUR"))`, so `select_model_inputs` **drops** `ETH/BTC` and `SOL/BTC` rather than contracting them, and the model's targets are ten EUR bases. Folding an `ETH/BTC` fill into `held["ETH"]` would therefore inflate held against a target that never included it. Fills on the two `/BTC` legs are excluded from the drift half and counted in the output, so their absence is visible rather than silent.
- **Post-decision attribution.** The floor measures drift *after* the placement decision — *"a placing asset contributes exactly 0"*. The realized side attributes a fill to the **cycle whose decision produced it** — matched through the fill's own submitted row, whose boundary is recorded — never by comparing the fill's wall-clock stamp against a boundary, which lands a fill arriving minutes after boundary N on boundary N+1.
- **A pure price move DOES move realized drift, and that is the signal rather than an artifact.** NAV is held constant by design, so a base-keyed target moves inversely with price while a base-keyed held does not. The floor half absorbs that by re-placing every cycle; the realized half absorbs it only when the engine actually places. So an engine that keeps trading tracks the target, and an engine that stops accumulates drift without bound — which is precisely the divergence the whole comparison exists to detect. An earlier draft of this spec claimed a price move "re-prices target AND held together"; on a one-fill fixture at NAV 1000 with the close moving 50000 → 60000, target is 0.01667 BTC against held 0.02, i.e. 200 EUR and **2000 bps** of drift. The claim was false and the corrected behaviour is the wanted one.
- **One key space per run.** Schema 1 records are base-keyed and schema 2 are symbol-keyed; a window straddling the bump mixes them. The reader contracts both to base keys, and a run whose records span the bump says so in its output.

**Each week is labelled with the rung its cycles came from, and rung-2 weeks are marked measured-but-not-gate-eligible.** Averaging them into a verdict would corrupt the exact number the go/no-go reads, against a ratified decision. Nothing in the journal records a rung, so the boundary is supplied by the operator and defaults to *nothing is gate-eligible* — the safe direction.

### D4 — the cost basis is PROPOSED, never applied

The report emits the realized maker share, the blended per-side cost it implies, the registered constant, and the proposal — with `n`, the maker/taker split, and the per-fill realized cost's **min/median/max** — a spread, not a standard deviation, because a handful of probe-scale fills cannot support a parametric dispersion and quoting one would dress up a sample of tens. It writes nothing.

**The constant is `cli/portfolio/crossfreq_system.py`'s `CrossfreqSystemConfig.fee_per_side = 0.0040` — the fee term alone.** It is NOT `builder.spot_fee_per_side`, which is fed `cost_per_side` (`fee_per_side + spread_per_side = 0.0060`) at the builder seam under an explicit `# DO NOT "correct" this` comment. Proposing a realized fee-only rate against the 0.0060 sum would silently delete the `spread_per_side = 0.0020` term that T0090's ruling exists to keep separate. The report imports the current value rather than writing a literal, reports the proposal against the fee term only, and states that the spread term is unchanged and why.

`fee_per_side` is an input registry record 47 was validated under. Re-pricing it changes what the deployable IS, which is re-ratification territory, not a side effect of reading a number — and a go/no-go that reads a constant which moved under it is reading two things at once.

### D5 — it fails closed rather than reporting a number it cannot stand behind

- **A week with no fills reads _no data_, never zero drift.** An empty result is not an absent event; this repo has already booked a `[30d]` selector over a series that had not lived that long ([[T0129]]), and made the same error again on 2026-08-22 quoting a 30-day flatness over ~14 days of retention.
- **`NO_LIQUIDITY_SIDE` is counted but unpriced, never an abort.** It is a name the venue's own enum yields, so a fill carrying it is a real fill with an unknown side: it stays in the drift half, leaves the blend, and appears in the output. Only a value the enum cannot name at all — `"1"`, the shipped defect — aborts.
- **A fill whose `liquidity` is not a name the venue's enum yields aborts the RUN.** The ledger stores `_liquidity(...)`, which is the venue's NAME — **`"MAKER"`/`"TAKER"`, uppercase** — precisely because `str()` on the pinned library's `IntFlag` yields `"1"`, a bug this repo shipped into the forensic ledger once. The reader matches the stored casing; a lowercase-only match would abort every real fill while every lowercase fixture passed, which is the same always-refusing-ships-green failure D6 exists to prevent.
- **A non-EUR `fee_currency` disables the COST half only, and the report says so** — it does not abort the run. `ETH/BTC` and `SOL/BTC` fills carry BTC-denominated fees legitimately (the engine's own `_fee_eur` returns `None` for them rather than raising), and taking the whole report down over a leg that is structurally at zero target would be a refusal out of proportion to the doubt.
- **"EUR" is not the only spelling of the euro.** The executor carries `_EUR_CODES = ("EUR", "ZEUR")` — Kraken's adapter surfaces spell it `EUR`, its asset/instrument-quote surfaces `ZEUR`. The reader IMPORTS that constant rather than testing `== "EUR"`: a hand-written literal would silently drop every `ZEUR` fill out of the cost half as though it were a foreign currency, which is the quiet half of the same failure the bullet above describes.
- The venue-minimums snapshot stamp is quoted in the output, as `accum-replay` does: *"these floors move, so a band quoted from an older table is stale, not conservative."*

### D6 — proving it before its input exists

Constructed fixtures pin the arithmetic — known fills to known drift, known blend — with each refusal in D5 constructed and seen to trip.

Then the **true-positive**, which is what makes this more than fixtures: `--simulated-fills` takes `accumulation_payload`'s simulated placements as the fill source, so the reader runs end-to-end over the **258 real journal cycles** available today and emits a real-shaped number before rung 1 funds anything. Without it an always-zero or always-refusing report ships green, and its first real invocation would be inside the decision window it exists to inform.

The simulated source is explicitly **not** a substitute for the real one: it exercises the pipeline, not the measurement. The report labels any run using it.

### D7 — the surfaces that move with it

- **`README.md` `## Usage`** — a new subcommand is documented in the same change (`readme-usage.md`).
- **`infra/runbooks/engine.md`'s sleeve-composition alert, step 3** — it currently tells the operator to re-derive *"the model-consistency band the gate compares realized performance against"* and names only `accum-replay`, which is the **floor** half. Once the realized half exists that step sends someone to half the comparison; it gains the second command.
- **A `## engine-tracking-report — PROCEDURE` section is deliberately NOT written here.** The procedure that uses this instrument is rung 3's go/no-go, which has not run and is not this spec's scope; documenting it now would describe something nobody can execute. It is owed by rung 3.
- **`infra/runbooks/engine.md`'s `## engine-probe-window — PROCEDURE`** gains the weekly reading as a numbered step — the surface that makes D2's dropped timer safe. It names the command, the ISO week to pass, and what an unproducible week means (a refusal to record, never a zero to shrug at).
- **Component C's surfaces**, which A and B do not have: `cli/config.py`'s parsed `tracking_band_bps` key (a frozen dataclass with a hand-written per-key parser — a knob needs a field, a parse arm and refusals, not a `.get()`), the trip's rendered state in the capture role's keep-regex, a dashboard target, and a runbook section — a trip an operator can meet at 3am owes one, unlike the report. **No new alert rule**: a latched trip already pages via `zcrypto-engine-exec-kill-tripped`, and a second rule would double-page one event. That is a decision, recorded here so its absence does not read as an oversight.
- **The cycle record's schema widening (D9)** carries its own deploy discipline: every reader converges before the writer, and the converge runs `--tags capture,engine` because the keep-regex lives in the capture role.
- The decisions-log entry (phase 6) records D2's, D4's, D9's and D10's choices.

### D8 — automated Kraken ledger-export ingestion (component B)

[[T0018]]: *"Rung 1's rollover rows are read by hand from the owner's ledger export during the attended window; the standing reader is `00091`'s."* Read-only, over a file the owner exports; it replaces a manual read, not an automated fetch.

- **It reads an export the owner supplies — it does not call Kraken.** No API key, no credential surface, no scheduled fetch. The probe checklist already has the owner exporting the ledger; this reads that artifact.
- **Rollover rows are the load-bearing content**, because they are the one cost the fill events cannot carry: a margin position's rollover fee is charged by the venue against the position, not against a fill, so a cost basis built from fills alone omits it. That is why this component belongs with the cost recalibration rather than in a spec of its own — it closes a hole in D4's number.
- **It reconciles against the ledger, and an unmatched row fails the RECONCILIATION, not the run.** Every export row it consumes must match a journaled fill by `trade_id`, or be a rollover row. A row matching nothing means the account did something the engine's record does not know about — the one thing this component exists to detect — so the reconciliation block reports `FAILED` and names every unmatched id, and the cost half refuses to publish a blend built over a ledger it could not reconcile. The drift half and the rest of the report still print: taking the whole instrument down would deny the operator the very numbers they need to investigate, which is the same disproportion D5 rejects. Exit code is non-zero so a script cannot read a failed reconciliation as a pass.
- **A rollover row is only a euro cost when its `asset` is a euro.** Filter the row's asset against the same `_EUR_CODES` the fill reader uses; an unfiltered sum lands a BTC-denominated rollover in a EUR total.
- The verify-by-outcome step of the probe window gains the reconciled count, so a hand-read and the reader's read are compared once while both exist.

### D9 — the cycle artifact journals the closes it used (component C's precondition)

**A cold review measured the alternative and it is not shippable: reconstructing one ISO week of cycles costs 73 s.** Timed on the real journal — `accum-replay` over 2026-08-10..16, 42 cycles, ~91 MB — because the only producer of `CycleStages` is `replay_stages`, which re-runs snapshot reads, content-hash verification and the whole builder per cycle. Inside the executor at a boundary that blocks the event loop for over a minute with orders possibly resting: fills and cancels go unprocessed, and the cycle's `completed_at` is pushed toward the `[B, B+30 min]` bound that is itself a gate-streak condition.

**So the fix is to stop reconstructing.** The cycle artifact already carries `final_targets`; it does **not** carry the closes those targets were computed against, and closes are the only missing term. Journaling them makes realized drift computable from the journal alone — no parquet read, no builder replay, for either component.

- **The record lives in `journal.py`, not `cycle.py`.** `CycleRecord` is an eight-field dataclass whose `to_json`/`from_json` write and read explicit key lists, and `validate_record` is schema-aware — so nothing done in `cycle.py` alone can put a key into the artifact. The widening is a `journal.py` change; `cycle.run_cycle` merely passes the value, which it already holds as `model_h4` (base-keyed, the ten EUR legs, the identical construction `replay_stages` uses for `CycleStages.closes` — **not** the pair-keyed `h4_closes`).
- **`cycle-<HH>.json` gains `closes`** — the base-keyed closes that cycle actually used, ten floats. Small, and an INPUT rather than a derived number: a journaled derivative would rot against the code that derived it, while a journaled input stays true.
- **Readers converge before the writer** (`capture-deploys.md`): old code meeting the first widened record must not misread it. The reader tolerates the key's absence by construction, which is also what makes the 258 existing artifacts still readable.
- **Component A always replays** — it runs on a workstation where 73 s is a cost, not a hazard, and a second code path would be a second thing to be wrong for no gain. The journaled closes exist for component C, which cannot replay. So there is no fallback and no path label to report.
- **Component C refuses any week whose cycles lack journaled closes** — fail closed. It cannot fall back to replay, because the whole point is that replay does not belong on the trade path.

### D10 — the tracking-error kill-switch trip (component C, live trade path)

[[T0018]]: *"Drawdown trips stay with `00092` and **tracking-error trips with `00091`**, where their inputs are built."* An automatic trip in the executor: it latches the kill file, cancels resting orders, refuses every further intent, and pages.

**The call site is the 4-hourly boundary alert, not the 5-second tick.** Three review rounds died on this and each assumed the hook had to live in `on_timer`, where every `_evaluate` call sits behind an operator-written `probe-plan.json` — so the trip could only fire while a plan existed, i.e. never in the stopped-placing state it exists to catch. `node.ShadowStrategy._on_cycle_alert` has no such dependency: nothing in that chain reads the plan file, `self._plan`, or the venue. It runs six times a day, on the cadence this decision already required, and `on_timer` is not edited at all.

**It carries NO durable state.** The most recently closed ISO week is re-derived from immutable journal artifacts at every boundary; idempotence comes from the kill file and `_kill_tripped`, never from a marker. Three candidate designs died on state — a stale checkpoint's wrong `held` is self-reinforcing, and a crash between trip and write corrupts it. Re-deriving is also strictly *more* correct: `update_submitted_row` files a fill under the boundary its ORDER was filed under, so a fill can land in an already-scored boundary days later; a checkpoint loses it permanently, a re-derivation folds it in at the next boundary.

**The cost is measured, not estimated.** All 66 exec records read in 40 ms and 260 cycle records in 0.19 s (≤0.6 s total, ~0.27 s each projected at the 60-day steady state), against `run_cycle`'s own 9.90 s median / 14.60 s max and **1683.9 s of headroom** to the `[B, B+30 min]` bound that is a gate-streak condition. Six times a day, that is not a cost. Both components therefore call the SAME `realized_drift` — not a private loop — so the number a human bands cannot drift from the number the engine trips on, and the trip inherits its signed-fill rule, its NAV validation and its orphan refusal.

**Eligibility is the journaled `level == "full"`, per boundary — not the live config.** This is the largest spurious-trip vector found: `restart_hold` is written unconditionally at every engine start and cleared only by hand, so a week spent under it reads as fully armed while the engine never traded — `held` frozen, targets moving, kill file latched on a healthy engine. `level` is one already-journaled field that reduces arm-file, kill-file, restart-hold, config and venue status together.

- **Complete weeks only** (42 boundaries), and a week **straddling the first fill is refused** — the same rule, and the same reason, as D3's partial weeks.
- **A week whose targets miss a model leg, or whose records lack journaled closes, is refused rather than guessed** — an unchecked read of nine perfectly-tracked legs measures ~8 bps and passes while the tenth carries all the drift.
- **`held` is cumulative from the first fill ever, so a PRUNED journal head is refused, not scored.** The engine journal is pruned whole day-dirs at a 60-day retention, and a review constructed the consequence: with the opening fill's boundaries removed, the healthy fixture read **298.4 bps and latched the kill file**. The trip therefore writes a **write-once birth record** (`exec/first-fill`) at the series' start and refuses whenever the journal's earliest fill disagrees with it. A second review then constructed a resurrection — the mint was gated on the file's absence, so a *lost* record over a quiet-cut pruned head re-minted a wrong birth and latched again — closed by a **7-day mint recency bound**: on the healthy path the record lands one boundary after the first fill, so any mint dating a fill weeks old is a reconstruction rather than a birth, and becomes a loud refusal.
- **The residual is named and not closed.** Once the day holding the first fill ages past the retention, the trip refuses **permanently** — those fills are not on the host and no operator action recovers them. The recency bound converts wrong-birth cases into refusals rather than false kills; it does not extend the trip's life. Defeating it now takes four coincidences (fill early, go quiet for months, head pruned, record lost, fill again recently, and the cut landing on a quiet boundary). The class answer is journalling the position beside `closes`, which this spec does not do.
- **Any read failure leaves the trip un-evaluated and logged.** `on_boundary` cannot raise: it sits in a `finally` and carries a total `except Exception`, so it can neither replace an in-flight exception nor break the alert chain.
- **It ships disarmed** (`tracking_band_bps` unset, a parsed config key with `isfinite` and `> 0` refusals) and **renders its state** — a gauge in the capture keep-regex and a dashboard target, so disarmed is confirmable on the board rather than inferred from an absence. It is refused entirely while `exec_armed` is false.
- **The defect is constructed and seen to trip, both directions, AND the call site is proven** — a test drives the boundary alert with no plan file and asserts the kill file appears, because a guard nothing calls ships green exactly as an always-refusing one does.
- **It ships on the live trade path.** Fable review floor; canary-gated converge; `--tags capture,engine`, readers before writer. The branch also changes `command.py`, `cycle.py` and `journal.py`, inside the NAS gate-export's replay closure, so that leg replays at its measured **2490 s** cold cost.

**One condition is unresolved and is owed as a verify-by-outcome step, not a footnote.** All 66 live exec records read `level: "none"` (`reasons: [config_not_armed, arm_file_absent, restart_hold]`) — the engine has never traded. If restart-hold is left set through armed windows, or venue status blips at any boundary, the trip is **structurally inert even when armed**. It resolves at the first armed probe window by counting `level == "full"` across that week's 42 exec records; a count below 42 means either the hold-clearing step or the eligibility rule must change *before* the band is set. That count is a step in the probe-window procedure (D7).

## Verification

- Each D5 refusal constructed and seen to trip, and a healthy production-shaped input that must pass — both halves, per the guard-proving rule.
- A rung-2-labelled week is proven excluded from the verdict by a constructed case, not by reading the code.
- Partial ISO weeks are proven excluded from every verdict and marked in the output.
- `--simulated-fills` produces a non-degenerate number over the real journal — a run that emits zero drift across 258 cycles fails the test rather than passing it.
- The floor figures the report quotes match `accum-replay`'s for the same window and NAV, **asserted rather than assumed** — the two paths genuinely differ (`accum-replay` goes through `accumulation_report` with its own NAV list and stamp), so the assertion is not redundant.
- A buy-then-sell round trip returns `held` to zero — the signed-quantity rule proven, not just stated.
- A week with fills followed by a week with none: the second week carries a NUMBER and is tripable, proving the "no data" rule is about the series never starting, not about a quiet week.
- The trip's CALL SITE proven by driving the executor through a boundary tick — not only the method called directly.
- An armed band plus a false `exec_armed` does not trip.

## Out of scope

- Applying the re-priced constant (D4) — the proposal is the deliverable.
- Rung 3's go/no-go procedure and its runbook section, which rung 3 owes.
- **Re-deriving the band itself.** That is `accum-replay`'s job. Its trigger has already **fired** — the 2026-08-22 sleeve reversal moved the p95 floor 115.7 → 148.1 bps on a like-for-like replay — and the obligation now lives on the **operating surface**, `infra/runbooks/engine.md`'s sleeve-alert step 3, with the ≥3-complete-ISO-weeks basis and the flat-start trap. It is deliberately NOT parked on [[T0116]], which is `status: resolved` and archived: a live obligation cannot be owed by a closed topic.
- **A systemd timer for component A — consciously dropped, not deferred.** D2 carries the reasoning and the procedure step that replaces it; the report itself is unchanged either way, since it reads a pulled journal offline and a retrospective run for a past week produces the same numbers a timely one would. What a missed week loses is the *reading*, and a reading is what a procedure step compels.
