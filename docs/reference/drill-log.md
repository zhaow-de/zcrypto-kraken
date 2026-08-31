# Drill log

One entry per drill run, appended in date order. The heading is `## <YYYY-MM-DD> — <scenario id> — <pass | fail | partial | blocked>`, and the body is one paragraph of labelled clauses: *host* · *induction* · *time-to-alert* (with the three timestamps wherever a Slack path is involved — rule `activeAt`, message, device) · *channels* · *operator action* · *follow-ups* (a `T<NNNN>` or an explicit drop).

`blocked` is a status, not prose. It is the outcome when the induction never landed — a precondition refused it, or the instrument did not take — and the reason is then a required clause. The alternatives are both false records: `fail` asserts a guard did not fire when nothing exercised it, and `partial` a run that half-happened.

`tests/test_drill_log.py` guards the heading shape and the date order; everything below a heading is prose it does not read.
