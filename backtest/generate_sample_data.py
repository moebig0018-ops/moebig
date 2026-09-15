#!/usr/bin/env python3
"""Generate SYNTHETIC 1H OHLCV for smoke-testing the backtest engine.

This is fake, regime-switching random-walk data — good for proving the
pipeline runs end-to-end without crashing, USELESS for judging whether
either strategy is actually profitable. Real testing needs real market data
(see backtest/README.md).
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd


def generate(n_bars: int, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    start = pd.Timestamp("2024-01-01", tz="UTC")
    idx = pd.date_range(start, periods=n_bars, freq="1h")

    price = 40000.0
    closes = []
    # Regime-switching drift so trend + range + reversal setups all occur.
    regime_len = 200
    for i in range(n_bars):
        if i % regime_len == 0:
            drift = rng.choice([-1, 0, 1]) * rng.uniform(0.0005, 0.002)
        vol = rng.uniform(0.002, 0.01)
        price *= 1 + drift + rng.normal(0, vol)
        price = max(price, 100)
        closes.append(price)

    closes = np.array(closes)
    opens = np.roll(closes, 1)
    opens[0] = closes[0]
    highs = np.maximum(opens, closes) * (1 + rng.uniform(0, 0.004, n_bars))
    lows = np.minimum(opens, closes) * (1 - rng.uniform(0, 0.004, n_bars))
    volume = rng.uniform(100, 1000, n_bars)

    return pd.DataFrame(
        {"timestamp": idx, "open": opens, "high": highs, "low": lows, "close": closes, "volume": volume}
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bars", type=int, default=24 * 400, help="number of 1H bars (default ~400 days)")
    parser.add_argument("--out", default="sample_1h.csv")
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()

    df = generate(args.bars, args.seed)
    df.to_csv(args.out, index=False)
    print(f"synthetic 데이터 {len(df)}행 저장: {args.out}")
