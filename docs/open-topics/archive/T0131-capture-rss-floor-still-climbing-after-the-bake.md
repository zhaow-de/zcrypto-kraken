---
status: resolved
---

# The capture RSS floor was still climbing when the bake residual was declared discharged

## Context — what

The `zcrypto-captures-rollout` skill names a residual the bake window cannot catch: a memory leak slower than three rotation hours still passes the slope row, so both daemons are re-read against their **own** earlier samples at ~T+24 h.

That re-read was taken 2026-08-08 03:08Z for the 2026-08-05 `ccedc9dd6bf4` capture re-pin on `zcrypto-red` (T+61.6 h). It was first written up as **"no leak; residual closed"**. A pre-push review refuted that verdict, and the refutation was reproduced independently before being accepted.

The measured 6 h floor series on `zcrypto-red`, oldest → newest, **none of these windows containing the 2026-08-05 13:30Z restart**:

```
131.08 · 131.70 · 132.25 · 138.84 · 139.04 · 139.16 · 138.23 · 141.26 · 141.20   MiB
```

## Why this matters

- **The floor rose +10.12 MiB across 48 restart-free hours.** A leak raises the floor; a rotation sawtooth does not. That is the discriminator the rollout skill relies on, and applied to the whole restart-free window it reads leak-shaped.
- **The floor slope corroborates the deriv rather than contradicting it.** Floor rise is +5.06 MiB/day against a 48 h `deriv` of +5.27 MB/day — agreement to under 1 %. The original write-up dismissed the positive deriv as sawtooth phase; if that were so, it would not reproduce an independently computed floor slope this closely.
- **The "plateau" that justified discharge was 12 h of flatness inside a signal with a measured ~24 h period.** The rise is two discrete steps — +6.59 MiB landing 2026-08-06 15:20–18:20Z and +3.03 MiB landing 2026-08-07 15:20–18:20Z, the same clock band 24 h apart. The final pair (141.26 → 141.20) is the only adjacent pair in the series that agrees, and it sits in the trough between steps.
- **It is probably still benign, and that is exactly why it must be checked rather than assumed.** Step amplitude is roughly halving (6.59 → 3.03), which asymptotes near ~144 MiB — a warm-up settling on a daily cadence, not an unbounded leak. But that is a prediction from two points presented as a measurement, and the same-host precedent cuts slightly against comfort: red's own prior plateau was `144,715,776 B` (138.01 MiB, recorded 2026-08-03), and today's floor already exceeds it.
- **No urgency, and that is measured too**: 141 MiB against `zcrypto-red`'s 1 GiB container limit, at +5.3 MB/day, is roughly 166 days of headroom. This is a correctness-of-record and rollout-discipline item, not an incident.

## Findings so far

- Every figure above was measured twice — once by the reviewer, once reproduced independently — via `infra/scripts/grafana-query.py` against Grafana Cloud, plus host-direct `/metrics` on both capture hosts.
- `RestartCount` is 0 on both hosts; `zcrypto-red` runs `ccedc9dd6bf4`, `StartedAt` 2026-08-05T13:30:00Z.
- **The primary is a control here, not a subject** — its capture was deliberately left on `99faf16514e3` (only its engine took `ccedc9dd6bf4`), verified from the container. Its own floor is flat: 146.18 → 145.46 → 145.31 MiB, 24 h slope −0.55 MB/day.
- **Two method errors from the first write-up, worth not repeating.** (1) "The oldest window straddles the restart" is true of the 24 h-bucket floor reading 112.7 MiB, but **not** of the 24 h or 48 h `deriv` windows — the restart precedes the 48 h window by 13 h 44 m, so warm-up cannot explain those slopes. (2) The primary's 7-day range of 145.31–172.56 MiB was cited as a normal working envelope; it is not, it spans a **regime shift** (a −19.3 MiB step landing 2026-08-05 21:20–08-06 03:20Z). Within-regime amplitude is ~8–10 MiB, so the envelope argument overstated what "normal" covers.

## Reading taken 2026-08-08 16:13Z — strongly suggestive, deliberately NOT a discharge

2h floors over the preceding 26 h, oldest → newest: `138.23 · 140.43 · 141.32 · 141.35 · 141.34 · 141.22 · 141.39 · 141.20 · 141.32 · 141.32 · 141.39 · 141.29 · 141.27 · 141.43` MiB.

- **Step 2 is now pinned to ~2026-08-07 15:00Z** (138.23 → 140.43 → 141.32 across consecutive 2 h buckets), tighter than the 3 h band recorded above.
- **Since then: 26 h flat inside a 0.23 MiB range** (141.20–141.43). The decaying-amplitude model predicts step 3 at ~+1.5 MiB, which would put a floor near 142.8. Nothing approaches it.
- **Step 3 was due ~2026-08-08 15:00Z and has not appeared** through the window ending 16:14Z.

**Why this is still not a discharge.** The read was taken at 16:13Z — inside the step band, and two hours before this topic's own trigger. Only the last ~1 h is genuinely ambiguous (a step landing now has no full post-step window yet to raise a floor), but that is exactly the residual the trigger exists to remove, and the first verdict on this topic was wrong through precisely this kind of strong-but-early reasoning. One clean read settles it.
## Resolution

**Discharged 2026-08-08 18:26Z (T+77.0 h) — no leak. The floor settled; the third step never came.**

Step 2 is pinned to ~2026-08-07 15:00Z, so step 3 was due ~24 h later. 2 h floors across and after that band — ending 10:26 / 12:26 / 14:26 / 16:26 / **18:26Z** — read `141.39 · 141.29 · 141.27 · 141.43 · 141.37` MiB: **28 hours flat inside 0.25 MiB**, with the final window sitting entirely past the anniversary. The predicted ~+1.5 MiB step would read ~142.8, and step 2 was unmissable at this resolution (`138.23 → 140.43 → 141.32`).

Confirmed on the host: `RestartCount` 0, digest `ccedc9dd6bf4`, instantaneous 144.08 MiB against a 141.37 floor — a ~2.7 MiB sawtooth around a settled level, matching the decaying-amplitude model's predicted ~144 MiB asymptote. **13.8 % of red's 1 GiB limit.**

**The lesson this topic actually carries is about the instrument, and it failed three times.** Every wrong answer here came from a measurement window misaligned with the event it measured, never from a wrong number:

1. The original "no leak" verdict read 12 h of flat floor inside a signal with a 24 h step period — the trough, not a plateau.
2. This topic's own `ripe_when` then specified a `[6h]` read after 18:20Z. That window covers 12:20–18:20Z and **straddles** the step band, so its floor reports the pre-step value whether or not a step occurred. The rule written to prevent the error reproduced it.
3. A scheduled background watch carrying that same `[6h]` query fired at 18:25Z and returned "asymptote confirmed" — the right conclusion, reached by an instrument that could not have detected the alternative. It was discarded and re-measured.

**The rule worth keeping: a floor read must sit ENTIRELY past the event band.** A `[2h]` window after the band closes, or `[6h]` only 6 h later. This generalises beyond RSS — it is the same defect as reading `count_over_time` on a burst emitter and concluding it is continuous.
## Suggested next steps

_(none — resolved. The follow-on lesson about window-vs-event alignment is recorded above and in `fleet-pins.md`, where the next person reading a floor will be standing.)_
