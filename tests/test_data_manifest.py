"""The manifest contract (spec 00099) — one shape, so no consumer needs per-set knowledge."""

import hashlib
import io
import json
import urllib.error
import zipfile
from datetime import UTC, datetime

import pytest

from cli.data.manifest import (
    SCHEMA_VERSION,
    ManifestError,
    build_manifest,
    read_manifest,
    series_entry,
    set_digest,
)
from cli.ohlc.dataset import to_frame

WRITTEN_AT = "2026-08-24T09:00:00+00:00"


def _rows(n, start=1577836800):
    return [[start + i * 86400, "1", "2", "0.5", "1.5", "1.2", "10", 3] for i in range(n)]


def _series(paths_and_rows):
    return {p: series_entry(to_frame(_rows(n)), p) for p, n in paths_and_rows}


def _two():
    return _series([("ADA/EUR/1440.parquet", 5), ("BTC/EUR/1440.parquet", 7)])


# --- the leaf ------------------------------------------------------------------------------------


def test_a_series_entry_carries_exactly_the_contract_fields():
    entry = series_entry(to_frame(_rows(5)), "ADA/EUR/1440.parquet")
    assert set(entry) == {"sha256", "rows", "first_ts", "last_ts"}
    assert entry["rows"] == 5
    assert len(entry["sha256"]) == 64
    assert "T" in entry["first_ts"], "timestamps are ISO-8601 T-form, matching every writer today"


# --- the digest ----------------------------------------------------------------------------------


def test_the_digest_orders_by_series_key_not_by_insertion():
    s = _two()
    reordered = {k: s[k] for k in reversed(list(s))}
    assert set_digest(s) == set_digest(reordered)


def test_the_digest_moves_when_content_moves():
    a = _two()
    b = dict(a)
    b["ADA/EUR/1440.parquet"] = series_entry(to_frame(_rows(6)), "ADA/EUR/1440.parquet")
    assert set_digest(a) != set_digest(b)


def test_a_digest_over_an_empty_series_set_is_refused():
    # sha256("") is a fixed sentinel: two unrelated empty sets would compare EQUAL, which is the
    # opposite of what a set digest is for.
    with pytest.raises(ManifestError, match="empty"):
        set_digest({})


def test_a_subset_digest_covers_only_its_keys():
    s = _two()
    only_ada = set_digest(s, keys=["ADA/EUR/1440.parquet"])
    assert only_ada != set_digest(s)
    assert only_ada == set_digest({"ADA/EUR/1440.parquet": s["ADA/EUR/1440.parquet"]})


def test_a_subset_naming_an_unknown_key_is_refused():
    with pytest.raises(ManifestError, match="not in series"):
        set_digest(_two(), keys=["NOPE/EUR/1440.parquet"])


# --- identity ------------------------------------------------------------------------------------


def test_identity_defaults_to_the_set_wide_digest():
    m = read_manifest_from(build_manifest(_two(), written_at=WRITTEN_AT))
    assert m.identity_digest == m.set_sha256


def test_identity_can_name_a_subset_so_no_caller_branches_on_a_dataset_name():
    # Why this exists: reach's identity is its CONTINUOUS subset while ohlc-full's is set-wide.
    # Without a declared identity the caller must know which is which -- the per-set knowledge
    # this contract exists to remove, merely moved one layer up.
    s = _two()
    raw = build_manifest(s, written_at=WRITTEN_AT, subsets={"continuous": ["ADA/EUR/1440.parquet"]}, identity="subset:continuous")
    m = read_manifest_from(raw)
    assert m.identity_digest == m.subset_sha256["continuous"]
    assert m.identity_digest != m.set_sha256


def test_identity_naming_an_absent_subset_is_refused():
    with pytest.raises(ManifestError, match="identity"):
        build_manifest(_two(), written_at=WRITTEN_AT, identity="subset:nope")


def test_a_subset_with_no_members_is_refused():
    with pytest.raises(ManifestError, match="empty"):
        build_manifest(_two(), written_at=WRITTEN_AT, subsets={"continuous": []})


# --- provenance is quarantined, in code ------------------------------------------------------------


def test_provenance_does_not_move_any_digest():
    s = _two()
    bare = build_manifest(s, written_at=WRITTEN_AT)
    loud = build_manifest(s, written_at=WRITTEN_AT, provenance={"source": "/somewhere/local", "built_at": "whenever"})
    assert bare["set_sha256"] == loud["set_sha256"]


def test_a_hash_planted_in_provenance_never_reaches_the_vouched_set():
    # `_manifest_sha256s` walks ANY json for the key `sha256`, so prose alone would not have held:
    # a hash under provenance would attest content nothing checked. The reader reads series
    # explicitly instead.
    planted = "f" * 64
    raw = build_manifest(_two(), written_at=WRITTEN_AT, provenance={"nested": {"sha256": planted}})
    m = read_manifest_from(raw)
    assert planted not in m.vouched
    assert len(m.vouched) == 2


# --- reading -------------------------------------------------------------------------------------


def read_manifest_from(raw, tmp=None):
    import tempfile
    from pathlib import Path

    d = Path(tmp or tempfile.mkdtemp())
    (d / "manifest.json").write_text(json.dumps(raw))
    return read_manifest(d / "manifest.json")


def test_round_trip_preserves_every_field():
    raw = build_manifest(_two(), written_at=WRITTEN_AT, provenance={"source": "x"})
    m = read_manifest_from(raw)
    assert m.schema_version == SCHEMA_VERSION
    assert m.written_at == WRITTEN_AT
    assert m.provenance == {"source": "x"}
    assert m.hash_by_path()["ADA/EUR/1440.parquet"] == raw["series"]["ADA/EUR/1440.parquet"]["sha256"]


def test_a_legacy_manifest_is_refused_typed_rather_than_guessed_at():
    # The zoo's four shapes are readable only by guessing. Refusing is what makes the contract a
    # contract; the caller decides whether to convert.
    with pytest.raises(ManifestError, match="schema_version"):
        read_manifest_from({"fetched_at": "x", "series": {"ADA": {"1440": {"sha256": "a" * 64}}}})


def test_an_unknown_schema_version_is_refused():
    raw = build_manifest(_two(), written_at=WRITTEN_AT)
    raw["schema_version"] = SCHEMA_VERSION + 1
    with pytest.raises(ManifestError, match="schema_version"):
        read_manifest_from(raw)


@pytest.mark.parametrize("missing", ["sha256", "rows", "first_ts", "last_ts"])
def test_a_leaf_missing_any_contract_field_is_refused(missing):
    raw = build_manifest(_two(), written_at=WRITTEN_AT)
    del raw["series"]["ADA/EUR/1440.parquet"][missing]
    with pytest.raises(ManifestError, match=missing):
        read_manifest_from(raw)


@pytest.mark.parametrize("bad", ["/abs/path.parquet", "../escape.parquet", "no-suffix"])
def test_a_series_key_that_is_not_a_relative_parquet_path_is_refused(bad):
    # The key IS the path, so a key that cannot be one silently breaks every path-bound consumer.
    s = _two()
    s[bad] = s.pop("ADA/EUR/1440.parquet")
    with pytest.raises(ManifestError):
        read_manifest_from(build_manifest(s, written_at=WRITTEN_AT))


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("set_sha256", None),
        ("set_sha256", "not-a-hash"),
        ("set_sha256", "z" * 64),
        ("written_at", ""),
        ("identity", 7),
    ],
)
def test_the_documents_own_identity_fields_are_refused_when_malformed(field, value):
    # This reader feeds committed provenance citations, so "refusing beats guessing" has to hold
    # for the document's identity, not only for its series.
    raw = build_manifest(_two(), written_at=WRITTEN_AT)
    raw[field] = value
    with pytest.raises(ManifestError):
        read_manifest_from(raw)


def test_a_subset_digest_that_is_not_a_digest_is_refused():
    raw = build_manifest(
        _two(), written_at=WRITTEN_AT, subsets={"continuous": ["ADA/EUR/1440.parquet"]}, identity="subset:continuous"
    )
    raw["subset_sha256"]["continuous"] = None
    with pytest.raises(ManifestError, match="subset_sha256"):
        read_manifest_from(raw)


def test_an_empty_series_map_is_refused_at_build():
    with pytest.raises(ManifestError, match="empty"):
        build_manifest({}, written_at=WRITTEN_AT)


# --- the ordering pin, on fixtures that can actually bite -------------------------------------------
#
# Path-lexicographic re-anchors reach's committed digests -- safe only because `convert_dataset`
# refuses any conversion whose recomputed hash SET is not exactly what the legacy manifest attested.

from pathlib import Path as _Path

_HUB_REACH = _Path("/mnt/zhao-crypto/hot/ohlc-reach/manifest.json")
_LOCAL_REACH = _Path("data/ohlc-reach-20260813/manifest.json")


def _reach_series(manifest_path, *, continuous):
    """Legacy-shaped rows and the value the legacy writer digested them to.

    Reads `provenance.legacy` once a set has been converted, so the pin keeps comparing against the
    ORIGINAL recipe's output rather than re-pinning itself to the new one."""
    raw = json.loads(manifest_path.read_text())
    if raw.get("schema_version") is not None:
        legacy = raw["provenance"]["legacy"]
        suffix = ".detached.parquet" if not continuous else ".parquet"
        out = {
            key: {"sha256": leaf["sha256"]}
            for key, leaf in raw["series"].items()
            if key.endswith(".detached.parquet") is (not continuous) and key.endswith(suffix)
        }
        return legacy, out
    out = {}
    for row in raw["series"]:
        if (row["status"] == "continuous") is not continuous:
            continue
        stem = f"{row['interval']}.parquet" if continuous else f"{row['interval']}.detached.parquet"
        out[f"{row['symbol']}/EUR/{stem}"] = {"sha256": row["sha256"]}
    return raw, out


@pytest.mark.skipif(not _HUB_REACH.is_file(), reason="needs the hot hub mounted")
def test_path_order_re_anchors_the_hub_reach_continuous_digest_and_the_move_is_deliberate():
    raw, series = _reach_series(_HUB_REACH, continuous=True)
    assert len({k.rsplit("/", 1)[1] for k in series}) > 1, "degenerate fixture: needs >1 interval to bite"
    assert set_digest(series) == "356826a172dd33cab5caa3e527592e827c619fb6d1975baf0c7d95020141c6f1"
    assert set_digest(series) != raw["basket_sha256"], (
        "the re-anchor is expected; silently matching would mean the recipe did not change"
    )
    assert raw["basket_sha256"] == "8a826898241a5f1e5501db6ffeb398b81780ffd7cbbfedc1b230231432e13ab2"


@pytest.mark.skipif(not _LOCAL_REACH.is_file(), reason="needs the local reach sibling")
def test_path_order_re_anchors_the_local_reach_detached_digest():
    raw, series = _reach_series(_LOCAL_REACH, continuous=False)
    assert len({k.rsplit("/", 1)[1] for k in series}) > 1, "degenerate fixture: needs >1 interval to bite"
    assert set_digest(series) == "5907b1e31f45237831449c72e00185299bfa8a604ee7c4f10ed4133c931032d9"
    assert set_digest(series) != raw["detached_sha256"]
    assert raw["detached_sha256"] == "0c07900fb9cf68419630dd8d14d62894e144f2d8f66a07c8bd130964007d53e0"


def test_an_empty_series_is_a_healthy_producer_output_not_a_fault():
    # derivatives-funding and -oi already emit first_ts: None for a perp with no rows. Refusing
    # that would refuse a healthy run; the KEY must still be present, because absent means the
    # writer forgot and null means there is no span.
    entry = series_entry(to_frame([]), "PF_XBTUSD/funding.parquet")
    assert entry["rows"] == 0 and entry["first_ts"] is None and entry["last_ts"] is None
    m = read_manifest_from(build_manifest({"PF_XBTUSD/funding.parquet": entry}, written_at=WRITTEN_AT))
    assert m.vouched == {entry["sha256"]}


def test_one_span_bound_null_and_the_other_set_is_refused():
    s = _two()
    s["ADA/EUR/1440.parquet"]["last_ts"] = None
    with pytest.raises(ManifestError, match="span"):
        read_manifest_from(build_manifest(s, written_at=WRITTEN_AT))


# --- every writer, one contract --------------------------------------------------------------------
#
# One driver per module of `cli/` that names `build_manifest`. Each reaches its remote through an
# injected seam, so every producer runs offline against a tmp tree.


class _Resp(io.BytesIO):
    """What `urlopen` hands back: a context manager over the body."""

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()
        return False


def _zipped(member: str, text: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(member, text)
    return buf.getvalue()


def _binance_opener(zips: dict[str, bytes]):
    """A `urlopen` stand-in over a {url: zip-bytes} map, deriving each `.CHECKSUM` from its zip's real
    sha256 so the producers' verify path runs rather than passes; an absent url 404s, which both
    Binance producers read as an unpublished period."""
    files = dict(zips)
    for url, body in zips.items():
        files[f"{url}.CHECKSUM"] = f"{hashlib.sha256(body).hexdigest()}  {url.rsplit('/', 1)[-1]}\n".encode()

    def _open(url, timeout=None):
        if url not in files:
            raise urllib.error.HTTPError(url, 404, "Not Found", {}, None)
        return _Resp(files[url])

    return _open


def _drive_backfill(tmp_path):
    """The OHLCVT dump reader: previously nested symbol -> interval, two levels deep."""
    from cli.backfill.backfill import backfill_basket

    src = tmp_path / "src"
    src.mkdir()
    minute = "\n".join(f"{1577836800 + i * 60},1,2,0.5,1.5,10,3" for i in range(60)) + "\n"
    with zipfile.ZipFile(src / "Kraken_OHLCVT.zip", "w") as zf:
        zf.writestr("master_q4/XBTEUR_1.csv", minute)
    out = tmp_path / "full"
    backfill_basket(src, ["BTC/EUR"], ["60"], out, WRITTEN_AT)
    return out / "manifest.json"


def _drive_ingest(tmp_path):
    """v0 ingest: previously a LIST of rows, hashing under the key `dataset_hash`."""
    from cli.ohlc.ingest import ingest_basket

    out = tmp_path / "v0"
    ingest_basket(
        {"BTC/EUR": "XXBTZEUR"},
        [1440],
        out,
        WRITTEN_AT,
        fetch_fn=lambda *_: [[1577836800, "1", "2", "0.5", "1.5", "1.2", "10", 3]],
    )
    return out / "manifest.json"


def _drive_reach(tmp_path):
    """The REST reach round: the one producer whose identity is a declared subset, not the set digest.

    The REST rows overlap the canonical tail by ten stamps, so the leg lands continuous and this is the
    one driver whose manifest carries `identity == "subset:continuous"` rather than the set digest."""
    from cli.ohlc.dataset import write_parquet
    from cli.ohlc.reach import reach_round

    canonical, out = tmp_path / "canon", tmp_path / "reach"
    write_parquet(to_frame(_rows(20)), canonical / "BTC" / "EUR" / "1440.parquet")
    rest = _rows(15, start=1577836800 + 10 * 86400)
    reach_round(
        canonical,
        out,
        intervals=(1440,),
        fetch_fn=lambda *_: rest,
        clock=lambda: datetime(2020, 3, 1, tzinfo=UTC),
        sleep_fn=lambda _seconds: None,
    )
    return out / "manifest.json"


def _drive_funding(tmp_path):
    """The funding substrate: one perp, one published month; the earlier months 404 as a pre-listing run."""
    from cli.derivatives.funding import build_funding_substrate

    url = "https://data.binance.vision/data/futures/um/monthly/fundingRate/BTCUSDT/BTCUSDT-fundingRate-2020-01.zip"
    csv = "calc_time,funding_interval_hours,last_funding_rate\n1577836800000,8,0.0001\n"
    out = tmp_path / "funding"
    build_funding_substrate(
        out,
        perps={"BTC": "BTCUSDT"},
        clock=lambda: datetime(2020, 2, 15, tzinfo=UTC),
        opener=_binance_opener({url: _zipped("BTCUSDT-fundingRate-2020-01.csv", csv)}),
    )
    return out / "manifest.json"


def _drive_oi(tmp_path):
    """The open-interest substrate: one perp, one published day."""
    from cli.derivatives.oi import build_oi_substrate

    url = "https://data.binance.vision/data/futures/um/daily/metrics/BTCUSDT/BTCUSDT-metrics-2020-01-01.zip"
    header = (
        "create_time,symbol,sum_open_interest,sum_open_interest_value,"
        "count_toptrader_long_short_ratio,sum_toptrader_long_short_ratio,"
        "count_long_short_ratio,sum_taker_long_short_vol_ratio"
    )
    row = "2020-01-01 00:00:00,BTCUSDT,100.5,100000.0,2.1,1.2,2.0,0.94"
    out = tmp_path / "oi"
    build_oi_substrate(
        out,
        perps={"BTC": "BTCUSDT"},
        start=datetime(2020, 1, 1, tzinfo=UTC),
        clock=lambda: datetime(2020, 1, 2, tzinfo=UTC),
        opener=_binance_opener({url: _zipped("BTCUSDT-metrics-2020-01-01.csv", f"{header}\n{row}\n")}),
    )
    return out / "manifest.json"


def _drive_convert(tmp_path):
    """The converter: rebuilds one legacy set's manifest from the parquets on disk."""
    from cli.data.manifest import convert_dataset
    from cli.ohlc.dataset import dataset_hash, write_parquet

    root = tmp_path / "legacy"
    frames = {"ADA/EUR/1440.parquet": to_frame(_rows(5)), "BTC/EUR/1440.parquet": to_frame(_rows(7))}
    for relpath, frame in frames.items():
        write_parquet(frame, root / relpath)
    legacy = {relpath: {"rows": frame.height, "sha256": dataset_hash(frame)} for relpath, frame in frames.items()}
    (root / "manifest.json").write_text(json.dumps({"fetched_at": WRITTEN_AT, "series": legacy}))
    convert_dataset(root, apply=True)
    return root / "manifest.json"


_PRODUCERS = {
    "cli/backfill/backfill.py": _drive_backfill,
    "cli/data/manifest.py": _drive_convert,
    "cli/derivatives/funding.py": _drive_funding,
    "cli/derivatives/oi.py": _drive_oi,
    "cli/ohlc/ingest.py": _drive_ingest,
    "cli/ohlc/reach.py": _drive_reach,
}


@pytest.mark.parametrize("module", sorted(_PRODUCERS))
def test_every_writer_emits_a_manifest_the_reader_accepts(module, tmp_path):
    """Asserted through `read_manifest` rather than by comparing dicts, because the reader is what a
    consumer actually uses -- a shape that only a bespoke assertion accepts is the zoo again."""
    m = read_manifest(_PRODUCERS[module](tmp_path))
    assert m.schema_version == SCHEMA_VERSION, module
    if module == "cli/ohlc/reach.py":
        assert m.identity == "subset:continuous", module
    assert m.identity_digest, module
    assert m.vouched, module
    assert all(k.endswith(".parquet") for k in m.series), module


def test_the_driver_table_names_every_module_that_builds_a_manifest():
    """A module that names `build_manifest` and is absent from the driver table reds here."""
    root = _Path(__file__).resolve().parents[1]
    naming = {p.relative_to(root).as_posix() for p in (root / "cli").rglob("*.py") if "build_manifest" in p.read_text()}
    assert naming == set(_PRODUCERS)
