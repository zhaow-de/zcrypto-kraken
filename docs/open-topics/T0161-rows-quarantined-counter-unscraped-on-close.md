---
status: open
ripe_when: 'a capture converge is scheduled for its own reasons AFTER spec 00109''s — every candidate fix needs one, so this rides a window rather than opening one'
---

# The quarantined-rows counter is blind to the spill that happens as the process dies

## Context — what

`zcrypto-capture-rows-quarantined` watches `increase(zcrypto_capture_rows_quarantined_total{host=~"zcrypto|zcrypto-red"}[6h]) > 0` (`for: 15m`, warning). The counter has **two** increment sites in `cli/capture/segment_writer.py`, and they do not behave alike:

- **`_hold()`'s `flush_rows` cap branch** — the live path, reached when one unconfirmed hour piles up `flush_rows` held rows. The process keeps running, the next scrape publishes the step, and `increase()` reads it correctly. **This half of the detector works.**
- **`close()`'s held-spill loop** — the shutdown path. The increment lands in a process that is exiting. Scrapes are 60 s apart and `stop_grace_period` is set nowhere under `infra/`, so Docker's default applies and the process is normally gone before the next scrape. **A value that is never published cannot be read by any expression, absolute or windowed.**

*(Sites are named by function rather than by line: the two coordinates differ between `develop` and any branch that edits this file above `_hold()`, and citing one without its tree is how this topic's first draft went wrong.)*

Spec `00109` D3 excluded this rule from that spec's fix and **already contains the per-site analysis above**, including that the cap site is not start-correlated so D2's argument does not reach it. D3 is the authority here; this topic exists only because D3 says in terms that it registers no topic for the remaining decision.

## Why this matters

The `.held` sidecar is the quarantine for rows the oracle never corroborated. Its own alert summary says the baseline is zero and any firing is a real event. A shutdown-time spill is exactly the case an operator most wants to know about — it is the one correlated with a capture process stopping near an hour boundary, which is also when a re-pin, a converge or a crash happens.

The failure is silent in the worst direction: the rule reads healthy, so the surface asserts coverage it does not have. Same class as [[T0034]], and as the defect `00109` D2 fixed — an instrument that cannot report the thing it names.

Scope, stated so nobody over-reads this: the metric is **not** wholly blind. Cap-site spills are seen. Only the `close()` path is lost.

## Findings so far

- **There is no CRITICAL log line to promote to a detector, and any plan that assumes one is unbuildable.** Measured: `grep -rni critical cli/capture/` returns exactly one hit — a comment in `command.py` about the Loki rule's `level=~"ERROR|CRITICAL"` selector — and `segment_writer.py` contains none. `_write_part` is the sole writer of a `.held` file, and its only logger call is a `logger.exception` on the **failure** branch, which fires when the spill does not happen. A successful spill emits nothing at any level. `00109` D3 states this outright.
- `stop_grace_period` does not appear anywhere under `infra/` — checked, not assumed. Nothing widens the shutdown window today.
- Scrape interval is 60 s (`infra/ansible/roles/capture/files/config.alloy`).
- Registered 2026-09-02 during `00109`'s execution. **Its first draft claimed a converge-free fix existed; pre-push review falsified that, and the correction is recorded below rather than quietly swapped in.**

## Suggested next steps

**All three candidate fixes require a capture converge. There is no cheap option, and the one that looks cheapest is the broadest.**

- **Emit a log line on the `.held` spill, then rule that the detector.** This is *not* a Grafana-only change: the emission does not exist, so it means editing `segment_writer.py` — writer code, a new image, a re-pin behind the secondary bake — **plus** the rule push and the runbook edit. Broadest of the three.
- **Persist the count across restart** so the step survives the process that made it. Owes a capture converge.
- **Widen the shutdown grace** so the final scrape lands. Smallest code change, but a timing bet against a 60 s scrape rather than a fix. Owes a capture converge.

**Do not push a Loki rule ahead of the emission.** A rule matching a line nothing emits can never fire, and `fleet-deploys.md` forbids pruning the superseded rule until the replacement's first sample is read BY VALUE — a sample that never arrives. The operator then either stalls or prunes anyway and loses the metric-based rule too. That trap has no exit once entered.

**None of these may ride `00109`'s own capture converge**, which carries no design for this.

**To decide against evidence rather than reasoning**, on each capture host:

```
ssh zcrypto      'sudo find /var/lib/zcrypto-capture -name "*.held*.parquet" -printf "%T@ %TF %TT %p\n" | sort -n | tail -20'
ssh zcrypto-red  'same command'
```

Then read `zcrypto_capture_rows_quarantined_total{host=~"zcrypto|zcrypto-red"}` by value (`infra/scripts/grafana-query.py`), and compare each `.held` file's mtime against the capture container's stop times (`docker inspect --format '{{.State.FinishedAt}}' zcrypto-capture`, scoped — never an unscoped inspect on this fleet). A `.held` file written within the shutdown window whose rows never appear in the counter is a `close()`-path spill the metric lost, and is the direct evidence. If production has never produced one, that is itself an argument for the smallest fix.
