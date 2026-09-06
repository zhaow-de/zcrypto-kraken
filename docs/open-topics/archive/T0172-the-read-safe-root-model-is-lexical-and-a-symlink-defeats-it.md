---
status: resolved
---

# The read-safe-root model is lexical, and a symlink defeats it

## Context — what

`_reads_only_safe_paths` in `infra/scripts/ops_daily.py` **decided on its own** whether a content head — `cat`, `grep` — read only paths under a read-safe root; today it answers for the SPELLED paths and `_resolves_only_safe_paths` carries what those names reach. The check was a string test over the spelled path alone: it asked whether the operand started with one of `_READ_SAFE_DIRS`, or was one of `_READ_SAFE_FILES`, and never resolved it — while a classifier running on the workstation cannot resolve a remote host's links by itself.

So any symlink under a read-safe root that pointed outside it was read as safe. Measured, with `/var/log/dirlink` and `/var/log/filelink` standing for a planted link, every one of these classified **AUTONOMOUS** on both `ops` and `zcrypto`, and every one reads a file outside the spelled root on GNU grep 3.11 and ugrep 7.8.4 alike:

```
grep -r <pattern> /var/log/dirlink
grep <pattern> /var/log/filelink
grep -r <pattern> /var/log/*
cat /var/log/filelink
grep -irn <pattern> /var/log/dirlink
```

### What the letter fix closed, and what it did not

**The distinction that matters, and that the fix on `feat/t0168-unasserted-claims` did not close.** `-R` follows a symlink met while *descending* a spelled directory, where `-r` does not; that is why the letter was dropped from the grep shape — it widens what a safe root reaches. It was not why the class was open. An operand that is *itself* a link — spelled, or landed there by a glob — is read through by `-r`, `-R` and a bare `grep` alike, and no flag letter closes that. The corrected rationale is in `_FIRST_STAGE_SHAPES`' grep entry comment; the branch's test `test_the_R_spelling_of_a_recursion_classifies_prepared` asserts only the letter, and `test_no_grep_shape_admits_a_dereferencing_option` plus `test_the_grep_shapes_admit_exactly_the_pinned_surface` hold every probed short spelling and any `--der…` long form across every grep shape, and pin the admitted surface so a further spelling cannot be added silently — `--dereference-recursive`, GNU's long form, escaped a letters-only probe until a review measured it.

### Why it was a topic and not a fix

It needed a **pre-planted link**, and no autonomous shape can create one: `ln -s /etc/shadow /var/log/x` classifies PREPARED. That is why it was parked here rather than fixed inside the branch that found it.

### A second instance, one head further out

`ls` carries `-R` too, and both `ls -R /var/log` and `ls -R /var/log/dirlink` classify AUTONOMOUS. The exposure differs in kind — through a planted link it lists NAMES outside a safe root rather than contents — and `ls` sits outside `_CONTENT_HEADS` by design, because the runbooks' own permission check on `logship-secrets.env` reads `ls`/`stat` without printing bytes. So the safe-root check never applies to it at all, and the Resolution below says why that was kept.

## Why this matters

The daily pass reads those roots autonomously on ops, the NAS and zaccess. A planted link is a one-time write by anyone holding the deploy user — so the model's guarantee was "no operand NAMES a path outside a safe root", which was weaker than the guarantee its name implied and weaker than a reader would assume.

## Findings so far

Found while closing a different defect on the same helper on `feat/t0168-unasserted-claims`: the grep recursion flag `-R` dereferences symlinks met during traversal, so a link under a safe root leads the read outside it. Removing that flag closed the traversal entry, and the branch's guards now hold its absence across every grep shape and pin the shapes' admitted surface. The wider class — every content head, through an operand that is itself a link — was unchanged by that flag removal and is what this topic held. Its long-form spellings were measured on both binaries here: GNU accepts every unambiguous abbreviation of `--dereference-recursive`, ugrep spells the same hazard `--dereference` and `--dereference-files`, and the branch reads them as the prefix `--der` rather than as a list.

## Resolution (2026-09-06)

**The host-side pre-check, chosen over refusing every operand that is a symlink.** `classify_action` and `_classify_one` take a required keyword `resolve`, a callable `(host, operands) -> list[str]`; where the veto in `_matches` has found a first-stage content head's spelled operands safe, the host is asked what those operands really name and `_path_is_read_safe` — the same predicate, now factored out of `_reads_only_safe_paths` — is applied to every path that comes back. The live resolver `ssh_resolve` runs `readlink -f` over all the operands in one ssh, so a link chain answers its final target and a glob answers the expansion the remote shell made. Three states are refusals rather than answers: no `--host` (there is no filesystem to resolve on), a resolver that raises, and an operand the host resolves to nothing.

**The one conscious drop: `ls`.** It stays outside `_CONTENT_HEADS` and nothing about it is resolved, so `ls -R /var/log/dirlink` still lists through a planted link. What it exposes is NAMES outside a safe root, never contents, and the runbooks' own permission check on `logship-secrets.env` reads `ls`/`stat` without printing bytes — the read-safe model is for the heads that print them.

**What the docstrings now claim.** `_reads_only_safe_paths` says what it tests — the paths a content head SPELLS — and `_resolves_only_safe_paths` carries the claim about what those names reach, so neither implies the other's guarantee.
