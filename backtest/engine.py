"""Bar-by-bar trade simulation and performance stats.

Simplification (stated explicitly, not hidden): when a bar's high AND low both
cross a trade's stop and target in the same bar, we cannot know which was hit
first from OHLC alone. This engine conservatively assumes the STOP is hit
first in that case — it never overstates results by assuming the best case.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional

import numpy as np
import pandas as pd

Direction = Literal["long", "short"]


@dataclass
class Trade:
    strategy: str
    direction: Direction
    entry_time: pd.Timestamp
    entry_price: float
    stop_price: float
    initial_risk: float  # |entry - initial stop|, always > 0
    target_price: Optional[float] = None
    exit_time: Optional[pd.Timestamp] = None
    exit_price: Optional[float] = None
    exit_reason: Optional[str] = None  # "stop" | "target" | "eod"
    moved_to_breakeven: bool = False
    r_multiple: Optional[float] = None

    def close(self, time: pd.Timestamp, price: float, reason: str) -> None:
        self.exit_time = time
        self.exit_price = price
        self.exit_reason = reason
        signed = (price - self.entry_price) if self.direction == "long" else (self.entry_price - price)
        self.r_multiple = signed / self.initial_risk


def _hit(direction: Direction, bar: pd.Series, stop: float, target: Optional[float]):
    """Return ('stop'|'target'|None, price) for this bar, stop-first on overlap."""
    if direction == "long":
        stop_hit = bar["low"] <= stop
        target_hit = target is not None and bar["high"] >= target
    else:
        stop_hit = bar["high"] >= stop
        target_hit = target is not None and bar["low"] <= target

    if stop_hit:
        return "stop", stop
    if target_hit:
        return "target", target
    return None, None


def simulate(
    df_1h: pd.DataFrame,
    signals: list[dict],
    strategy_name: str,
    trail_atr_mult: Optional[float] = None,
    atr_series: Optional[pd.Series] = None,
) -> list[Trade]:
    """Run one trade at a time (no pyramiding, no overlap) through df_1h.

    `signals` is a list of dicts, each with at least:
        {time, direction, entry_price, stop_price, target_price(optional)}
    sorted by time. `trail_atr_mult` enables chandelier trailing after the
    trade reaches +1R (used by the trend-pullback strategy; leave None for
    strategies with a fixed target, like the liquidity-sweep reversal).
    """
    trades: list[Trade] = []
    signals_by_time = {s["time"]: s for s in signals}
    open_trade: Optional[Trade] = None
    extreme_since_entry = None  # highest high (long) / lowest low (short) since entry

    for time, bar in df_1h.iterrows():
        if open_trade is not None:
            if trail_atr_mult is not None and atr_series is not None and time in atr_series.index:
                cur_atr = atr_series.loc[time]
                if open_trade.direction == "long":
                    extreme_since_entry = max(extreme_since_entry, bar["high"])
                    r_gained = (extreme_since_entry - open_trade.entry_price) / open_trade.initial_risk
                    if r_gained >= 1 and not open_trade.moved_to_breakeven:
                        open_trade.stop_price = max(open_trade.stop_price, open_trade.entry_price)
                        open_trade.moved_to_breakeven = True
                    if open_trade.moved_to_breakeven and pd.notna(cur_atr):
                        chandelier = extreme_since_entry - trail_atr_mult * cur_atr
                        open_trade.stop_price = max(open_trade.stop_price, chandelier)
                else:
                    extreme_since_entry = min(extreme_since_entry, bar["low"])
                    r_gained = (open_trade.entry_price - extreme_since_entry) / open_trade.initial_risk
                    if r_gained >= 1 and not open_trade.moved_to_breakeven:
                        open_trade.stop_price = min(open_trade.stop_price, open_trade.entry_price)
                        open_trade.moved_to_breakeven = True
                    if open_trade.moved_to_breakeven and pd.notna(cur_atr):
                        chandelier = extreme_since_entry + trail_atr_mult * cur_atr
                        open_trade.stop_price = min(open_trade.stop_price, chandelier)

            reason, price = _hit(open_trade.direction, bar, open_trade.stop_price, open_trade.target_price)
            if reason:
                open_trade.close(time, price, reason)
                trades.append(open_trade)
                open_trade = None
                extreme_since_entry = None
            continue  # one position at a time — no new entry while in a trade

        sig = signals_by_time.get(time)
        if sig is None:
            continue
        risk = abs(sig["entry_price"] - sig["stop_price"])
        if risk <= 0:
            continue
        open_trade = Trade(
            strategy=strategy_name,
            direction=sig["direction"],
            entry_time=time,
            entry_price=sig["entry_price"],
            stop_price=sig["stop_price"],
            initial_risk=risk,
            target_price=sig.get("target_price"),
        )
        extreme_since_entry = bar["high"] if sig["direction"] == "long" else bar["low"]

    if open_trade is not None:
        last_time = df_1h.index[-1]
        open_trade.close(last_time, df_1h.iloc[-1]["close"], "eod")
        trades.append(open_trade)

    return trades


def summarize(trades: list[Trade]) -> dict:
    if not trades:
        return {"n_trades": 0}

    r = np.array([t.r_multiple for t in trades])
    wins = r[r > 0]
    losses = r[r <= 0]

    # Longest losing streak, for the "8~10연패는 정상" sanity check.
    streak = max_streak = 0
    for x in r:
        streak = streak + 1 if x <= 0 else 0
        max_streak = max(max_streak, streak)

    equity = np.cumsum(r)

    return {
        "n_trades": len(trades),
        "win_rate_pct": round(100 * len(wins) / len(trades), 1),
        "avg_r": round(float(r.mean()), 2),
        "avg_win_r": round(float(wins.mean()), 2) if len(wins) else 0.0,
        "avg_loss_r": round(float(losses.mean()), 2) if len(losses) else 0.0,
        "expectancy_r": round(float(r.mean()), 2),
        "profit_factor": round(float(wins.sum() / -losses.sum()), 2) if losses.sum() != 0 else float("inf"),
        "max_losing_streak": int(max_streak),
        "total_r": round(float(r.sum()), 2),
        "max_drawdown_r": round(float((np.maximum.accumulate(equity) - equity).max()), 2),
    }
