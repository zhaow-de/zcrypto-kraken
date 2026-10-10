from __future__ import annotations

import errno
import hashlib
import json
import os
import re
import stat
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from typer.testing import CliRunner

from cli.__main__ import app
from cli.data import rolling
from cli.data.manifest import build_manifest, series_entry
from cli.data.rolling import Q3_15M_SHA256, Close, RollingError, extend, head, read_rolling, stage_base
from cli.ohlc.dataset import FRAME_SCHEMA, dataset_hash
from cli.tick.materialize import RESCAN_DAYS
from tests.rolling_fixtures import BASE_DAY, CLOSED, HOLE, SEAM, TAPE_ORDER, day_bars, line_bytes, write_chain

pytestmark = pytest.mark.data

runner = CliRunner()
TWELVE = (
    "ADA/EUR",
    "AVAX/EUR",
    "BTC/EUR",
    "DOGE/EUR",
    "DOT/EUR",
    "ETH/BTC",
    "ETH/EUR",
    "LINK/EUR",
    "LTC/EUR",
    "SOL/BTC",
    "SOL/EUR",
    "XRP/EUR",
)
OUTSIDER = "BTC/USD"
D = date(2026, 10, 2)
WORD, WORD_DATE = "the pair's tape stopped", date(2026, 10, 9)
_FINISHED = re.compile(
    r"index/\d{4}/\d{2}/\d{2}\.json|base/[A-Z0-9]+/[A-Z0-9]+/15\.parquet|days/[A-Z0-9]+/[A-Z0-9]+/\d{4}/\d{2}/\d{2}\.parquet"
)

_REPO_ROOT = Path(__file__).resolve().parents[1]
_DATA_ROOT = _REPO_ROOT / "data"
_ROLLING = _DATA_ROOT / "ohlc-rolling"

# `ts, open, high, low, close, count` of each of `ohlc-full-20261007`'s files under `dataset_hash`, which `derive_bars`
# over the pair's `ohlc-15m-20261007` file reproduces at 60, 240 and 1440.
Q3_COARSE_IDENTITY = {
    "ADA/EUR": {
        60: "4aa8c7415e74b3f3533b737c196bbd832765a2fb0e16d8780b00373fe9328d05",
        240: "9f1d43e614f84c4ff41df15400642251425b65805c7e376f19b18bd2488b1c17",
        1440: "3bde97837b0713986c863a7607952684079dc7bc6e8333925aabc04424361b4a",
    },
    "AVAX/EUR": {
        60: "45f5bb236e58347c66bf53aa117ef3089830f54daadef6fc372b4302e4fe9cc8",
        240: "b76742f54b1f88aeec7160e4316be39a7fe0f6a5662f9947be33564bbd4a36ce",
        1440: "baf79ba33a23d444f7dc9995b78e51fa57fb29b593df465d18ffd33e546d0199",
    },
    "BTC/EUR": {
        60: "8de3b163c16efdcedda516d72e10b2d8057a82955ab6908ef8f98e43ab81d39e",
        240: "e7345b65a39c4c1144a13252b42a139de011e074102496016976d3c98f569649",
        1440: "d7df07ba52d788c879e1e362cc70d39bbce55db5be14aec4b9a027b1622e3328",
    },
    "DOGE/EUR": {
        60: "0186967c78cd806626c8d2475b2df453bb084659ca03a00e409e2387c93767ba",
        240: "cad5590ebfd403f482143496acf72dfb80cdc6180c343499857c8eb63a349e80",
        1440: "717605594e7df07b488ff1093cd496340755fddc8ee82eead3605ae45f502561",
    },
    "DOT/EUR": {
        60: "00973ad27478169fc6049200ab47e7700aec8fbbc8019d2974019158567a3d32",
        240: "30987cc17987caa2b7482629435f23942a9b5d78eb420df0add10f32f0b3e9b2",
        1440: "6abc6d78db49dc68e048a662ffb60cf116a7dff4b9e93153e9445cc5d7a8389c",
    },
    "ETH/BTC": {
        60: "0555619676a8ed7e24335a0c0b67ca9fef3ed78478f29822b3536f1f916395c6",
        240: "5898792fd3437371515b68441e5701e6268e11bdb66b4cb5da7826e17bff3911",
        1440: "53b3081460b728ed5a6855f5f4517e28e9e203b30723475cf79350dd760a4070",
    },
    "ETH/EUR": {
        60: "3f762502336894481f2fe7d52d079b72b12ba86160a960678a4a9097ab015f43",
        240: "f86a1780c95fd2cbb11df2931a01f1d4c1c50a5cea48c5552364fd18ba737dea",
        1440: "52e4160a9a9622240fae7f88bcb5e869d4d4d960c3fe55771b873a7d3d959bca",
    },
    "LINK/EUR": {
        60: "5fbc1dd565b8e62f7cf6b507acc1e7302d8138167c2063fd7be0d341b3e104b4",
        240: "463babc098296071468b1ccbcc118fa464517c8870d8a5994dee61c9b6151eac",
        1440: "f34b6f5df5dc97980766c44a9177fd5c475e35d73137f5fea4e58daeeb4dfa71",
    },
    "LTC/EUR": {
        60: "6a2d7ab71292f5f957f6dab6c6815420ea498f48d5fed06b0150f157e4b8dc70",
        240: "a71a2ae703e476fef9e02c51d7d9faec6de822dfc5d2fd6b85e0fdf4675bd8e6",
        1440: "92737571f0cc6c08941d07dab62ea6beb1853365c81b3e2748d43def1b980638",
    },
    "SOL/BTC": {
        60: "4da1b35b90ddf8efdbc10629041a28a2235e6c2c5def0c3f403f85d2ec4966ae",
        240: "1822fa2c798811be5d13ebc0e54b35f1d5ecad5670746f24cb635cbb87b0f2d7",
        1440: "6f85440cda658edcad829c0abeece384af62353545c909ceaf1441cf025bf0f0",
    },
    "SOL/EUR": {
        60: "6f62c26e90bf0f30634f3baa885f9a7c4ffbf561716ddd1467f9ea8b675a6abc",
        240: "b0b362e6bc1842592772076ebfe1c04f18f46b91b61b060c3cd098673b98637e",
        1440: "468a7adb2f4610eab5df9a3bc31f043f46e9d4019cc7e4b99fbfbb5a15bf2147",
    },
    "XRP/EUR": {
        60: "a21afb27c5f900f05a63d5a9189c645260ac536c934b222020f3451c12d9b728",
        240: "06b0ae87eb745e695d1c644b06b507bb708a8ad9378ee7ffb3bfee4887b376d4",
        1440: "fe5bbf99b8d72a6ce463444e248880932b9e2bb0c9318ab53f11ab7f63155f52",
    },
}


def _days(first: date, last: date) -> list[date]:
    return [first + timedelta(days=n) for n in range((last - first).days + 1)]


def _source(root: Path, pairs: tuple[str, ...] = TWELVE) -> tuple[Path, dict[str, str]]:
    """A 15-minute source set of `pairs`, each file one day of `day_bars` in `FRAME_SCHEMA`'s order, under a conformant
    manifest; returns its directory and each pair's file sha256."""
    source = root / "ohlc-15m-fixture"
    series, hashes = {}, {}
    for pair in pairs:
        relpath = f"{pair}/15.parquet"
        frame = day_bars(TWELVE.index(pair), BASE_DAY, {})
        (source / pair).mkdir(parents=True)
        frame.write_parquet(source / relpath)
        series[relpath] = series_entry(frame, relpath)
        hashes[pair] = hashlib.sha256((source / relpath).read_bytes()).hexdigest()
    (source / "manifest.json").write_text(json.dumps(build_manifest(series, written_at="2026-10-07T00:00:00+00:00")))
    return source, hashes


def _edit_manifest(source: Path, edit: Callable[[dict], None]) -> None:
    manifest = json.loads((source / "manifest.json").read_text())
    edit(manifest)
    (source / "manifest.json").write_text(json.dumps(manifest))


def _put_final(tape: Path, pair: str, day: date) -> Path:
    """A tape-bars final in its own layout, beside its sidecar."""
    final = tape / pair / f"{day:%Y}" / f"{day:%m}" / f"{day:%d}.parquet"
    final.parent.mkdir(parents=True, exist_ok=True)
    index = TWELVE.index(pair) if pair in TWELVE else len(TWELVE)
    day_bars(index, day, {}).select(TAPE_ORDER).write_parquet(final)
    final.with_suffix(".parquet.sha256").write_text(f"{hashlib.sha256(final.read_bytes()).hexdigest()}  {final.name}\n")
    return final


def _finals(tape: Path, pairs: tuple[str, ...], first: date, last: date, *, skip: tuple[date, ...] = ()) -> None:
    for pair in pairs:
        for day in _days(first, last):
            if day not in skip:
                _put_final(tape, pair, day)


def _outbox(tmp_path: Path, pairs: tuple[str, ...] = TWELVE, days: int = 0) -> tuple[Path, Path, Path]:
    """A tape root, a set written by hand at `out` -- its base and `days` days -- and an empty staging directory."""
    tape, out, staging = tmp_path / "tape", tmp_path / "out", tmp_path / "staging"
    write_chain(out, pairs=pairs, days=days)
    tape.mkdir()
    staging.mkdir()
    return tape, out, staging


def _line(out: Path, day: date) -> dict:
    return json.loads((out / f"index/{day:%Y}/{day:%m}/{day:%d}.json").read_bytes())


def _line_sha256(out: Path, day: date) -> str:
    return hashlib.sha256((out / f"index/{day:%Y}/{day:%m}/{day:%d}.json").read_bytes()).hexdigest()


def _line_days(out: Path) -> list[date]:
    return sorted(date(int(p.parent.parent.name), int(p.parent.name), int(p.stem)) for p in (out / "index").glob("*/*/*.json"))


def _files_under(root: Path) -> set[str]:
    return {path.relative_to(root).as_posix() for path in root.rglob("*") if path.is_file()}


def _pairs_named(line: dict) -> set[str]:
    return {"/".join(relpath.split("/")[1:3]) for relpath in line["files"]} | set(line["holes"])


def _replace_refusing(monkeypatch, refuse: Callable[[Path], bool]) -> None:
    """`os.replace` raising what a replace across filesystems raises for each destination `refuse` names."""
    real = os.replace

    def replace(src, dst, *args, **kwargs):
        if refuse(Path(dst)):
            raise OSError(errno.EXDEV, os.strerror(errno.EXDEV), str(src), None, str(dst))
        return real(src, dst, *args, **kwargs)

    monkeypatch.setattr(os, "replace", replace)


def _close_args(pairs: tuple[str, ...], from_day: date) -> list[str]:
    args = [arg for pair in pairs for arg in ("--close-pair", pair)]
    return [*args, "--from", str(from_day), "--owner-word", WORD, "--owner-date", str(WORD_DATE)]


def _note(from_day: date) -> str:
    return f"from {from_day}, the owner's word of {WORD_DATE}: {WORD}"


def _extend_cli(tape: Path, out: Path, staging: Path, *extra: str):
    return runner.invoke(
        app, ["data", "rolling", "extend", "--tape-root", str(tape), "--out", str(out), "--staging", str(staging), *extra]
    )


def _base_cli(source: Path, out: Path, staging: Path):
    return runner.invoke(app, ["data", "rolling", "base", "--source", str(source), "--out", str(out), "--staging", str(staging)])


def _summary(result) -> str:
    return result.output.strip().splitlines()[-1]


def _says_ended(result) -> bool:
    return any(line.startswith("head=") and line.endswith(" ended") for line in result.output.splitlines())


def test_the_base_copies_the_source_byte_for_byte_and_writes_the_base_line(tmp_path, monkeypatch):
    source, hashes = _source(tmp_path)
    monkeypatch.setattr(rolling, "Q3_15M_SHA256", hashes)
    out, staging = tmp_path / "out", tmp_path / "staging"
    staging.mkdir()

    line = stage_base(source, out, staging)

    for pair in TWELVE:
        assert (out / "base" / pair / "15.parquet").read_bytes() == (source / pair / "15.parquet").read_bytes()
    data = (out / "index/2026/09/30.json").read_bytes()
    assert data == line_bytes(
        {
            "day": "2026-09-30",
            "prev": None,
            "files": {f"base/{pair}/15.parquet": hashes[pair] for pair in TWELVE},
            "holes": {},
            "notes": {
                "seam": "2026-10-01T00:00:00+00:00",
                "base_from": "ohlc-15m-fixture",
                "base_identity_digest": json.loads((source / "manifest.json").read_text())["set_sha256"],
                "vwap": "the dump's close-weighted proxy before the seam, the tape's tick-weighted mean from it",
            },
        }
    )
    assert line.sha256 == hashlib.sha256(data).hexdigest()
    assert list(staging.iterdir()) == []


def test_the_base_refuses_a_source_whose_bytes_are_not_the_q3_frame(tmp_path):
    source, _ = _source(tmp_path)
    out, staging = tmp_path / "out", tmp_path / "staging"
    staging.mkdir()

    with pytest.raises(RollingError, match=r"ADA/EUR/15\.parquet"):
        stage_base(source, out, staging)

    assert not out.exists()
    assert list(staging.iterdir()) == []


def test_the_base_refuses_a_source_file_its_manifest_does_not_attest(tmp_path, monkeypatch):
    source, hashes = _source(tmp_path)
    monkeypatch.setattr(rolling, "Q3_15M_SHA256", hashes)
    _edit_manifest(source, lambda m: m["series"]["BTC/EUR/15.parquet"].update(sha256=m["series"]["ETH/BTC/15.parquet"]["sha256"]))
    out, staging = tmp_path / "out", tmp_path / "staging"
    staging.mkdir()

    with pytest.raises(RollingError, match=r"BTC/EUR/15\.parquet"):
        stage_base(source, out, staging)

    assert not out.exists()
    assert list(staging.iterdir()) == []


def test_the_base_refuses_a_source_missing_one_of_the_twelve_pairs(tmp_path, monkeypatch):
    _, hashes = _source(tmp_path / "twelve")
    eleven = tuple(pair for pair in TWELVE if pair != "LINK/EUR")
    source, eleven_hashes = _source(tmp_path / "eleven", eleven)
    assert eleven_hashes == {pair: hashes[pair] for pair in eleven}
    monkeypatch.setattr(rolling, "Q3_15M_SHA256", hashes)
    out, staging = tmp_path / "out", tmp_path / "staging"
    staging.mkdir()

    with pytest.raises(RollingError, match="missing LINK/EUR"):
        stage_base(source, out, staging)

    assert not out.exists()
    assert list(staging.iterdir()) == []


def test_a_days_line_is_written_only_after_its_files(tmp_path, monkeypatch):
    tape, out, staging = _outbox(tmp_path, pairs=("BTC/EUR", "ETH/BTC"))
    _finals(tape, ("BTC/EUR", "ETH/BTC"), SEAM, SEAM)
    _replace_refusing(monkeypatch, lambda dst: dst.suffix == ".json")

    with pytest.raises(OSError, match=r"index/2026/10/01\.json"):
        extend(tape, out, staging)

    assert (out / "days/BTC/EUR/2026/10/01.parquet").is_file()
    assert (out / "days/ETH/BTC/2026/10/01.parquet").is_file()
    assert _line_days(out) == [BASE_DAY]


def test_a_rerun_after_a_stop_between_files_and_line_completes_the_day(tmp_path, monkeypatch):
    tape, out, staging = _outbox(tmp_path, pairs=("BTC/EUR", "ETH/BTC"))
    _finals(tape, ("BTC/EUR", "ETH/BTC"), SEAM, SEAM)
    with monkeypatch.context() as patched:
        _replace_refusing(patched, lambda dst: dst.suffix == ".json")
        with pytest.raises(OSError):
            extend(tape, out, staging)
    stopped = {relpath: (out / relpath).read_bytes() for relpath in _files_under(out) if relpath.startswith("days/")}
    assert len(stopped) == 2

    result = extend(tape, out, staging)

    assert (result.days_written, result.head.day) == (1, SEAM)
    assert {relpath: (out / relpath).read_bytes() for relpath in stopped} == stopped
    assert _line(out, SEAM)["files"] == {relpath: hashlib.sha256(data).hexdigest() for relpath, data in stopped.items()}
    assert list(staging.iterdir()) == []


def test_a_rerun_after_a_stop_between_the_base_files_and_its_line_completes_the_base(tmp_path, monkeypatch):
    source, hashes = _source(tmp_path)
    monkeypatch.setattr(rolling, "Q3_15M_SHA256", hashes)
    out, staging = tmp_path / "out", tmp_path / "staging"
    staging.mkdir()
    with monkeypatch.context() as patched:
        _replace_refusing(patched, lambda dst: dst == out / "index/2026/09/30.json")
        with pytest.raises(OSError):
            stage_base(source, out, staging)
    stopped = {relpath: (out / relpath).read_bytes() for relpath in _files_under(out)}
    assert set(stopped) == {f"base/{pair}/15.parquet" for pair in TWELVE}
    assert list(staging.iterdir()) == []

    line = stage_base(source, out, staging)

    assert (out / "index/2026/09/30.json").is_file()
    assert line.files == {relpath: hashes[relpath.removeprefix("base/").removesuffix("/15.parquet")] for relpath in stopped}
    assert {relpath: (out / relpath).read_bytes() for relpath in stopped} == stopped


def test_a_final_disagreeing_with_its_sidecar_is_refused_and_nothing_of_that_day_written(tmp_path):
    tape, out, staging = _outbox(tmp_path, pairs=("BTC/EUR", "ETH/BTC"))
    _finals(tape, ("BTC/EUR", "ETH/BTC"), SEAM, D)
    final = tape / "BTC/EUR/2026/10/02.parquet"
    data = bytearray(final.read_bytes())
    data[len(data) // 2] ^= 0xFF
    final.write_bytes(bytes(data))

    with pytest.raises(RollingError, match=r"BTC/EUR/2026/10/02\.parquet does not hash to its sidecar"):
        extend(tape, out, staging)

    assert D not in _line_days(out)
    assert not any(relpath.endswith("2026/10/02.parquet") for relpath in _files_under(out))


def test_a_final_without_its_sidecar_is_refused_and_nothing_of_that_day_written(tmp_path):
    tape, out, staging = _outbox(tmp_path, pairs=("BTC/EUR", "ETH/BTC"))
    _finals(tape, ("BTC/EUR", "ETH/BTC"), SEAM, D)
    (tape / "BTC/EUR/2026/10/02.parquet.sha256").unlink()

    with pytest.raises(RollingError, match=r"BTC/EUR/2026/10/02\.parquet has no sidecar"):
        extend(tape, out, staging)

    assert D not in _line_days(out)
    assert not any(relpath.endswith("2026/10/02.parquet") for relpath in _files_under(out))


def test_no_existing_file_is_rewritten(tmp_path):
    tape, out, staging = _outbox(tmp_path, pairs=("BTC/EUR", "ETH/BTC"))
    _finals(tape, ("BTC/EUR", "ETH/BTC"), SEAM, SEAM)
    present = line_bytes(
        {
            "day": "2026-10-01",
            "prev": _line_sha256(out, BASE_DAY),
            "files": {"days/BTC/EUR/2026/10/01.parquet": "1" * 64, "days/ETH/BTC/2026/10/01.parquet": "2" * 64},
            "holes": {},
        }
    )
    (out / "index/2026/10").mkdir(parents=True)
    (out / "index/2026/10/01.json").write_bytes(present)
    assert head(out).day == BASE_DAY

    with pytest.raises(RollingError, match=r"index/2026/10/01\.json is present with other bytes"):
        extend(tape, out, staging)

    assert (out / "index/2026/10/01.json").read_bytes() == present
    assert (out / "days/BTC/EUR/2026/10/01.parquet").read_bytes() == (tape / "BTC/EUR/2026/10/01.parquet").read_bytes()
    assert (out / "days/ETH/BTC/2026/10/01.parquet").read_bytes() == (tape / "ETH/BTC/2026/10/01.parquet").read_bytes()


def test_day_d_plus_one_waits_while_d_is_pending(tmp_path):
    tape, out, staging = _outbox(tmp_path)
    _finals(tape, TWELVE, SEAM, D + timedelta(days=1))
    (tape / "DOT/EUR/2026/10/02.parquet").unlink()
    (tape / "DOT/EUR/2026/10/02.parquet.sha256").unlink()

    result = extend(tape, out, staging)

    assert (result.head.day, result.days_written, result.ended) == (D - timedelta(days=1), 1, False)
    assert _line_days(out) == [BASE_DAY, SEAM]


def test_a_hole_is_written_only_past_the_rescan_window(tmp_path):
    tape, out, staging = _outbox(tmp_path)
    _finals(tape, TWELVE, SEAM, D + timedelta(days=1), skip=())
    (tape / "DOT/EUR/2026/10/02.parquet").unlink()
    (tape / "DOT/EUR/2026/10/02.parquet.sha256").unlink()
    _finals(tape, ("DOT/EUR",), D + timedelta(days=2), D + timedelta(days=RESCAN_DAYS))

    assert extend(tape, out, staging).head.day == D - timedelta(days=1)
    assert _line_days(out) == [BASE_DAY, SEAM]

    _put_final(tape, "DOT/EUR", D + timedelta(days=RESCAN_DAYS + 1))
    result = extend(tape, out, staging)

    assert _line(out, D)["holes"] == {"DOT/EUR": HOLE}
    assert _pairs_named(_line(out, D)) == set(TWELVE)
    assert _line(out, D + timedelta(days=1))["holes"] == {}
    assert (result.head.day, result.days_written, result.holes) == (D + timedelta(days=1), 2, 1)


def test_a_day_missing_two_pairs_is_a_hole_only_once_both_are_past_the_window(tmp_path):
    tape, out, staging = _outbox(tmp_path)
    window_end = D + timedelta(days=RESCAN_DAYS + 1)
    _finals(tape, tuple(p for p in TWELVE if p not in ("ADA/EUR", "XRP/EUR")), SEAM, window_end)
    _finals(tape, ("ADA/EUR",), SEAM, window_end, skip=(D,))
    _finals(tape, ("XRP/EUR",), SEAM, D + timedelta(days=2), skip=(D,))

    assert extend(tape, out, staging).head.day == D - timedelta(days=1)
    assert _line_days(out) == [BASE_DAY, SEAM]

    _finals(tape, ("XRP/EUR",), D + timedelta(days=3), window_end)
    result = extend(tape, out, staging)

    assert _line(out, D)["holes"] == {"ADA/EUR": HOLE, "XRP/EUR": HOLE}
    assert result.head.day == window_end


def test_a_pair_whose_newest_final_is_before_the_day_holds_the_head(tmp_path):
    tape, out, staging = _outbox(tmp_path)
    _finals(tape, tuple(p for p in TWELVE if p != "DOT/EUR"), SEAM, D + timedelta(days=8))
    _finals(tape, ("DOT/EUR",), SEAM, D - timedelta(days=1))

    result = extend(tape, out, staging)

    assert result.head.day == D - timedelta(days=1)
    assert _line_days(out) == [BASE_DAY, SEAM]


def test_prev_is_the_sha256_of_the_predecessors_bytes(tmp_path):
    tape, out, staging = _outbox(tmp_path, pairs=("BTC/EUR", "ETH/BTC"))
    _finals(tape, ("BTC/EUR", "ETH/BTC"), SEAM, D)

    extend(tape, out, staging)

    assert _line(out, D)["prev"] == _line_sha256(out, SEAM)
    assert _line(out, SEAM)["prev"] == _line_sha256(out, BASE_DAY)


def test_only_finished_names_appear_under_the_outbox(tmp_path, monkeypatch):
    source, hashes = _source(tmp_path)
    monkeypatch.setattr(rolling, "Q3_15M_SHA256", hashes)
    out, staging, tape = tmp_path / "out", tmp_path / "staging", tmp_path / "tape"
    staging.mkdir()
    _finals(tape, TWELVE, SEAM, D)
    seen: set[str] = set()
    real = os.replace

    def replace(src, dst, *args, **kwargs):
        seen.update(_files_under(out))
        return real(src, dst, *args, **kwargs)

    monkeypatch.setattr(os, "replace", replace)

    stage_base(source, out, staging)
    extend(tape, out, staging)

    assert len(seen) > len(TWELVE)
    assert [name for name in sorted(seen) if not _FINISHED.fullmatch(name)] == []


def test_the_outbox_holds_exactly_the_lines_and_the_files_they_list_each_renamed_in(tmp_path, monkeypatch):
    source, hashes = _source(tmp_path)
    monkeypatch.setattr(rolling, "Q3_15M_SHA256", hashes)
    out, staging, tape = tmp_path / "out", tmp_path / "staging", tmp_path / "tape"
    staging.mkdir()
    _finals(tape, TWELVE, SEAM, D)
    renamed: set[str] = set()
    real = os.replace

    def replace(src, dst, *args, **kwargs):
        real(src, dst, *args, **kwargs)
        renamed.add(Path(dst).relative_to(out).as_posix())

    monkeypatch.setattr(os, "replace", replace)

    stage_base(source, out, staging)
    result = extend(tape, out, staging)

    days = _line_days(out)
    listed = {f"index/{day:%Y}/{day:%m}/{day:%d}.json" for day in days}
    listed |= {relpath for day in days for relpath in _line(out, day)["files"]}
    assert (result.days_written, days) == (2, [BASE_DAY, SEAM, D])
    assert _files_under(out) == renamed == listed


def test_every_directory_the_writer_creates_is_group_writable_and_setgid(tmp_path, monkeypatch):
    source, hashes = _source(tmp_path)
    monkeypatch.setattr(rolling, "Q3_15M_SHA256", hashes)
    outbox, staging, tape = tmp_path / "hot-out", tmp_path / "staging", tmp_path / "tape"
    for directory in (outbox, staging):
        directory.mkdir()
        os.chmod(directory, 0o2770)
    out = outbox / "ohlc-rolling"
    _finals(tape, TWELVE, SEAM, SEAM)
    real_chmod = os.chmod

    def run(call: Callable[[], object]) -> set[Path]:
        before = {tmp_path, *tmp_path.parents, *tmp_path.rglob("*")}

        def chmod(path, mode, *args, **kwargs):
            if Path(path) in before:
                raise PermissionError(errno.EPERM, os.strerror(errno.EPERM), str(path))
            return real_chmod(path, mode, *args, **kwargs)

        monkeypatch.setattr(os, "chmod", chmod)
        # Without the owner's write bit: a directory left at the umask's mode refuses the mkdir below it.
        umask = os.umask(0o222)
        try:
            call()
        finally:
            os.umask(umask)
            monkeypatch.setattr(os, "chmod", real_chmod)
        return before

    def modes(paths) -> dict[Path, int]:
        return {path: stat.S_IMODE(path.stat().st_mode) for path in paths}

    def created_dirs(before: set[Path]) -> list[Path]:
        return [path for path in out.rglob("*") if path.is_dir() and path not in before] + ([out] if out not in before else [])

    before = run(lambda: stage_base(source, out, staging))

    assert created_dirs(before) and set(modes(created_dirs(before)).values()) == {0o2775}
    assert set(modes(p for p in out.rglob("*") if p.is_file()).values()) == {0o664}
    assert modes((outbox, staging)) == {outbox: 0o2770, staging: 0o2770}

    based = [out, *(path for path in out.rglob("*") if path.is_dir())]
    for directory in based:
        os.chmod(directory, 0o2770)
    before = run(lambda: extend(tape, out, staging))

    assert created_dirs(before) and set(modes(created_dirs(before)).values()) == {0o2775}
    assert set(modes(p for p in out.rglob("*") if p.is_file()).values()) == {0o664}
    assert set(modes([outbox, staging, *based]).values()) == {0o2770}


def test_extend_refuses_an_outbox_without_a_base_line(tmp_path):
    tape, out, staging = tmp_path / "tape", tmp_path / "out", tmp_path / "staging"
    for directory in (tape, out, staging):
        directory.mkdir()
    _finals(tape, ("BTC/EUR", "ETH/BTC"), SEAM, SEAM)

    with pytest.raises(RollingError, match=f"{re.escape(str(out))} holds no base line"):
        extend(tape, out, staging)

    assert list(out.iterdir()) == []
    assert list(staging.iterdir()) == []


def test_a_tape_pair_outside_the_base_is_neither_copied_nor_listed(tmp_path):
    tape, out, staging = _outbox(tmp_path)
    _finals(tape, (*TWELVE, OUTSIDER), SEAM, D)

    result = extend(tape, out, staging)

    assert result.days_written == 2
    for day in (SEAM, D):
        assert _pairs_named(_line(out, day)) == set(TWELVE)
    assert not (out / "days" / OUTSIDER).exists()


def test_a_closed_pairs_later_lines_carry_the_hole(tmp_path):
    tape, out, staging = _outbox(tmp_path)
    closed = ("AVAX/EUR", "SOL/BTC")
    others = tuple(p for p in TWELVE if p not in closed)
    _finals(tape, closed, SEAM, D - timedelta(days=1))
    _finals(tape, others, SEAM, D + timedelta(days=2))
    notes = {f"closed {pair}": _note(D) for pair in closed}

    result = _extend_cli(tape, out, staging, *_close_args(closed, D))

    assert result.exit_code == 0, result.output
    assert _line_days(out)[-1] == D + timedelta(days=2)

    _finals(tape, others, D + timedelta(days=3), D + timedelta(days=4))
    result = _extend_cli(tape, out, staging)

    assert result.exit_code == 0, result.output
    assert _line_days(out)[-1] == D + timedelta(days=4)
    for day in _days(D, D + timedelta(days=4)):
        line = _line(out, day)
        assert (line["holes"], line["notes"]) == (dict.fromkeys(closed, CLOSED), notes), day


def test_a_final_reappearing_after_the_close_is_copied_and_ends_the_hole(tmp_path):
    tape, out, staging = _outbox(tmp_path)
    others = tuple(p for p in TWELVE if p != "LTC/EUR")
    _finals(tape, others, SEAM, D + timedelta(days=2))
    _finals(tape, ("LTC/EUR",), SEAM, D + timedelta(days=1), skip=(D,))

    result = _extend_cli(tape, out, staging, *_close_args(("LTC/EUR",), D))

    assert result.exit_code == 0, result.output
    assert (_line(out, D)["holes"], _line(out, D)["notes"]) == ({"LTC/EUR": CLOSED}, {"closed LTC/EUR": _note(D)})
    reappeared = _line(out, D + timedelta(days=1))
    assert "days/LTC/EUR/2026/10/03.parquet" in reappeared["files"]
    assert "notes" not in reappeared
    assert _line_days(out)[-1] == D + timedelta(days=1)


def test_a_final_reappearing_in_a_run_given_no_close_ends_the_close(tmp_path):
    tape, out, staging = _outbox(tmp_path)
    others = tuple(p for p in TWELVE if p != "LTC/EUR")
    _finals(tape, others, SEAM, D + timedelta(days=2))
    _finals(tape, ("LTC/EUR",), SEAM, D - timedelta(days=1))

    result = _extend_cli(tape, out, staging, *_close_args(("LTC/EUR",), D))

    assert result.exit_code == 0, result.output
    for day in _days(D, D + timedelta(days=2)):
        assert _line(out, day)["holes"] == {"LTC/EUR": CLOSED}, day

    _put_final(tape, "LTC/EUR", D + timedelta(days=3))
    _finals(tape, others, D + timedelta(days=3), D + timedelta(days=4))
    result = _extend_cli(tape, out, staging)

    assert result.exit_code == 0, result.output
    reappeared = _line(out, D + timedelta(days=3))
    assert "days/LTC/EUR/2026/10/05.parquet" in reappeared["files"]
    assert "notes" not in reappeared
    assert _line_days(out)[-1] == D + timedelta(days=3)


def test_a_close_on_a_pair_with_a_final_for_its_day_is_refused(tmp_path):
    tape, out, staging = _outbox(tmp_path)
    _finals(tape, tuple(p for p in TWELVE if p != "ADA/EUR"), SEAM, D + timedelta(days=1))
    _finals(tape, ("ADA/EUR",), SEAM, D - timedelta(days=1))

    with pytest.raises(RollingError, match="XRP/EUR has a tape-bars final for 2026-10-02"):
        extend(tape, out, staging, close=Close(("ADA/EUR", "XRP/EUR"), D, WORD, WORD_DATE))

    assert _line_days(out) == [BASE_DAY]
    assert not (out / "days").exists()
    assert list(staging.iterdir()) == []


def test_a_close_whose_first_line_cannot_be_written_is_refused(tmp_path):
    tape, out, staging = _outbox(tmp_path)
    _finals(tape, tuple(p for p in TWELVE if p not in ("LTC/EUR", "DOGE/EUR")), SEAM, D + timedelta(days=1))
    _finals(tape, ("LTC/EUR",), SEAM, D - timedelta(days=1))
    _finals(tape, ("DOGE/EUR",), SEAM, D + timedelta(days=1), skip=(D,))

    with pytest.raises(RollingError, match="the close from 2026-10-02 is refused: this run writes no line for that day"):
        extend(tape, out, staging, close=Close(("LTC/EUR",), D, WORD, WORD_DATE))

    assert _line_days(out) == [BASE_DAY]
    assert not (out / "days").exists()


def test_a_line_closing_every_pair_ends_the_set(tmp_path):
    tape, out, staging = _outbox(tmp_path)
    eleven = TWELVE[:-1]
    _finals(tape, eleven, SEAM, D - timedelta(days=1))
    _finals(tape, ("XRP/EUR",), SEAM, D + timedelta(days=1))

    result = _extend_cli(tape, out, staging, *_close_args(eleven, D))

    assert result.exit_code == 0, result.output
    assert _summary(result) == "head=2026-10-03 days_written=3 holes=22"
    for day in (D, D + timedelta(days=1)):
        line = _line(out, day)
        assert line["holes"] == dict.fromkeys(eleven, CLOSED), day
        assert list(line["files"]) == [f"days/XRP/EUR/{day:%Y/%m/%d}.parquet"], day

    result = _extend_cli(tape, out, staging, *_close_args(("XRP/EUR",), D + timedelta(days=2)))

    assert result.exit_code == 0, result.output
    assert _summary(result) == "head=2026-10-04 days_written=1 holes=12 ended"
    ended = _line(out, D + timedelta(days=2))
    assert ended["holes"] == dict.fromkeys(TWELVE, CLOSED)
    assert set(ended["notes"]) == {f"closed {pair}" for pair in TWELVE}
    assert _line_days(out)[-1] == D + timedelta(days=2)

    _put_final(tape, OUTSIDER, D + timedelta(days=3))
    result = _extend_cli(tape, out, staging)

    assert result.exit_code == 0, result.output
    assert _summary(result) == "head=2026-10-04 days_written=0 holes=0 ended"
    assert _line_days(out)[-1] == D + timedelta(days=2)


def _ended_pair_set(tmp_path: Path) -> tuple[Path, Path, Path, date]:
    """The two-pair set written by hand to 2026-10-02, both pairs' finals ending there, closed from the day after by the
    command, which stops at that line; returns the tape, the set, the staging and that day."""
    tape, out, staging = _outbox(tmp_path, pairs=("BTC/EUR", "ETH/BTC"), days=2)
    _finals(tape, ("BTC/EUR", "ETH/BTC"), SEAM, D)
    day = D + timedelta(days=1)

    result = _extend_cli(tape, out, staging, *_close_args(("BTC/EUR", "ETH/BTC"), day))

    assert result.exit_code == 0, result.output
    assert _summary(result) == "head=2026-10-03 days_written=1 holes=2 ended"
    assert _line(out, day)["holes"] == {"BTC/EUR": CLOSED, "ETH/BTC": CLOSED}
    return tape, out, staging, day


def test_a_final_reappearing_after_an_ended_line_reopens_the_set(tmp_path):
    tape, out, staging, ended = _ended_pair_set(tmp_path)
    _put_final(tape, "ETH/BTC", ended + timedelta(days=3))

    result = _extend_cli(tape, out, staging)

    assert result.exit_code == 0, result.output
    assert _summary(result) == "head=2026-10-06 days_written=3 holes=5"
    both = {"closed BTC/EUR": _note(ended), "closed ETH/BTC": _note(ended)}
    for day in (ended + timedelta(days=1), ended + timedelta(days=2)):
        line = _line(out, day)
        assert (line["files"], line["holes"], line["notes"]) == ({}, {"BTC/EUR": CLOSED, "ETH/BTC": CLOSED}, both), day
    reopened = _line(out, ended + timedelta(days=3))
    assert list(reopened["files"]) == ["days/ETH/BTC/2026/10/06.parquet"]
    assert (reopened["holes"], reopened["notes"]) == ({"BTC/EUR": CLOSED}, {"closed BTC/EUR": _note(ended)})
    for day in _days(ended + timedelta(days=1), ended + timedelta(days=3)):
        assert _line(out, day)["prev"] == _line_sha256(out, day - timedelta(days=1)), day


def test_a_close_given_while_the_set_is_ended_is_refused(tmp_path):
    tape, out, staging, ended = _ended_pair_set(tmp_path)
    lines = _files_under(out / "index")

    result = _extend_cli(tape, out, staging, *_close_args(("BTC/EUR",), ended + timedelta(days=1)))

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert "this run writes no line for that day (the set is ended at 2026-10-03)" in result.output
    assert _files_under(out / "index") == lines
    assert list(staging.iterdir()) == []

    _put_final(tape, "ETH/BTC", ended + timedelta(days=3))
    result = _extend_cli(tape, out, staging, *_close_args(("ETH/BTC",), ended + timedelta(days=4)))

    assert result.exit_code == 0, result.output
    assert _summary(result) == "head=2026-10-07 days_written=4 holes=7 ended"
    assert list(_line(out, ended + timedelta(days=3))["files"]) == ["days/ETH/BTC/2026/10/06.parquet"]
    last = _line(out, ended + timedelta(days=4))
    assert last["holes"] == {"BTC/EUR": CLOSED, "ETH/BTC": CLOSED}
    assert last["notes"] == {"closed BTC/EUR": _note(ended), "closed ETH/BTC": _note(ended + timedelta(days=4))}


@pytest.mark.skipif(os.geteuid() == 0, reason="root bypasses directory permissions")
def test_an_unlistable_tape_is_refused_never_read_as_no_final(tmp_path):
    tape, out, staging, ended = _ended_pair_set(tmp_path / "first")
    lines = _files_under(out / "index")
    away = tape.with_name("tape-away")
    tape.rename(away)

    result = _extend_cli(tape, out, staging)

    assert result.exit_code == 1
    assert str(tape) in result.output
    assert not _says_ended(result)
    assert _files_under(out / "index") == lines

    away.rename(tape)
    _put_final(tape, "ETH/BTC", ended + timedelta(days=3))
    month = tape / "ETH/BTC/2026/10"
    os.chmod(month, 0o000)
    try:
        result = _extend_cli(tape, out, staging)
    finally:
        os.chmod(month, 0o755)

    assert result.exit_code == 1
    assert str(month) in result.output
    assert not _says_ended(result)
    assert _files_under(out / "index") == lines

    first = date(2026, 10, 28)
    for mode in (0o000, 0o400):
        tape, out, staging = _outbox(tmp_path / f"held-{mode:o}", pairs=("BTC/EUR", "ETH/BTC"), days=27)
        _finals(tape, ("ETH/BTC",), first, date(2026, 11, 3))
        _put_final(tape, "BTC/EUR", first)
        _finals(tape, ("BTC/EUR",), date(2026, 11, 1), date(2026, 11, 3))
        hidden = tape / "BTC/EUR/2026/10"
        written = _files_under(out)
        os.chmod(hidden, mode)
        try:
            result = _extend_cli(tape, out, staging)
        finally:
            os.chmod(hidden, 0o755)

        assert result.exit_code == 1, oct(mode)
        assert str(hidden) in result.output, oct(mode)
        assert _files_under(out) == written, oct(mode)


def test_a_close_without_the_owners_word_and_date_is_refused(tmp_path):
    tape, out, staging = _outbox(tmp_path, pairs=("BTC/EUR", "ETH/BTC"))
    _finals(tape, ("BTC/EUR", "ETH/BTC"), SEAM, D)

    result = _extend_cli(tape, out, staging, "--close-pair", "BTC/EUR", "--from", str(D))

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert "--owner-word" in result.output and "--owner-date" in result.output
    assert _line_days(out) == [BASE_DAY]
    assert not (out / "days").exists()
    assert list(staging.iterdir()) == []


@pytest.mark.parametrize("mistyped", ["LNIK/EUR", "DOTEUR"])
def test_a_close_of_a_pair_outside_the_set_is_refused(tmp_path, mistyped):
    tape, out, staging = _outbox(tmp_path)
    _finals(tape, tuple(p for p in TWELVE if p != "DOT/EUR"), SEAM, D)
    _finals(tape, ("DOT/EUR",), SEAM, D - timedelta(days=1))

    result = _extend_cli(tape, out, staging, *_close_args(("DOT/EUR", mistyped), D))

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert all(pair in result.output for pair in (mistyped, *TWELVE))
    assert D not in _line_days(out)
    assert list(staging.iterdir()) == []


def test_a_tape_path_that_is_not_a_day_is_a_one_line_refusal(tmp_path):
    tape, out, staging = _outbox(tmp_path)
    _finals(tape, TWELVE, SEAM, D, skip=())
    (tape / "DOT/EUR/2026/10/02.parquet").unlink()
    (tape / "DOT/EUR/2026/10/02.parquet.sha256").unlink()
    stray = tape / "DOT/EUR/2026/10/notes.parquet"
    stray.write_bytes(b"not a day")

    result = _extend_cli(tape, out, staging)

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert str(stray) in result.output
    assert D not in _line_days(out)


def test_a_base_whose_rename_fails_is_a_one_line_refusal(tmp_path, monkeypatch):
    source, hashes = _source(tmp_path)
    monkeypatch.setattr(rolling, "Q3_15M_SHA256", hashes)
    out, staging = tmp_path / "out", tmp_path / "staging"
    staging.mkdir()
    _replace_refusing(monkeypatch, lambda dst: True)

    result = _base_cli(source, out, staging)

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert str(out / "base/ADA/EUR/15.parquet") in result.output


def test_an_extension_whose_rename_fails_is_a_one_line_refusal(tmp_path, monkeypatch):
    tape, out, staging = _outbox(tmp_path, pairs=("BTC/EUR", "ETH/BTC"))
    _finals(tape, ("BTC/EUR", "ETH/BTC"), SEAM, SEAM)
    _replace_refusing(monkeypatch, lambda dst: True)

    result = _extend_cli(tape, out, staging)

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert str(out / "days/BTC/EUR/2026/10/01.parquet") in result.output


def test_the_base_refuses_a_source_whose_manifest_is_not_conformant(tmp_path, monkeypatch):
    source, hashes = _source(tmp_path)
    monkeypatch.setattr(rolling, "Q3_15M_SHA256", hashes)
    _edit_manifest(source, lambda m: m.pop("schema_version"))
    out, staging = tmp_path / "out", tmp_path / "staging"
    staging.mkdir()

    result = _base_cli(source, out, staging)

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert str(source / "manifest.json") in result.output
    assert not out.exists()


def test_a_base_whose_source_file_polars_cannot_read_is_a_one_line_refusal(tmp_path, monkeypatch):
    source, hashes = _source(tmp_path)
    unreadable = source / "DOT/EUR/15.parquet"
    unreadable.write_bytes(b"these bytes are not a parquet file" * 8)
    hashes["DOT/EUR"] = hashlib.sha256(unreadable.read_bytes()).hexdigest()
    monkeypatch.setattr(rolling, "Q3_15M_SHA256", hashes)
    out, staging = tmp_path / "out", tmp_path / "staging"
    staging.mkdir()

    result = _base_cli(source, out, staging)

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert str(unreadable) in result.output
    assert not out.exists()


def test_the_extend_summary_line_names_the_head_the_days_and_the_holes(tmp_path):
    tape, out, staging = _outbox(tmp_path, pairs=("BTC/EUR", "ETH/BTC"))
    last = SEAM + timedelta(days=RESCAN_DAYS + 1)
    _finals(tape, ("ETH/BTC",), SEAM, last)
    _finals(tape, ("BTC/EUR",), SEAM, last, skip=(SEAM,))

    result = _extend_cli(tape, out, staging)

    assert result.exit_code == 0, result.output
    assert _summary(result) == f"head={last} days_written={RESCAN_DAYS + 2} holes=1"


@pytest.mark.skipif(
    not _ROLLING.is_dir(), reason="data/ohlc-rolling absent — the staged base is on the data-bearing workstation only"
)
def test_the_staged_base_is_the_q3_15m_frame_byte_for_byte():
    staged = {}
    for pair in Q3_15M_SHA256:
        staged[pair] = hashlib.sha256((_ROLLING / "base" / pair / "15.parquet").read_bytes()).hexdigest()

    assert staged == Q3_15M_SHA256


@pytest.mark.skipif(
    not _ROLLING.is_dir(),
    reason="data/ohlc-rolling absent — the base's derivation is checked on the data-bearing workstation only",
)
def test_the_grids_derived_from_the_staged_base_equal_the_q3_coarse_frames():
    identity = {
        pair: {
            interval: dataset_hash(
                read_rolling(_ROLLING, pair, interval, BASE_DAY).frame.select("ts", "open", "high", "low", "close", "count")
            )
            for interval in (60, 240, 1440)
        }
        for pair in Q3_COARSE_IDENTITY
    }

    assert identity == Q3_COARSE_IDENTITY

    extended = head(_ROLLING)
    assert extended.day > BASE_DAY, "no extended day to read back across the seam"
    for pair in Q3_COARSE_IDENTITY:
        frame = read_rolling(_ROLLING, pair, 15, extended.day, accept_holes=True).frame
        assert frame.schema == FRAME_SCHEMA, pair
        assert frame["ts"].is_sorted() and frame["ts"].n_unique() == frame.height, pair
        assert frame["ts"].max() >= datetime(SEAM.year, SEAM.month, SEAM.day, tzinfo=UTC), pair
