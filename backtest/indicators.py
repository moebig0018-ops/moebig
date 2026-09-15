"""Minimal technical indicators (no TA-Lib dependency) — EMA, ATR, ADX."""
from __future__ import annotations

import numpy as np
import pandas as pd


def ema(series: pd.Series, length: int) -> pd.Series:
    return series.ewm(span=length, adjust=False).mean()


def true_range(df: pd.DataFrame) -> pd.Series:
    prev_close = df["close"].shift(1)
    tr = pd.concat(
        [
            df["high"] - df["low"],
            (df["high"] - prev_close).abs(),
            (df["low"] - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr


def atr(df: pd.DataFrame, length: int = 14) -> pd.Series:
    tr = true_range(df)
    # Wilder's smoothing (RMA), matches TradingView's default ATR.
    return tr.ewm(alpha=1 / length, adjust=False).mean()


def adx(df: pd.DataFrame, length: int = 14) -> pd.Series:
    """Wilder's ADX. Returns a Series aligned to df.index."""
    up_move = df["high"].diff()
    down_move = -df["low"].diff()

    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    tr = true_range(df)
    atr_ = tr.ewm(alpha=1 / length, adjust=False).mean()

    plus_dm_s = pd.Series(plus_dm, index=df.index).ewm(alpha=1 / length, adjust=False).mean()
    minus_dm_s = pd.Series(minus_dm, index=df.index).ewm(alpha=1 / length, adjust=False).mean()

    plus_di = 100 * (plus_dm_s / atr_.replace(0, np.nan))
    minus_di = 100 * (minus_dm_s / atr_.replace(0, np.nan))

    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    adx_ = dx.ewm(alpha=1 / length, adjust=False).mean()
    return adx_.fillna(0.0)


def rolling_swing_high(series: pd.Series, window: int = 2) -> pd.Series:
    """True where a bar is the highest in a centered window (a fractal swing high)."""
    return series == series.rolling(window * 2 + 1, center=True).max()


def rolling_swing_low(series: pd.Series, window: int = 2) -> pd.Series:
    return series == series.rolling(window * 2 + 1, center=True).min()
