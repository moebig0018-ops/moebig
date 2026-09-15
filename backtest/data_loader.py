"""Load 1H OHLCV from CSV and derive 4H / daily / Asia-session context.

Expected CSV columns (header row required): timestamp,open,high,low,close,volume
`timestamp` must be parseable by pandas (ISO 8601 or unix seconds/ms) and UTC.
"""
from __future__ import annotations

import pandas as pd

from indicators import adx, atr, ema, rolling_swing_high, rolling_swing_low

# Asia session convention used here: 00:00-08:00 UTC (Tokyo pre/regular hours).
# This is a modeling choice, not a universal standard — adjust to taste.
ASIA_SESSION_START_UTC = 0
ASIA_SESSION_END_UTC = 8


def load_ohlcv_1h(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    ts = df["timestamp"]
    if pd.api.types.is_numeric_dtype(ts):
        unit = "ms" if ts.iloc[0] > 10**12 else "s"
        df["timestamp"] = pd.to_datetime(ts, unit=unit, utc=True)
    else:
        df["timestamp"] = pd.to_datetime(ts, utc=True)
    df = df.set_index("timestamp").sort_index()
    df = df[["open", "high", "low", "close", "volume"]].astype(float)
    return df


def build_4h_trend_context(df_1h: pd.DataFrame, adx_len: int = 14) -> pd.DataFrame:
    """Resample to 4H, compute EMA20/50 + ADX, then forward-fill back onto the
    1H index so each 1H bar carries the *most recently closed* 4H trend state.
    """
    df_4h = df_1h.resample("4h", label="right", closed="right").agg(
        {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    ).dropna()

    df_4h["ema20"] = ema(df_4h["close"], 20)
    df_4h["ema50"] = ema(df_4h["close"], 50)
    df_4h["adx"] = adx(df_4h, adx_len)
    df_4h["trend_up"] = (df_4h["ema20"] > df_4h["ema50"]) & (df_4h["close"] > df_4h["ema20"])
    df_4h["trend_down"] = (df_4h["ema20"] < df_4h["ema50"]) & (df_4h["close"] < df_4h["ema20"])
    df_4h["ranging"] = df_4h["adx"] < 20

    df_4h["swing_high"] = df_4h["high"].where(rolling_swing_high(df_4h["high"], window=2))
    df_4h["swing_low"] = df_4h["low"].where(rolling_swing_low(df_4h["low"], window=2))
    # Most recent confirmed swing (shifted so we never look ahead).
    df_4h["last_swing_high"] = df_4h["swing_high"].ffill().shift(1)
    df_4h["last_swing_low"] = df_4h["swing_low"].ffill().shift(1)

    cols = [
        "ema20", "ema50", "adx", "trend_up", "trend_down", "ranging",
        "last_swing_high", "last_swing_low",
    ]
    # shift(1): a 1H bar may only see the 4H bar that has *already closed*
    # strictly before it — this avoids look-ahead bias at the resample boundary.
    ctx = df_4h[cols].shift(1)
    return ctx.reindex(df_1h.index, method="ffill")


def build_daily_and_session_levels(df_1h: pd.DataFrame) -> pd.DataFrame:
    daily = df_1h.resample("1D", label="left", closed="left").agg({"high": "max", "low": "min"})
    daily = daily.shift(1)  # previous day's high/low
    daily.columns = ["prev_day_high", "prev_day_low"]
    prev_day = daily.reindex(df_1h.index, method="ffill")

    hour = df_1h.index.hour
    in_asia = (hour >= ASIA_SESSION_START_UTC) & (hour < ASIA_SESSION_END_UTC)
    session_date = (df_1h.index - pd.to_timedelta(hour, unit="h")).normalize()

    asia = df_1h[in_asia].copy()
    asia["session_date"] = session_date[in_asia]
    per_day = asia.groupby("session_date").agg(asia_high=("high", "max"), asia_low=("low", "min"))

    day_key = session_date
    asia_levels = per_day.reindex(day_key).set_axis(df_1h.index)
    # Only usable once that day's Asia session has fully closed.
    asia_levels_prev = per_day.shift(1).reindex((day_key - pd.Timedelta(days=1))).set_axis(df_1h.index)

    out = prev_day.copy()
    out["asia_high"] = asia_levels["asia_high"].combine_first(asia_levels_prev["asia_high"])
    out["asia_low"] = asia_levels["asia_low"].combine_first(asia_levels_prev["asia_low"])
    return out


def build_context(df_1h: pd.DataFrame, atr_len: int = 14) -> pd.DataFrame:
    ctx = build_4h_trend_context(df_1h)
    ctx = ctx.join(build_daily_and_session_levels(df_1h))
    ctx["atr14_1h"] = atr(df_1h, atr_len)
    ctx["ema20_1h"] = ema(df_1h["close"], 20)
    return ctx
