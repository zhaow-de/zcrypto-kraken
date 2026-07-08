from __future__ import annotations


class CaptureError(Exception):
    """The capture daemon (WS client, book state, segment writer, or gap monitor) hit a fatal error."""
