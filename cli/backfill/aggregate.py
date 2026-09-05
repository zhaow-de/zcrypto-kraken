from __future__ import annotations


def aggregate_minutes(minute_rows: list[list], interval_secs: int) -> list[list]:
    """Aggregate 1-minute OHLCVT rows into `interval_secs`-cadence bars with a reconstructed vwap.

    `vwap` is a close-price proxy (the dumps carry no vwap); a bucket with no rows produces no bar — `cli.ohlc.qa` reports gaps.
    """
    if not minute_rows:
        return []

    buckets: dict[int, list[list]] = {}
    for ts, o, h, l, c, v, n in minute_rows:
        bucket_ts = ts // interval_secs * interval_secs
        buckets.setdefault(bucket_ts, []).append([ts, o, h, l, c, v, n])

    out: list[list] = []
    for bucket_ts in sorted(buckets):
        rows = sorted(buckets[bucket_ts], key=lambda r: r[0])
        open_ = float(rows[0][1])
        close = float(rows[-1][4])
        high = max(float(r[2]) for r in rows)
        low = min(float(r[3]) for r in rows)
        volume = sum(float(r[5]) for r in rows)
        count = sum(int(r[6]) for r in rows)
        vwap = close if volume == 0 else sum(float(r[4]) * float(r[5]) for r in rows) / volume
        out.append([bucket_ts, open_, high, low, close, vwap, volume, count])
    return out
