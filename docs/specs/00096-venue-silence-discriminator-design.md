# 00096 — venue silence vs capture loss: a triage discriminator for the residual-gap counter

Resolves [[T0143]]. **Nothing here changes what `zcrypto_reconcile_residual_gap_seconds_total` books, by how much, or when.** What is added is a verdict — recorded on the ledger, exported as a parallel counter, and surfaced in the page's triage line — saying *why* the reconciler believes the fleet went dark.

## Context — venue outages are indelibly recorded as permanent capture loss

This has happened **twice**, and both are in the ledger:

| Window | Booked as `both_streams_silent` | Kraken status page |
| --- | --- | --- |
| 2026-08-06 07:01:02 → 07:18:18 | 10,588.382751 s | **Posted** — `maintenance` → `cancel_only` → `post_only` → `online` |
| 2026-08-20 07:01:04 → 07:10:14 | 6,251.35 s | **Not posted** |

Both correct by the counter's definition, and both wrong as descriptions of what happened: each was investigated after the fact and found venue-side, so nothing was lost because there was nothing to lose. (That is a retrospective human conclusion on two specific events, with Kraken's own status posting behind the first — a stronger warrant than the automatic verdict D2 introduces, which is why D5 forbids the summary from asserting it.) Two harms follow:

- **The alert teaches the wrong lesson.** `Reconciler · residual gap increased (permanent loss)` is `severity: critical` and fires on any increase at all (`> 0`, deliberately no tolerance). A venue outage paging it at top severity trains the operator to discount the one alert that must never be discounted — the [[T0135]] failure mode `00089` D2 exists to avoid, arriving from the opposite direction.
- **The denominator is corrupted, and nothing can answer it mechanically.** `continuity.py` over 2026-08-20 reports 1.88 % and FAILS its exit bar entirely on that window. Today the only way to ask "how much of our booked permanent loss was never ours?" is to read prose.

The counter is monotonic and derived by summing an append-only ledger, so those seconds can never be walked back — only explained.

## The load-bearing measurements

**Venue status alone is not the discriminator.** 2026-08-06 was posted; 2026-08-20 was not. A `SystemStatus` read — the same public endpoint `00088`'s execution gate consumes — therefore catches **one of the two**, and brief degradations routinely go unposted. That is a property of the source, not bad luck on one sample.

**Cross-host agreement catches both.** On each event the primary and the secondary — independent hosts, separate networks, separate processes — recorded the same sparse events with microsecond-identical timestamps (`07:01:04.553253` → `07:08:01.113758` on BTC/EUR on both, 2026-08-20).

That agreement is sound rather than coincidental, and the reason is verifiable in the capture writer: `cli/capture/command.py` sets `ts = _parse_ts(entry["timestamp"])` — **Kraken's own message timestamp, carried in the payload, never local receipt time.** Two hosts that receive the same message therefore record byte-identical `ts` by construction, and a host that was not receiving cannot manufacture one.

**What agreement does and does not establish.** It establishes that both hosts were connected and receiving *at those instants*, and therefore that the silence was **upstream of both hosts' write paths**. It is evidence-weighting, not proof. The one constructible shared-code failure — the canary rule makes both hosts run the same image digest by design, so a regression writing only `snapshot` rows would produce byte-identical sparse mirrors — is refused mechanically by D2a's `update` requirement. What remains is a shared Kraken-edge path failure another vantage could have captured, which our own two hosts cannot detect at all. This is precisely why the verdict never feeds the booking (D1), and why a verdict arriving right after a fleet-wide image change deserves scepticism.

## Decisions

**D1 — `residual_gap_seconds_total` books ABSENCE of data, not FAULT attribution, and the booking never changes.** Its contract is "no book data exists for this window on either mirror, and no later cycle can heal it." That was true on both events and stays true. Three reasons this is a ruling rather than a limitation: the counter has already survived one traumatic ledger correction (2026-07-14, 6261.8 → 2661.8 s) whose `resets()` guard still costs a 24 h blind spot; the failure direction is asymmetric, because *not* booking a `venue_silent`-classified window would let the shared-mode failures above go unbooked and unpaged; and the verdict is evidence-weighting (above), which must never gate a monotonic, unwalkbackable record. The mismatch is the *label* "permanent loss", and D5 fixes the label surface.

**D2 — a three-valued verdict, computed from evidence the booking block already holds.** A booked window contains zero events *by construction* — `fleet_dark_windows` runs over the union of both mirrors across all pairs — so evidence cannot come from inside one. It comes from the **interior span**: events falling *between* adjacent booked windows of the same hour, which exist precisely because some stream ticked there. Per pair, compare the two mirrors' `ts` multisets over that span:

| Interior evidence | Verdict | Reading |
| --- | --- | --- |
| Contains an **`update`**, mirrors **equal** | `venue_silent` | Both hosts were receiving the same incremental venue messages during the episode; the silence was upstream of both |
| Non-empty, mirrors **differ** | `capture_divergent` | One host missed what the other received — a capture-side finding in its own right |
| Empty, or **snapshots only** | `undetermined` | No interior evidence that the feed was live; the case cannot be distinguished |

**`venue_silent` requires at least one interior row of type `update`.** A `snapshot` is a periodic/resubscribe artifact and does not prove the feed is live; an incremental `update` mid-episode does. This closes the one constructible false-positive path (D2a). The comparison key is `(ts, type)`, so a type divergence between mirrors is a divergence like any other.

Divergence outranks agreement: one mirror missing one message is a finding that must not be masked by every other pair agreeing. Both mirrors' frames are already in hand at the booking site — the block reads `["ts", "type"]` already — so this costs no I/O.

**D2a — the snapshot-only interior is why the `update` requirement exists, and it is the only false positive we could construct.** For a window to book at all, essentially every book write on every pair must stop — the window is the intersection over the union of both mirrors — so a parser that drops *some* payload shapes leaves other messages flowing and books nothing. The false-`venue_silent` case therefore needs code that drops almost everything while letting an identical sparse subset through on both hosts, and the plausible instance is a regression that breaks update-row writing while leaving `book_snapshot` handling intact: both hosts, same image by the canary rule, writing identical sparse snapshot rows. Requiring an interior `update` refuses exactly that, mechanically. What remains uncovered — a shared upstream path failure another vantage could have captured — is named in the bounded claims and is not mechanically detectable from our own two hosts.

**D3 — `undetermined` is the default, and bracketing events never promote.** Agreement on events *before* and *after* the episode proves only that both hosts were healthy either side of it — exactly the signature of a simultaneous both-host outage that self-healed. Accepting brackets would label a real correlated capture failure `venue_silent`, the one direction this must not fail in. Only interior evidence counts. The genuinely uncovered case is a hard halt emitting nothing at all: one window, no interior, `undetermined` — and it pages exactly as today, by design.

**D4 — the verdict is durable: a ledger field and a parallel counter, never a subtraction.** The log line alone is ephemeral (finite retention), and for every future episode the ledger — the durable record — would carry no verdict at all, leaving 3am triage evidence to expire. So:

- The `both_streams_silent` record gains `verdict`, plus the evidence behind it: `interior_updates`, `interior_snapshots`, `pairs_agreeing`, `divergent_pairs`. The two row counts are recorded **separately and always**, so a `undetermined` verdict on a snapshot-only interior explains itself in the record rather than needing the classifier re-run to find out why.
- The exporter gains `zcrypto_reconcile_dark_episode_seconds_total{verdict=...}`, derived by summing the ledger exactly as every sibling counter is. Its three label values **fully partition** the `both_streams_silent` seconds, so the parts sum to the whole and the metric checks itself.
- **It is a parallel view, never a subtraction.** `residual_gap` continues to book every second; `venue_silent` ≤ `residual_gap` always. Anyone wanting "loss that was actually ours" subtracts at read time, in a query, where the judgement is revisable — not in the ledger, where it would not be.

Costs measured rather than assumed: `capture-deploys.md`'s **readers-before-writer** converge ordering is **not owed** — the only reader of `reconcile-ledger.jsonl` is `cli/archive/command.py` itself, the NAS transports it without parsing, and every read is `record.get(...)` with a default, a pattern `_booked_dark` already uses to tolerate records written before an earlier widening. No **Alloy keep-list edit** is owed either: the ops keep-list admits `zcrypto_reconcile_.*` as a prefix family. `gate_cache.py`'s replay fingerprint is untouched — `cli/archive/command.py` is measured absent from the 74-file transitive `cli.*` replay closure — so no NAS converge pays the cold gate-export replay.

**D4a — the two historical episodes book as `undetermined`, and that is the honest answer.** Their records predate the discriminator and `_decided` prevents re-deciding an already-ledgered `(pair, kind, hour, state)`, so they carry no `verdict` and the exporter counts them `undetermined`. The counter must never retroactively claim knowledge the system did not have. A useful side effect: the series is non-zero from its first scrape, so it does not trip the eagerly-registered-at-zero staleness trap.

**D5 — the alert gains a triage line; no rule is added, and the new series is excluded with a written reason.** `zcrypto-reconcile-residual-gap`'s `summary` gains the next step — read the verdict, and what each value means — with its `expr`, threshold, `for`, severity, and uid unchanged, so this is an annotation upsert with **no prune owed**. The new series gets **no rule of its own**: venue silence is not a fault and must not page, and the residual rule already owns the wake-up. The admitted-metrics guard requires every admitted series watched or excluded-with-reason; this is the exclusion, the shape `00089` D6 set for its level gauges.

The summary says the silence was upstream of both hosts — never "no data was lost", which overclaims past what agreement establishes. It is operator-facing text read on a phone with nothing open, so it carries no topic id, spec serial, or phase token (`operator-facing-text.md`, enforced by `tests/test_internal_terms_not_operator_visible.py`).

**D6 — both historical events are annotated where their numbers are read.** `docs/reference/capture-era-data-hygiene-map.md` already carries the 2026-08-06 row in exactly the right form — venue cause, gap-seconds, the reconciler's booking, and a FLAG verdict for continuity-sensitive analyses. 2026-08-20 gets its row in the same shape. The narrative is written in place, never appended as a retraction (`agent-ops.md`), and the per-event evidence belongs to the updating commit's message rather than the living doc (`docs-style.md`).

## Verification

- **The guard is unproven until the defect trips it** (`agent-ops.md`): each verdict is constructed from synthetic two-mirror frames — equal interior multisets → `venue_silent`; one event dropped from one mirror → `capture_divergent`; no interior events → `undetermined` — and the classifier is mutation-probed through `infra/scripts/mutate-probe.sh`, never a hand-rolled mutate-and-restore loop.
- **The snapshot-only interior is constructed and must read `undetermined`** — the D2a defect, built as an interior span carrying only `snapshot` rows, identical on both mirrors. A classifier that ignores `type` ships green without it.
- **A true-positive is mandatory**: a production-shaped healthy hour, with no fleet-dark window at all, must book nothing and emit no verdict, so an always-classifying implementation cannot ship green.
- **The booking is pinned as unchanged**, and this is the load-bearing regression: splitting an episode into two windows must leave `residual_seconds` identical to the single-window case, to the second.
- **The counter partitions**: for any ledger, the three label values sum to exactly the `both_streams_silent` seconds inside `residual_gap` — asserted, not assumed.
- **Replayed against both real events** — 2026-08-06 hour 07 and 2026-08-20 hour 07 — on a pulled copy, never the live capture dir. Every number reproduced from source at full precision, not quoted from this spec. **The interior rows' `type` is read, not assumed**: T0143 describes 2026-08-20's lone mid-window event as an update, and if it proves to be a snapshot the verdict is `undetermined` and the spec's central example is uncovered by its own discriminator — a finding to report, never to soften the rule around.
- The alert's post-push verification reads the rule **evaluating**, by value.

## What this does NOT do — bounded claims

- It does not detect a shared upstream path failure — one where the venue sent data that some other vantage could have captured but neither of our hosts' paths carried. Two hosts cannot see that; it needs a third, independent vantage.
- It does not prove venue silence. It records what the available evidence weighs toward, for the subset of episodes carrying interior evidence, and says `undetermined` otherwise.
- It does not change alert severity, threshold, or firing behaviour. A venue outage still pages `critical`; what changes is that triage is one field away instead of a derivation.
- It does not subtract anything from `residual_gap`, now or ever.
- It does not retroactively classify the two historical episodes (D4a), or alter the seconds already booked.

## Out of scope

- Any venue-status input to the reconciler — it catches one of the two known events, and cross-host catches both. Re-opening needs a source that demonstrably reports brief degradations.
- `continuity.py`'s exit-bar arithmetic — and **not** because a classification is missing. It takes a single positional capture `root` and never reads the reconcile ledger, so nothing built here is visible to it, and with one mirror the cross-host discriminator is unavailable in principle. More decisively, spec `00050` deliberately isolates the exit-bar report from any second source that heals gaps — its own docstring: an overlay "would otherwise let a raw-capture regression bank a 'clean' run -- exactly the defect class the bar exists to catch". A venue-fault verdict is structurally that same move, so feeding one in is refused by design rather than deferred. Stakes are bounded: T0003's bar was met and resolved 2026-07-16, so what this instrument gates today is the post-deploy truncated-hours check, which neither window touches.
