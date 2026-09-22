#!/usr/bin/env python3
"""Fetch merged PRs since the last release tag and prepare data for changelog generation.

Writes one JSON file and prints its path on stdout, alone, so whoever runs it reads the path.
Everything a human reads goes to stderr; the path comes from `tempfile`, so two runs never collide.
"""

import json
import re
import subprocess
import sys
import tempfile
from datetime import datetime

# `gh pr list` returns at most `--limit` rows and says nothing when it truncates, so a limit below
# the real count silently drops the oldest PRs. The number is headroom; the refusal below is the
# guard, because any fixed number is outgrown eventually.
PR_LIMIT = 2000

version_result = subprocess.run(["cz", "version", "--project"], capture_output=True, text=True)
new_version = version_result.stdout.strip()
release_date = datetime.now().strftime("%Y-%m-%d")

tag_result = subprocess.run(
    ["git", "describe", "--tags", "--abbrev=0", "origin/main"],
    capture_output=True,
    text=True,
)
last_tag = tag_result.stdout.strip() if tag_result.returncode == 0 else None

last_tag_date = None
if last_tag:
    tag_date_result = subprocess.run(["git", "log", "-1", "--format=%aI", last_tag], capture_output=True, text=True)
    last_tag_date = datetime.fromisoformat(tag_date_result.stdout.strip())

result = subprocess.run(
    [
        "gh",
        "pr",
        "list",
        "--state",
        "merged",
        "--base",
        "develop",
        "--limit",
        str(PR_LIMIT),
        "--json",
        "number,title,body,url,author,mergedAt",
    ],
    capture_output=True,
    text=True,
)
prs = json.loads(result.stdout)

# `>=`, not `>`: saturation is indistinguishable from a coincidence at exactly the limit.
if len(prs) >= PR_LIMIT:
    print(
        f"REFUSING: `gh pr list` returned {len(prs)} PRs against --limit {PR_LIMIT}, so the list may be "
        f"truncated and the changelog would silently lose its oldest entries. Raise PR_LIMIT in "
        f"{__file__} above the real count and re-run.",
        file=sys.stderr,
    )
    sys.exit(1)

filtered_prs = []
for pr in prs:
    merged_at = pr.get("mergedAt")
    if merged_at:
        pr_date = datetime.fromisoformat(merged_at)
        if last_tag_date is None or pr_date > last_tag_date:
            filtered_prs.append(pr)


def parse_title(title):
    match = re.match(r"^(\w+)(?:\(([^)]+)\))?:\s*(.*)$", title)
    if match:
        return {
            "type": match.group(1),
            "scope": match.group(2) or "",
            "desc": match.group(3),
        }
    return {"type": "other", "scope": "", "desc": title}


TYPE_MAP = {
    "feat": "Features",
    "fix": "Bug Fixes",
    "refactor": "Refactoring",
    "docs": "Documentation",
    "test": "Tests",
    "ci": "CI/Build",
    "build": "CI/Build",
}

pr_data = []
for pr in filtered_prs:
    parsed = parse_title(pr["title"])
    pr_data.append(
        {
            "number": pr["number"],
            "title": pr["title"],
            "description": pr.get("body", ""),
            "url": pr["url"],
            "author": pr["author"]["login"],
            "type": parsed["type"],
            "type_label": TYPE_MAP.get(parsed["type"], "Other Changes"),
            "short_desc": parsed["desc"],
        }
    )

output = {
    "version": new_version,
    "release_date": release_date,
    "prs": pr_data,
}

with tempfile.NamedTemporaryFile(mode="w", prefix="release_pr_data_", suffix=".json", delete=False) as handle:
    json.dump(output, handle, indent=2)
    out_path = handle.name

print(f"Prepared {len(pr_data)} PRs for changelog generation", file=sys.stderr)
print(out_path)
