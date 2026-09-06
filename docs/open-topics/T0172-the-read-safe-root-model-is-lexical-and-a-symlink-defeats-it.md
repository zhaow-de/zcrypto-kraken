---
status: open
---

# The read-safe-root model is lexical, and a symlink defeats it

## Context — what

`_reads_only_safe_paths` in `infra/scripts/ops_daily.py` decides whether a content head — `cat`, `grep` — reads only paths under a read-safe root. The check is a **string test over the spelled path**: it asks whether the operand starts with one of `_READ_SAFE_DIRS`, or is one of `_READ_SAFE_FILES`. It never resolves the path, and a classifier running on the workstation cannot resolve a remote host's links.

So any symlink under a read-safe root that points outside it is read as safe. Measured, with `/var/log/dirlink` and `/var/log/filelink` standing for a planted link, every one of these classifies **AUTONOMOUS** on both `ops` and `zcrypto`, and every one reads a file outside the spelled root on GNU grep 3.11 and ugrep 7.8.4 alike:

```
grep -r <pattern> /var/log/dirlink
grep <pattern> /var/log/filelink
grep -r <pattern> /var/log/*
cat /var/log/filelink
grep -irn <pattern> /var/log/dirlink
```

### What the letter fix closes, and what it does not

**The distinction that matters, and that the fix on `feat/t0168-unasserted-claims` does not close.** `-R` follows a symlink met while *descending* a spelled directory, where `-r` does not; that is why the letter was dropped from the grep shape — it widens what a safe root reaches. It is not why the class is open. An operand that is *itself* a link — spelled, or landed there by a glob — is read through by `-r`, `-R` and a bare `grep` alike, and no flag letter closes that. The corrected rationale is in `_FIRST_STAGE_SHAPES`' grep entry comment; the branch's test `test_the_R_spelling_of_a_recursion_classifies_prepared` asserts only the letter, and `test_no_grep_shape_admits_a_dereferencing_option` plus `test_the_grep_shapes_admit_exactly_the_pinned_surface` hold every probed short spelling and any `--der…` long form across every grep shape, and pin the admitted surface so a further spelling cannot be added silently — `--dereference-recursive`, GNU's long form, escaped a letters-only probe until a review measured it.

### Why it is a topic and not a fix

It needs a **pre-planted link**, and no autonomous shape can create one: `ln -s /etc/shadow /var/log/x` classifies PREPARED. That is why this is a topic rather than a fix.

### A second instance, one head further out

`ls` carries `-R` too, and both `ls -R /var/log` and `ls -R /var/log/dirlink` classify AUTONOMOUS. The exposure differs in kind — through a planted link it lists NAMES outside a safe root rather than contents — and `ls` sits outside `_CONTENT_HEADS` by design, because the runbooks' own permission check on `logship-secrets.env` reads `ls`/`stat` without printing bytes. So the safe-root check never applies to it at all, and any answer chosen below has to say whether it should.

## Why this matters

The daily pass reads those roots autonomously on ops, the NAS and zaccess. A planted link is a one-time write by anyone holding the deploy user — so the model's guarantee is "no operand NAMES a path outside a safe root", which is weaker than the guarantee its name implies and weaker than a reader will assume.

## Findings so far

Found while closing a different defect on the same helper on `feat/t0168-unasserted-claims`: the grep recursion flag `-R` dereferences symlinks met during traversal, so a link under a safe root leads the read outside it. Removing that flag closed the traversal entry, and the branch's guards now hold its absence across every grep shape and pin the shapes' admitted surface. The wider class — every content head, through an operand that is itself a link — is unchanged and is what this topic holds. Its long-form spellings were measured on both binaries here: GNU accepts every unambiguous abbreviation of `--dereference-recursive`, ugrep spells the same hazard `--dereference` and `--dereference-files`, and the branch reads them as the prefix `--der` rather than as a list.

## Suggested next steps

- **A decision at pick time, not a task**: resolve the spelled path with `realpath` on the HOST before the read, or refuse any operand under a safe root that IS a symlink. The first is a host-side check the classifier cannot make from the workstation, which is the whole difficulty; the second is checkable where the classifier already runs but refuses a shape that may be legitimate.
- Decide whether `ls` joins `_CONTENT_HEADS`, or whether the answer covers name-listing heads some other way.
- Whichever is chosen, the safe-root docstring says what the model guarantees — that no operand NAMES a path outside a safe root — rather than implying it guarantees the read stays inside one.
