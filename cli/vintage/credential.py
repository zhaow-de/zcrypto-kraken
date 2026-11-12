"""The keyed source's credential: read once from a stream, held so that no `str` or `repr` shows it, and the scan that
keeps it out of every stored byte, a body read through its decoded Content-Encoding where the stdlib can undo it."""

from __future__ import annotations

import re
import urllib.parse
import zlib
from compression.zstd import ZstdDecompressor, ZstdError
from typing import BinaryIO

B64TOKEN = re.compile(r"[A-Za-z0-9._~+/-]+=*")
_PERCENT_ESCAPE = re.compile(rb"%[0-9A-F]{2}")
_IDENTITY = frozenset({"", "identity"})


class ApiKey:
    __slots__ = ("_value",)

    def __init__(self, value: str) -> None:
        self._value = value

    def reveal(self) -> str:
        return self._value

    def __str__(self) -> str:
        return "<redacted>"

    def __repr__(self) -> str:
        return "<redacted>"


def read_key(stream: BinaryIO | None) -> tuple[ApiKey | None, str | None]:
    if stream is None:
        return None, "no credential"
    try:
        data = stream.read()
    except OSError:
        return None, "no credential"
    data = data.rstrip()
    if not data:
        return None, "no credential"
    try:
        text = data.decode("ascii")
    except UnicodeDecodeError:
        return None, "malformed credential"
    if not B64TOKEN.fullmatch(text):
        return None, "malformed credential"
    return ApiKey(text), None


def key_forms(key: ApiKey) -> tuple[bytes, bytes, bytes, bytes]:
    raw = key.reveal().encode("ascii")
    escaped = raw.replace(b"/", b"\\/")
    percent = urllib.parse.quote(raw, safe="").encode("ascii")
    lower = _PERCENT_ESCAPE.sub(lambda escape: escape.group().lower(), percent)
    return raw, escaped, percent, lower


def holds_key(data: bytes, forms) -> bool:
    return any(form in data for form in forms)


def _layer(decompressor, data: bytes, max_bytes: int) -> bytes | None:
    try:
        out = decompressor.decompress(data, max_bytes + 1)
    except zlib.error, ZstdError:
        return None
    # One call stops without raising at the end of the first gzip member or zstd frame, and short of a truncated end.
    if not decompressor.eof or decompressor.unused_data:
        return None
    return out if len(out) <= max_bytes else None


def _zlib_wrapped(data: bytes) -> bool:
    return len(data) >= 2 and data[0] & 0x0F == 8 and (data[0] << 8 | data[1]) % 31 == 0


def _decode_layer(coding: str, data: bytes, max_bytes: int) -> bytes | None:
    if coding == "gzip":
        return _layer(zlib.decompressobj(16 + zlib.MAX_WBITS), data, max_bytes)
    if coding == "deflate":
        return _layer(zlib.decompressobj(zlib.MAX_WBITS if _zlib_wrapped(data) else -zlib.MAX_WBITS), data, max_bytes)
    if coding == "zstd":
        return _layer(ZstdDecompressor(), data, max_bytes)
    return None


def decode_for_scan(body: bytes, content_encoding: str | None, *, max_bytes: int) -> bytes | None:
    """The body as its Content-Encoding undoes it, the codings undone right to left; None where it does not decode
    under the encoding it names, names one the stdlib cannot undo, or decodes past `max_bytes`."""
    data = body
    codings = [coding.strip().lower() for coding in (content_encoding or "").split(",")]
    for coding in reversed(codings):
        if coding in _IDENTITY:
            continue
        decoded = _decode_layer(coding, data, max_bytes)
        if decoded is None:
            return None
        data = decoded
    return data if len(data) <= max_bytes else None
