"""Signal generation for the two strategies.

IMPORTANT — stated assumption: the user's message referenced an existing
"EMA 되돌림 진입" (EMA pullback entry) rule ("지금 하는 ... 그대로 두고")
without spelling it out here. It is formalized below as: price touches/dips
to the 1H EMA20 while the 4H trend filter is intact, then a same-direction
"big body" candle (body >= BODY_ATR_MULT x ATR14) closes back beyond EMA20.
Adjust PullbackConfig if this doesn't match your actual rule.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass
class PullbackConfig:
    stop_atr_mult: float = 0.5       # stop = pullback swing low/high -/+ this * ATR
    trail_atr_mult: float = 2.0      # chandelier trail distance, active after +1R
    pullback_lookback: int = 5       # bars searched back for the pullback extreme
    body_atr_mult: float = 0.5       # min candle body size (x ATR) to count as confirmation


@dataclass
class SweepConfig:
    stop_atr_mult: float = 0.4       # stop = wick extreme -/+ this * ATR
    min_reward_r: float = 1.0        # skip signals where opposite level gives < this R


def generate_trend_pullback_signals(
    df_1h: pd.DataFrame, ctx: pd.DataFrame, cfg: PullbackConfig = PullbackConfig()
) -> list[dict]:
    signals = []
    touched_ema_long = False
    touched_ema_short = False

    for i in range(cfg.pullback_lookback, len(df_1h)):
        time = df_1h.index[i]
        row = df_1h.iloc[i]
        c = ctx.loc[time]

        if pd.isna(c["ema20_1h"]) or pd.isna(c["atr14_1h"]) or c["ranging"]:
            touched_ema_long = touched_ema_short = False
            continue

        # Track whether price has dipped to/through the 1H EMA20 recently —
        # required before a confirmation candle counts as a pullback entry.
        if row["low"] <= c["ema20_1h"]:
            touched_ema_long = True
        if row["high"] >= c["ema20_1h"]:
            touched_ema_short = True

        body = row["close"] - row["open"]
        big_body = abs(body) >= cfg.body_atr_mult * c["atr14_1h"]

        window = df_1h.iloc[i - cfg.pullback_lookback : i]

        if c["trend_up"] and touched_ema_long and big_body and body > 0 and row["close"] > c["ema20_1h"]:
            swing_low = window["low"].min()
            stop = swing_low - cfg.stop_atr_mult * c["atr14_1h"]
            entry = row["close"]
            if entry > stop:
                signals.append({
                    "time": time, "direction": "long",
                    "entry_price": entry, "stop_price": stop, "target_price": None,
                })
            touched_ema_long = False

        elif c["trend_down"] and touched_ema_short and big_body and body < 0 and row["close"] < c["ema20_1h"]:
            swing_high = window["high"].max()
            stop = swing_high + cfg.stop_atr_mult * c["atr14_1h"]
            entry = row["close"]
            if entry < stop:
                signals.append({
                    "time": time, "direction": "short",
                    "entry_price": entry, "stop_price": stop, "target_price": None,
                })
            touched_ema_short = False

    return signals


def generate_liquidity_sweep_signals(
    df_1h: pd.DataFrame, ctx: pd.DataFrame, cfg: SweepConfig = SweepConfig()
) -> list[dict]:
    """Only trades sweeps in the direction of the 4H trend (a low-sweep in an
    uptrend => long; a high-sweep in a downtrend => short), per the user's
    stated filter ("진짜 추세 반대 매매는 일봉 레벨에서만" is NOT modeled
    here — only the HTF-aligned sweep variant is implemented).
    """
    signals = []

    for time, row in df_1h.iterrows():
        c = ctx.loc[time]
        if pd.isna(c["atr14_1h"]):
            continue

        levels_below = [c[k] for k in ("prev_day_low", "asia_low", "last_swing_low") if pd.notna(c[k])]
        levels_above = [c[k] for k in ("prev_day_high", "asia_high", "last_swing_high") if pd.notna(c[k])]

        # Long: uptrend + wick sweeps a support level but closes back above it.
        if c["trend_up"]:
            swept = [lv for lv in levels_below if row["low"] < lv <= row["close"]]
            if swept:
                level = max(swept)  # nearest swept level
                stop = row["low"] - cfg.stop_atr_mult * c["atr14_1h"]
                entry = row["close"]
                target_candidates = [lv for lv in levels_above if lv > entry]
                target = min(target_candidates) if target_candidates else None
                risk = entry - stop
                if risk > 0 and target is not None and (target - entry) / risk >= cfg.min_reward_r:
                    signals.append({
                        "time": time, "direction": "long",
                        "entry_price": entry, "stop_price": stop, "target_price": target,
                    })

        # Short: downtrend + wick sweeps a resistance level but closes back below it.
        if c["trend_down"]:
            swept = [lv for lv in levels_above if row["high"] > lv >= row["close"]]
            if swept:
                level = min(swept)
                stop = row["high"] + cfg.stop_atr_mult * c["atr14_1h"]
                entry = row["close"]
                target_candidates = [lv for lv in levels_below if lv < entry]
                target = max(target_candidates) if target_candidates else None
                risk = stop - entry
                if risk > 0 and target is not None and (entry - target) / risk >= cfg.min_reward_r:
                    signals.append({
                        "time": time, "direction": "short",
                        "entry_price": entry, "stop_price": stop, "target_price": target,
                    })

    return signals
