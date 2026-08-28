# Fleet runbooks — every long-lived daemon's memory and restarts

You are here because **an alert fired in Slack**. Find the section whose anchor matches the alert `uid`. Each section is written to be actioned without opening any other document.

These four rules are one routine — memory watched continuously across the fleet, regardless of converges — and they cover every long-lived process the fleet scrapes: both capture daemons, the engine, the ops liquidations poller, and Alloy on all four hosts. They replaced the hand-scheduled RSS reads the capture-image bake used to carry.

`README.md` beside this file is the index, and states what belongs in a runbook at all.

______________________________________________________________________

<a name="zcrypto-fleet-memory-headroom"></a>

## zcrypto-fleet-memory-headroom — ALERT

### What you are seeing

A warning-severity Grafana alert, one instance per `(host, job)`: that daemon's resident memory has been above **70 % of its container limit** for five minutes. The limits: `2g` for capture on `zcrypto`, `1g` for capture on `zcrypto-red`, and `1g` for the engine — the ansible vars that render each compose file. **Not covered by this rule**: Alloy, which has its own rule and its own bar (see the `zcrypto-fleet-alloy-memory-headroom` section below); the ops liquidations poller, whose compose sets no memory limit, so there is no ceiling to measure against — the leak and restart rules below do cover it; and the NAS `archive-pull` container, which exposes no metrics at all.

### What it means

This is the slow-leak alarm, and it is the only one that matters: a leak's one real harm is the OOM-kill, and this says so before it happens, on any image, at any process age. The capture daemons sit near 7 % of their limit on a healthy day, so being here means a long climb. **Memory is watched as a fleet-wide routine, not as part of a rollout** — no bake owes a memory read, and this rule is what replaced those reads.

### What to do

1. **Read how long it has been climbing** — the fleet board's *Daemon RSS growth per day — fleet* panel (602). A steady positive rate over days is a leak; a single step that then plateaued is an allocation that converged and is not going to reach the limit on its own.
2. **Read what it has been running since** — `docs/reference/fleet-pins.md`'s `since` column names the image and the date; `docs/reference/deploy-log.jsonl` has every converge as a machine line. The suspect is the image; the rollback operand is in the same row.
3. **A leaking capture daemon is restarted, not rolled back, first** — `sudo systemctl restart zcrypto-capture` on the affected host, one host at a time, never both in one window. The restart costs a resubscribe (seconds) and buys the full limit back; the peer host keeps capturing. Then decide on the image with the growth rate in hand.
4. **If it is the engine**, the restart must land inside the 4-hourly inter-cycle gap like any engine restart (`.claude/rules/fleet-deploys.md`, engine converges). **If it is Alloy** (`integrations/self`), `sudo docker restart grafana-alloy` — the container name is identical on all four hosts, and restarting the container alone touches no other service (a `compose restart` would: on the NAS, Alloy and `archive-pull` share one compose project). On the NAS the binary is `sudo /usr/local/bin/docker restart grafana-alloy`. **If it is the liquidations poller**, it will not be this rule (no limit) — see the leak rule.

### Retire when

`zcrypto-fleet-memory-headroom` is absent from `infra/grafana/alerts.yaml` — i.e. the rule was deliberately removed.

______________________________________________________________________

<a name="zcrypto-fleet-alloy-memory-headroom"></a>

## zcrypto-fleet-alloy-memory-headroom — ALERT

### What you are seeing

A **warning** Grafana alert, one instance per host: Grafana Alloy there has been above **90 % of its container limit** — 1 GiB on ops, 512 MiB on zcrypto, zcrypto-red and nas — for fifteen minutes. That 90 % bar is Alloy's Go soft limit (GOMEMLIMIT) on every host, so crossing it means the runtime lost its soft limit.

### What it means

**Alloy runs closer to its ceiling than the app daemons do, by design** — it holds the remote-write WAL and the journald reader's buffers. Ordered by proximity to its bar: ops highest (it reads the most journal — reconcile, panel, verify-replay, tape-bars, liquidations), then zcrypto, zcrypto-red, nas. The app daemons sit far lower, which is why Alloy has its own bar and its own rule: a shared one pages ops on a perfectly healthy fleet.

If Alloy is OOM-killed, that host's telemetry goes dark and `Fleet · Alloy dark` reports it within ~10 min. **This is the warning before that**, not the detector for it.

### What to do

1. **Read which host, and against its own history** — the fleet board's *Daemon memory* panel (601), `job="integrations/self"`. Steady state sits well below the bar on every host, and a host climbing toward 0.9 is the runtime losing its soft limit — read the trend on panel 601 against that host's cap.
2. **Restart Alloy if it is climbing** — `sudo docker restart grafana-alloy` (on the NAS: `sudo /usr/local/bin/docker restart grafana-alloy`). Telemetry-only, seconds, and the `alloy-data` WAL and journal cursor survive it, so no backlog is re-shipped and no log tail is lost.
3. **Repeated firing on one host is a capacity finding, not an incident** — its Alloy needs a larger `memory:` in that host's Alloy compose, which is an ansible change and a converge, not a restart.

### Retire when

`zcrypto-fleet-alloy-memory-headroom` is absent from `infra/grafana/alerts.yaml`, or a host's GOMEMLIMIT stops being 0.9 of its cap — the ratio this bar is, pinned by `test_gomemlimit_is_the_same_fraction_of_the_cap_on_every_alloy_host`.

______________________________________________________________________

<a name="zcrypto-fleet-memory-leak"></a>

## zcrypto-fleet-memory-leak — ALERT

### What you are seeing

A warning-severity Grafana alert, one instance per `(host, job)`: that daemon's **hourly memory floor** is at least 64 MiB above where it was 24 hours earlier, and has been for six hours.

### What it means

The early warning, a week or more ahead of the memory-limit page from a normal starting size. It reads floors so the hour-boundary sawtooth cannot cause it, compares a day apart so a ~4 h step and its trough are both inside the window, and is switched off for the first 30 hours after a restart — so a new image's larger working set never pages as a leak during a bake, and the day-one warm-up ramp is never compared against a converge-time cold floor.

The bar is provisional: no real leak has ever been measured on this fleet. Healthy day-scale drift measured 2026-08-23/24 was 2.7–3.6 MiB per 8 h, an order below it.

### What to do

1. **Look at the shape on panel 602**, not the number. Two steps of decaying size with flat troughs between them is a converging allocation and will stop; equal or growing steps are a leak.
2. **Note the image and the date from `docs/reference/fleet-pins.md`**, and whether a converge happened in the last day (`docs/reference/deploy-log.jsonl`) — a new image is the first suspect, and the leak page a day after a converge is the one this rule exists for.
3. **Do nothing else yet.** This is notice, not a fault. The headroom rule owns the decision point; until it fires the only action is to keep the two numbers (rate, image) where the next reader finds them.

### Retire when

`zcrypto-fleet-memory-leak` is absent from `infra/grafana/alerts.yaml` — i.e. the rule was deliberately removed.

______________________________________________________________________

<a name="zcrypto-fleet-daemon-restarted"></a>

## zcrypto-fleet-daemon-restarted — ALERT

### What you are seeing

A warning-severity Grafana alert, one instance per `(host, job)`: that daemon's process start time moved in the last 15 minutes — it restarted.

### What it means

**If a converge or an Alloy bump just ran on that host, this is that action.** `job` names the daemon — a capture or engine daemon, the ops poller, or Alloy itself (`integrations/self`) — and the action's own record in the channel needs nothing. **If nothing was converged, the daemon was OOM-killed or crashed and came back on its own** — and this is the only signal for that: the container is back in seconds, the dead-man keeps pinging, and the log-dead rules never see a gap that short. There is no container-restart metric on these hosts, so this rule reads the same fact from inside the process.

### What to do

1. **Check the deploy log first** — `docs/reference/deploy-log.jsonl`'s last line, or the channel: a converge in the last 15 minutes explains it completely.
2. **Otherwise read the container**: `sudo docker inspect --format '{{.RestartCount}} {{.State.OOMKilled}}' <name>` — `zcrypto-capture`, `zcrypto-engine`, `grafana-alloy`, or the ops poller `zcrypto-ops-liquidations` (`ssh hp`); on the NAS docker is `/usr/local/bin/docker`. `OOMKilled=true` names the cause; read the memory panels for how it got there and treat it as the headroom page that did not get a chance to fire.
3. **For a capture daemon, confirm capture recovered**: `sudo find /var/lib/zcrypto-capture -name '*.parquet' -mmin -3 | head` shows files advancing. A single-host restart costs seconds and the peer's copy heals it; the reconciler will book whatever was not.
4. **A repeating restart** — this rule firing again within the hour with no converge — is a crash loop; read `sudo docker logs --since 20m zcrypto-capture` before anything else.

### Retire when

`zcrypto-fleet-daemon-restarted` is absent from `infra/grafana/alerts.yaml`, or a container-restart metric reaches Grafana from these hosts and a rule reads it instead.
