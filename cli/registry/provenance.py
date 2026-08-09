"""Dataset provenance capture for the trial registry (spec 00086).

A record's `dataset_hash` used to be an opaque string the caller supplied; for 44 of 46 committed
records nobody can resolve it, because the driver that computed it was never committed. This module
captures, from disk, the block that replaces it: the resolved slice a trial declared, the set's own
digest, and that slice's extent.

SCOPE IS AN EXPLICIT ALLOWLIST, and that is the design rather than a limitation (D1). An earlier
generic version -- capture from any dataset's manifest -- failed four cold-review rounds because the
manifest ecosystem has no contract: five writers, four `series` shapes, two set-digest spellings, a
per-run nonce in `ohlc-reach`, an absolute machine-local `source` in `ohlc-15m`. Two hand-written
adapters cover every dataset that has ever backed a trial. A new one is refused until someone adds
an adapter deliberately -- which is exactly when they have the context to decide what that dataset's
identity should be. See [[T0132]] for the normalisation this defers.
"""

from __future__ import annotations

import json
from pathlib import Path

from cli.registry.errors import RegistryError

# name -> adapter. Every key matches exactly OR as a `<key>-...` prefix, so `ohlc-holdout-<date>`
# resolves, and so does a re-freeze sibling `ohlc-full-<stamp>`: revisions mint siblings rather than
# overwriting (cli/data/rebuild.py), so a sibling is the canonical's own successor -- same writer,
# same shape. Refusing it would refuse the revision workflow itself.
ALLOWLIST: dict[str, str] = {"ohlc-full": "backfill", "ohlc-15m": "backfill", "ohlc-holdout": "holdout"}

_AXES: dict[str, tuple[str, ...]] = {"backfill": ("pairs", "intervals"), "holdout": ("assets",)}


def _adapter_for(name: str) -> str:
    for key, adapter in ALLOWLIST.items():
        if name == key or name.startswith(key + "-"):
            return adapter
    raise RegistryError(
        f"{name}: no adapter -- provenance capture is an explicit allowlist ({', '.join(sorted(ALLOWLIST))}). "
        "Add an adapter for this dataset deliberately rather than reading its manifest generically."
    )


def _selected(token: str, wanted: list[str] | None) -> bool:
    # An absent or empty axis list means all of that axis (D2).
    return not wanted or token in wanted


def _check_axes(name: str, sel: dict[str, list[str]], adapter: str) -> None:
    allowed = _AXES[adapter]
    for key in sel:
        if key not in allowed:
            raise RegistryError(f"{name}: unknown select axis {key!r}; this adapter's axes are {list(allowed)}")


def _check_tokens(name: str, axis: str, wanted: list[str] | None, membership: set[str]) -> None:
    for token in wanted or []:
        if token not in membership:
            raise RegistryError(f"{name}: select {axis} token {token!r} matches nothing in this manifest")


def _resolved(wanted: list[str] | None, membership: set[str]) -> list[str]:
    # RESOLVED, not echoed: the caller's list when non-empty, else the axis's full membership, so
    # `{}` and the fully spelled-out slice produce one digest and the block names what was read
    # without the (gitignored) manifest.
    return sorted(set(wanted)) if wanted else sorted(membership)


def _extent(leaves: list[dict]) -> dict:
    rows = sum(leaf["rows"] for leaf in leaves)
    # Raw strings: the holdout's stamps use a space rather than `T`, and a round-trip through a
    # datetime would silently rewrite what is recorded.
    return {
        "series": len(leaves),
        "rows": rows,
        "span": [min(leaf["first_ts"] for leaf in leaves), max(leaf["last_ts"] for leaf in leaves)],
    }


def _series(name: str, manifest: dict, *, nested: bool) -> dict:
    series = manifest.get("series")
    shape = "series[pair][interval]" if nested else "series[asset]"
    if not isinstance(series, dict):
        raise RegistryError(f"{name}: key 'series' is {type(series).__name__}, expected a dict shaped {shape}")
    for value in series.values():
        if not isinstance(value, dict):
            raise RegistryError(f"{name}: key 'series' is not shaped {shape}")
        if nested and not all(isinstance(leaf, dict) for leaf in value.values()):
            raise RegistryError(f"{name}: key 'series' is not shaped {shape}")
    return series


def _capture_backfill(name: str, manifest: dict, sel: dict[str, list[str]]) -> dict:
    series = _series(name, manifest, nested=True)
    pairs = set(series)
    intervals = {interval for by_interval in series.values() for interval in by_interval}
    _check_tokens(name, "pairs", sel.get("pairs"), pairs)
    _check_tokens(name, "intervals", sel.get("intervals"), intervals)
    resolved = {"intervals": _resolved(sel.get("intervals"), intervals), "pairs": _resolved(sel.get("pairs"), pairs)}
    leaves = [
        leaf
        for pair, by_interval in series.items()
        for interval, leaf in by_interval.items()
        if _selected(pair, sel.get("pairs")) and _selected(interval, sel.get("intervals"))
    ]
    if not leaves:
        raise RegistryError(f"{name}: select {resolved} matched no series in this manifest")
    return {"select": resolved, "set_digest": manifest["basket_sha256"], "extent": _extent(leaves)}


def _capture_holdout(name: str, manifest: dict, sel: dict[str, list[str]]) -> dict:
    series = _series(name, manifest, nested=False)
    assets = set(series)
    _check_tokens(name, "assets", sel.get("assets"), assets)
    resolved = {"assets": _resolved(sel.get("assets"), assets)}
    leaves = [leaf for asset, leaf in series.items() if _selected(asset, sel.get("assets"))]
    if not leaves:
        raise RegistryError(f"{name}: select {resolved} matched no series in this manifest")
    # `manifest_sha256`, not `basket_sha256` -- the freeze is written outside this repo. Normalised
    # to one name so the block does not leak which writer produced the manifest (D2).
    return {"select": resolved, "set_digest": manifest["manifest_sha256"], "extent": _extent(leaves)}


_CAPTURE = {"backfill": _capture_backfill, "holdout": _capture_holdout}
_DIGEST_KEY = {"backfill": "basket_sha256", "holdout": "manifest_sha256"}


def capture_datasets(select: dict[str, dict[str, list[str]]], data_root: Path) -> dict:
    """The `datasets` block for a trial record, read from each named dataset's manifest.

    `select` maps dataset name -> per-axis token lists; an absent or empty axis means all of it.
    Refuses rather than guesses: an empty mapping, an unlisted dataset, an absent or unreadable
    manifest, a `series` block of the wrong shape, an unknown axis, a token matching nothing, or a
    selection resolving to no series. A record whose provenance could not be captured must not
    exist -- the alternative is a record that looks pinned and is not.
    """
    if not select:
        raise RegistryError("no dataset named: a record must declare the data it was fitted on")

    block: dict[str, dict] = {}
    for name in sorted(select):
        adapter = _adapter_for(name)
        sel = select[name] or {}
        _check_axes(name, sel, adapter)

        path = data_root / name / "manifest.json"
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc:
            raise RegistryError(f"{path}: manifest absent -- cannot capture provenance for {name}") from exc
        except (OSError, json.JSONDecodeError) as exc:
            raise RegistryError(f"{path}: manifest unreadable ({exc})") from exc

        digest_key = _DIGEST_KEY[adapter]
        if not manifest.get(digest_key):
            raise RegistryError(f"{name}: manifest carries no {digest_key}, which this adapter requires")

        block[name] = _CAPTURE[adapter](name, manifest, sel)
    return block
