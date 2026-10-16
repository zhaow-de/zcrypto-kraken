## Standing lines

- Never look for, open, count or quote a real account export anywhere outside the repository's tracked fixtures. Never read `.local/memo.md`, `data/ohlc-holdout-*`, `/mnt/zhao-crypto/` or a vault-shaped file; every tree search is `git grep` with the `VAULT_EXCLUDES` pathspecs of `infra/scripts/consumers.sh`. Never print a credential, token, webhook URL or IP address.
- Never ssh, docker, an `ansible-playbook` run that executes tasks or connects to a host, `ansible-inventory`, `converge.sh`, `grafana-push.sh`, `grafana-query.py` or `ops-daily.py report`, and never call a Grafana or Kraken endpoint: this workstation is the live fleet host `zcrypto-ops`. Never run `tests/test_grafana_push_sh.py`.
- A scratch tree is a detached worktree under the brief's own `.tmp/<role>/`, removed before the report; never a `git archive`, a copy or a clone of the repository. Scratch is written only there, never in the session scratchpad or `/tmp`, and a generic name is never removed. A process started is stopped by its PID before the report.
- Every path the brief names exists now and every argument matches the script's own contract; a report a parallel read is still writing is not an input.
- Plain blocking commands, nothing backgrounded; a run that would pass 600 s is split into parts. No subagents, no agent tools.
- A sha, a stamp or a figure is pasted from the command that printed it in the same call.
- The only writes are the ones the brief names; the return is status, the report's path and concerns.
