# Fleet runbooks — every long-lived daemon's memory and restarts

You are here because **an alert fired in Slack**. Find the section whose anchor matches the alert `uid`. Each section is written to be actioned without opening any other document.

These three rules are one routine — memory watched continuously across the fleet, regardless of converges — and they cover every long-lived process the fleet scrapes: both capture daemons, the engine, the ops liquidations poller, and Alloy on all four hosts. They replaced the hand-scheduled RSS reads the capture-image bake used to carry.

`README.md` beside this file is the index, and states what belongs in a runbook at all.

______________________________________________________________________

<a name="zcrypto-fleet-memory-headroom"></a>

## zcrypto-fleet-memory-headroom — ALERT

### What you are seeing

A warning-severity Grafana alert, one instance per `(host, job)`: that daemon's resident memory has been above **70 % of its container limit** for five minutes. The limits: `2g` for capture on `zcrypto`, `1g` for capture on `zcrypto-red`, `1g` for the engine — the ansible vars that render each compose file — and `512m` for Alloy (`job="integrations/self"`) on all four hosts, the literal in each Alloy compose template. **Not covered by this rule**: the ops liquidations poller, whose compose sets no memory limit, so there is no ceiling to measure against — the leak and restart rules below do cover it; and the NAS `archive-pull` container, which exposes no metrics at all.

### What it means

This is the slow-leak alarm, and it is the only one that matters: a leak's one real harm is the OOM-kill, and this says so before it happens, on any image, at any process age. The capture daemons sit near 7 % of their limit on a healthy day, so being here means a long climb. **Memory is watched as a fleet-wide routine, not as part of a rollout** — no bake owes a memory read, and this rule is what replaced those reads.

### What to do

1. **Read how long it has been climbing** — the fleet board's *Capture RSS growth per day* panel (602). A steady positive rate over days is a leak; a single step that then plateaued is an allocation that converged and is not going to reach the limit on its own.
2. **Read what it has been running since** — `docs/reference/fleet-pins.md`'s `since` column names the image and the date; `docs/reference/deploy-log.jsonl` has every converge as a machine line. The suspect is the image; the rollback operand is in the same row.
3. **A leaking capture daemon is restarted, not rolled back, first** — `sudo systemctl restart zcrypto-capture` on the affected host, one host at a time, never both in one window. The restart costs a resubscribe (seconds) and buys the full limit back; the peer host keeps capturing. Then decide on the image with the growth rate in hand.
4. **If it is the engine**, the restart must land inside the 4-hourly inter-cycle gap like any engine restart (`.claude/rules/fleet-deploys.md`, engine converges). **If it is Alloy** (`integrations/self`), `sudo docker compose restart` in that host's Alloy project dir — telemetry-only, it touches no daemon; the `/zcrypto-bump-alloy` skill's per-host map names the dirs. **If it is the liquidations poller**, it will not be this rule (no limit) — see the leak rule.

### Retire when

`zcrypto-fleet-memory-headroom` is absent from `infra/grafana/alerts.yaml` — i.e. the rule was deliberately removed.

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
2. **Otherwise read the container**: `sudo docker inspect --format '{{.RestartCount}} {{.State.OOMKilled}}' <name>` — `zcrypto-capture`, `zcrypto-engine`, `grafana-alloy`, or the ops poller (`ssh hp`, container name per `docs/reference/fleet.md`); on the NAS docker is `/usr/local/bin/docker`. `OOMKilled=true` names the cause; read the memory panels for how it got there and treat it as the headroom page that did not get a chance to fire.
3. **For a capture daemon, confirm capture recovered**: `sudo find /var/lib/zcrypto-capture -name '*.parquet' -mmin -3 | head` shows files advancing. A single-host restart costs seconds and the peer's copy heals it; the reconciler will book whatever was not.
4. **A repeating restart** — this rule firing again within the hour with no converge — is a crash loop; read `sudo docker logs --since 20m zcrypto-capture` before anything else.

### Retire when

`zcrypto-fleet-daemon-restarted` is absent from `infra/grafana/alerts.yaml`, or a container-restart metric reaches Grafana from these hosts and a rule reads it instead.
