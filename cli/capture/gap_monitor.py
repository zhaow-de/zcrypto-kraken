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
    """Tracks per-pair gap time (WS reconnect windows, checksum resyncs) and derives gap ratios
    for the exit-bar's <0.1% gap-time bar."""

    def __init__(self) -> None:
        self._open: dict[str, _OpenGap] = {}
        self._closed_seconds: dict[str, float] = {}
        # The disk-watermark breach window (T0032). A breach stops EVERY write, so it is ONE global
        # window, not a per-pair gap — and it is tracked INDEPENDENTLY of `_open`. It is deliberately
        # not routed through `start_gap`: that is idempotent per pair, so a concurrent checksum_resync
        # gap already open on a pair would swallow the breach, and its `end_gap` would then resume the
        # dead-man ping while the disk is STILL breached — reintroducing the very silent-loss bug.
        self._watermark_open: datetime | None = None
        self._watermark_seconds: float = 0.0
        # Upstream silence -- a subscribed, CONNECTED stream receiving nothing (T0101, spec 00073).
        # Its own per-pair window for the same reason the watermark has one: `start_gap` is
        # idempotent per pair, so routing silence through it would let a concurrent checksum_resync
        # gap swallow it, and whichever window closed first would book the other's duration as its
        # own. These two faults genuinely co-occur -- a venue that stops publishing is exactly when a
        # book also stops passing its checksum -- so the windows must be independent.
        self._silent_open: dict[str, datetime] = {}
        self._silent_seconds: dict[str, float] = {}

    def start_gap(self, pair: str, reason: str, *, at: datetime) -> None:
        """Open a gap window for `pair`. Idempotent: a second `start_gap` before the matching
        `end_gap` is a no-op — the earliest start time wins, since that's when the gap truly began."""
        if pair in self._open:
            return
        self._open[pair] = _OpenGap(reason=reason, start=at)
        logger.warning("gap start pair=%s reason=%s at=%s", pair, reason, at.isoformat())

    def end_gap(self, pair: str, *, at: datetime) -> float:
        """Close `pair`'s open gap window, returning its duration in seconds (0.0 if none was open).

        A negative duration — the wall clock stepped BACKWARD across the open window (chrony
        makestep, a VM snapshot-restore) — is clamped to zero, never raised, mirroring
        `end_watermark_gap`: `at` comes straight from the wall clock, and an escaping
        CaptureError here kills the consumer task and with it the whole daemon. The stepped
        clock cannot measure the window; the next gap books normally.
        """
        open_gap = self._open.pop(pair, None)
        if open_gap is None:
            return 0.0
        duration = max((at - open_gap.start).total_seconds(), 0.0)
        self._closed_seconds[pair] = self._closed_seconds.get(pair, 0.0) + duration
        logger.warning("gap end pair=%s reason=%s seconds=%.3f", pair, open_gap.reason, duration)
        return duration

    def start_watermark_gap(self, *, at: datetime) -> None:
        """Open the global disk-watermark breach window (T0032). Idempotent on its OWN state — the
        earliest breach time wins — so the 30 s watermark poll can call it every breached tick. See
        `__init__` for why this is a dedicated window rather than a `start_gap` call."""
        if self._watermark_open is not None:
            return
        self._watermark_open = at
        logger.warning("gap start reason=disk_watermark at=%s", at.isoformat())

    def end_watermark_gap(self, *, at: datetime) -> float:
        """Close the breach window, accumulating its duration into the global watermark total. Returns
        the closed window's seconds (0.0 if none was open).

        A negative duration — the wall clock stepped BACKWARD across the open window (chrony
        makestep, a VM snapshot-restore) — is clamped to zero, never raised: this runs inside
        `_disk_watermark_loop`, a task nothing awaits until shutdown, and an escaping exception
        silently ends watermark polling for the life of the process. A frozen `breached` means a
        later REAL breach never withholds the dead-man ping — the exact T0032 silent death.
        """
        if self._watermark_open is None:
            return 0.0
        duration = max((at - self._watermark_open).total_seconds(), 0.0)
        self._watermark_seconds += duration
        self._watermark_open = None
        logger.warning("gap end reason=disk_watermark seconds=%.3f", duration)
        return duration

    def start_silence(self, pair: str, *, at: datetime) -> None:
        """Open `pair`'s upstream-silence window, stamped at its LAST SEEN message (T0101).

        `at` is the last-message time, never the detection time. The watchdog cannot notice until the
        staleness threshold has already elapsed, so stamping at detection would discard exactly the
        threshold from every outage -- under-reporting by 30 s each time, which is the same direction
        as the defect this exists to fix.

        Idempotent per pair, earliest stamp wins: the watchdog re-evaluates every tick while a pair
        stays silent, and a later open must not restart the window.
        """
        if pair in self._silent_open:
            return
        self._silent_open[pair] = at
        logger.warning("gap start pair=%s reason=upstream_silent at=%s", pair, at.isoformat())

    def end_silence(self, pair: str, *, at: datetime) -> float:
        """Close `pair`'s silence window, returning its duration (0.0 if none was open).

        Negative durations are clamped rather than raised, mirroring `end_gap`: this is driven from a
        bare task nothing awaits until shutdown, so an escaping exception would end silence tracking
        for the life of the process -- reintroducing the blind spot silently.
        """
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
        """Total closed gap seconds for `pair` — its own gaps plus the global disk-watermark breach
        (T0032), which lost data for every pair — plus upstream silence (T0101) — plus any
        still-open windows' duration as of `at`.

        THE THREE KINDS ARE SUMMED INDEPENDENTLY AND CAN DOUBLE-COUNT THE SAME SECOND. That is
        deliberate: each answers a different question (did this pair desync / did the disk stop us
        writing / did the venue stop sending), and collapsing them would make a pair that suffers
        two faults at once look like it suffered one. The cost is that the total is an upper bound
        on lost time, not a measurement of it, and it can exceed the elapsed wall clock — a pair
        desynced *through* an upstream blackout books that window twice. A rule on
        `increase(zcrypto_capture_gap_seconds_total[...])` therefore reads "how bad, roughly",
        never "what fraction of the window was lost"; T0105 owns that rule and must not treat this
        as a coverage ratio.
        Each open window's contribution is clamped to >= 0: an `at` before a window's start (a
        backward-stepped wall clock) must not produce a negative gap or eat booked gap time."""
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
        """Gap seconds over `window_seconds`. **CAN EXCEED 1.0** — see `gap_seconds`: the three
        window kinds are summed independently, so a pair that is desynced *through* an upstream
        blackout books the same wall-clock seconds twice. Any consumer treating this as a fraction
        of elapsed time must say what it does above 1.0 (T0101; the paging work is T0105)."""
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
        """True iff none of `pairs` currently has an open gap (reconnecting or desynced).

        DELIBERATELY does NOT consult `is_silent` (spec 00073 D3). This gates the healthchecks.io
        ping for EVERY pair at once, so an upstream-silence threshold fitted to ~4 days of thin-leg
        data would let one twitchy pair darken the fleet's last-resort liveness signal on both
        capture hosts -- strictly worse than the metric gap it would close. Silence is BOOKED first;
        gating waits until the exported gauge shows a production distribution worth thresholding.
        """
        return not any(self.is_open(pair) for pair in pairs)


def ping_healthcheck(url: str | None, *, timeout: int = DEFAULT_HEALTHCHECK_TIMEOUT_SECS) -> None:
    """Best-effort liveness ping to a healthchecks.io URL. No-op if `url` is falsy (the feature is
    optional, per `HEALTHCHECK_URL`). Never raises: a transport failure is logged and swallowed —
    the whole point of a dead-man's-switch is that a *missed* ping is what alerts, not an
    exception here taking down the capture loop."""
    if not url:
        return
    try:
        urllib.request.urlopen(url, timeout=timeout)  # noqa: S310 - fixed https healthchecks.io URL from env
    except (urllib.error.URLError, OSError) as exc:
        logger.warning("healthcheck ping failed url=%s error=%s", url, exc)


@dataclass
class DiskWatermark:
    """Disk-space guard: `breached` once free space on `path`'s filesystem drops below
    `min_free_bytes`. The caller (the capture loop) checks this before writing new segments and
    stops accepting them while breached; `usage_fn` is injectable for testing."""

    path: Path
    min_free_bytes: int = DEFAULT_MIN_FREE_BYTES
    usage_fn: Callable[[Path], object] = shutil.disk_usage
    _breached: bool = field(default=False, init=False, repr=False)
    _measurable: bool = field(default=True, init=False, repr=False)

    def check(self) -> bool:
        """Recompute breach state from current free space. Returns True iff healthy (not
        breached). Logs only on the state transition, not on every call.

        A probe that RAISES (a flaky mount) sets `measurable` False and re-raises. Freezing `breached`
        at its last value while the probe is down -- and pinging the dead-man green through it -- is the
        exact T0032 silent death: a disk that fills during the outage goes undetected. "Cannot measure"
        is not "healthy", so `measurable` gates the ping too; the healthcheck's grace absorbs a
        transient blip, and only a sustained probe failure withholds enough pings to page."""
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
        """False once a probe has raised without a later success -- so the ping loop can treat a
        sustained-unmeasurable disk as not-healthy rather than pinging green on a frozen `breached`."""
        return self._measurable
