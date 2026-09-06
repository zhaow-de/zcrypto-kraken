from __future__ import annotations

import shutil
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from cli.capture.errors import CaptureError
from cli.logging import get_logger

logger = get_logger("capture.gap_monitor")

DEFAULT_MIN_FREE_BYTES = 1 * 1024**3  # 1 GiB
DEFAULT_HEALTHCHECK_TIMEOUT_SECS = 5


@dataclass
class _OpenGap:
    reason: str
    start: datetime


class GapMonitor:
    """Tracks per-pair gap time and derives gap ratios for the exit-bar's <0.1% gap-time bar."""

    def __init__(self) -> None:
        self._open: dict[str, _OpenGap] = {}
        self._closed_seconds: dict[str, float] = {}
        # The disk-watermark breach window (T0032): a breach stops EVERY write, so it is one
        # global window, independent of `_open` — were it routed through the idempotent per-pair
        # `start_gap`, a concurrent gap would swallow it.
        self._watermark_open: datetime | None = None
        self._watermark_seconds: float = 0.0
        # Upstream silence -- a subscribed, CONNECTED stream receiving nothing (T0101;
        # spec 00073). Its own per-pair window for the same reason the watermark has one, and because the
        # two faults co-occur: a venue that stops publishing is exactly when a book stops passing its checksum.
        self._silent_open: dict[str, datetime] = {}
        self._silent_seconds: dict[str, float] = {}

    def start_gap(self, pair: str, reason: str, *, at: datetime) -> None:
        """Open a gap window for `pair`; idempotent, and the earliest start wins because that is when the gap began."""
        if pair in self._open:
            return
        self._open[pair] = _OpenGap(reason=reason, start=at)
        logger.warning("gap start pair=%s reason=%s at=%s", pair, reason, at.isoformat())

    def end_gap(self, pair: str, *, at: datetime) -> float:
        """Close `pair`'s open gap window, returning its seconds (0.0 if none was open); a clock that stepped BACKWARD
        is clamped to zero rather than raised, since an escaping error here kills the consumer task and the daemon."""
        open_gap = self._open.pop(pair, None)
        if open_gap is None:
            return 0.0
        duration = max((at - open_gap.start).total_seconds(), 0.0)
        self._closed_seconds[pair] = self._closed_seconds.get(pair, 0.0) + duration
        logger.warning("gap end pair=%s reason=%s seconds=%.3f", pair, open_gap.reason, duration)
        return duration

    def start_watermark_gap(self, *, at: datetime) -> None:
        """Open the global disk-watermark breach window, idempotently on its OWN state — the earliest breach wins."""
        if self._watermark_open is not None:
            return
        self._watermark_open = at
        logger.warning("gap start reason=disk_watermark at=%s", at.isoformat())

    def end_watermark_gap(self, *, at: datetime) -> float:
        """Close the breach window into the global watermark total, returning its seconds (0.0 if none was open); a
        clock that stepped BACKWARD is clamped to zero rather than raised, as `end_gap` is."""
        if self._watermark_open is None:
            return 0.0
        duration = max((at - self._watermark_open).total_seconds(), 0.0)
        self._watermark_seconds += duration
        self._watermark_open = None
        logger.warning("gap end reason=disk_watermark seconds=%.3f", duration)
        return duration

    def start_silence(self, pair: str, *, at: datetime) -> None:
        """Open `pair`'s upstream-silence window, stamped at its LAST SEEN message and never at detection: the watchdog
        cannot notice until the staleness threshold has elapsed, so a detection stamp would discard that threshold from
        every outage. Idempotent per pair, and the earliest stamp wins."""
        if pair in self._silent_open:
            return
        self._silent_open[pair] = at
        logger.warning("gap start pair=%s reason=upstream_silent at=%s", pair, at.isoformat())

    def end_silence(self, pair: str, *, at: datetime) -> float:
        """Close `pair`'s silence window, returning its duration (0.0 if none was open); a clock that stepped BACKWARD
        is clamped to zero rather than raised, as `end_gap` is."""
        started = self._silent_open.pop(pair, None)
        if started is None:
            return 0.0
        duration = max((at - started).total_seconds(), 0.0)
        self._silent_seconds[pair] = self._silent_seconds.get(pair, 0.0) + duration
        logger.warning("gap end pair=%s reason=upstream_silent seconds=%.3f", pair, duration)
        return duration

    def is_silent(self, pair: str) -> bool:
        return pair in self._silent_open

    def is_open(self, pair: str) -> bool:
        return pair in self._open

    def gap_seconds(self, pair: str, *, at: datetime | None = None) -> float:
        """Total gap seconds for `pair` — its own gaps, the global disk-watermark breach and upstream silence, plus each
        still-open window's contribution as of `at`, clamped to >= 0 against a backward-stepped clock. The three kinds
        are summed INDEPENDENTLY, each answering a different question, so the total is an upper bound that can exceed
        the elapsed wall clock and is never a coverage ratio (T0105 records why)."""
        total = self._closed_seconds.get(pair, 0.0) + self._watermark_seconds + self._silent_seconds.get(pair, 0.0)
        open_gap = self._open.get(pair)
        if open_gap is not None and at is not None:
            total += max((at - open_gap.start).total_seconds(), 0.0)
        if self._watermark_open is not None and at is not None:
            total += max((at - self._watermark_open).total_seconds(), 0.0)
        silent_since = self._silent_open.get(pair)
        if silent_since is not None and at is not None:
            total += max((at - silent_since).total_seconds(), 0.0)
        return total

    def gap_ratio(self, pair: str, *, window_seconds: float, at: datetime | None = None) -> float:
        """Gap seconds over `window_seconds`. CAN EXCEED 1.0 (see `gap_seconds`), so a consumer treating it as a fraction
        of elapsed time must say what it does above 1.0."""
        if window_seconds <= 0:
            raise CaptureError(f"window_seconds must be > 0, got {window_seconds}")
        return self.gap_seconds(pair, at=at) / window_seconds

    def summary(self, pairs: list[str], *, window_seconds: float, at: datetime) -> dict[str, dict]:
        """Per-pair gap seconds/ratio plus whether each pair currently has an open gap."""
        return {
            pair: {
                "gap_seconds": self.gap_seconds(pair, at=at),
                "gap_ratio": self.gap_ratio(pair, window_seconds=window_seconds, at=at),
                "open": self.is_open(pair),
            }
            for pair in pairs
        }

    def is_healthy(self, pairs: list[str]) -> bool:
        """True iff none of `pairs` currently has an open gap; DELIBERATELY not `is_silent` (spec 00073 D3), because
        this gates the healthchecks.io ping for EVERY pair at once and an unfitted silence bar would darken the fleet's
        last-resort liveness signal — silence pages through its own Grafana rules instead."""
        return not any(self.is_open(pair) for pair in pairs)


def ping_healthcheck(url: str | None, *, timeout: int = DEFAULT_HEALTHCHECK_TIMEOUT_SECS) -> None:
    """Best-effort liveness ping to a healthchecks.io URL, a no-op on a falsy `url` since the feature is optional.
    Never raises on a transport failure: a dead-man's-switch alerts on a MISSED ping, so the failure is
    logged and swallowed."""
    if not url:
        return
    try:
        urllib.request.urlopen(url, timeout=timeout)  # noqa: S310 - fixed https healthchecks.io URL from env
    except (urllib.error.URLError, OSError) as exc:
        logger.warning("healthcheck ping failed url=%s error=%s", url, exc)


@dataclass
class DiskWatermark:
    """Disk-space guard: `breached` once free space on `path`'s filesystem drops below `min_free_bytes`. The capture
    loop stops accepting new segments while breached; `usage_fn` is injectable for testing."""

    path: Path
    min_free_bytes: int = DEFAULT_MIN_FREE_BYTES
    usage_fn: Callable[[Path], object] = shutil.disk_usage
    _breached: bool = field(default=False, init=False, repr=False)
    _measurable: bool = field(default=True, init=False, repr=False)

    def check(self) -> bool:
        """Recompute breach state from current free space, returning True iff healthy; logs only on the transition. A
        probe that RAISES sets `measurable` False and re-raises, because "cannot measure" is not "healthy": freezing
        `breached` while the dead-man pings green is the T0032 silent death."""
        try:
            free = self.usage_fn(self.path).free
        except Exception:
            if self._measurable:
                logger.error("disk watermark UNMEASURABLE path=%s -- treating as not-healthy (probe failing)", self.path)
            self._measurable = False
            raise
        if not self._measurable:
            logger.info("disk watermark measurable again path=%s", self.path)
        self._measurable = True
        now_breached = free < self.min_free_bytes
        if now_breached and not self._breached:
            logger.error("disk watermark breached path=%s free=%d min_free_bytes=%d", self.path, free, self.min_free_bytes)
        elif not now_breached and self._breached:
            logger.info("disk watermark cleared path=%s free=%d", self.path, free)
        self._breached = now_breached
        return not now_breached

    @property
    def breached(self) -> bool:
        return self._breached

    @property
    def measurable(self) -> bool:
        """False once a probe has raised without a later success — the ping loop must not ping green on a frozen `breached`."""
        return self._measurable
