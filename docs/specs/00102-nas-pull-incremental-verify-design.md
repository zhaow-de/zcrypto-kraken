# 00102 — bound the NAS pull's per-cycle verify cost, and make that cost observable

Closes [[T0028]]. Two components, shipped in that order, on one branch and one PR:

| # | component | what it buys | ships via |
| --- | --- | --- | --- |
| A | publish the per-cycle verify cost as a metric | the "before" baseline, and the standing read of the cost curve | NAS converge (`--limit nas`), Alloy config included |
| B | hash only what rsync transferred, plus a rotating 1/24 slice | the cut itself: per-cycle cost stops tracking archive size | NAS converge (`--limit nas`) |

**A ships and runs first.** Its baseline is the only evidence B worked; landing them together leaves the change unmeasured in both directions.

## The measured basis

Verified against the repo and the live NAS, 2026-08-28:

- **`verify_tree` re-hashes the whole destination every cycle, for five channels.** `cli/archive/pull.py::verify_tree` walks `root.rglob("*.parquet")` and calls `verify_manifest` on each. The NAS loop (`infra/nas/pull-entrypoint.sh`) runs `zcrypto archive pull` **with** verification on `CAPTURE_SOURCE`, `CAPTURE_RED_SOURCE`, `LIQUIDATIONS_SOURCE`, `PANEL_SOURCE` and `RECONCILED_SOURCE`; `JOURNAL_SOURCE` is `--no-verify` and `HOT_SOURCE` is a raw rsync. T0028 reasons about two mirrors — there are **five**, so its ripe estimate is optimistic by an unmeasured factor.
- **75,806 parquet files were re-hashed in the 2026-08-28 13:37–14:40Z cycle** — `checked=` of 27,931 + 24,901 + 8,624 + 13,908 + 442 across the five verified channels. A single observation from the pull log, not an instrumented measurement, which is component A's whole point.
- **The failure mode is drift, not a stall.** The loop is `work; sleep "${ARCHIVE_PULL_INTERVAL:-3600}"` — no fixed schedule, so cycles cannot overlap and nothing piles up. The period simply stretches to `work + 3600`, degrading into pull lag. T0028's "a single sweep no longer fits in the pull period and the in-container loop stalls" describes a mechanism this design does not have, and there is therefore **no cliff at 3600 s** to trigger on.
- **The loop has already been observed past an hour.** The entrypoint records that "the Atom tax on every step sharing this clock had stretched the 'hourly' loop to ~103 minutes" before spec 00054 moved reconcile to the ops node. The mode is real on this host; only its cause was different.
- **Nothing measures the cost.** No verify duration, no cycle duration is exported. The NAS pull's entire observability is `NAS · archive-pull stalled (dead-man)` (fires on silence), `NAS · archive-pull ERROR logs`, and the `lag_s` field, which is **data freshness, not sweep cost**. T0028's `ripe_when: one hourly verify_tree sweep approaches the pull interval` is therefore **not satisfiable from any data source we have** — the defect `open-topics.md` names ("never a condition the data source cannot deliver").
- **`cli/archive/` is outside the replay-fingerprint closure.** `gate_cache._replay_code_paths()` resolves to 79 files, none under `cli/archive/`; `cli/config.py` and `cli/__init__.py` **are** inside it. So neither converge pays the cold gate replay (last measured 3508 s on this host) **provided the change stays out of those two files**.
- **A new metric family is dropped silently unless admitted.** `infra/nas/config.alloy`'s keep regex is a subset filter on `__name__` admitting `zcrypto_gate_.*`, `zcrypto_reconcile_.*` and `zcrypto_trade_backfill_.*`. The same file warns of the inverse: "a keep-list entry for a series that cannot exist is the T0051 trap".
- **The dead-man parses the pull's log line.** `NAS · archive-pull stalled (dead-man)` matches `failed=0`, and its own comment calls that token load-bearing. The line's shape is an interface.

## Decisions

### D1 — the walk stays whole; only the HASH is narrowed

`verify_tree` does three things that share one traversal: it walks the tree, it hashes each parquet, and it derives `newest_ts` and the `verified` list. The walk (`rglob` + `_hour_ts`) is O(files) and cheap; the hash is O(bytes) and is the entire cost.

**The traversal is not narrowed. Only `verify_manifest` is skipped.** Two consumers make this load-bearing:

- `newest_ts` feeds `pull_lag_seconds`, which the entrypoint calls "the dead-man signal that a stuck pull gets noticed". Narrowing the walk to transferred files makes `newest_ts` `None` on a cycle where nothing arrived — the freshness signal would go blank **exactly when nothing is arriving**, the condition it exists to detect.
- `verified` feeds `prune_stale_parts`. Narrowing the walk narrows the prune.

This is why the design is a skip test inside the existing loop rather than the `verify_paths(paths, *, now)` sibling T0028 suggested: one code path, and both derived values keep their present meaning by construction rather than by care.

### D2 — the skip test is rsync's own itemization

`_run_rsync` gains an output contract: it runs rsync with `--out-format='%i %n'` and returns the transferred `*.parquet` paths alongside the return code. `verify_tree` hashes a file iff it is in that set (or in this cycle's slice, D3).

Chosen over a checkpoint store with a sidecar-digest or `stat` probe (spec 00078's pattern, in this same package) for one reason: **those probes are themselves O(total files) per cycle** — ~75,806 sidecar reads or stats on spinning RAID-5 — so they shrink the constant while keeping the growth term this spec exists to remove. Itemization costs no probe at all.

What it gives up: a file changed **outside** rsync is not hashed until its slice comes round. That is D3's job, and D3 is built regardless.

**One class arrives THROUGH rsync and is still not itemized on its next appearance — accepted, bounded by the slice.** When rsync exits non-zero part-way (23 partial; 24 vanished-source, which the VPS's 7-day prune makes routine; 255 on an ssh drop), `pull` exits 2 before `verify_tree` runs, and every file rsync *did* complete in that cycle passes its size+mtime quick-check next cycle: it is never `>f` again, and under `incremental` it waits for its slice (≤ 24 cycles, D3). Today's whole-archive sweep hashes it the next cycle. Accepted rather than closed because rsync's own whole-file checksum already verified the TRANSPORT of those files; what the sidecar hash adds for them — a source-side or post-write discrepancy — is exactly what the slice sweeps for, inside its bound. No per-channel "full next time" state is kept in the entrypoint for this. A sidecar-only update at source shares the same bound by a different route: the sidecar itemizes as `>f …parquet.sha256`, which the parsing rule below correctly drops for not ending `.parquet`, so the parquet it describes is not itemized either and waits for its slice exactly as the rsync-failure class above does (≤ 24 cycles, D3).

Parsing rules, stated because the itemize format has three shapes that are not transfers: a line is a transferred parquet iff its itemize flags begin `>f` (received, regular file) **and** its path ends `.parquet`. Directory lines (`cd`), deletions (`*deleting`), and the `.part`/`.held` names `verify_tree` already skips are excluded.

### D3 — a stateless rotating 1/24 slice, keyed on the cycle, never the clock

A final belongs to slice `int(sha256(<root-relative posix name>).hexdigest()[:8], 16) % 24`; each cycle additionally hashes the finals whose slice equals the cycle's **rotation index** — the NAS entrypoint's own cycle counter modulo 24, passed as `--slice`. Every final is therefore re-hashed **every 24 cycles**, and the selection is a pure function of the name and the counter — **no cursor, no persisted state, no new store**; a container restart resets the counter and merely re-visits the low slices sooner.

**Not the clock.** The obvious key, `now.hour % 24` (spec `00062`'s shape), is wrong for THIS loop: the period is `3600 + work`, so the hour the verify samples drifts every cycle, and whenever the period divides 24 h the loop lands on the same hours forever. Simulated over 400 days: at a 65-minute period the worst gap between two re-hashes of one slice is ~48 h; at 72, 80 and 90 minutes a fixed set of 4, 6 and 8 slices is **never visited**. The post-leg-B period will sit in that band. The slice is the ONLY detector for bytes that change without rsync itemizing them (D2), and the VPS prunes its copy after ~7 days, so the bound has to sit well inside a week: a cycle-keyed slice gives `24 × period` (≈ 26–30 h at the expected period) regardless of drift; a clock-keyed one gives no bound at all.

The `_ROTATION_SLICES <= 24` assert is kept from `00062` for the reason it exists there: a modulus larger than the index range leaves high slices unreachable and their finals silently never re-hashed. `--slice` is validated to `[0, 23]` and is **required** with `--hash-scope incremental` — an incremental pull with no slice is the narrowed hash with no safety net, so it is a usage error, never a silent default.

**Stated honestly: per-cycle cost becomes `O(new) + O(archive)/24`, not constant.** A fixed budget with a persisted cursor is the only genuinely flat option; it was declined as YAGNI. 24× headroom moves the cost T0028 feared from its ~1.7-year horizon to decades, and the D4 metric makes any future regression visible rather than inferred.

### D4 — the cost is published as a gauge, per channel

A textfile-collector metric written beside the existing gate export, labelled by channel:

- `zcrypto_archive_pull_verify_seconds{channel}` — wall-clock spent hashing this cycle
- `zcrypto_archive_pull_files_hashed{channel}` — files whose bytes were actually read
- `zcrypto_archive_pull_files_walked{channel}` — files traversed, i.e. the archive's size in files

`files_walked` is not decoration: it is the denominator that makes `files_hashed` interpretable, and it is the series that grows. Both are needed to tell "the cut worked" from "the archive stopped growing".

**Five invocations share one textfile directory, so each channel owns its own file.** `zcrypto archive pull` gains `--textfile <path>` and `--channel <name>` (following `gate-export`'s existing `--textfile` precedent); the entrypoint passes a distinct path and name per channel, so no invocation can clobber another's series and the collector merges the directory. Both options are optional — a pull invoked without them publishes nothing and behaves exactly as today, which is what keeps the workstation and ops callers unchanged.

**A skipped channel leaves a stale file, and that is intended**: an unset `*_SOURCE` means the channel is not wired, and its last published values persist rather than vanishing. The reader distinguishes fresh from stale by the collector's own `node_textfile_mtime_seconds`, not by absence — so a channel that silently stopped running is visible as an ageing mtime rather than as a gap that reads like a zero. That series is **not admitted by the NAS keep regex today**, so the edit that admits `zcrypto_archive_pull_.*` admits `node_textfile_mtime_seconds` in the same token — a reader resting on a series remote_write drops would be the T0051 trap inverted.

`infra/nas/config.alloy`'s keep regex gains `zcrypto_archive_pull_.*`, in the same change that first writes the series — never before it (the T0051 trap the file itself names).

### D5 — the log line gains the same numbers, and `failed=0` survives verbatim

The `pull complete ...` line gains `verify_s=` and `hashed=`. This is not redundant with D4: the log line is the only record when the CLI is killed before it can publish (OOM, signal), which the entrypoint's own comment identifies as precisely when someone needs to know.

`failed=%d` keeps its position and spelling. A test asserts the dead-man's `failed=0` substring is present in a clean line — the rule lives in Grafana and cannot fail the suite, so the suite must carry the claim.

### D6 — T0028 closes on the measurement, and nothing pages on the curve

[[T0028]]'s original `ripe_when` named a quantity nothing measured, so it has already been dropped rather than restated. Nothing replaces it: the topic goes `partial` when this PR lands the code and **`resolved` at leg B**, on the measured drop — it is closed by a fix, not by a trigger, and a resolved topic carries no `ripe_when` by construction. The measured horizon the new curve implies is written into its `## Resolution`.

**No alert rule is added.** The per-cycle cost after leg B is `O(new) + O(archive)/24` (D3) and moves over months; a rule paging on it would be read as noise. The standing read is the dashboard panel D8 adds, and the metric is what makes any future regression visible rather than inferred. This is a conscious drop, not a deferral.

### D7 — one image serves both legs: the hash scope is a deployed setting, not a build

`.github/workflows/capture-image.yml` builds on push to `develop`/`main` only, so a single PR yields a single image, and that image carries A and B together. "A runs first" therefore cannot mean two images. It means the narrowing is **off by default and switched on by configuration**: `zcrypto archive pull --hash-scope full|incremental` (default `full`, so every other caller is unchanged), fed on the NAS by `ARCHIVE_PULL_HASH_SCOPE` from the ansible-rendered `.env`, whose committed source is `nas_archive_pull_hash_scope` in `infra/ansible/host_vars/nas/vars.yml`.

Leg A converges the new digest with the scope at `full` — the instrumentation runs, the hash is still whole, the baseline is real. Leg B is a **config-only converge on the currently-running digest** that flips the committed variable to `incremental`. Two consequences worth having: B's rollback is the same one-line flip with no image change, and the operand that decides which mode the NAS runs is a committed file reviewed like any other.

### D8 — a new family is admitted, charted, and pinned in the same change

`tests/test_dashboards_cover_metrics.py::test_every_published_app_family_is_charted` fails on a published family no dashboard charts, and `tests/test_infra_alloy_series.py::test_keep_regex_admits_every_published_series` pins the NAS keep regex against `NAS_REQUIRED`. So the change carries, together: the keep-regex edit (D4), `zcrypto_archive_pull_files_walked` in `NAS_REQUIRED` (so deleting the keep entry fails the suite rather than going dark), and two panels on `infra/grafana/data-integrity-dashboard.json` — verify seconds by channel, and hashed against walked. The second panel is how "the cut worked" is read.

## Verification

- **The guard must be seen to bite.** A test constructs a tree where the defect and the fix differ: an archive of N already-verified parquets plus one transferred file, asserting `files_hashed == 1` while `files_walked == N + 1`. Under the current code both equal `N + 1`, so the test fails before the change and passes after — a degenerate fixture (an empty archive) cannot move and proves nothing.
- **The true positive**: a real, healthy, production-shaped tree must still verify clean, and a corrupted parquet **in this cycle's slice** must still be caught. Without the second, an always-skipping implementation ships green.
- **`newest_ts` and the prune are pinned against D1's failure mode**: a cycle that transfers nothing must still report a lag figure, and must not report `None`.
- **The suite's own guards on a new family run green**: `tests/test_infra_alloy_series.py` (keep-regex admission) and `tests/test_dashboards_cover_metrics.py` (charted, admitted where selected). `README.md`'s `## Usage` documents the four new options in the same change (`readme-usage.md`).
- **The deploy is verified by outcome, not by exit code**: after converge A, `uv run python infra/scripts/grafana-query.py 'zcrypto_archive_pull_files_walked{host="nas"}'` must return a value — `(no series)` is FAIL and means the keep-list or the container recreate did not take. After converge B, the same query plus `files_hashed` must show the drop against A's baseline.

## Deploy sequence

Both legs are `--limit nas`, outside the canary regime (no secondary, no bake owed), and neither pays the cold replay per the measured basis.

**The NAS's `config.alloy` needs no digest variable, unlike capture and ops.** There is no `nas_alloy_digest` — the pin is `nas_alloy_image`, and `roles/nas/tasks/main.yml` registers the config deploy and **restarts Alloy in the same converge** so it re-reads the file it just wrote — **but only under `-e nas_apply_compose=true`**. Every apply task in that role (`compose up -d`, the archive-pull restart, the Alloy restart) is gated on that flag; a converge without it is render-only — files land, nothing restarts, and both legs would read as success while the old process kept running until the by-value read caught it. The `.env` value change does recreate archive-pull (environment is part of the compose service hash) — under the same flag. The capture/ops discipline (pass the currently-running digest, satisfy the drift assert) does not transfer, and passing `-e nas_alloy_digest=...` would be silently accepted as an unknown extra var and do nothing.

**Both legs happen BEFORE this PR merges, on an interim image built from the feature branch — an exception, not a pattern.** The norm is: merge, let CI build, converge CI's digest. It is inverted here because this component's whole deliverable IS a measurement: taken before the PR opens, [[T0028]] resolves in the PR that completes it instead of merging `partial` against a promise, and a defect found at leg B is fixed on the branch without `develop` ever having carried it. `capture-image.yml`'s `workflow_dispatch` builds any ref, and its push step is not branch-gated.

Nothing in `fleet-deploys.md` is relaxed by this, and nothing is added to it: a later rollout meeting a NAS pins row built from a feature branch is reading a recorded exception, and `agent-ops.md` already rules that observed drift is not license. Two constraints make it safe — **the branch is rebased before the image is built and never rewritten after** (the image bakes `org.opencontainers.image.revision`, which is the pin's provenance), and the merge is a merge commit, so those SHAs stay reachable and the interim digest stays auditable. A post-merge re-pin is therefore optional, but not on a byte-identity claim taken at planning time: `infra/docker/Dockerfile` copies all of `cli/`, `pyproject.toml`, `uv.lock` and `README.md` into the image, so byte-identity holds only if nothing touching that build context lands on `develop` between the Task 6 build and this PR's merge — a condition to recompute at merge time, never to assume. Behavioural identity for the NAS holds regardless: nothing outside `cli/archive/` is on the pull path.

**The new entrypoint requires an image that knows `--hash-scope`.** The entrypoint is bind-mounted and re-read on any container restart, and an image predating this PR answers the option with exit 2 — the code the loop books as `capture_ok=0`, which the ops writer reads as a not-clean capture pull and skips on, fail-closed, until the dead-man pages. So leg A lands the image pin AND the entrypoint in one applied converge, and a render-only converge of this entrypoint against the old image is never run. The nas role also refuses a `nas_archive_pull_hash_scope` outside `full|incremental` — the CLI would reject it with that same exit 2.

1. **Leg A** — pull the new `-compat` digest on the NAS, prove `runtime=compat` by running polars in it, re-pin `nas_capture_image`, converge with `infra/ansible/scripts/converge.sh site.yml --limit nas -e nas_apply_compose=true`, `nas_archive_pull_hash_scope` at `full`. Wait one full pull cycle, then read all three series **by value** for every channel; `(no series)` is FAIL and means the keep-regex edit or the Alloy restart did not take. The baseline goes in leg A's pins-row commit message.
2. **Leg B** — flip `nas_archive_pull_hash_scope` to `incremental`, converge the same way with `nas_capture_image` unchanged (config-only — the flag is what recreates the container with the new value). Wait one full pull cycle, read the same series, record the drop against A's baseline in leg B's pins-row commit message, and resolve [[T0028]] with the measured horizon.
3. Prune the NAS's stale image only after leg B's row is written.

**This ordering is enforced by the plan, not by memory.** Leg B's first step requires leg A's pins-row commit — the one carrying the baseline values — to exist on the rollout branch AND to touch `docs/reference/fleet-pins.md` (`git log HEAD --grep='archive_pull baseline' --format=%h -- docs/reference/fleet-pins.md`) — `develop` cannot carry it, the rollout PR merges after leg B — and leg B's comparison reads A's per-channel numbers from that commit's message, so the token alone satisfies nothing and a skipped baseline fails the step instead of being discovered afterwards. Per `spec-plan-locations.md`, the *standing* half of this — verify a new metric family by value, and how `config.alloy` reaches the running container on this tier — lands in `fleet-deploys.md`'s NAS section in this same change, because a ruling recorded only in a spec is invisible at execution time.

## Out of scope

- **Making per-cycle cost genuinely flat** (fixed budget + cursor) — declined in D3 with the reason, not deferred.
- **An alert rule on the cost curve** — declined in D6.
- **The `hot` channel and the journal channel** — the former is a raw rsync with no verification to narrow, the latter is already `--no-verify`.
