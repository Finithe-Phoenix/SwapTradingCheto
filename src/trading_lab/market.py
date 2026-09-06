from dataclasses import dataclass
from datetime import datetime, timezone
import math


def utc_timestamp(value: str) -> int:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return int(parsed.timestamp())


def iso(timestamp: int) -> str:
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class Candle:
    timestamp: int
    open: float
    high: float
    low: float
    close: float
    volume: float

    def validate(self):
        if type(self.timestamp) is not int or self.timestamp < 0:
            raise ValueError("Invalid timestamp")
        values = (self.open, self.high, self.low, self.close, self.volume)
        if not all(math.isfinite(x) for x in values):
            raise ValueError("Non-finite OHLCV")
        if min(values[:4]) <= 0 or self.volume < 0:
            raise ValueError("Nonpositive price or negative volume")
        if not self.low <= min(self.open, self.close) <= max(self.open, self.close) <= self.high:
            raise ValueError("Inconsistent OHLC")


def aggregate(candles: list[Candle], seconds: int) -> list[Candle]:
    """Aggregate hourly input; incomplete UTC-aligned buckets are omitted."""
    groups = {}
    for c in candles:
        bucket = c.timestamp // seconds * seconds
        groups.setdefault(bucket, []).append(c)
    result = []
    for ts, rows in sorted(groups.items()):
        if [c.timestamp for c in rows] != list(range(ts, ts + seconds, 3600)):
            continue
        result.append(Candle(ts, rows[0].open, max(c.high for c in rows),
                             min(c.low for c in rows), rows[-1].close, sum(c.volume for c in rows)))
    return result


@dataclass(frozen=True)
class Signal:
    available_at: int
    atr: float
    enter: bool
    exit: bool
    trend: bool


def ema(values, period):
    out = [None] * len(values)
    if len(values) < period:
        return out
    value = sum(values[:period]) / period
    out[period - 1] = value
    alpha = 2 / (period + 1)
    for i in range(period, len(values)):
        value = alpha * values[i] + (1 - alpha) * value
        out[i] = value
    return out


def atr(candles, period):
    tr = [max(c.high - c.low, abs(c.high - candles[i - 1].close),
              abs(c.low - candles[i - 1].close)) if i else c.high - c.low
          for i, c in enumerate(candles)]
    out = [None] * len(candles)
    if len(tr) >= period:
        value = sum(tr[:period]) / period
        out[period - 1] = value
        for i in range(period, len(tr)):
            value = (value * (period - 1) + tr[i]) / period
            out[i] = value
    return out


def evaluate(candles4h, daily, config):
    """Shared S1 implementation. Every daily value is joined by its close time."""
    trends = ema([x.close for x in daily], config.trend_period)
    volatility = atr(candles4h, config.atr_period)
    day_index = -1
    result = []
    for i, c in enumerate(candles4h):
        available = c.timestamp + 14400
        while day_index + 1 < len(daily) and daily[day_index + 1].timestamp + 86400 <= available:
            day_index += 1
        fresh_day = day_index >= 0 and available - (daily[day_index].timestamp + 86400) < 86400
        trend = bool(fresh_day and trends[day_index] is not None and daily[day_index].close > trends[day_index])
        enter = bool(trend and i >= config.breakout_period and volatility[i] is not None
                     and c.volume > 0 and c.close > max(x.high for x in candles4h[i - config.breakout_period:i]))
        exit_signal = bool(i >= config.exit_period and c.close < min(x.low for x in candles4h[i - config.exit_period:i]))
        result.append(Signal(available, volatility[i] or 0.0, enter, exit_signal, trend))
    return result


def signals(hourly, config):
    return {s.available_at: s for s in evaluate(aggregate(hourly, 14400), aggregate(hourly, 86400), config)}
