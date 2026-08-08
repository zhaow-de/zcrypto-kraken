---
status: open
ripe_when: **one `min_over_time(process_resident_memory_bytes{host="zcrypto-red",job="capture_app"}[2h])` read taken after 2026-08-08 18:30Z** — a 2h window, and after the step band closes, so the window sits ENTIRELY past it. **The original trigger here said "a `[6h]` read after 18:20Z" and that was wrong**: a 6h window read at 18:20 covers 12:20–18:20Z, straddling the band, so its floor still reports the pre-step value — the same window-vs-event misalignment that produced the first wrong verdict on this topic. Either a `[2h]` read after 18:30Z, or a `[6h]` read after 00:20Z, satisfies it; a `[6h]` read before 00:20Z does not
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
## Suggested next steps

- **After 2026-08-08 18:30Z**, take one `min_over_time(...[2h])` reading (see the corrected trigger above — a `[6h]` window straddles the step band unless taken after 00:20Z) on `zcrypto-red` and compare against the 141.20 MiB floor. Interpret as: **no third step** → the asymptote is confirmed, discharge the residual honestly and record it; **a third step of ~1.5 MiB** → still converging, re-read after the next daily window; **a third step of ≥3 MiB** → the residual is **not** dischargeable, and the leak question is live against `ccedc9dd6bf4` on the capture path.
- Record whichever outcome in `docs/reference/fleet-pins.md` beside the existing residual paragraph, replacing its provisional verdict.
- If a third step appears, compare against `zcrypto`'s capture on `99faf16514e3` **as a same-workload control on the old image** — a rise present on the candidate and absent on the control is the strongest available evidence that the image is implicated, since a cross-host absolute comparison remains forbidden (limits differ: primary 2 GiB, secondary 1 GiB).
