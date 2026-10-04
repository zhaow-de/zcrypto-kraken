"""The live text of a hand-edited Alloy config or Jinja secrets template: comments blanked, line count kept."""

import re
from pathlib import Path


def live_alloy_text(path: Path) -> str:
    """The config with its comments blanked; a `//` inside a quoted string (a URL) is part of the string."""
    text = path.read_text()
    out, i, n = [], 0, len(text)
    while i < n:
        if text[i] == '"':
            j = i + 1
            while j < n and text[j] != '"':
                j += 2 if text[j] == "\\" else 1
            out.append(text[i : j + 1])
            i = j + 1
        elif text.startswith("//", i):
            j = text.find("\n", i)
            i = n if j < 0 else j
        elif text.startswith("/*", i):
            j = text.find("*/", i + 2)
            end = n if j < 0 else j + 2
            out.append("\n" * text.count("\n", i, end))
            i = end
        else:
            out.append(text[i])
            i += 1
    return "".join(out)


def live_j2_text(path: Path) -> str:
    return re.sub(r"\{#.*?#\}", lambda m: "\n" * m.group(0).count("\n"), path.read_text(), flags=re.S)
