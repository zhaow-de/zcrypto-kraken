---
status: open
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

## Suggested next steps

Either candidate adds a gate every session pays, so **the choice is the owner's**, not a session's.

- **A CI job running the tripwire on `pull_request` into `develop`.** Catches this instance, and also the case neither hook can see — a merge result that is red though both parents were green. Needs no per-clone state and is visible in the merge gate. Cost: another check that `merge-pr`'s evaluator blocks on when it fails.
- **A `pre-push` hook stage.** Catches this instance too, since the pushed tip measures red. Cheaper to run, but it is per-clone state: a fresh worktree or a new session's clone silently has no such hook, so the guard is absent exactly where it is most needed.
