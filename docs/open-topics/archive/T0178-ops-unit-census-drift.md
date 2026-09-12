---
status: resolved
---

# Ops unit census drift — how many timers, writers and log sources, restated in file after file and agreeing with nothing

## Context — what

Several durable files state a COUNT of the units on `zcrypto-ops`: how many systemd timers the roles install, how many of those write a node-exporter textfile, and how many units' journal lines Alloy ships. The counts were written when they were true and none is re-derived when a unit is added, so they have drifted apart from the tree and from each other. Several were already wrong before the keep-alive branch that surfaced this.

## Why this matters

These are the files an operator reads when a host does not match expectations, and a count is exactly what they reconcile against `systemctl list-timers`. A file saying six where the host shows seven sends them looking for a phantom unit, or invites them to disable the extra one as unauthorised — the failure mode is acting on the document rather than doubting it. The keep-alive branch corrected instance after instance, and each review round found the next one standing, which is why this is a census rather than a fix: the instances are not discoverable from any one of them.

## Findings so far

Enumerated during the `feat/grafana-keepalive` reviews. Every line below was read from the tree, and the counts are measured from the templates rather than from the prose.

**This file demonstrated its own subject, which is its strongest evidence.** As first written it carried a stale count in its title ("stated six ways"), one in its Context ("two of them were already wrong", where the list below marks three), and one in its Why ("corrected three instances", against its own list of four) — and its index bullet carried a fourth, "six durable files" for a list spanning five files. Then the paragraph written to record those got its own members wrong, attributing the index bullet's count to this file and omitting the title. Every one was authored in the same hours as, and by the author of, the measurements below, and a review round found each. The arithmetic fix does not work even for someone who has just measured the thing; that is the case for deleting a count rather than maintaining it, and it is why the first suggested step below is the one it is.

- `infra/ansible/roles/ops/templates/alloy-compose.yaml.j2:78` — "four timers' textfiles"; six templates write into `ops_textfile_dir`. **Wrong before the keep-alive branch.**
- `infra/ansible/roles/ops/templates/alloy-compose.yaml.j2:80-81` — "the four `zcrypto-*.service` units' logs", while the journal regex on those lines names five. **Wrong before the keep-alive branch.**
- `infra/runbooks/ops-node.md:5` — "**five** fire a `Type=oneshot` unit that runs an ephemeral, digest-pinned `docker run` and then publishes a node-exporter textfile": five is right for the `docker run` half and wrong for the publishing half, which is now six. One sentence carrying two counts that have diverged.
- `docs/reference/fleet.md:34` — the row's trailing `.prom outputs under …` clause spans `grafana-watchdog`, which publishes no textfile at all. **Wrong before the keep-alive branch** — `git show e96054eb:docs/reference/fleet.md | sed -n 34p` on the pre-branch tree shows it. Only that clause is open: the unit enumeration earlier on the same line was corrected on that branch and is listed below as done. **Delivered 2026-09-10 by the fleet-contracts rewrite: the ops timers row now names which units publish a textfile (all but the watchdog); the other items above stand.**
- `infra/ops/README.md:206` — the verify-by-outcome list omits `zcrypto_grafana_keepalive_*`.
- `infra/ansible/roles/ops/templates/grafana-keepalive.timer.j2` — the schedule comment says the minute is one "no other unit on this host uses", which is broader than the check it names: it was verified against the `ops` and `access_ops` roles, not against the host's own OS timers.

Measured baselines, so a future pass starts from numbers rather than re-deriving them: `ls infra/ansible/roles/ops/templates/*.timer.j2` gives **7** timers; `grep -l 'Persistent=true'` over those gives **5**; `grep -l ops_textfile_dir infra/ansible/roles/ops/templates/*.sh.j2` gives **6** writers; `systemctl list-timers` on the host shows **8** project timers, because `access_ops` installs `zaccess-probe-ops.timer` as well. Each of these is the answer to a different question, and the prose above conflates them.

Corrected on `feat/grafana-keepalive` and NOT part of this topic: `infra/runbooks/ops-node.md`'s timer table and its "five of the seven are `Persistent=true`" sentence, `ops-node.md:5`'s opening timer count, `docs/reference/fleet.md:34`'s ops-timers enumeration, and `infra/ansible/roles/ops/files/config.alloy:66`'s textfile-writer list.

## Resolution

Swept, fixed and partly guarded on the branch that carries this file into the archive.

**The sweep ran by CLAIM, not by phrase**, which the first step asked for: four modalities — a numeral, a
spelled-out number, a list whose length IS the count, and a count encoded as a pattern (an Alloy relabel regex, a
unit glob) — over `infra/`, `docs/` and `.claude/`, plus a completeness critic asking what surface or modality
none of them covered. 66 distinct sites; 15 files changed.

**The six instances above, each by name:**

- `alloy-compose.yaml.j2`'s "four timers' textfiles" and "the four `zcrypto-*.service` units' logs" — numerals
  deleted; the sentences name their members and the keep-regex is six lines below the second.
- `ops-node.md:5` carried two counts that had diverged in one sentence. Split: the `docker run` half keeps its
  five, and the publishing half is now a complement, "all but `grafana-watchdog`". The opening timer count is
  scoped to the role and says the host shows one more, from `access_ops`.
- `fleet.md:34` was delivered 2026-09-10 by the fleet-contracts rewrite, as recorded above.
- `infra/ops/README.md:206` gained the omitted `zcrypto_grafana_keepalive_*`.
- `grafana-keepalive.timer.j2`'s "no other unit on this host uses" is narrowed to the two roles it was checked
  against, with the command, and says the host's own OS timers were not part of that check.

**Where a count stayed it carries the command that measures it**; elsewhere the number is gone, because a
sentence that names its members carries its own length. The baselines above each answer a different question and
the prose conflated them, which is why several counts were "right" for a question nobody asked.

**One relationship is held by a test**, which is the fourth step's answer: a timer the ops role installs is either
named in the Alloy journal keep-regex or listed in `tests/test_infra_alloy_series.py` as deliberately unshipped
with its reason, and the regex may name no unit the role does not install. That one is guarded because it is the
only remaining count with a consequence beyond prose — a timer missing from that regex ships no journal lines at
all, silently. Both directions are proved by `infra/scripts/mutate-probe.sh` against the regex.

**Not covered, stated rather than implied:** recurrence. Nothing fails when someone writes a new unheld count
tomorrow; the textfile-writer census, the catch-up count and the healthcheck-URL claim are prose carrying their
commands, not assertions. Guarding those would need a prose-count instrument, which is a larger thing than this
topic, and [[T0183]] rules the same question out of its own criteria for the same reason — a topic that must
prevent its own recurrence can never close.

**Refused during the sweep, both behaviour changes wearing a census fix's clothes:** widening the production
journal keep-regex to a wildcard (it would ship two more units' logs to Loki; the regex is byte-identical), and
substituting a different numeral where the census said to delete one.

**One correction the branch read caught:** the sweep deleted `alerts.yaml`'s "The other three stay at 512m",
which was correct AND exhaustive — three container Alloys carry that cap. The replacement said "the other
hosts", which is false for the bridgehead's uncapped apt Alloy. It names its members now. A numeral that is the
claim is not a numeral to delete, which is the sweep's own rule read from the other side.
