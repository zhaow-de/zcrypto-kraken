# Reading 9 — the engine's execution cost: its maker-first ladder replayed at the deployable's cycle boundaries over the captured book

Iteration `iter-199`, topic [T0214](../open-topics/T0214-cost-basis-re-priced-at-rung-2.md), beside [T0122](../open-topics/T0122-ongoing-register-kill-criteria.md). A design in two parts, both pre-registered by this spec's sha256 before either exists: a frozen derived dataset — the engine's order ladder replayed against the captured depth-100 book and trades at the instants the deployable trades — and a no-slot reading over it of what a side costs, against the registered 0.006. No hypothesis, no bar, no verdict, no slot. Serials: iter-199 and 00153 are minted past iter-198 and 00152, which the branch `research/iter-198-deployable-revalidation` holds unmerged; that branch merges first.

## The measured basis

Measured 2026-10-29 on `zcrypto-ops`, the workstation, by the controller.

- **The engine's `execute` intent** (`cli/engine/executor.py`): `_limit_price` joins the touch — a buy at the bid, a sell at the ask — as a post-only GTC order; `_reprice` runs only on the venue's post-only rejection or its accept-then-cancel ("Two callers: the venue's synchronous post-only rejection and its accept-then-cancel"), never on a touch that moves away, so the order rests at its first price; `_TIME_BOX` is 15 minutes, after which `_fallback` sends at most `_MAX_IOC_ATTEMPTS` 3 limit-IOC orders "at the opposite touch, each sized to what is still owed", each bounded by `_ACK_WAIT` 30 s, and a remainder after the third ends `unfilled`.
- **The C1 fill model** (`cli/panel/fills.py`, spec 00151 D2) posts every 15 s at the touch and cancels an order once its side's best quote stands a tick away for 5 s (`tick_cancel`, `CANCEL_AFTER_S` 5): its fill rate within 900 s is a floor on the engine's unchased order's, never the engine's own. Reading 8's unconditioned fill rates, 0.25 %–16.6 % of posts within 900 s, are that floor. Its fill rule — `apply_trade`, the queue-ahead cap in `tick_cancel`, `post_orders`'s sizes at the touch — is the one this reading reuses unchanged.
- **Rung 2's own fills**: entry day 2026-10-05's counters "filled 9 … fills maker 10, taker 0" (`docs/reference/rung2-box/days.md`), every live fill so far a maker's and far too few to price a blend; T0214's trigger asks for 30.
- **The fee schedule and the registered basis**: tier-1 maker 0.0040 a side and taker 0.0080 (master plan §2); the registered 0.006 a side is `fee_per_side` 0.0040 plus `spread_per_side` 0.0020 (`cli/research/subjects.py`'s `_RECORD44_CONFIG`).
- **When the deployable trades**: at its cycle boundaries, 00, 04, 08, 12, 16 and 20Z; the 12Z cycle's records were journaled at 12:01:42Z–12:02:05Z on every rung-2 box day the record reads (`docs/reference/rung2-box/days.md` on `records/rung2-week-4`: 9 days at 12:01:42Z, 7 at 12:01:43Z, 1 at 12:02:05Z), and a cycle's plan starts after its record.
- **The seed**: the panel tree `/mnt/zhao-crypto/l2-panel` holds each hour's `<HH>.state.json`, the end-of-hour book `seed_book` loads (`cli/panel/fills.py`), as the C1 production read it over the span below.
- **The replay's cost**: a full captured hour of BTC/EUR in 6.6 s and of ADA/EUR in 5.5 s (spec 00151's measured basis); a ladder episode needs one boundary hour's first 1,040 s, so the span's 6,192 pair-boundaries (6 a day × 86 days × 12 pairs) cost at most about 11.4 CPU-hours at the full-hour rate, timed after the hash.

## Operating model

- **One machine, one controller.** The dataset is produced on `zcrypto-ops`, which mounts the NAS read-only, by the controller alone; it writes a new root `data/l2-ladder-<stamp>/` in the main checkout — a derivation to a new path, never a write into an existing set. The reading runs in the branch's worktree over a symlink to that frozen root. No dispatch reads `/mnt/zhao-crypto/`.
- **The processes.** One `uv run zcrypto panel ladder …` process per pair, each awaited to its exit, their outputs disjoint by pair; one `uv run zcrypto research eval --reading` process; no daemon, timer or concurrent writer of one file; the capture pipeline is not touched.
- **No trial-attempts log**: a reading spends no trial.

## The question (no hypothesis, no bar)

When the engine's maker-first ladder places a €100 or €1,000 order on a pair at a cycle boundary — posted at the touch, resting unchased for 15 minutes, then crossing at the opposite touch — how often does it fill as a maker, and what does a side cost against the mid at the post, per pair and side, and over the ten EUR legs, against the registered 0.006?

## D1 — the pick

- **The owner's words of 2026-10-29**, verbatim: "go ahead with 1 and 2, the window from 2026-07-10 is fine" — item 2 read "Put the kept fill model to work on cost … The fill model can estimate maker fill rates and adverse selection now, for the deployable's own order sizes at its own cycle times. That gives a cost-basis estimate ahead of the live one." — then "if there is no other dependency, start item-2 in parallel".
- **Author's call — a ladder replay with the engine's semantics, never a re-read of the C1 set**, among three: (1) the ladder replay as a small frozen dataset — the engine's own order path at its own instants, the C1 fill rule unchanged. Chosen. (2) A re-read of `l2-fills-20261029T000157Z` — its away-cancel makes every fill rate a floor and every cost a ceiling, an answer about another order path. (3) Waiting for 30 live fills (T0214's trigger) — rung 2's book leaves most legs under Kraken's minimums, so the count arrives slowly.

## D2 — the instrument: the ladder replay as a frozen derived dataset

- **The producer**, `zcrypto panel ladder <primary-root> <out-root> --reconciled-root <overlay> --panel-root <panel> --pair <PAIR> --since <hour> --until <hour>` (`--until` exclusive), new, in `cli/panel/ladder.py`, reusing `cli/panel/fills.py`'s `_post` (with `post_orders` inside it), `apply_trade`, `seed_book`, its hour reads and its production mark `_mark`; the queue cap, two lines inside `tick_cancel`, is extracted into a helper `cap_queue` that `tick_cancel` and the ladder both call — a refactor that changes neither C1's behaviour, which its tests hold, nor its dataset. Like the fill producer, the ladder producer marks its out root in production and refuses an out root holding its `manifest.json`.
- **An episode** per pair at each cycle boundary `B` of the span: the book seeded from the panel's state of the hour before `B` (`seed_book`), hour `B`'s book messages and trades replayed second by second as `simulate_hour` replays them; at `B + 120 s`, after the cycle's record and before its plan's orders, four orders posted at the touch through `_post` — two sides, the C1 rungs €100 and €1,000 of the quote, each joining the back of the queue — skipped and counted as `_post` skips and counts them (a book stale past 30 s, or one-sided).
- **The fill rule**: spec 00151 D2's, unchanged — `apply_trade` for every print up to each second, the queue ahead capped at the level's resting quantity as the second before left it (`cap_queue`) — **with no away-cancel**: an order rests at its first price until it fills or until `post + 900 s`, the time box.
- **The fallback leg**: an order unfilled at `post + 900 s` is recorded with the opposite touch at that second — its price and resting quantity — and the mid at that second; its fallback is priced at that touch, the first IOC. An order larger than the touch's quantity is recorded as larger; the later IOC attempts at deeper levels are not modelled, so a fallback's cost is a floor for such an order and exact for every other.
- **A row** per order: `ts` (the post), `pair`, `side` (`bid` a buy, `ask` a sell), `size` (rung 0 or 1), `price`, `our_qty`, `queue_ahead_qty`, `mid_at_post`, `spread_at_post_bps`, `filled`, `time_to_fill_s`, `fill_price`, `box_end_mid`, `box_end_touch_price`, `box_end_touch_qty`.
- **The layout**: `data/l2-ladder-<stamp>/<BASE>/<QUOTE>/<YYYY>/<MM>/<DD>.parquet` + `.sha256` (the frame's `dataset_hash`), one day per file, a run record per pair and a conformant `manifest.json`, in the forms spec 00151 D2 gives `l2-fills-<stamp>`.
- **The span and pairs**: spec 00151 D2's, 2026-08-01T00:00Z ≤ `B` < 2026-10-26T00:00Z, the twelve pairs the capture holds; a boundary hour the capture lacks is a skipped episode, counted.
- **Proven on known answers before it runs on the real set**: a synthetic hour whose prints fill the bid at its 300th second and never the ask; an order the touch moves away from and back to, filled by a later print — the case C1's rule cancels; an order unfilled at the box end, its opposite touch and quantity read at exactly `post + 900 s`; an order larger than that touch's quantity recorded as larger; a stale book skipped and counted; an episode seeded from a planted state sidecar.

## D3 — the reading: reading 9

- **Per pair × side × size**, over the span and per month window (2026-08, 2026-09, 2026-10 through the 25th): the posts; the maker share, filled by `post + 900 s`, over the posts; the median time to fill; and the cost of a side against `mid_at_post`, signed against the order, in return units: a maker fill `s·(fill_price − mid_at_post)/mid_at_post + 0.0040`, a fallback `s·(box_end_touch_price − mid_at_post)/mid_at_post + 0.0080`, `s` +1 for a buy and −1 for a sell; the mean cost, and its 95 % interval from `cli/validation/bootstrap.py`'s `bootstrap_ci` over the posts in boundary order, mean block 6 (one day), 2,000 resamples, seed 42; the share of fallbacks larger than their touch.
- **The blend**: per size, the mean over the ten EUR legs' cost, each leg weighted equally, with its interval by the same bootstrap over the legs' per-boundary means.
- **Read against the registered 0.006 a side, never a verdict**: the reading prices; re-pricing the registered basis is T0214's decision, the owner's, as a new registry record.

## D4 — the hash rule and the order of work

- Before this spec's hash nobody runs the producer over the real archive or reads a fill, a box-end touch or a mid after a post over it; the producer and the reading are proven on synthetic hours. After the hash: the timed episodes, the production, its manifest and catalog entry, the reading's run, its entry; T0214's and T0122's findings.

## D5 — what the reading changes

- Nothing on the live path. Its figures go to T0214 beside rung 2's measured point, for the owner's re-pricing decision, and to T0122 as the expected execution error the paired live-minus-simulation harness will read against.

## Out of scope

Changing the engine's ladder or its time box; re-pricing the registered cost basis (T0214's decision); the IOC attempts past the first touch; sizes below €100 — at one post, a smaller order fills whenever a larger one does, since a fill needs the prints to meet the queue ahead and the order, so the €100 maker share bounds a smaller order's from below; any change to `cli/panel/fills.py`'s behaviour, the capture pipeline, the panel materializer or an existing dataset.
