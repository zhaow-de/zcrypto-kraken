---
status: open
---

# Ops unit census drift — how many timers, writers and log sources, restated in file after file and agreeing with nothing

## Context — what

Several durable files state a COUNT of the units on `zcrypto-ops`: how many systemd timers the roles install, how many of those write a node-exporter textfile, and how many units' journal lines Alloy ships. The counts were written when they were true and none is re-derived when a unit is added, so they have drifted apart from the tree and from each other. Several were already wrong before the keep-alive branch that surfaced this.

## Why this matters

These are the files an operator reads when a host does not match expectations, and a count is exactly what they reconcile against `systemctl list-timers`. A file saying six where the host shows seven sends them looking for a phantom unit, or invites them to disable the extra one as unauthorised — the failure mode is acting on the document rather than doubting it. The keep-alive branch corrected instance after instance across four review rounds, and each round found the next one standing, which is why this is a census rather than a fix: the instances are not discoverable from any one of them.

## Findings so far

Enumerated during the `feat/grafana-keepalive` reviews. Every line below was read from the tree, and the counts are measured from the templates rather than from the prose.

**This file demonstrated its own subject and that is its strongest evidence.** As first written it carried three stale counts — "six durable files" for a list spanning five, "corrected three instances" against its own list of four, "two were already wrong" where three were — authored in the same hours as, and by the author of, the measurements below. A fifth review round found them. The arithmetic fix does not work even for someone who has just measured the thing; that is the case for deleting the numbers rather than maintaining them, and it is why the first suggested step below is the one it is.

- `infra/ansible/roles/ops/templates/alloy-compose.yaml.j2:78` — "four timers' textfiles"; six templates write into `ops_textfile_dir`. **Wrong before the keep-alive branch.**
- `infra/ansible/roles/ops/templates/alloy-compose.yaml.j2:80-81` — "the four `zcrypto-*.service` units' logs", while the journal regex on those lines names five. **Wrong before the keep-alive branch.**
- `infra/runbooks/ops-node.md:5` — "**five** fire a `Type=oneshot` unit that runs an ephemeral, digest-pinned `docker run` and then publishes a node-exporter textfile": five is right for the `docker run` half and wrong for the publishing half, which is now six. One sentence carrying two counts that have diverged.
- `docs/reference/fleet.md:34` — the row's trailing `.prom outputs under …` clause spans `grafana-watchdog`, which publishes no textfile at all.
- `infra/ops/README.md:206` — the verify-by-outcome list omits `zcrypto_grafana_keepalive_*`.
- `infra/ansible/roles/ops/templates/grafana-keepalive.timer.j2` — the schedule comment says the minute is one "no other unit on this host uses", which is broader than the check it names: it was verified against the `ops` and `access_ops` roles, not against the host's own OS timers.

Measured baselines, so a future pass starts from numbers rather than re-deriving them: `ls infra/ansible/roles/ops/templates/*.timer.j2` gives **7** timers; `grep -l 'Persistent=true'` over those gives **5**; `grep -l ops_textfile_dir infra/ansible/roles/ops/templates/*.sh.j2` gives **6** writers; `systemctl list-timers` on the host shows **8** project timers, because `access_ops` installs `zaccess-probe-ops.timer` as well. Each of these is the answer to a different question, and the prose above conflates them.

Corrected on `feat/grafana-keepalive` and NOT part of this topic: `infra/runbooks/ops-node.md`'s timer table and its "five of the seven are `Persistent=true`" sentence, `ops-node.md:5`'s opening timer count, `docs/reference/fleet.md:34`'s ops-timers enumeration, and `infra/ansible/roles/ops/files/config.alloy:66`'s textfile-writer list.

## Suggested next steps

- Sweep for the CLAIM rather than for any phrase: enumerate the variants first — a numeral, a spelled-out number, a parenthesised list whose length IS the count, a regex whose alternation count is the claim — then grep `infra/`, `docs/` and `.claude/` for each. The instances above were found one at a time by three separate reviews, which is the evidence that a phrase-shaped sweep misses them.
- Decide per instance whether the count is load-bearing at all. `prose.md` asks first whether a number is needed: "the following timers" needs no count beside it, and a list that names its members carries its own length. The cheapest durable fix for most of these is deleting the number, not maintaining it.
- Where a count must stay, put the command that measures it in the same sentence, as the measured baselines above do.
- Consider whether a test can hold the ones that remain — the counts are all derivable from the templates, so an assertion comparing a stated number against a glob would make the next drift a failing test instead of a fourth review round.

## Owner

Unassigned. One pass, one author: the failure mode this topic records is precisely a fix applied instance by instance.
