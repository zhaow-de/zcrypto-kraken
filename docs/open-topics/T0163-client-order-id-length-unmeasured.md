---
status: open
ripe_when: 'an adapter-verification row quotes a minted client order id as the venue returned it: grep -l "FIXMINT-" docs/reference/adapter-verification/*.md is non-empty'
---

# Client order id length — the probe's 18-character truncation comment contradicts its own 27-character acceptance

## Context — what

`infra/scripts/kraken-order-semantics-probe.py` mints client order ids of the shape `O-<YYYYMMDD>-<HHMMSS>-901-P6V-<seq>` — 27 characters at a one-digit sequence — and the `1.230.0`, `1.231.0` and `2.0.0rc4.dev20260825` rows in `docs/reference/adapter-verification/` record those runs passing. A comment in the same file says the probe's recovery read matches on the `-901-P6V-` infix because that infix "survives Kraken's 18-char client-order-id truncation". The infix starts at character 18, so an 18-character cut ends exactly where it begins and keeps `O-20260823-120000-`: the comment's two halves cannot both be true. The wider question is unmeasured rather than merely inconsistent — acceptance at submit does not establish what the venue STORES, and no run in this repository has ever read a client order id back from the venue.

## Why this matters

Every id shape this repository sends is sized against a limit nobody has measured. `infra/scripts/kraken-fixture-mint.py` sends 29-, 31- and 32-character ids, all longer than the only length ever observed to be accepted. If a truncation is real, two things follow silently: an id echoed back shortened no longer matches what was sent, and the probe's own crash-recovery read — keyed on an infix a cut would remove — finds nothing and reports a clean account where leftovers rest. Both failures read as success.

## Findings so far

- `infra/scripts/kraken-order-semantics-probe.py`, the `--probes 6` recovery read: the comment claiming the infix survives an 18-character truncation, above the line that matches on `PROBE_ORDER_ID_INFIX`.
- `docs/reference/adapter-verification/2.0.0rc4.dev20260825.md` and the two `1.23x` rows: probe runs passing with 27-character ids. Every `--probes 6` row on record found zero open orders, so none of them exercised the recovery match against a real leftover.
- No row in `docs/reference/adapter-verification/` records a client order id as the venue returned it; the repository holds no other measurement of the venue's handling of id length.

## Suggested next steps

- At the fixture-minter's first attended `--execute`, record in that version's `docs/reference/adapter-verification/<version>.md` row what the venue did with each 32-, 31- and 29-character id: accepted unchanged, refused, or echoed back shortened. Read the ids from Kraken's own open-orders page as well as from the adapter, and quote each id verbatim both as sent and as the venue shows it — the point is the venue's spelling, not ours, and quoting the sent id is what makes this topic's trigger readable.
- Then re-tense the probe comment to whatever that row measured, or cut it. If a truncation is real, the recovery read's infix must move inside the surviving prefix in the same change, because that read is what a crashed probe depends on.
