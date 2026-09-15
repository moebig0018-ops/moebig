#!/usr/bin/env python3
"""CLI: backtest the trend-pullback or liquidity-sweep strategy on 1H OHLCV.

Usage:
    python run.py --data btcusdt_1h.csv --strategy trend
    python run.py --data btcusdt_1h.csv --strategy sweep
    python run.py --data btcusdt_1h.csv --strategy both
"""
from __future__ import annotations

import argparse

from data_loader import build_context, load_ohlcv_1h
from engine import simulate, summarize
from strategies import (
    PullbackConfig,
    SweepConfig,
    generate_liquidity_sweep_signals,
    generate_trend_pullback_signals,
)


def print_summary(name: str, stats: dict) -> None:
    print(f"\n=== {name} ===")
    if stats.get("n_trades", 0) == 0:
        print("거래 없음 (데이터 기간이 짧거나 조건을 만족하는 셋업이 없었습니다).")
        return
    print(f"거래 수          : {stats['n_trades']}")
    print(f"승률             : {stats['win_rate_pct']}%")
    print(f"평균 R           : {stats['avg_r']}")
    print(f"평균 익절 R      : {stats['avg_win_r']}")
    print(f"평균 손절 R      : {stats['avg_loss_r']}")
    print(f"기대값(R/거래)   : {stats['expectancy_r']}")
    print(f"프로핏 팩터      : {stats['profit_factor']}")
    print(f"최대 연속 손절   : {stats['max_losing_streak']}")
    print(f"누적 R           : {stats['total_r']}")
    print(f"최대 낙폭(R)     : {stats['max_drawdown_r']}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", required=True, help="1H OHLCV CSV (timestamp,open,high,low,close,volume)")
    parser.add_argument("--strategy", choices=["trend", "sweep", "both"], default="both")
    args = parser.parse_args()

    df_1h = load_ohlcv_1h(args.data)
    ctx = build_context(df_1h)

    if args.strategy in ("trend", "both"):
        cfg = PullbackConfig()
        sigs = generate_trend_pullback_signals(df_1h, ctx, cfg)
        trades = simulate(df_1h, sigs, "trend_pullback", trail_atr_mult=cfg.trail_atr_mult, atr_series=ctx["atr14_1h"])
        print_summary("추세추종: EMA 되돌림 + ATR 트레일링", summarize(trades))

    if args.strategy in ("sweep", "both"):
        cfg = SweepConfig()
        sigs = generate_liquidity_sweep_signals(df_1h, ctx, cfg)
        trades = simulate(df_1h, sigs, "liquidity_sweep")
        print_summary("역추세: 유동성 스윕 리버설", summarize(trades))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
