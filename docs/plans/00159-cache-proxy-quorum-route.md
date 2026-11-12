# The cache proxy cuts the engine's sessions only when the Sentinels contradict its route Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The engine's cache proxy carries both sessions on one route server per node, cut only when the Sentinels the proxy can read contradict that node, with new sessions still routed on two votes, proven on the pinned HAProxy 3.4.5 binary before rollout.

**Architecture:** `haproxy.cfg.j2` gives each node a votes backend of three check-only servers and a route backend of one server checked against a loopback `frontend quorum` (D1, D2, D3, D4). `infra/scripts/cache-proxy-harness.py` fetches the pinned image's layers (the coordinator's network read) and runs the role's render on that binary in an unprivileged namespace against scripted Sentinels and Valkeys, nine cases (D7). The no-backend page, panel 402, the proxy row, the Alloy fixtures, two runbooks and the rollout skill read the new names and rule (D5, D10). The rollout is one gap-bound engine converge, outside every task (D6, D11).

**Tech Stack:** Python 3.14, pytest, Jinja2 (the role's settings), HAProxy 3.4.5 (pin `76928c0d6b39`), `unshare`, `/usr/bin/ip`, `/usr/sbin/nft`, `infra/scripts/mutate-probe.sh`.

**Spec:** `docs/specs/00159-cache-proxy-quorum-route-design.md`

## Global Constraints

- The spec, `docs/specs/00159-cache-proxy-quorum-route-design.md` in this worktree, is the authority; a task that names one of its sections reads it there — Task 2 *The template*, Task 3 *The harness* and *Left to the implementer*, Task 4 *The alert and its panel*, Task 6 *Runbook texts*, Task 7 *Change list* — and where it is silent this plan rules, in the task the ruling binds. Exact copy the spec fixes — the template, the alert's model block and annotations, the panels, the runbook passages, the rollout skill's clauses — is taken from the spec's own fenced blocks and bullets, verbatim; where the spec's text cannot pass a gate as written, the task stops and the coordinator amends the spec, as P0 did, never the copy.
- The worktree is `/home/zhaow/Projects/zcrypto-kraken/.claude/worktrees/proxy-quorum` (branch `feat/00159-cache-proxy-quorum-route`); every command runs with it as the working directory. Each task's scratch is `.tmp/00159/t<N>/`, its own, removed by the task before its report; no shell variable outlives the call that set it.
- `ROOTFS` is `/home/zhaow/Projects/zcrypto-kraken/.claude/worktrees/proxy-quorum/.tmp/00159/haproxy-76928c0d6b39`, the pinned image's unpacked tree, written by the coordinator's fetch (*Outside the implementer's tasks*, P1) after Task 1 and before Task 2. No implementer runs `cache-proxy-harness.py fetch`, writes under `ROOTFS`, or runs anything Python from inside it; every `run` names it in full.
- `PROCS` is `pgrep -af -- '/[.]tmp/00159/'`, each read its own call, one before and one after every harness run, the two compared: every process a run starts but its `ip` and `nft` calls, which end before it goes on, carries an absolute path under `.tmp/00159/` in its command line (Task 3's Interfaces), and the bracket keeps the read from matching the shell that runs it. `pgrep -a haproxy`, which matches the process name, sees none of them: a binary run through the loader takes the loader's name — `/lib64/ld-linux-x86-64.so.2 /bin/cat /proc/self/comm` printed `ld-linux-x86-64` — and a scripted peer takes its interpreter's. A PID the second read lists and the first did not goes to the coordinator with its command line, and is stopped by that PID.
- A run's files are `<scratch>/run-<YYYYmmddTHHMMSSZ>-<pid>/`, one directory per case and `maps/` for the once-per-run HAProxy, each holding `haproxy.cfg`, `haproxy.out` and `haproxy.err` (Task 3's Interfaces). Every call that runs the harness, directly or through `mutate-probe.sh`, takes the Bash tool's `timeout` of 600000 ms, never the default.
- No ssh, docker, `ansible-playbook`, `converge.sh`, `grafana-push.sh`, `grafana-query.py`, Grafana or Kraken call, and no network fetch in any task; never `tests/test_grafana_push_sh.py`. Every tree search is `git grep -l <pattern> -- <paths>` with `infra/scripts/consumers.sh`'s `VAULT_EXCLUDES` pathspecs.
- Order: one task at a time, in number order, Task 1 to Task 8, each after the last one's final commit: the tasks share one worktree, `mutate-probe.sh` refuses a dirty worktree and a second run in the checkout, and the gate's rewrites are staged by path, so two tasks at once would refuse each other's probes and could mix their commits. P1, the coordinator's, runs after Task 1's verdict commit and before Task 2; it writes only the gitignored tree under `.tmp/`.
- Tests per commit, one call: `S=.tmp/00159/t<N>; mkdir -p "$S"; T="$(infra/scripts/consumers.sh --tests --direct <the commit's changed paths> 2>"$S/consumers.err" | grep -v -x tests/test_grafana_push_sh.py) <the task's own test files>"; uv run pytest $T -m "not slow" -n auto -q -p no:cacheprovider --basetemp="$S/pt"`. Every task names its own test files, so `$T` is never empty. Read `$S/consumers.err` before using the result; a refusal there other than `found no test file` re-runs the line. Read the result line in a separate call before writing the commit message, and quote it with the command in full.
- `WALKERS`, for a task that edits a page under `infra/runbooks/`: `uv run pytest tests/test_internal_terms_not_operator_visible.py tests/test_runbook_internal_tokens.py tests/test_runbook_triggers.py tests/test_infra_alert_rules.py tests/test_ops_daily.py tests/test_guidance_guard.py tests/test_count_list.py tests/test_guidance_refs_resolve.py tests/test_code_prose_citations.py -q -p no:cacheprovider --basetemp=.tmp/00159/t<N>/walkers`.
- The gate is `uv run pre-commit run -a`, re-run until clean, its rewrites staged. Stage by explicit path, new files first; `infra/scripts/cache-proxy-harness.py` opens `#!/usr/bin/env python3` and is `chmod +x` before its first `git add`.
- A comment or docstring stays only where a reader would act differently without it, and is correct; state and decisions stay, an event goes to the PR body. No code prose cites a plan task number. No string literal under `infra/scripts/` and no operator-read text carries a spec serial or a decision number (`tests/test_internal_terms_not_operator_visible.py`): the start bound prints as `3.40 s`, the engine's retry budget. An existing Markdown file keeps its shape.
- Commits: Conventional Commits; a `.claude/` change is its own `claude(` commit. Every message says what changed and carries the result line of the test command it names, run over its own tree, and ends with `Co-Authored-By: Claude <the executing model> <noreply@anthropic.com>`, the implementer's own model in place of the placeholder, and the `Claude-Session:` line its dispatch brief gives. One state-changing git command per Bash call; never amend, never `--no-verify`.
- Probes. The tier, from `uv run python infra/scripts/tier.py --paths <every path below under File structure, in its listed order>`:

```
tier: full
full infra/ansible/roles/engine/templates/haproxy.cfg.j2 — under infra/ansible/roles/engine/, read as a non-prose change
full infra/ansible/roles/engine/defaults/main.yml — under infra/ansible/roles/engine/, read as a non-prose change
full tests/test_infra_alert_rules.py — a test importing cli.engine.store, read as a non-prose change
full infra/grafana/alerts.yaml — under infra/grafana/alerts.yaml, read as a non-prose change
full .claude/skills/zcrypto-rollout-image/SKILL.md — under .claude/, read as a non-prose change
```

- Each arm a task lists runs as its own call, on the committed tree, after the commit it proves: `infra/scripts/mutate-probe.sh --file <f> --control '<control>' --mutation '<sed>' -- <probe>`. A pytest arm's probe is `uv run pytest <its test file> -k '<its case>' -q -p no:cacheprovider --basetemp=.tmp/00159/t<N>/pt` and its control `1,$d`. A harness arm's probe is `uv run python infra/scripts/cache-proxy-harness.py run --rootfs <ROOTFS> --scratch .tmp/00159/t<N>/probe --case <its case>` and its control `s/^global$/glob4l/`, an unknown top-level keyword chosen so that HAProxy refuses the render and every case fails; `mutate-probe.sh` proves that on each arm, refusing one whose control passes. An arm the plan names by its effect, not by a `sed`, takes the `sed` the implementer writes to reach that one site; `mutate-probe.sh` refuses a `sed` that changes nothing. The task's verdicts go in one empty commit naming `infra/scripts/mutate-probe.sh`, each arm's verdict line as the script printed it.

## File structure

- Create: `infra/scripts/cache-proxy-harness.py`, `tests/test_cache_proxy_harness.py`.
- Modify: `infra/ansible/roles/engine/templates/haproxy.cfg.j2`, `infra/ansible/roles/engine/defaults/main.yml`, `tests/test_infra_cache_proxy.py`, `tests/test_infra_alert_rules.py`.
- Modify: `infra/grafana/alerts.yaml`, `infra/grafana/cache-dashboard.json`, `tests/test_dashboards_cover_metrics.py`, `tests/test_infra_alloy_levels.py`.
- Modify: `infra/runbooks/cache.md`, `infra/runbooks/engine-procedures.md`, `docs/specs/00118-engine-cache-design.md`, `docs/specs/00120-engine-cache-engine-half-design.md`, `docs/research/14.phase6-decisions.md`.
- Modify, in its own `claude(skills)` commit: `.claude/skills/zcrypto-rollout-image/SKILL.md`.

## Review Focus

- The pinned binary loading this workstation's libraries instead of the image's — an absolute link in the tree, followed outside it, names a host path — so the harness proves another build: every tree path resolves against `--rootfs`, and a run whose HAProxy maps an executable file from outside the tree is refused, while a mapping that is no file of code — `[heap]`, `[vdso]`, a shared anonymous area reading `/dev/zero (deleted)` — refuses nothing. Task 3, `test_a_mapping_outside_the_tree_is_foreign`.
- A run that did not land in a fresh namespace on `zcrypto-ops`, a live fleet host: nothing is bound and no `nft` rule written unless `lo` is the only interface the namespace's own list names. Task 3, `test_the_run_refuses_a_namespace_with_any_interface_but_lo` (the predicate) and `test_the_inner_run_starts_nothing_in_a_namespace_with_any_interface_but_lo` (its place before every start, and its source, `socket.if_nameindex()`); the maps read's target, the listening HAProxy's own `/proc/<pid>/maps` against `--rootfs`'s realpath, is the task reviewer's read.
- A case that raises or overruns: it prints a `FAIL` line and every process it started is stopped by its own PID, never by its command line, so no HAProxy or peer outlives the run and nothing else is stopped. Task 3, `test_a_case_that_raises_prints_fail_and_stops_every_process_it_started`; Task 3 Steps 5 and 7 read it on the live host with `PROCS`, the process name of a binary run through the loader being the loader's. Its `nft` table is deleted by `stop_all()` at its end, and every scripted peer binds its listener with `SO_REUSEADDR`, a full run's cases sharing one namespace: no unit test holds either, so the task reviewer reads both, and a rule a case left shows first in Step 5's full run, as a later case's `FAIL`.
- A layer whose member, hard link or whiteout names a path outside the tree, by its own text or through a link a lower layer laid: the fetch is refused before anything is written or deleted, and nothing outside the tree changes. Task 1, `test_the_fetch_writes_no_member_outside_its_tree`.
- A later layer's entry at a path a lower layer made a link: it replaces the link, is never written through it, and is not refused for where the old link pointed. Task 1, `test_a_later_layer_replaces_a_lower_layers_link`.
- A later layer's whiteouts: the named file and an opaque directory's lower contents are gone, and no `.wh.` file is left in the tree. Task 1, `test_a_later_layers_whiteouts_remove_what_they_name`.

---

### Task 1: The harness's render and fetch

**Files:** Create `infra/scripts/cache-proxy-harness.py`, `tests/test_cache_proxy_harness.py`.

**Interfaces:**
- Produces, in `infra/scripts/cache-proxy-harness.py`: `NODES` — `({"name": "node1", "address": "127.0.0.11"}, {"name": "node2", "address": "127.0.0.12"}, {"name": "node3", "address": "127.0.0.13"})`; `MASTER_NAME = "zcache"`; `REQUIREPASS`, a dummy no fleet value resembles; `TEMPLATE`, the role's `haproxy.cfg.j2` resolved from the script's own path; `EDITS`, a tuple of `(old, new)` whole-line pairs, each line with its newline — `chroot /var/lib/haproxy`, `user haproxy` and `group haproxy` each to `""`, `bind 0.0.0.0:6379` to `bind 127.0.0.1:6379`, all four-space indented — declared on its own `EDITS = (` line; `render(template: str) -> str`, the template through `jinja2.Environment(trim_blocks=True, lstrip_blocks=False, undefined=jinja2.StrictUndefined)` with `engine_cache_proxy_nodes=list(NODES)`, `engine_cache_proxy_master_name=MASTER_NAME`, `cache_sentinel_requirepass=REQUIREPASS`, then each `EDITS` pair by `str.replace`.
- Produces: `class FetchRefused(Exception)`; `IMAGE_DIGEST_FILE = ".harness-image-digest"`; `fetch(digest: str, into: Path, get: Callable[[str, Mapping[str, str]], bytes] = <the urllib getter>) -> None` — an anonymous Docker Hub pull of `library/haproxy` by index digest, every index, manifest and blob checked through one `_verified(body: bytes, digest: str) -> bytes` whose test reads `if "sha256:" + hashlib.sha256(body).hexdigest() != digest:`, the `linux/amd64` manifest's layers applied in order into `into` (absent or empty, else `FetchRefused`), and last `into / IMAGE_DIGEST_FILE` holding the digest. The default getter is `urllib.request`'s and sends the registry's bearer token through `Request.add_unredirected_header`, so a blob's redirect to its storage host carries no `Authorization` header.
- Produces, for each layer member, in this order, every check before anything is written or deleted:
  - its name, a hard link's `linkname`, and a whiteout's target name (the member's last component with `.wh.` stripped) each pass `_member_ok(name: str) -> bool`, false for an absolute name or one holding a `..` component, its body one `return` line and no docstring;
  - the directory its name's parent names, and a hard link's whole target, resolve through `_inside(into: Path, path: str) -> Path`: `os.path.realpath(into / path, strict=os.path.ALLOW_MISSING)`, links followed as the host follows them, returned only when it is `into`'s own realpath or lies under it followed by `/`, else `FetchRefused`;
  - a whiteout then acts on that resolved directory and is never written: `.wh.<name>` removes `<name>` there, a directory with its contents and a link as the link, never followed; `.wh..wh..opq` empties that directory of what lower layers put there;
  - any other member: an existing entry at its path in that resolved directory is removed, a link as the link and never followed, unless both it and the member are directories — so a later layer replaces a lower one's link rather than writing through it, and the filter never resolves the old link's target — then the member is extracted through `tarfile` with `filter="tar"`, Python 3.14's default being `data` (`tarfile.TarFile._get_filter_function` returns `data_filter` when no filter is named), which refuses the absolute links an image carries;
  - a refused name, a path `_inside` refuses, or a `tarfile.FilterError` is raised as `FetchRefused`.
- Produces the CLI: `cache-proxy-harness.py fetch --digest sha256:<64 hex> --into <dir>`, one line per blob verified and a last line naming the tree and the digest's first 12 hex; exit 0 fetched, 2 refused (`FetchRefused`, a non-empty `--into` among its causes), 1 any other error, printed. Task 3 adds `run`.

- [ ] **Step 1: The failing tests,** `tests/test_cache_proxy_harness.py`, importing `difflib`, `hashlib`, `importlib.util`, `io`, `json`, `os`, `tarfile`, `jinja2`, `pytest` and `yaml`, `Callable` from `collections.abc` and `Path` from `pathlib`, with `REPO = Path(__file__).resolve().parents[1]`, the module loaded with `importlib.util.spec_from_file_location("cache_proxy_harness", REPO / "infra/scripts/cache-proxy-harness.py")` as `harness`, and `TEMPLATE = REPO / "infra/ansible/roles/engine/templates/haproxy.cfg.j2"`. Two helpers: `_layer(entries: dict[str, bytes | str | None | tuple[str, str]]) -> bytes`, a gzipped tar whose `bytes` value is a file, `str` a symlink's target, `None` a directory and `("hard", <target>)` a hard link to `<target>`, in insertion order; `_registry(*layers: bytes, impostor: bytes | None = None) -> tuple[str, Callable, list[str]]`, the index digest, a `get(url, headers)` answering a URL holding `/token` with `{"token": "t"}`, `/manifests/<a platform manifest's digest>` with that manifest, any other `/manifests/<digest>` with the index — the index listing, in this order, a `linux`/`arm64` manifest whose one layer is `{"usr/local/sbin/haproxy": b"other"}`, the `linux`/`amd64` manifest (a config blob and the layers given), and an `unknown`/`unknown` attestation manifest naming no layer, so a fetch that takes the first entry or matches `os` alone unpacks `other` — `/blobs/<digest>` with the blob, the last layer's digest answered with `impostor` in its place when one is given, and raising `LookupError(url)` otherwise, and the list of URLs asked in order.

```python
def test_the_harness_render_differs_from_the_roles_only_in_the_named_lines():
    env = jinja2.Environment(trim_blocks=True, lstrip_blocks=False, undefined=jinja2.StrictUndefined)
    text = TEMPLATE.read_text()
    role = env.from_string(text).render(
        engine_cache_proxy_nodes=list(harness.NODES),
        engine_cache_proxy_master_name=harness.MASTER_NAME,
        cache_sentinel_requirepass=harness.REQUIREPASS,
    )
    changed = [ln for ln in difflib.ndiff(role.splitlines(), harness.render(text).splitlines()) if ln[:2] in ("- ", "+ ")]
    assert changed == ["-     chroot /var/lib/haproxy", "-     user haproxy", "-     group haproxy", "-     bind 0.0.0.0:6379", "+     bind 127.0.0.1:6379"]
    assert [n["address"] for n in harness.NODES] == ["127.0.0.11", "127.0.0.12", "127.0.0.13"]
    defaults = yaml.safe_load((REPO / "infra/ansible/roles/engine/defaults/main.yml").read_text())
    # The anchored expect's length marker reads as the fleet's.
    assert [len(n["address"]) for n in harness.NODES] == [len(n["address"]) for n in defaults["engine_cache_proxy_nodes"]]


def test_the_fetch_refuses_an_index_whose_digest_is_not_the_pin(tmp_path):
    digest, get, asked = _registry(_layer({"usr/local/sbin/haproxy": b"pinned"}))
    other = "sha256:" + hashlib.sha256(b"another index").hexdigest()
    with pytest.raises(harness.FetchRefused):
        harness.fetch(other, tmp_path / "refused", get=get)
    assert not any("/blobs/" in url for url in asked)
    assert not (tmp_path / "refused").exists() or not any((tmp_path / "refused").iterdir())
    harness.fetch(digest, tmp_path / "pinned", get=get)
    assert (tmp_path / "pinned/usr/local/sbin/haproxy").read_bytes() == b"pinned"
    assert (tmp_path / "pinned" / harness.IMAGE_DIGEST_FILE).read_text().strip() == digest
```

  - `test_the_fetch_writes_no_member_outside_its_tree`, parametrised by id: `tmp_path/outside` holds `victim`, reading `kept`, and `pointer`, a symlink to `victim`; a base layer `{"etc/base": b"b"}`, with `"link": str(tmp_path / "outside")` beside it for the three `-through-a-link` ids, then the id's layer; `fetch` into `tmp_path / "tree"` raises `FetchRefused`, the tree's `etc/base` still reads `b`, and `tmp_path/outside` still lists `pointer` and `victim` alone, `victim` reading `kept` with `st_nlink` 1 and `pointer` a link to it, and the tree holds no `IMAGE_DIGEST_FILE`. The ids' layers:
    - `dotdot`: `{"../outside/planted": b"x"}`;
    - `member-through-a-link`: `{"link/pointer": b"x"}`;
    - `whiteout-through-a-link`: `{"link/.wh.victim": b""}`;
    - `whiteout-of-dotdot`: `{"etc/.wh...": b""}`, a whiteout whose target is `..`;
    - `hard-link-out`: `{"x": ("hard", "../outside/victim")}`;
    - `hard-link-through-a-link`: `{"x": ("hard", "link/victim")}`, a target `_member_ok` admits and `_inside` alone refuses.
  - `test_a_later_layer_replaces_a_lower_layers_link`: layers `{"etc/alt": "/usr/bin/x", "etc/f": b"lower", "etc/g": "f"}` then `{"etc/alt": "/usr/bin/y", "etc/g": b"upper"}`. After `fetch`, `os.readlink(tree / "etc/alt")` reads `/usr/bin/y`, `etc/g` is a file and no link, reading `upper`, and `etc/f` reads `lower`.
  - `test_a_later_layers_whiteouts_remove_what_they_name`: layers `{"etc/a": b"a", "etc/b": b"b", "opt/x/old": b"o"}` then `{"etc/.wh.a": b"", "opt/x/.wh..wh..opq": b"", "opt/x/new": b"n"}`; after `fetch`, `etc/a` is absent, `etc/b` reads `b`, `opt/x` lists `new` alone, and `tree.rglob(".wh.*")` finds nothing.
  - `test_the_fetch_refuses_a_layer_whose_bytes_are_not_its_digest`: `_registry(_layer({"usr/local/sbin/haproxy": b"pinned"}), impostor=_layer({"usr/local/sbin/haproxy": b"impostor"}))`, a whole gzipped tar served under the pinned layer's digest; `fetch` into `tmp_path / "tree"` raises `FetchRefused`, and the tree holds neither `usr/local/sbin/haproxy` nor `IMAGE_DIGEST_FILE`.
  - `test_the_fetch_refuses_a_tree_already_holding_a_file`: `tmp_path/tree` holds `left`, reading `partial`; `fetch` of `_registry(_layer({"usr/local/sbin/haproxy": b"pinned"}))`'s digest into it raises `FetchRefused`, and the tree still lists `left` alone, reading `partial`.
- [ ] **Step 2: Run them and read them fail** at the module load.
- [ ] **Step 3: The module** as the Interfaces block says, its docstring stating `fetch` and its exits, that it is a network read and that the tree is never executed from as Python; Task 3 adds `run` to it. No test reaches the network: every `fetch` in a test passes `get=`.
- [ ] **Step 4: Tests** with `tests/test_cache_proxy_harness.py` and `tests/test_internal_terms_not_operator_visible.py` as the task's own, the gate, commit `feat(infra): the cache proxy harness renders the role's config for a namespace and fetches the pinned image's layers`.
- [ ] **Step 5: Probes,** pytest arms, each KILLED:
  - `--file infra/scripts/cache-proxy-harness.py`, `-k test_the_harness_render_differs_from_the_roles_only_in_the_named_lines`: a substitution the list does not name, on a line today's template and the spec's both carry, `s/^EDITS = ($/&\n    ("timeout check 2s", "timeout check 3s"),/`;
  - same file, `-k test_the_fetch_refuses_an_index_whose_digest_is_not_the_pin`: the comparison inverted, `s/hexdigest() != digest/hexdigest() == digest/`; and the platform selection taking the index's first manifest, by effect — the tree's `haproxy` then reads `other`;
  - same file, `-k 'test_the_fetch_writes_no_member_outside_its_tree and member-through-a-link'`: `_inside` returning the resolved path without its containment test, by effect — the host's `pointer` is then removed before the filter refuses the member; and `IMAGE_DIGEST_FILE` written before the layers are applied, by effect — the refused tree then holds it;
  - same file, `-k 'test_the_fetch_writes_no_member_outside_its_tree and whiteout-through-a-link'`: the same mutation — the host's `victim` is then removed;
  - same file, `-k 'test_the_fetch_writes_no_member_outside_its_tree and whiteout-of-dotdot'`: `_member_ok` admitting every name, `/def _member_ok/,/return /s/return .*/return True/` — the whiteout then removes `etc/..`, the tree itself, and nothing outside it;
  - same file, `-k 'test_the_fetch_writes_no_member_outside_its_tree and hard-link-out'`: a hard link's target passed through neither `_member_ok` nor `_inside`, by effect — the link to `victim` is then made, `st_nlink` 2;
  - same file, `-k 'test_the_fetch_writes_no_member_outside_its_tree and hard-link-through-a-link'`: `_inside` skipped for a hard link's target alone, by effect — the link to `victim` is then made through `link`, `st_nlink` 2;
  - same file, `-k test_a_later_layer_replaces_a_lower_layers_link`: the removal of an existing entry before a member is extracted skipped, by effect;
  - same file, `-k test_a_later_layers_whiteouts_remove_what_they_name`: the `.wh.<name>` removal skipped, by effect; and the opaque marker's emptying skipped, by effect;
  - same file, `-k test_the_fetch_refuses_a_layer_whose_bytes_are_not_its_digest`: `_verified` skipped for a blob, by effect — the impostor's `haproxy` then lands and the marker is written;
  - same file, `-k test_the_fetch_refuses_a_tree_already_holding_a_file`: the refusal of a non-empty `into` removed, by effect — the layer then lands beside `left`;
  - `--file infra/ansible/roles/engine/defaults/main.yml`, `-k test_the_harness_render_differs_from_the_roles_only_in_the_named_lines`: `s/address: 10\.98\.0\.13}/address: 10.98.0.113}/`, a mesh address a character longer than the harness's.

  No arm on `dotdot`, which `_member_ok` and `_inside` each refuse alone, so a mutation of either survives it; and none on `filter="tar"`, whose containment test `_member_ok`, `_inside` and the removal before extraction leave nothing to catch — it stays as the extraction's last check, and a mutation of it survives every case by construction.
- [ ] **Step 6: The verdict commit,** empty, `test(infra): mutate-probe.sh verdicts for the cache proxy harness's render and fetch`, each arm's verdict line as the script printed it.

### Task 2: The template (D1 to D4)

**Files:** Modify `infra/ansible/roles/engine/templates/haproxy.cfg.j2`, `infra/ansible/roles/engine/defaults/main.yml`, `tests/test_infra_cache_proxy.py`, `tests/test_infra_alert_rules.py`.

**Interfaces:**
- Produces: backends `votes-node<N>` (servers `via-node1` to `via-node3`) and `node<N>` (server `valkey`), `frontend quorum` on `127.0.0.1:9105`, and the template text the later tasks' regexes read: `nbsrv(votes-{{ node.name }}) ge 2` and `nbsrv({{ node.name }}) ge 1` in the cache frontend.

- [ ] **Step 1: The failing tests,** in `tests/test_infra_cache_proxy.py`, replacing `test_each_backend_checks_every_sentinel_for_its_own_node_and_routes_on_two_of_three`, with a module helper `_ms(value: str) -> int` (`"250ms"` to 250, `"2s"` to 2000) and `FLEET = {1: "10.98.0.11", 2: "10.98.0.12", 3: "10.98.0.13"}`:

```python
def test_a_new_session_routes_only_on_two_votes_and_an_up_route():
    rules = [f"use_backend node{n} if {{ nbsrv(votes-node{n}) ge 2 }} {{ nbsrv(node{n}) ge 1 }}" for n in (1, 2, 3)]
    assert _sections(_render())["frontend cache"] == ["bind 0.0.0.0:6379", "option tcplog", *rules]
    assert not [ln for ln in _lines(_render()) if ln.startswith("default_backend")]


def test_each_node_has_one_vote_per_sentinel_and_no_vote_cuts_a_session():
    sections = _sections(_render())
    assert [s for s in sections if s.startswith("backend ")] == [f"backend {kind}node{n}" for n in (1, 2, 3) for kind in ("votes-", "")]
    for n in (1, 2, 3):
        servers = [ln for ln in sections[f"backend votes-node{n}"] if ln.startswith("server ")]
        assert servers == [f"server via-node{s} {FLEET[s]}:26379 check inter 2s fastinter 1s downinter 1s fall 2 rise 2 init-state fully-down" for s in (1, 2, 3)]


def test_a_votes_connect_budget_holds_a_retransmitted_syn():
    sections = _sections(_render())
    (connect,) = [_ms(ln.split()[2]) for ln in sections["defaults"] if ln.startswith("timeout connect ")]
    vias = [ln.split() for name, lines in sections.items() if name.startswith("backend votes-") for ln in lines if ln.startswith("server ")]
    assert len(vias) == 9
    for words in vias:
        assert min(connect, _ms(words[words.index("inter") + 1])) >= 2000, words
        assert _ms(words[words.index("downinter") + 1]) <= 1000, words


def test_each_node_has_one_route_server_checked_against_the_quorum_frontend():
    sections = _sections(_render())
    (port,) = [ln.rsplit(":", 1)[1] for ln in sections["frontend quorum"] if ln.startswith("bind ")]
    for n in (1, 2, 3):
        route = sections[f"backend node{n}"]
        assert route == [
            f"option httpchk GET /node{n}",
            "http-check expect status 200",
            f"server valkey {FLEET[n]}:6379 check addr 127.0.0.1 port 9105 inter 250ms fall 2 rise 1 init-state fully-down on-marked-down shutdown-sessions",
        ]
        words = route[2].split()
        assert words[words.index("port") + 1] == port


def test_only_the_route_servers_cut_sessions():
    cutters = [ln for ln in _lines(_render()) if "shutdown-sessions" in ln]
    assert len(cutters) == 3 and all(ln.startswith("server valkey ") for ln in cutters), cutters
```

  - `test_the_quorum_frontend_answers_503_only_on_a_contradiction`: `_sections(_render())["frontend quorum"]` equals `["mode http", "bind 127.0.0.1:9105", "no log"]` followed by the thirteen `http-request return` lines of the spec's rendered `frontend quorum` (*The template*, its second fence), each stripped, written out literally in order.
  - `test_haproxy_chroots_and_logs_connections_on_the_cache_frontend_alone` gains `assert "no log" in sections["frontend quorum"]`.
  - `test_the_check_authenticates_pings_and_expects_the_anchored_master_reply_with_no_quit` and `test_the_timeouts_the_logging_and_the_metrics_endpoint` stay as they are.
- [ ] **Step 2: Run the file and read the six new cases and the extended one fail.**
- [ ] **Step 3: The template,** `haproxy.cfg.j2` replaced whole by the spec's *The template* first fence. In `defaults/main.yml`, the comment above `engine_cache_proxy_nodes` reads "a votes backend and a route backend each" for "one backend each". In `tests/test_infra_alert_rules.py`'s `test_the_cache_proxy_rules_read_the_primary_and_the_write_rule_reads_the_librarys_lines`, the bound's regex becomes `r"nbsrv\(votes-\{\{ node\.name \}\}\) ge (\d+)"`, its comment naming the votes' bound, and nothing else of the case changes until Task 4: the old regex now reads the route clause's 1.
- [ ] **Step 4: Tests,** `tests/test_infra_cache_proxy.py` as the task's own, the gate, commit `fix(engine): the cache proxy cuts a session only when the Sentinels contradict its route`.
- [ ] **Step 5: Probes,** pytest arms on `--file infra/ansible/roles/engine/templates/haproxy.cfg.j2` through `tests/test_infra_cache_proxy.py`, each KILLED:
  - `-k test_a_new_session_routes_only_on_two_votes_and_an_up_route`: `s/nbsrv(votes-{{ node\.name }}) ge 2 }/nbsrv(votes-{{ node.name }}) ge 1 }/`; `s/ { nbsrv({{ node\.name }}) ge 1 }//`; and `s/^    option tcplog$/&\n    default_backend votes-node1/`, a session riding a vote;
  - `-k test_the_quorum_frontend_answers_503_only_on_a_contradiction`: `s/{{ node\.name }}) eq 0 }/{{ node.name }}) lt 2 }/`; and `/{{ other\.name }}) ge 2 }/d`;
  - `-k test_each_node_has_one_vote_per_sentinel_and_no_vote_cuts_a_session`: `s/fall 2 rise 2 init-state fully-down$/fall 2 rise 2 init-state fully-down on-marked-down shutdown-sessions/`;
  - `-k test_a_votes_connect_budget_holds_a_retransmitted_syn`: `s/check inter 2s fastinter/check inter 1s fastinter/`; `s/timeout connect 2s/timeout connect 1s/`; and `s/downinter 1s/downinter 3s/`;
  - `-k test_each_node_has_one_route_server_checked_against_the_quorum_frontend`: `s/fall 2 rise 1/fall 1 rise 1/`; and `s/bind 127\.0\.0\.1:9105/bind 127.0.0.1:9106/`;
  - `-k test_only_the_route_servers_cut_sessions`: `s/ init-state fully-down on-marked-down shutdown-sessions$/ init-state fully-down/`;
  - `-k test_haproxy_chroots_and_logs_connections_on_the_cache_frontend_alone`: `/^frontend quorum$/,/^    no log$/{/^    no log$/d}`;
  - through `tests/test_infra_alert_rules.py -k test_the_cache_proxy_rules_read_the_primary_and_the_write_rule_reads_the_librarys_lines`, the bound's regex this task re-aims: `s/nbsrv(votes-{{ node\.name }}) ge 2 }/nbsrv(votes-{{ node.name }}) ge 3 }/`, the bound then reading 3 against the rule's `lt 2`.

  Each `sed` here and in Tasks 3 and 4 that names the template was run through GNU `sed` as a basic expression, the form `mutate-probe.sh`'s `sed -i` reads, over the spec's *The template* first fence, and changes the one line it names.
- [ ] **Step 6: The verdict commit,** empty, `test(engine): mutate-probe.sh verdicts for the cache proxy's votes, routes and quorum frontend`, each arm's verdict line as the script printed it.

### Task 3: The harness's run (D7)

**Files:** Modify `infra/scripts/cache-proxy-harness.py`, `tests/test_cache_proxy_harness.py`.

**Interfaces:**
- Consumes: Task 1's `render`, `TEMPLATE`, `NODES`, `IMAGE_DIGEST_FILE`; Task 2's template; `ROOTFS`.
- Produces the CLI: `cache-proxy-harness.py run --rootfs <tree> --scratch <dir> [--case <name>]...`, `--case` repeatable, none meaning all nine in the order `parse`, `start`, `no-early-route`, `vote-down-cuts-nothing`, `one-vote-cuts-nothing`, `no-vote-cuts`, `contradiction-cuts-both`, `lost-syn-inside-budget`, `stalled-exchange`. Each case prints `PASS <case>: <figure> <value> s (bound <value> s)[; …]` or `FAIL <case>: <the read that failed>[; <figures>]`; the run ends `<p> passed, <f> failed -- <haproxy -vv's first line> -- image <the digest's first 12 hex>`; exit 0 every case passing, 1 any case failing, 2 refused, never 5.
- Produces the run's files: `<scratch>/run-<YYYYmmddTHHMMSSZ>-<pid>/<case>/`, and `maps/` beside them for the once-per-run HAProxy, each holding `haproxy.cfg` (the render), `haproxy.out` and `haproxy.err` (HAProxy's stdout and stderr), kept for the caller; `run` creates `--scratch` and its parents when they are absent.
- Produces the run's processes, each but its `/usr/bin/ip` and `/usr/sbin/nft` calls, which end before the run goes on, carrying an absolute path under `--rootfs` or `--scratch` in its command line, so a read by full command line finds every one that lives on: `--rootfs` and `--scratch` are made absolute before the re-exec under `unshare`; HAProxy's argv names the tree's loader and `-f <its directory>/haproxy.cfg`, a case's or `maps/`; each scripted peer is started with its case directory, absolute, among its arguments, and binds its listener with `SO_REUSEADDR` set, as HAProxy binds its own: a connection the peer's side closes first leaves TCP TIME_WAIT on the peer's fixed address and port, which no stop clears and which refuses a plain bind there by the next case's peer.
- Produces: `CASES`, the nine names in that order; `PINNED_VERSION = "3.4.5"`, which a proxy re-pin changes in its own change; `version_ok(first_line: str) -> bool`, true when the word after `version` in `haproxy -vv`'s first line is `PINNED_VERSION` or opens with `PINNED_VERSION` and `-`; `tree_whole(root: Path) -> bool`, true when `root / IMAGE_DIGEST_FILE` is a file; `loopback_only(names: Iterable[str]) -> bool`; `run_inside(rootfs: Path, scratch: Path, cases: Sequence[str]) -> int`, the run inside the namespace and its exit, the module importing `socket` and `subprocess` whole and calling them through the module, and `run_inside` starting every process through `subprocess.Popen` or `subprocess.run` alone, never `os.system`, `os.posix_spawn` or an `os.exec*`, so a test stands in for their calls; `Procs`, with `start(argv: list[str], **popen: Any) -> subprocess.Popen`, `nft(*args: str) -> str`, the call's stdout, every `nft` rule, set and counter a case makes, all in one table of its own named for the case, which the first call makes, and `stop_all() -> None`, each process stopped by its own PID and waited for, then that table deleted, and forgotten, when one was made, so no rule outlives its case in a full run's one namespace; `run_case(name: str, body: Callable[[Procs], tuple[bool, str]]) -> str`, the printed line, an exception in `body` or in `stop_all()` a `FAIL` line carrying its text, `stop_all()` in a `finally`; `foreign_mappings(maps: str, root: str) -> list[str]`, in order, the path of each line of a `/proc/<pid>/maps` text whose permission field carries `x` and whose path field opens with `/` and does not start with `root + "/"` — a file of code mapped from outside the tree. Every shared library, the tree's or the host's, maps an executable segment, so a host library is still named; a shared anonymous mapping, which reads `/dev/zero (deleted)` with `rw-s` on this host, and `[heap]`, `[vdso]` and the like are not.

- [ ] **Step 1: The failing tests,** appended to `tests/test_cache_proxy_harness.py`, which now imports `contextlib`, `subprocess` and `sys` beside Task 1's:

```python
def test_the_run_refuses_a_namespace_with_any_interface_but_lo():
    assert harness.loopback_only(["lo"])
    assert not harness.loopback_only(["lo", "eth0"]) and not harness.loopback_only(["eth0"]) and not harness.loopback_only([])


def test_the_inner_run_starts_nothing_in_a_namespace_with_any_interface_but_lo(monkeypatch, tmp_path):
    started = []

    class Started(Exception):
        pass

    def record(argv, *args, **kwargs):
        started.append(argv)
        raise Started(argv)

    rootfs = tmp_path / "rootfs"
    rootfs.mkdir()
    (rootfs / harness.IMAGE_DIGEST_FILE).write_text("sha256:" + "0" * 64 + "\n")
    monkeypatch.setattr(harness.subprocess, "Popen", record)
    monkeypatch.setattr(harness.subprocess, "run", record)
    monkeypatch.setattr(harness.socket, "if_nameindex", lambda: [(1, "lo"), (2, "eth0")])
    assert harness.run_inside(rootfs, tmp_path / "scratch", list(harness.CASES)) == 2
    assert started == []
    monkeypatch.setattr(harness.socket, "if_nameindex", lambda: [(1, "lo")])
    with contextlib.suppress(Started):
        harness.run_inside(rootfs, tmp_path / "scratch", list(harness.CASES))
    assert started[:1] == [["/usr/bin/ip", "link", "set", "lo", "up"]], started


def test_the_run_refuses_a_binary_that_does_not_print_the_pinned_version():
    pin = harness.PINNED_VERSION
    assert harness.version_ok(f"HAProxy version {pin} 2026/10/01 - https://haproxy.org/")
    assert harness.version_ok(f"HAProxy version {pin}-1a2b3c4 2026/10/01 - https://haproxy.org/")
    assert not harness.version_ok("HAProxy version 0.0.1 2026/10/01 - https://haproxy.org/")
    assert not harness.version_ok(f"HAProxy version {pin}0 2026/10/01 - https://haproxy.org/")


def test_the_run_refuses_a_tree_the_fetch_did_not_finish(tmp_path):
    assert not harness.tree_whole(tmp_path)
    (tmp_path / harness.IMAGE_DIGEST_FILE).write_text("sha256:" + "0" * 64 + "\n")
    assert harness.tree_whole(tmp_path)


def test_a_case_that_raises_prints_fail_and_stops_every_process_it_started(tmp_path):
    argv = [sys.executable, "-c", "import time; time.sleep(30)", str(tmp_path)]
    twin = subprocess.Popen(argv)
    started = []

    def body(procs):
        started.append(procs.start(argv))
        raise RuntimeError("the case broke")

    try:
        line = harness.run_case("start", body)
        assert line.startswith("FAIL start") and "the case broke" in line, line
        assert started and started[0].poll() is not None
        with pytest.raises(subprocess.TimeoutExpired):  # a process the case did not start, on the same command line, lives on
            twin.wait(timeout=0.5)
    finally:
        for process in [twin, *started]:
            if process.poll() is None:
                process.kill()
                process.wait()


def test_a_mapping_outside_the_tree_is_foreign():
    maps = "\n".join(
        [
            "55d0-55e0 r--p 00000000 fd:01 11 /x/root/usr/local/sbin/haproxy",
            "55e0-55f0 rw-p 00000000 00:00 0 [heap]",
            "7f00-7f10 r-xp 00000000 fd:01 12 /x/root/usr/lib/x86_64-linux-gnu/libc.so.6",
            "7f10-7f20 r-xp 00000000 fd:01 13                          /usr/lib/x86_64-linux-gnu/libssl.so.3",
            "7f20-7f30 rw-p 00000000 00:00 0 ",
            "7ffd-7ffe r-xp 00000000 00:00 0 [vdso]",
            "7f30-7f40 r-xp 00000000 fd:01 14                          /x/rootfs/lib/libz.so.1",
            "7f40-7f50 rw-s 00000000 00:01 15 /dev/zero (deleted)",
        ]
    )
    assert harness.foreign_mappings(maps, "/x/root") == ["/usr/lib/x86_64-linux-gnu/libssl.so.3", "/x/rootfs/lib/libz.so.1"]
```

- [ ] **Step 2: Run them and read them fail** on the missing names.
- [ ] **Step 3: `run`,** within *The harness* and *Left to the implementer*, in this order. Outside the namespace it refuses (2) a tree `tree_whole` refuses and a missing `/usr/bin/unshare`, `/usr/bin/ip` or `/usr/sbin/nft`, runs nothing from the tree, and re-runs itself under `unshare -rn`; inside, `run_inside`'s first act reads the namespace's interfaces from `socket.if_nameindex()` and refuses (2) unless `loopback_only` holds — never from `/sys/class/net`, which inside a fresh `unshare -rn` still lists the host's: there `socket.if_nameindex()` printed `[(1, 'lo')]` and `/sys/class/net` held 7 entries. Its next act brings `lo` up, `subprocess.run(["/usr/bin/ip", "link", "set", "lo", "up"], check=True, timeout=1.0)`, before it resolves anything in the tree, a `CalledProcessError` or `TimeoutExpired` from it refusing (2), its line naming the call; then it refuses (2) a binary whose `haproxy -vv` first line `version_ok` refuses, its line naming the version the binary printed and `PINNED_VERSION` in `infra/scripts/cache-proxy-harness.py`, which a re-pin's own change moves to the candidate's version before its run. Every path in the tree resolves against `--rootfs`, an absolute link target re-rooted there and never followed on the host; the binary runs through the tree's own loader with `--library-path` naming the tree's library directories, with the flags the tree's own entrypoint script adds to a bare `haproxy`, read from the tree, and `-f <the render>`. Once per run, before the first case, HAProxy is started on the render through a `Procs`, its `/proc/<pid>/maps` read once it listens, and stopped by that `Procs`'s `stop_all()` in a `finally`, on the refusal's path as on the others; a file `foreign_mappings` names refuses the run (2), naming it. A render on which HAProxy exits before it listens is no refusal: the read is skipped and the cases report it, each `FAIL`, exit 1. Each case but `parse` starts its own scripted peers and its own HAProxy and stops them by PID through `run_case`; the peers, the `nft` rules, the reads at 0.1 s or finer, the bounds (the source's worst case plus 1.0 s) and each case's setup, reads and verdict are the spec's *The harness* bullets, case by case. Every wait and every single read inside a case ends at a deadline, none blocks without one, and one that reaches its deadline reads as the case's `FAIL`. A case's bound times only the figure it prints, so a wait takes the deadline of what it waits on, these six kinds and no other: a wait that times a printed figure ends at that figure's bound; a wait on votes falling before the timed figure — `one-vote-cuts-nothing`'s two votes DOWN, the one such wait, the silent Sentinel's worst case bounding the refused one's too, its checks failing at once — ends at *The bounds*' worst case for that transition plus the 1.0 s margin; a wait on a start — `parse`'s `haproxy -c` exiting, each scripted peer listening, a HAProxy listening, the route or vote a case needs up before it acts, its first two sessions in every case that opens them — ends at `start`'s 3.40 s bound; a stated window — the 10 s of `no-early-route`, `vote-down-cuts-nothing`, `one-vote-cuts-nothing` and `lost-syn-inside-budget` — is held to its length and never cut short, its end the deadline of every read the spec's bullet makes inside it, `vote-down-cuts-nothing`'s DOWN line among them; and each of `stalled-exchange`'s three tries waits for the vote's next close until `inter`'s 2 s plus the margin, then until its aimed window's close plus `timeout check`'s 2 s plus the margin for the read-back; and a call or read made once outside those waits — each `nft` call, made through the case's `Procs.nft` (the Interfaces), a scrape of the exporter (`start`'s and `contradiction-cuts-both`'s `L7STS` reads, `one-vote-cuts-nothing`'s `L4CON` and `L4TOUT` reads), a read of HAProxy's output, `lost-syn-inside-budget`'s read of its rule's counter — ends at the 1.0 s margin. The once-per-run HAProxy's listen takes a start's deadline, reaching it read as an exit before it listens. The run writes nothing outside `--scratch`. The module docstring gains `run`, its exits 0, 1 and 2, and that it never exits 5.
- [ ] **Step 4: The unit tests and the direct readers,** with `tests/test_cache_proxy_harness.py` and `tests/test_internal_terms_not_operator_visible.py` as the task's own.
- [ ] **Step 5: The full run,** the template's first on the binary. `PROCS`, then the run in its own call, `uv run python infra/scripts/cache-proxy-harness.py run --rootfs /home/zhaow/Projects/zcrypto-kraken/.claude/worktrees/proxy-quorum/.tmp/00159/haproxy-76928c0d6b39 --scratch .tmp/00159/t3/harness`, then `PROCS` again. Expected: nine `PASS` lines, the summary `9 passed, 0 failed -- HAProxy version 3.4.5… -- image 76928c0d6b39`, exit 0; the second `PROCS` lists no PID the first did not. A `FAIL` here stops the plan: it goes to the coordinator with its line and its case's `haproxy.err`, and the coordinator returns it to the spec, whose *The constructs* row that case measures — and the template or decision resting on that row — is amended there before any task resumes; no bound is widened and no case is reworded to pass. The one exception is a `FAIL` whose read is the harness's own, these three and no other: `lost-syn-inside-budget`'s dropped-SYN count disagreeing with its set; `stalled-exchange`'s fault not landed in three tries; and a case's setup or teardown — a scripted peer not listening by a start's deadline, an `nft` call failing or reaching its margin, the case's table not deleted. That is a defect in this task's code, fixed here as a fix commit with the case's figures and bounds unchanged, and the full run then repeated; in a run where one case's teardown failed, every later case's `FAIL` waits for the repeated run before it is classed, since what that case left in the shared namespace can fail it; every other `FAIL` is a construct's and goes to the spec as above.
- [ ] **Step 6: The gate, commit** `feat(infra): the cache proxy harness runs the role's render on the pinned HAProxy against scripted Sentinels and Valkeys`, the message carrying Step 4's result line and Step 5's ten lines.
- [ ] **Step 7: Probes.** Pytest arms, `--file infra/scripts/cache-proxy-harness.py`, each KILLED:
  - `-k test_the_run_refuses_a_namespace_with_any_interface_but_lo`: `loopback_only` admitting a set that holds `lo` beside another, by effect;
  - `-k test_the_inner_run_starts_nothing_in_a_namespace_with_any_interface_but_lo`: `run_inside`'s `loopback_only` refusal removed, by effect; the interfaces read from `os.listdir("/sys/class/net")` in place of `socket.if_nameindex()`, by effect, under which the host's list refuses the `lo`-alone half; and the `ip` call removed from `run_inside`, by effect, under which the `lo`-alone half records no `ip` argv first;
  - `-k test_the_run_refuses_a_binary_that_does_not_print_the_pinned_version`: `version_ok` testing that the word opens with `PINNED_VERSION` alone, by effect;
  - `-k test_the_run_refuses_a_tree_the_fetch_did_not_finish`: `tree_whole` testing that `root` exists in place of the file, by effect;
  - `-k test_a_case_that_raises_prints_fail_and_stops_every_process_it_started`: `run_case`'s `stop_all()` removed from its `finally`, by effect; its catch narrowed so a `RuntimeError` escapes, by effect; and `stop_all` stopping every process whose command line equals a started one's (`pkill -f -x` over its escaped argv) in place of its PID, by effect, which stops the twin;
  - `-k test_a_mapping_outside_the_tree_is_foreign`: the prefix test made without the trailing `/`, by effect; and the `x` test dropped, by effect, under which `/dev/zero (deleted)` is named too.

  `PROCS` runs in its own call before the first arm. Harness arms, `--file infra/ansible/roles/engine/templates/haproxy.cfg.j2`, each KILLED, one call per case:
  - `parse`: `/^frontend quorum$/,/^    bind 127\.0\.0\.1:9105$/{/^    mode http$/d}`;
  - `start`: `s/fastinter 1s/fastinter 4s/`;
  - `no-early-route`: `s/nbsrv(votes-{{ node\.name }}) ge 2 }/nbsrv(votes-{{ node.name }}) ge 1 }/`;
  - `vote-down-cuts-nothing`: `s/{{ node\.name }}) eq 0 }/{{ node.name }}) lt 3 }/`;
  - `one-vote-cuts-nothing`: `s/{{ node\.name }}) eq 0 }/{{ node.name }}) lt 2 }/`;
  - `no-vote-cuts`: `/{{ node\.name }}) eq 0 }/d`;
  - `contradiction-cuts-both`: `/{{ other\.name }}) ge 2 }/d`;
  - `lost-syn-inside-budget`: `s/check inter 2s fastinter/check inter 500ms fastinter/`;
  - `stalled-exchange`: `s/fall 2 rise 2 init-state/fall 1 rise 2 init-state/`.

  Then the same eight `sed`s after `parse`'s, each through `--case parse`, each SURVIVED: the mutation parses clean, so its case's kill is the behaviour's and not a refused start. A KILLED there goes to the coordinator with the arm. `PROCS`, in its own call after the last arm, lists no PID the read before the first did not.
- [ ] **Step 8: The verdict commit,** empty, `test(infra): mutate-probe.sh verdicts for the cache proxy harness and its nine cases`.

### Task 4: The page and its panel (D5)

**Files:** Modify `infra/grafana/alerts.yaml`, `infra/grafana/cache-dashboard.json`, `tests/test_infra_alert_rules.py`, `tests/test_dashboards_cover_metrics.py`.

**Interfaces:**
- Consumes: Task 2's template text.
- Produces: panel titles `Route per node` (401), `Sentinel votes on the routed node — the page's value` (402), `Sentinel votes per node` (404), `Check failures per server` (405), of which Task 6's runbook text names 401's and 402's.

- [ ] **Step 1: The failing tests.** In `tests/test_infra_alert_rules.py`'s `test_the_cache_proxy_rules_read_the_primary_and_the_write_rule_reads_the_librarys_lines`, the `'max(haproxy_backend_active_servers{host="zcrypto"})' in` line and the bound lines give way to:

```python
    expr = backend["data"][0]["model"]["expr"]
    haproxy_cfg = (REPO / "infra/ansible/roles/engine/templates/haproxy.cfg.j2").read_text()
    route = {int(n) for n in re.findall(r"nbsrv\(\{\{ node\.name \}\}\) ge (\d+)", haproxy_cfg)}
    read = {int(n) for n in re.findall(r'proxy=~"node\[0-9\]\+"\}\) >= (\d+)\)', expr)}
    assert route == read == {1}, (route, read)
    bound = {int(n) for n in re.findall(r"nbsrv\(votes-\{\{ node\.name \}\}\) ge (\d+)", haproxy_cfg)}
    assert bound == {2}, bound
    assert backend["data"][1]["model"]["conditions"] == [{"evaluator": {"type": "lt", "params": [bound.pop()]}}]
    assert expr == (
        '(max(haproxy_backend_active_servers{host="zcrypto", proxy=~"votes-node[0-9]+"}) and on() '
        '(max(haproxy_backend_active_servers{host="zcrypto", proxy=~"node[0-9]+"}) >= 1)) or on() vector(0)'
    )
```

  Its comments say that the threshold is the cache frontend's votes bound and the `>= 1` its route clause, the two pairings read before the literal pins the rest of the expression. In `tests/test_dashboards_cover_metrics.py`, beside `test_a_panels_red_line_agrees_with_the_rule_it_charts`:

```python
def test_the_proxy_page_panel_charts_the_rules_own_expression():
    pairs = {(uid, panel["id"], target["refId"]) for uid, panel, target, *_ in _rule_panel_pairs()}
    assert ("zcrypto-cache-proxy-no-backend", 402, "A") in pairs
```

- [ ] **Step 2: Run both files and read the alert case fail** on the expression; the panel case passes on today's expression and is proven by its arm.
- [ ] **Step 3: The rule.** `zcrypto-cache-proxy-no-backend` takes the spec's *The alert and its panel* fence as its refId A `model` comment and `expr`, on one line under `>-`; the `for` comment, `summary` and `unit` as the spec gives them; uid, `noDataState`, `execErrState`, the `lt 2` threshold, `__dashboardUid__`, `__panelId__: "402"`, labels and receiver unchanged. `NOT_A_FAULT_SIGNAL`'s comment above the four proxy families becomes the spec's text, wrapped as the file wraps its comments.
- [ ] **Step 4: The panels,** 401 to 406 of `cache-dashboard.json` as the spec's bullets give each title, target, legend and description, every id, place, threshold and type kept, 402's refId A the rule's expression exactly; edited in place, keeping the file's own layout, 402's em dash escaped as the file escapes the one it holds today.
- [ ] **Step 5: Tests,** both files as the task's own, the gate, commit `fix(grafana): the no-backend page and its panel read the cache frontend's own rule`.
- [ ] **Step 6: Probes,** each KILLED:
  - `--file infra/grafana/alerts.yaml`, through `tests/test_infra_alert_rules.py -k test_the_cache_proxy_rules_read_the_primary_and_the_write_rule_reads_the_librarys_lines`: `s/ and on() (max(haproxy_backend_active_servers{host="zcrypto", proxy=~"node\[0-9\]+"}) >= 1)//`;
  - `--file infra/ansible/roles/engine/templates/haproxy.cfg.j2`, the same case: `s/nbsrv(votes-{{ node\.name }}) ge 2 }/nbsrv(votes-{{ node.name }}) ge 3 }/`; and `s/{ nbsrv({{ node\.name }}) ge 1 }/{ nbsrv({{ node.name }}) ge 2 }/`, which the route pairing alone kills;
  - `--file infra/grafana/cache-dashboard.json`, through `tests/test_dashboards_cover_metrics.py -k test_the_proxy_page_panel_charts_the_rules_own_expression`: `/and on() (max(/s/proxy=~\\"node\[0-9\]+\\"/proxy=~\\"node.*\\"/`.
- [ ] **Step 7: The verdict commit,** empty, `test(grafana): mutate-probe.sh verdicts for the no-backend page and its panel`.

### Task 5: The Alloy fixtures (D10)

**Files:** Modify `tests/test_infra_alloy_levels.py`.

**Interfaces:**
- Consumes: Task 3's `run` CLI and the run's file layout (Global Constraints); `ROOTFS`.

- [ ] **Step 1: The lines.** Between two `PROCS` reads, each its own call, `uv run python infra/scripts/cache-proxy-harness.py run --rootfs /home/zhaow/Projects/zcrypto-kraken/.claude/worktrees/proxy-quorum/.tmp/00159/haproxy-76928c0d6b39 --scratch .tmp/00159/t5/harness --case contradiction-cuts-both`, `PASS` and exit 0, the second read listing no PID the first did not; from that case's `haproxy.out`, under `.tmp/00159/t5/harness/run-*/contradiction-cuts-both/`, the line opening `Server node2/valkey is DOWN`, and from its `haproxy.err` the `[WARNING]` line carrying the same text.
- [ ] **Step 2: The fixtures.** `Fixture("cache_proxy_route_down", "capture", {"container": "cache-proxy"}, <the stdout line>, DROP)` after `cache_proxy_server_down`, and `TWINS["cache_proxy_route_down"]`, the stderr line, after its twin's; both verbatim. `node1/via-node1` in `cache_proxy_server_up` and its twin becomes `votes-node2/via-node3`, `node2/via-node3` in `cache_proxy_server_down` and its twin becomes `votes-node2/via-node3`, and `node1/via-node1` in `cache_proxy_session` and `cache_proxy_session_cut` becomes `node2/valkey`, the rest of each line and its level unchanged.
- [ ] **Step 3: Tests,** `tests/test_infra_alloy_levels.py` as the task's own; the new fixture passes on today's drop selector. The gate, commit `test(infra): the Alloy fixtures carry the proxy's votes and route, and a route's DOWN line drops as its copy ships`.
- [ ] **Step 4: Probe,** `--file infra/ansible/roles/capture/files/config.alloy`, through `tests/test_infra_alloy_levels.py -k 'test_each_line_takes_the_level_its_source_reports and cache_proxy_route_down'`, KILLED: `s/S+ is |Proxy/S+ was |Proxy/`. The verdict commit, empty, `test(infra): mutate-probe.sh verdict for the route's DOWN fixture`.

### Task 6: The runbooks (D10)

**Files:** Modify `infra/runbooks/cache.md`, `infra/runbooks/engine-procedures.md`.

**Interfaces:**
- Consumes: Task 4's panel titles.

- [ ] **Step 1: Load `zcrypto-refine-rules`** and read its *Before you write guidance*. Read `RATIO`: `` uv run python -c 'from tests.test_ops_daily import _runbook_commands, _destructive, _identity, ops_daily; reads = [c for c in _runbook_commands() if not _destructive(c)]; print(len([c for c in reads if ops_daily.classify_action(f"`{c}`", host="ops", resolve=_identity) is ops_daily.Tier.AUTONOMOUS]), len(reads))' ``, which prints `375 534` at this plan's base, `89f71f75a`.
- [ ] **Step 2: `cache.md`,** the spec's *Runbook texts*, seven of its eight passages verbatim: `cache-manual-failover`'s *What it means*; `zcrypto-cache-proxy-no-backend`'s *What you are seeing*, its *What it means* up to `A running engine keeps trading, but no engine start succeeds while this fires`, the rest of that paragraph unchanged, and its *Verify by value*; `zcrypto-cache-proxy-no-engine-session`'s *What it means*, and its step 1's parenthesis naming `Route per node` where it names `Backend status per node`; `zcrypto-engine-cache-write-failed`'s *What it means*.
- [ ] **Step 3: `cache.md`'s `zcrypto-cache-proxy-no-backend` step 2,** the spec's *Runbook texts* step-2 fence verbatim, as the spec reads when this task starts. The page is a contract the commit-msg guidance guard reads for an uncounted universal in every list item, and the fence as committed at `89f71f75a` carries one, `Every route failing at once`: `infra/scripts/guidance-guard.py`'s `universals_without_a_count` over `cache.md` with that fence at line 374 returns `[(374, 'Every')]`. P0 amended the spec's fence at `72099202f`, which reads `All three routes failing at once`. Run `uv run python infra/scripts/guidance-guard.py --uncounted infra/runbooks/cache.md` after this step: a line it prints stops the task here, to the coordinator with that line, and the copy is never reworded.
- [ ] **Step 4: `engine-procedures.md`,** the spec's two passages: in `engine-restart-margin-position`'s opening paragraph, `` `Sentinel checks passing on the most-agreed backend` `` becomes `` `Sentinel votes on the routed node — the page's value` ``; in the `acct` procedure's step 4, `the time the proxy's checks need to pass twice` becomes `the time the proxy's Sentinel votes need to pass twice`.
- [ ] **Step 5: Reads.** `uv run python infra/scripts/guidance-guard.py --uncounted infra/runbooks/cache.md infra/runbooks/engine-procedures.md` prints nothing; `RATIO` prints `375 534` again; `git grep -l -E 'most-agreed|Backend status per node|roundrobin|per-entry cut' -- infra/runbooks infra/grafana .claude/skills`, with the `VAULT_EXCLUDES` pathspecs appended (Global Constraints), lists nothing.
- [ ] **Step 6: Tests** with `WALKERS`, the gate, commit `docs(runbooks): the proxy's pages read votes and a route, and one Sentinel's check cuts nothing`. No arm: no check reads these sentences beyond the walkers.

### Task 7: The rollout skill (D10)

**Files:** Modify, in its own `claude(skills)` commit, `.claude/skills/zcrypto-rollout-image/SKILL.md`.

**Interfaces:**
- Consumes: Task 3's `run` CLI.

- [ ] **Step 1: Load `zcrypto-refine-rules`** and read its *Before you write guidance*.
- [ ] **Step 2: *A cache proxy bump is an engine converge*.** "Before it:" gains, directly after the clause ending `` `sudo docker pull haproxy@sha256:<new>` on `zcrypto`; ``, the harness clause the spec's *Change list* quotes for this skill, verbatim. In "After it:", `on the host reads the three servers` becomes `` on the host reads four servers, the primary's three votes `votes-node<N>/via-node1` to `via-node3` and its route `node<N>/valkey` ``.
- [ ] **Step 3: *Phase 4 — Rollback*,** `` `zcrypto-cache-proxy-no-backend` wherever no backend has two checks passing `` becomes `` `zcrypto-cache-proxy-no-backend` wherever no node holds two Sentinel votes while a route of the proxy's is up ``.
- [ ] **Step 4: Tests,** `tests/test_guidance_guard.py` and `tests/test_guidance_refs_resolve.py` as the task's own, the gate, commit `claude(skills): a cache proxy re-pin runs the harness first, and its reads name the votes and the route`. The frontmatter stays as it is, so the message carries no `Ambient grows by` line; no arm, since no check reads these sentences.

### Task 8: The records

**Files:** Modify `docs/specs/00118-engine-cache-design.md`, `docs/specs/00120-engine-cache-engine-half-design.md`, `docs/research/14.phase6-decisions.md`.

- [ ] **Step 1: The amendments** (D9), each appended to its spec's `## Spec amendments`, verbatim. To 00118:

```markdown
- **D4, amended 2026-11-11 on the owner's word (spec 00159 D1 and D9).** The proxy holds, for each node, a votes backend of three check-only servers, one per Sentinel, which no session rides, and a route backend of one server that carries the engine's sessions and is health-checked against a loopback frontend answering 503 only while the votes contradict that node — two for another node, or none for it; `on-marked-down shutdown-sessions` sits on the route server alone, and a new session goes to a node with two votes whose route is up. Gone: the three server lines per backend whose health check goes to one Sentinel and which carry the sessions, the checks every second, and the per-line session cut. Standing: the one endpoint `cache-proxy:6379`, the HAProxy container in the engine's compose project, digest-pinned with a pins row, the 32m cap, the metrics endpoint on `127.0.0.1:9104`, the mesh addresses, a node routed when two Sentinels name it, and the Sentinel check's commands; the nine checks' 10–20 MiB becomes twelve checks', read at the rollout.
```

  To 00120:

```markdown
- 2026-11-11, spec 00159 on the owner's word (its D1 and D9), amended here rather than folded into the decision text above: D1 loses the three server lines per backend at the node's address with `check addr <Sentinel>`, `inter 1s` and a per-line `shutdown-sessions`, the frontend's `nbsrv(nodeN) ge 2`, "a node leaves routing within about six seconds of its Sentinels ceasing to name it" — now a route cut 1.25 to 4.6 s after a second Sentinel names another node and a new route 5 to about 7.3 s after it — the accepted per-entry cut, and "the default roundrobin balance", 3.4's default being `random`; D14 loses the no-backend rule's `max(haproxy_backend_active_servers{host="zcrypto"})`, now spec 00159 D5's expression, and "a per-entry cut leaves a session up", every cut now taking both sessions and the session count reading 1 after any cut. The rest of D1, D5 and D14 stands, and the measured basis's "the three-Sentinel `nbsrv` shape was not run" is answered by spec 00159's harness.
```

- [ ] **Step 2: The gate, commit** `docs(specs): 00118 and 00120 record what 00159 supersedes`. No test reads either spec — `infra/scripts/consumers.sh --tests --direct` over the two refuses with `found no test file` — so the commit's result line is the gate's, quoted with `uv run pre-commit run -a`.
- [ ] **Step 3: Load `iteration-closeout`.** Append to the end of `docs/research/14.phase6-decisions.md`, verbatim:

```
[00159] How does the engine's cache proxy stop cutting the engine's sessions when one Sentinel cannot be reached? (Decision: 1)
  1. **The redesign under this serial, with the skeptic's refinement** — per node, three check-only votes, one per Sentinel, and one route server carrying the sessions, cut only when the votes the proxy can read contradict its node: two for another node, or none for it. One Sentinel's reach never cuts a session and a partitioned old primary loses every session the proxy carries to it; the cost is a loopback frontend inside the proxy and, after a failover, some seconds more with no route for a new session.
  2. **Tolerance only** — `timeout connect 8s` and `inter 8s`, the per-line cut kept. Removes the burst cuts alone; a one-in-three cut stays on every reboot and Sentinel restart, the partition hole stays, and every proxied connect gets an 8 s connect timeout.
  3. **An interim budget change, then the redesign** — the bursts stop cutting sooner, at two gap-bound engine restarts for the same end.
  Human: "1 as recommended, yes to 2, pursue the loss bursts investigation but raising it with Linode does not seem like an option as none of the other services got impacted while in the end it is just a service listening on a TCP port like any other services we created at and deployed to the fleet."

[00159] Is the cache proxy's new configuration proven on a real HAProxy 3.4.5 on the workstation before it rolls out? (Decision: 1)
  1. **Yes** — a harness runs the pinned image's own binary, unpacked without Docker, in an unprivileged namespace against scripted Sentinels and Valkeys, its case lines in the pull request; a script to keep, and a run before every template change and proxy re-pin.
  2. **No, the converge's check-mode parse alone** — nothing to keep; the routing, the cuts and the timers are first seen on the engine host, behind an engine restart.
  Human: the reply quoted in the entry above, "yes to 2".

[00159] Are the packet-loss bursts on the inter-region path to valkey3 pursued, and how? (Decision: 1)
  1. **The coordinator's attended investigation** — a two-layer probe run on valkey3, its reading to the owner, outside the proxy change, which makes the engine tolerant of the bursts and removes none of them.
  2. **Raised with Linode** — the provider's view of its own network; no other service on the fleet was affected, and the Sentinel is a service on a TCP port like the others.
  3. **Not pursued** — the proxy's tolerance alone; the bursts' cause and any growth in them unread.
  Human: the reply quoted in the first entry above, "pursue the loss bursts investigation but raising it with Linode does not seem like an option as none of the other services got impacted while in the end it is just a service listening on a TCP port like any other services we created at and deployed to the fleet."

[00159] Do the contradiction form's two costs stand: a later route after a failover, and sessions kept on a primary cut off together with the engine host? (Decision: 1)
  1. **Accept both** — new sessions reach a new primary 5 to about 7.3 s after the switch, against 1.0 to 4.1 s today where the new primary's rule comes first; and with the engine host and the primary cut off together from both other nodes past the Sentinels' 5 s, both sessions stay on the primary, which accepts their writes for 9 to 12 s and loses them at the heal, where today two placements in three are cut 3 to 4 s in and the third loses the same 9 to 12 s.
  2. **Close the second by cutting on a lost quorum** — the judge's design 1, set aside under the first entry's option 1: a loss burst inside an in-region node's reboot then cuts both sessions while their path and the quorum stand.
  Human: "for 00159, accept both for Q1. for 00158, spec approved"
  The options stand as they were put. Their 9 to 12 s is read in Valkey 9.1.2's `replication.c` and `server.c` and not run (spec 00159, *The constructs*).
```

- [ ] **Step 4: Tests,** `tests/test_decisions_log_shape.py` and `tests/test_decisions_log_ties.py` as the task's own, the gate, commit `docs(research): the cache proxy's quorum route, its proof on the pinned binary, the bursts' investigation and the failover's two costs`.

## Outside the implementer's tasks

In the spec's order; no implementer runs any of these.

- **P0. The spec's step-2 fence — the coordinator, done at `72099202f`.** The spec's *Runbook texts* fence for `zcrypto-cache-proxy-no-backend`'s step 2 carried `Every route failing at once` in a numbered item of a contract page, which the commit-msg guidance guard refuses; it now reads `All three routes failing at once`, with a dated line in the spec's own amendments, and Task 6 takes it verbatim, Task 6 Step 3's `--uncounted` read its guard.
- **P1. The fetch — the coordinator, after Task 1's verdict commit and before Task 2.** From the branch worktree: `uv run python infra/scripts/cache-proxy-harness.py fetch --digest sha256:76928c0d6b39bdd5f1c15d519cf48c47a6aa18c1dc552f7af1c146d2aa003c14 --into /home/zhaow/Projects/zcrypto-kraken/.claude/worktrees/proxy-quorum/.tmp/00159/haproxy-76928c0d6b39`, the digest `docs/reference/fleet-pins.md`'s `76928c0d6b39` line spells in full; anonymous, no credential. Reads back: exit 0 and a last line naming the tree and `76928c0d6b39`. Tasks 3 and 5 take that tree as `ROOTFS`. It is the first run of `fetch`'s default getter against the real registry, which no test reaches: an exit 1 is a defect in Task 1's code and goes back to Task 1 as a fix commit, its lines the evidence, and P1 runs again once its partial tree is removed; an exit 2, a refusal, stops the plan and goes to the owner with its lines. P1 runs before Task 2 so the binary is in place before the template is committed; a `parse` run over the spec's template cannot join it there, since Task 1's code carries `render` and `fetch` alone and the binary is run only by Task 3's `run`, so Task 3 Step 5's full run is the template's first on the binary, a case failing there returning to the spec, and P2's run stays the merge's gate.
- **P2. Before the merge — the coordinator.** The branch's one walker run; the `pre-review`, `review` and fix reads; the full harness run on the tip, `run --rootfs <ROOTFS> --scratch .tmp/00159/pr`, its nine case lines and summary pasted verbatim into the PR body with the tip whose template it read; the PR body also names what this plan adds beyond the spec's letter — the run's once-per-run maps read and its exit 2, `IMAGE_DIGEST_FILE`, the fetch's `_inside` check and its replacement of a lower layer's entry, the default getter's unredirected token, the tests past the change list's "its two cases", Task 6's `RATIO` read, and Task 8's four decisions-log entries in `docs/research/14.phase6-decisions.md`; `docs/reference/change-index.md`'s row through `open-pr`'s Step 4.
- **1. The merge — the coordinator,** through `open-pr` and `merge-pr`. Immediately before it, the spec's push hold (*The rule and the board*): the recording branch the spec's *Deployment* step 1 names, cut from `develop`, and its PR opened as a draft through `open-pr`, whose Step 4 commits the branch's change-index row before the create, its body's `## Grafana push` section naming the hold and nothing pushed. Reads back: the push skill's Step 2 `gh pr list` line printing that draft's number, before the merge; the merge on `develop`.
- **2. Planning reads — the coordinator, on the workstation:** the Kraken maintenance feed at `https://status.kraken.com/api/v2/scheduled-maintenances.json` read whole. The gap is the owner's choice, Q2, open: the first after the merge clear of 09:25, 13:25, 17:25 and any window the feed carries, recommended.
- **3. The preview, early — the coordinator, under `zcrypto-rollout-image`:** step 5's converge with `--check --diff`, from the tree step 5 converges from. Reads back: no change shown but this change's — the render, shown only as changed, `no_log` and `diff: false` holding it; step 5 waits on that read; the role's `haproxy -c`, the render's first parse with the real `requirepass` on the host's pinned image, passing; the skill's Phase 3 item 9 — `engine preflight — refuse …` and `engine provenance — refuse …` each `All assertions passed`, `engine preflight override — …` `skipping`.
- **4. Immediately before, inside the gap.** The coordinator, on the workstation: the feed whole again; flat, `kraken open-orders -o json` listing nothing, `kraken positions -o json` printing `{}`, `kraken extended-balance -o json` showing no lot. The owner: `zcrypto_exec_reconciliation_positions` at 0 by value (Q2's second ask); on the host, the running digests by their `.Config.Image` field alone, the proxy's reading `76928c0d6b39`; `curl -s 127.0.0.1:9104/metrics | grep 'haproxy_server_check_status.*state="L7OK"} 1'` reading the primary's three lines and `curl -s 127.0.0.1:9104/metrics | grep 'haproxy_backend_current_sessions'` reading 2 on the primary's backend.
- **5. The converge — the owner's hand,** never wrapped in `timeout`, from the main checkout on `develop` holding the merge, whose preview at step 3 showed no diff but this change's: `infra/ansible/scripts/converge.sh site.yml --limit zcrypto --tags engine -e converge_primary=true -e engine_image_digest=sha256:<the running engine> -e cache_proxy_image_digest=sha256:<the running proxy>`. Reads back: the window assert and the engine preflight passing, rc 0, the deploy-log line appended uncommitted to the main checkout's `docs/reference/deploy-log.jsonl`; `fleet-pins.md` untouched.
- **6. After, by value.** The coordinator: the new deploy-log line's `preflight` — `engaged` true, `rc` 0, `first_parent` true, `line` carrying `"ok": true` — and its `window`. The owner, on the host: the engine container's `.State.StartedAt` alone; `L7OK` on four servers, the primary's three votes and its route; `L7STS` on the other two routes, the code the harness's `start` case reads on them; `L7TOUT` on the other six votes; `haproxy_backend_current_sessions{proxy="node<P>"}` at 2 after the engine's boot line; `sudo docker stats --no-stream zcrypto-cache-proxy` under 32m; `uname -r`, and `net.ipv4.tcp_syn_retries` with `net.ipv4.tcp_syn_linear_timeouts` through `sudo nsenter -t <pid> -n sysctl`, the pid from `sudo docker inspect --format '{{.State.Pid}}' zcrypto-cache-proxy` alone; at the next boundary, the engine's `cycle-<HH>.json` with `completed_at` inside its first 30 minutes.
- **7. Before the push — the coordinator:** `uv run python infra/scripts/grafana-query.py 'haproxy_backend_active_servers{host="zcrypto"}'` lists six backends, the primary's votes at 3 and its route at 1.
- **8. The push — the coordinator, through `zcrypto-grafana-push`:** first the hold's section removed from the recording PR's body through `open-pr`, the skill's Step 2 `gh pr list` then printing no number of this rollout's; then `alerts.yaml` and `cache-dashboard.json`. Reads back: the rule's A at 3 by value and the rule Normal; panel 402 above its red line; nothing pruned, the uid unchanged.
- **9. The record — the coordinator:** step 5's deploy-log line, and the way back's if it ran, committed on the recording branch step 1 cut, which first takes `origin/develop` by merge as the spec's step 9 says, the one recording PR undrafted and merged through `open-pr` and `merge-pr`, its message carrying steps 4, 6, 7 and 8 by value; `infra/scripts/count-list.sh engine-preflight-overrides` and `infra/scripts/count-list.sh engine-rows-outside-the-gap` count nothing from it; a commit made before the next boundary's cycle file lands owes that read as a second commit.
- **10. The days after — `zcrypto-daily-ops`, handed the converge's date by the coordinator:** for seven passes, by value through `grafana-query.py`, the routes' and the votes' `increase(haproxy_server_check_failures_total{…}[24h])` and the `cache-proxy` WARNING count, into each journal entry, findings classed as the spec's step 10 classes them; a vote DOWN outside a reboot, restart, converge or failover goes to the coordinator as a reading for the burst investigation.
- **The way back — the owner's hand, in the same gap:** a route not up within a minute of the restart, or no boot line within ten minutes, is the same converge from a detached worktree at the merge's first parent with `ZCRYPTO_DEPLOY_LOG=<the main checkout>/docs/reference/deploy-log.jsonl`, its row read back in the main checkout before the worktree is removed; the last resort `-e engine_cache_enabled=false` from the main checkout, the two proxy pages silenced as `cache.md` says. The push waits until the converge holds; the hold's section and the draft stay as the spec's *The rule and the board* says.
- **Not on this branch — the coordinator's attended work on the owner's word (D8):** the two-layer probe on valkey3 for the loss bursts, its reading to the owner; no file here, and not raised with Linode.
