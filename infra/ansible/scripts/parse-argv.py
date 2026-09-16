"""Ansible's own answer to "what is this argv?", for `converge.sh` to record and gate on.

Prints one TAB-separated line per field -- LIMIT, CHECK, TAGS, EXTRA (JSON) -- and nothing else;
a parse ansible would refuse exits non-zero with ansible's own message on stderr, which is the
right moment for the caller to refuse, before a preview or a pass.

No shebang on purpose: run it through the PROJECT VENV's interpreter, never the system `python3`,
which carries no ansible -- the point of this file is the parser the converge itself will use. `converge.sh` redirects both streams to files, because
ansible refuses to start on a non-blocking stdout.
"""

import json
import sys

from ansible import context
from ansible.cli.playbook import PlaybookCLI
from ansible.parsing.dataloader import DataLoader
from ansible.utils.vars import load_extra_vars


def main(argv: list[str]) -> int:
    PlaybookCLI(["ansible-playbook", *argv]).parse()
    cliargs = context.CLIARGS
    fields = {
        # Verbatim, because no parse can be wrong about it and every later question about this pass
        # is answerable from it.
        "ARGV": json.dumps(argv),
        "LIMIT": cliargs.get("subset") or "",
        "CHECK": "1" if cliargs.get("check") else "0",
        # The tags the operator PASSED: ansible's default is `('all',)`, and the row's cell has always
        # meant "un-tagged" when empty -- `count-list.sh un-tagged-primary-runs` is the rule "never run
        # site.yml un-tagged on the primary" made countable. An explicit `--tags all` runs every play
        # too, so it books the same empty cell rather than hiding from that count.
        # Sorted: tags are a SET to ansible and its iteration order is not the operator's, so an
        # unsorted cell would differ run to run for one invocation. Every reader splits on the comma.
        "TAGS": "" if tuple(cliargs.get("tags") or ()) == ("all",) else ",".join(sorted(cliargs["tags"])),
        # `load_extra_vars` opens an `@file` and YAML-loads a braced operand, so the row carries what
        # the pass received rather than what this script could re-read of it.
        "EXTRA": json.dumps(load_extra_vars(DataLoader()), sort_keys=True, default=str),
    }
    for key, value in fields.items():
        print(f"{key}\t{value}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
