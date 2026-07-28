from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import polars as pl
import pytest

from cli.archive.mint import already_minted, ledger_append, mint_hour
from cli.archive.pull import verify_tree
from cli.archive.reconcile import Block, Gap
from cli.capture.errors import CaptureError
from cli.capture.segment_writer import BOOK_SCHEMA, TRADE_SCHEMA, verify_manifest

H = datetime(2026, 7, 16, 9, tzinfo=UTC)
HOUR_END = H + timedelta(hours=1)  # the EXCLUSIVE next-hour boundary


def _frame(offsets: list[float], *, schema: dict = BOOK_SCHEMA) -> pl.DataFrame:
    n = len(offsets)
    return pl.DataFrame(
        {
            "ts": [H + timedelta(seconds=o) for o in offsets],
            "symbol": ["BTC/EUR"] * n,
            "type": ["update"] * n,
            "side": ["bid"] * n,
            "price": [float(o) for o in offsets],
            "qty": [1.0] * n,
            "checksum": [0] * n,
        },
        schema=schema,
    )


def _block(source: str, offsets: list[float], **kw) -> Block:
    frame = _frame(offsets, **kw)
    return Block(source, frame, frame["ts"].min(), frame["ts"].max())


def _blocks() -> list[Block]:
    """Primary, then secondary — and the secondary's rows are EARLIER than the primary's.

    Deliberately not time-sorted: `splice_book` emits block order, not time order, and a mint that
    "helpfully" sorted would reconstruct a different book (L2 rows carry absolute quantities). The
    price column doubles as a row fingerprint so the on-disk order is checkable.
    """
    return [_block("primary", [10.0, 20.0]), _block("secondary", [1.0, 2.0])]


def _trade_block(ids: list[int] | None = None) -> Block:
    """A trades-kind block, mirroring `_block` above but for a non-reconciler (backfill) caller."""
    ids = ids if ids is not None else [1]
    n = len(ids)
    frame = pl.DataFrame(
        {
            "ts": [H + timedelta(seconds=i) for i in range(n)],
            "symbol": ["BTC/EUR"] * n,
            "side": ["buy"] * n,
            "price": [float(i) for i in ids],
            "qty": [1.0] * n,
            "ord_type": ["market"] * n,
            "trade_id": ids,
        },
        schema=TRADE_SCHEMA,
    )
    return Block("rest", frame, frame["ts"].min(), frame["ts"].max())


def _hour_dir(root: Path) -> Path:
    return root / "BTC" / "EUR" / "book" / "2026" / "07" / "16"


def _mint(root: Path, **kw):
    kw.setdefault("gaps_healed", [])
    kw.setdefault("residual_gaps", [])
    return mint_hour(root, "BTC/EUR", "book", H, kw.pop("blocks", _blocks()), schema=BOOK_SCHEMA, tool_version="test", **kw)


# --- the plan's five ---------------------------------------------------------------------------


def test_mint_writes_a_verifiable_final_with_provenance(tmp_path):
    p = _mint(tmp_path)
    assert p == _hour_dir(tmp_path) / "09.parquet"
    assert p.exists()
    assert verify_manifest(p) is True  # the sidecar matches the final's bytes
    prov = json.loads(p.with_name("09.provenance.json").read_text())
    assert [b["source"] for b in prov["blocks"]] == ["primary", "secondary"]
    assert prov["pair"] == "BTC/EUR" and prov["kind"] == "book"
    assert prov["sha256"] == hashlib.sha256(p.read_bytes()).hexdigest()


def test_rows_land_in_block_order_never_sorted(tmp_path):
    p = _mint(tmp_path)
    # block order (10, 20 | 1, 2), NOT time order (1, 2, 10, 20)
    assert pl.read_parquet(p)["price"].to_list() == [10.0, 20.0, 1.0, 2.0]


def test_an_existing_minted_final_is_never_overwritten(tmp_path):
    p = _mint(tmp_path)
    before = p.read_bytes()
    assert already_minted(tmp_path, "BTC/EUR", "book", H) is True
    with pytest.raises(FileExistsError):
        _mint(tmp_path, blocks=[_block("secondary", [99.0])])
    assert p.read_bytes() == before  # the re-run is a no-op, not a rewrite
    assert verify_manifest(p) is True


def test_no_partial_state_is_left_if_the_mint_is_interrupted(tmp_path):
    # a torn temp file from a killed run must never be published as a final
    d = _hour_dir(tmp_path)
    d.mkdir(parents=True)
    (d / "09.parquet.tmp").write_bytes(b"garbage")
    p = _mint(tmp_path)
    assert verify_manifest(p) is True
    assert pl.read_parquet(p)["price"].to_list() == [10.0, 20.0, 1.0, 2.0]  # ours, not the garbage
    assert not (d / "09.parquet.tmp").exists()


def test_ledger_is_append_only_jsonl(tmp_path):
    ledger_append(tmp_path, {"state": "minted", "pair": "BTC/EUR"})
    ledger_append(tmp_path, {"state": "both_streams_silent", "pair": "ETH/EUR"})
    lines = (tmp_path / "reconcile-ledger.jsonl").read_text().splitlines()
    assert [json.loads(line)["state"] for line in lines] == ["minted", "both_streams_silent"]


# --- the hour-boundary contract (the caveat the plan flags) -------------------------------------


def _tail_gap(end: datetime) -> Gap:
    """The crash-shaped gap: last primary message -> the hour's end boundary."""
    start = H + timedelta(seconds=30)
    return Gap(
        start=start,
        end=end,
        seconds=(end - start).total_seconds(),
        start_is_primary_message=True,
        end_is_primary_message=False,
    )


def test_a_tail_gap_ending_on_the_exclusive_hour_boundary_is_accepted(tmp_path):
    p = _mint(tmp_path, gaps_healed=[_tail_gap(HOUR_END)])
    assert verify_manifest(p) is True


def test_a_tail_gap_that_stops_short_of_the_exclusive_hour_boundary_is_rejected(tmp_path):
    # Callers pass `hour_end` as the EXCLUSIVE next-hour boundary (10:00:00). 09:59:59.999999 makes
    # splice_book's tail filter (`ts >= gaps[-1].end`) admit primary rows AFTER the secondary block.
    # It must be loud, not silent.
    bad = _tail_gap(datetime(2026, 7, 16, 9, 59, 59, 999_999, tzinfo=UTC))
    with pytest.raises(CaptureError, match="hour boundary"):
        _mint(tmp_path, gaps_healed=[bad])
    assert not list(tmp_path.rglob("*.parquet"))  # nothing written on a rejected mint
    assert not list(tmp_path.rglob("*.tmp"))


def test_a_head_gap_that_does_not_start_on_the_hour_boundary_is_rejected(tmp_path):
    bad = Gap(
        start=H + timedelta(microseconds=1),
        end=H + timedelta(seconds=90),
        seconds=90.0,
        start_is_primary_message=False,
        end_is_primary_message=True,
    )
    with pytest.raises(CaptureError, match="hour boundary"):
        _mint(tmp_path, gaps_healed=[bad])


def test_a_gap_from_another_hour_is_rejected(tmp_path):
    stray = Gap(
        start=H + timedelta(hours=1, seconds=10),
        end=H + timedelta(hours=1, seconds=90),
        seconds=80.0,
        start_is_primary_message=True,
        end_is_primary_message=True,
    )
    with pytest.raises(CaptureError, match="outside the 09:00 hour"):
        _mint(tmp_path, gaps_healed=[stray])


def test_a_residual_gap_may_end_on_a_spliced_message_that_owns_no_primary_row(tmp_path):
    """A residual window is measured over the MINTED frame, so its interior edges are spliced
    secondary messages -- owned by neither the primary nor the hour. The ownership rule exists to
    keep `splice_book`'s row filters honest, and a residual gap drives no filter: it describes what
    the hour still lacks. Held to this contract, an hour could not report its own remaining holes."""
    interior = Gap(
        start=H,
        end=datetime(2026, 7, 16, 9, 19, 50, tzinfo=UTC),
        seconds=1190.0,
        start_is_primary_message=False,
        end_is_primary_message=False,
    )
    _mint(tmp_path, residual_gaps=[interior])  # no raise


def test_a_residual_gap_from_another_hour_is_still_rejected(tmp_path):
    """The bounds half of the contract still binds: a sidecar claiming a hole outside its own hour
    is a lie about which hour is incomplete."""
    stray = Gap(
        start=H + timedelta(hours=1, seconds=10),
        end=H + timedelta(hours=1, seconds=90),
        seconds=80.0,
        start_is_primary_message=True,
        end_is_primary_message=True,
    )
    with pytest.raises(CaptureError, match="outside the 09:00 hour"):
        _mint(tmp_path, residual_gaps=[stray])


def test_minting_a_datetime_that_is_not_an_exact_utc_hour_is_rejected(tmp_path):
    # `f"{hour:%H}"` would silently truncate 09:30 onto 09.parquet — the wrong hour's file.
    with pytest.raises(CaptureError, match="exact UTC hour"):
        mint_hour(
            tmp_path,
            "BTC/EUR",
            "book",
            H + timedelta(minutes=30),
            _blocks(),
            gaps_healed=[],
            residual_gaps=[],
            schema=BOOK_SCHEMA,
            tool_version="test",
        )


# --- the frame contract -------------------------------------------------------------------------


def test_minting_an_empty_hour_is_refused(tmp_path):
    # An empty final would claim "this hour is committed and complete, and it has no rows" — and the
    # reconciled-first reader would then shadow the raw primary hour with it.
    with pytest.raises(CaptureError, match="no blocks"):
        _mint(tmp_path, blocks=[])
    assert not list(tmp_path.rglob("*.parquet"))


def test_blocks_that_do_not_match_the_schema_are_refused(tmp_path):
    naive = {**BOOK_SCHEMA, "ts": pl.Datetime("us")}  # tz-naive: same columns, wrong dtype
    with pytest.raises(CaptureError, match="schema"):
        _mint(tmp_path, blocks=[_block("primary", [10.0], schema=naive)])
    assert not list(tmp_path.rglob("*.parquet"))


# --- crash states, built for real ---------------------------------------------------------------


def test_a_kill_between_the_sidecar_and_the_rename_leaves_no_final(tmp_path):
    """The invariant, exercised: `09.parquet` on disk ALWAYS means committed + complete + manifested.

    The kill is induced for real, not mocked: an obstruction on the provenance path (which is written
    after the sidecar and before the publishing rename) aborts the mint at exactly that point.
    """
    d = _hour_dir(tmp_path)
    d.mkdir(parents=True)
    (d / "09.provenance.json").mkdir()  # rename onto a directory -> IsADirectoryError, mid-mint

    with pytest.raises(IsADirectoryError):
        _mint(tmp_path)

    final = d / "09.parquet"
    assert not final.exists()  # NO final: the sidecar landed first, the rename never ran
    assert (d / "09.parquet.sha256").exists()
    assert already_minted(tmp_path, "BTC/EUR", "book", H) is False
    # the half-state is invisible to the archive verifier: it checks finals, and there is none
    assert verify_tree(tmp_path, now=HOUR_END).checked == 0

    # and the next run re-mints cleanly over it
    (d / "09.provenance.json").rmdir()
    p = _mint(tmp_path)
    assert verify_manifest(p) is True


def test_a_stale_sidecar_from_a_previous_run_is_never_trusted(tmp_path):
    """A sidecar left by a killed run certifies bytes that no longer exist. The re-mint must rewrite
    it from its OWN bytes — never publish a final under someone else's digest."""
    d = _hour_dir(tmp_path)
    d.mkdir(parents=True)
    stale = hashlib.sha256(b"the bytes of a mint that never landed").hexdigest()
    (d / "09.parquet.sha256").write_text(f"{stale}  09.parquet\n")
    (d / "09.parquet.tmp").write_bytes(b"a torn parquet")

    p = _mint(tmp_path)

    assert verify_manifest(p) is True  # never True over a file the sidecar does not match
    assert stale not in (d / "09.parquet.sha256").read_text()
    assert verify_tree(tmp_path, now=HOUR_END).failed == ()


def test_an_orphan_sidecar_with_no_final_is_not_a_minted_hour(tmp_path):
    d = _hour_dir(tmp_path)
    d.mkdir(parents=True)
    (d / "09.parquet.sha256").write_text(f"{'0' * 64}  09.parquet\n")
    assert already_minted(tmp_path, "BTC/EUR", "book", H) is False
    assert verify_tree(tmp_path, now=HOUR_END).checked == 0  # no final -> nothing to verify
    assert verify_manifest(_mint(tmp_path)) is True  # heals on the next run


def test_a_final_with_no_sidecar_is_reported_and_never_overwritten(tmp_path):
    """Unreachable from a kill (the sidecar is written first), so it is a hand-edit or a partial
    restore. Mint must refuse it rather than re-bless a file it did not write."""
    d = _hour_dir(tmp_path)
    d.mkdir(parents=True)
    (d / "09.parquet").write_bytes(b"someone else's bytes")

    with pytest.raises(CaptureError, match="no manifest"):
        verify_manifest(d / "09.parquet")
    assert verify_tree(tmp_path, now=HOUR_END).failed == (str(d / "09.parquet"),)
    assert already_minted(tmp_path, "BTC/EUR", "book", H) is True
    with pytest.raises(FileExistsError):
        _mint(tmp_path)
    assert (d / "09.parquet").read_bytes() == b"someone else's bytes"  # untouched
    assert not (d / "09.parquet.sha256").exists()  # and never manifested by us


def test_a_corrupted_final_never_verifies(tmp_path):
    p = _mint(tmp_path)
    p.write_bytes(p.read_bytes() + b"\x00")  # bit-rot after the mint
    assert verify_manifest(p) is False
    assert verify_tree(tmp_path, now=HOUR_END).failed == (str(p),)


# --- a second, non-reconciler caller (spec 00053 Task 3) ----------------------------------------


def test_tool_defaults_to_reconcile_and_is_overridable(tmp_path):
    hour = datetime(2026, 7, 11, 2, tzinfo=UTC)
    p = mint_hour(
        tmp_path,
        "BTC/EUR",
        "trades",
        hour,
        [_trade_block()],
        gaps_healed=[],
        residual_gaps=[],
        schema=TRADE_SCHEMA,
        tool_version="t",
    )
    prov = json.loads(p.with_name("02.provenance.json").read_text())
    assert prov["tool"] == "zcrypto archive reconcile"

    p2 = mint_hour(
        tmp_path,
        "ETH/EUR",
        "trades",
        hour,
        [_trade_block()],
        gaps_healed=[],
        residual_gaps=[],
        schema=TRADE_SCHEMA,
        tool_version="t",
        tool="zcrypto archive backfill-trades",
    )
    prov2 = json.loads(p2.with_name("02.provenance.json").read_text())
    assert prov2["tool"] == "zcrypto archive backfill-trades"


def test_extra_provenance_is_merged(tmp_path):
    hour = datetime(2026, 7, 11, 2, tzinfo=UTC)
    p = mint_hour(
        tmp_path,
        "BTC/EUR",
        "trades",
        hour,
        [_trade_block()],
        gaps_healed=[],
        residual_gaps=[],
        schema=TRADE_SCHEMA,
        tool_version="t",
        extra_provenance={"recovered_id_ranges": [[11, 14]], "deduped_rows": 2},
    )
    prov = json.loads(p.with_name("02.provenance.json").read_text())
    assert prov["recovered_id_ranges"] == [[11, 14]] and prov["deduped_rows"] == 2
    assert prov["sha256"] and prov["hour"]  # base fields survive the merge


def test_replace_false_still_refuses_an_existing_final(tmp_path):
    hour = datetime(2026, 7, 11, 2, tzinfo=UTC)
    mint_hour(
        tmp_path,
        "BTC/EUR",
        "trades",
        hour,
        [_trade_block()],
        gaps_healed=[],
        residual_gaps=[],
        schema=TRADE_SCHEMA,
        tool_version="t",
    )
    with pytest.raises(FileExistsError):
        mint_hour(
            tmp_path,
            "BTC/EUR",
            "trades",
            hour,
            [_trade_block()],
            gaps_healed=[],
            residual_gaps=[],
            schema=TRADE_SCHEMA,
            tool_version="t",
        )


def test_replace_true_re_mints_and_the_manifest_tracks_the_new_bytes(tmp_path):
    """The retry case: a gap recorded unrecoverable on an earlier run is recovered later, so the
    hour must be re-minted from the fuller union."""
    hour = datetime(2026, 7, 11, 2, tzinfo=UTC)
    mint_hour(
        tmp_path,
        "BTC/EUR",
        "trades",
        hour,
        [_trade_block(ids=[10, 11])],
        gaps_healed=[],
        residual_gaps=[],
        schema=TRADE_SCHEMA,
        tool_version="t",
    )
    p = mint_hour(
        tmp_path,
        "BTC/EUR",
        "trades",
        hour,
        [_trade_block(ids=[10, 11, 12])],
        gaps_healed=[],
        residual_gaps=[],
        schema=TRADE_SCHEMA,
        tool_version="t",
        replace=True,
    )
    assert pl.read_parquet(p).height == 3
    assert verify_manifest(p) is True  # sidecar regenerated for the NEW bytes


def test_extra_provenance_may_not_shadow_a_base_field(tmp_path):
    """The guard exists so a caller cannot make the provenance lie about the file it certifies:
    overriding `sha256` or `hour` would let the record disagree with the bytes it attests. Untested
    guards are one refactor away from silently not guarding, so the raising branch is pinned here.
    """
    hour = datetime(2026, 7, 11, 2, tzinfo=UTC)
    for field in ("sha256", "hour", "tool"):
        with pytest.raises(CaptureError, match="may not override the base field"):
            mint_hour(
                tmp_path / field,
                "BTC/EUR",
                "trades",
                hour,
                [_trade_block()],
                gaps_healed=[],
                residual_gaps=[],
                schema=TRADE_SCHEMA,
                tool_version="t",
                extra_provenance={field: "forged"},
            )
