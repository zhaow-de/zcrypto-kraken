---
status: resolved
---

# The prose ratchet's verdict is a tree property, and no gate evaluates it after a rebase or a merge

## Context — what

`infra/scripts/prose-tripwire.py --check-baseline` measures **every tracked file** against `infra/scripts/prose-tripwire-baseline.txt` as the tree holds it — the hook is declared `pass_filenames: false`, `always_run: true`, so its verdict is a property of the whole tree rather than of the commit being made. It is enforced in exactly one place: the `pre-commit` hook, which is the only hook installed in the main checkout.

Any operation that writes commits without running that hook therefore produces an unmeasured tree. `git rebase` is the routine one; `git merge` and a server-side merge are the same shape. `.github/workflows/` holds `capture-image.yml` and `coverage.yml`, and neither runs pre-commit or the tripwire, so no CI check evaluates it and the PR merge gate cannot see it. The result is a tip nothing has evaluated: a rebase replays commits without running the hook, so the ratchet never ran against the replayed tips at all. It is not that they passed — it is that nothing measured them, and four of #451's eight are red when measured after the fact.

## Why this matters

It landed a red `develop` and stopped the line for every session. The failure is silent and delayed: an offender rides in on a rebase, merges through a gate structurally unable to see it, and surfaces as a refused commit in the next unrelated session — which must then prove the row is not its own before it can work. That is the contamination pressure that makes absorbing another branch's offender into an unrelated commit look attractive, which `open-topics.md` forbids for good reason.

The config already knows: the comment above the hook says the baseline is "regenerated at every rebase". Nothing mechanises that.

## Findings so far

Measured instance: `develop` at `8e639df0` reports `infra/scripts/check-agent-lessons.py:1: file-prose 21.1 > 20`, with the baseline recording no entry for that file — a new offender, not a grown keep. It arrived via #451's wholesale rebase; every commit on that branch carries a committer date of 02:26:54 or 02:27:19 against author dates spread across the preceding hour.

The ratchet run at each commit of `7e5bbe17..2c20c8e2`, reproduced against the still-reachable objects:

| commit | exit | file-prose |
| --- | --- | --- |
| `986c0fd8` | 0 | — |
| `b54bf138` | 0 | — |
| `ce3515c6` | 0 | — |
| `6321d192` | 1 | 20.6 |
| `f744b6f4` | 1 | 20.6 |
| `6e86d5b6` | 0 | — |
| `8b6d698e` | 1 | 21.1 |
| `2c20c8e2` | 1 | 21.1 |

Post-#450 `develop` at `7e5bbe17` is clean, exit 0.

The baseline explains none of it. It was never touched on that branch — `git log --oneline --name-only 7e5bbe17..2c20c8e2 -- infra/scripts/prose-tripwire-baseline.txt` is empty — and records no entry for this file, so every red above is `new: 1` and there was never a recorded keep to outgrow. Re-measured with the tripwire's own `measure_python`:

| revision | total | prose | code | pct |
| --- | --- | --- | --- | --- |
| `7e5bbe17` | 55 | 9 | 38 | 16.4 |
| `6321d192` | 68 | 14 | 46 | 20.6 |
| `6e86d5b6` | 70 | 14 | 48 | 20.0 |
| `8b6d698e` | 71 | 15 | 48 | 21.1 |
| `2c20c8e2` | 71 | 15 | 48 | 21.1 |

Prose is unchanged, 14 to 14, across `6e86d5b6` — the commit that went green. It condensed one comment and added `import io`, a `line = raw.rstrip()` and a two-line comment: net **+2 code lines**, and the ratio fell to exactly 20.0. The file left the bar by gaining code, not by losing prose.

**That is the property worth carrying away.** The measure is a RATIO, so a file leaves the bar by gaining code as readily as by cutting prose, and the comparison is strict — `prose * 100 > FILE_PROSE_PERCENT * total` with `FILE_PROSE_PERCENT = 20` — so a file resting at exactly 20.0 passes by nothing at all, and the next comment line re-reds it.

Not measured, and so not established: whether the pre-rebase originals of those commits were green. Those objects are likely gone.

## Resolution

**The owner ruled for the `pre-push` stage over a CI job.** Closed by `.pre-commit-config.yaml` declaring `stages: [pre-commit, pre-push]` on `prose-tripwire`, plus `default_stages: [pre-commit]` and an explicit `stages: [pre-commit]` on the five upstream hooks whose own manifest declares `pre-push` — without those, installing the hook type puts all eighteen hooks in the push stage, and two of the five rewrite files.

Proven both ways against a local bare repo as the remote, from a clone carrying only the pre-push hook: a green tree pushes and the ref moves; a tree at `file-prose 21.1 > 20` is refused with `hook id: prose-tripwire`, and the remote ref does not move.

**The objection this topic raised against `pre-push` was false, and correcting it is why the option was nearly lost.** A worktree's hooks are not per-worktree state: `git rev-parse --git-path hooks` in every linked worktree resolves to the main checkout's `.git/hooks`, because a worktree's `.git` is a file pointing at the common directory. One install covers every worktree, present and future. `core.hooksPath` is unset here.

**`/usr/share/git-core/templates/hooks` is not the mechanism**, since it will be asked again. A template directory is copied into a repository at `git init` / `git clone` time only, so editing one does nothing for a repository that already exists; that system path is root-owned; and `init.templateDir` is unset at every level here. For *future* clones the supported path is `pre-commit init-templatedir`, which needs no root.

**The local step.** `pre-commit install --hook-type pre-push` is per-clone and is not carried by the repository: a fresh clone has to run it again, and the tracked `stages:` declarations are what make the intent version-controlled rather than folklore.
