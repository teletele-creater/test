#!/usr/bin/env python3
"""
過去1年間のバックテスト - 新閾値（厳格化後）でのシグナル検証

旧閾値と新閾値の両方でシグナルを比較し、フィルタリング効果を確認。
"""

import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta

# 設定
SYMBOLS = ["SPY", "IWM", "QQQ"]
BACKTEST_DAYS = 252  # 約1年（営業日ベース）
RSI_PERIOD = 14
MA_SHORT = 50
MA_LONG = 200
MA_PROXIMITY_PCT = 2.0
IV_LOOKBACK = 252

# 旧閾値
OLD_THRESHOLDS = {
    "A": {"ivr_min": 50, "vix_min": 20, "rsi_max": 35, "iv_hv_min": 1.2},
    "B": {"ivr_min": 50, "vix_min": 25, "iv_hv_min": 1.2},
    "C": {"ivr_min": 70, "vix_min": 20},
    "D": {"ivr_max": 20},
}

# 新閾値
NEW_THRESHOLDS = {
    "A": {"ivr_min": 65, "vix_min": 25, "rsi_max": 30, "iv_hv_min": 1.3},
    "B": {"ivr_min": 65, "vix_min": 30, "iv_hv_min": 1.3},
    "C": {"ivr_min": 80, "vix_min": 25},
    "D": {"ivr_max": 15},
}


def calculate_rsi_series(prices: pd.Series, period: int = 14) -> pd.Series:
    delta = prices.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)
    avg_gain = gain.rolling(window=period).mean()
    avg_loss = loss.rolling(window=period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def calculate_hv_series(prices: pd.Series, window: int = 20) -> pd.Series:
    log_returns = np.log(prices / prices.shift(1))
    return log_returns.rolling(window=window).std() * np.sqrt(252) * 100


def check_signals(date, vix_val, ivr, rsi_val, iv_hv, near_50ma, vix_declining, thresholds):
    """指定された閾値でシグナルをチェック"""
    triggered = []
    t = thresholds

    # 戦略A: ブルプットスプレッド
    conds_a = {
        f"IVR >= {t['A']['ivr_min']}%": ivr >= t["A"]["ivr_min"],
        f"VIX >= {t['A']['vix_min']}": vix_val >= t["A"]["vix_min"],
        f"RSI <= {t['A']['rsi_max']}": rsi_val <= t["A"]["rsi_max"],
        f"IV/HV >= {t['A']['iv_hv_min']}": iv_hv >= t["A"]["iv_hv_min"],
        "Near 50MA": near_50ma,
    }
    met_a = sum(v for v in conds_a.values())
    if met_a >= 3:
        strength = "STRONG" if met_a >= 4 else "MODERATE"
        triggered.append(("A:ブルプットSP", met_a, 5, strength, conds_a))

    # 戦略B: アイアンコンドル
    conds_b = {
        f"IVR >= {t['B']['ivr_min']}%": ivr >= t["B"]["ivr_min"],
        f"VIX >= {t['B']['vix_min']}": vix_val >= t["B"]["vix_min"],
        "VIX declining": vix_declining,
        f"IV/HV >= {t['B']['iv_hv_min']}": iv_hv >= t["B"]["iv_hv_min"],
    }
    met_b = sum(v for v in conds_b.values())
    if met_b >= 3:
        strength = "STRONG" if met_b >= 4 else "MODERATE"
        triggered.append(("B:アイアンコンドル", met_b, 4, strength, conds_b))

    # 戦略C: アイアンバタフライ
    conds_c = {
        f"IVR >= {t['C']['ivr_min']}%": ivr >= t["C"]["ivr_min"],
        f"VIX >= {t['C']['vix_min']}": vix_val >= t["C"]["vix_min"],
    }
    met_c = sum(v for v in conds_c.values())
    if met_c >= 2:
        triggered.append(("C:アイアンバタフライ", met_c, 2, "STRONG", conds_c))

    # 戦略D: カレンダースプレッド
    conds_d = {
        f"IVR <= {t['D']['ivr_max']}%": ivr <= t["D"]["ivr_max"],
    }
    met_d = sum(v for v in conds_d.values())
    if met_d >= 1:
        triggered.append(("D:カレンダーSP", met_d, 1, "MODERATE", conds_d))

    return triggered


def main():
    end_date = datetime.now()
    # IV Rank計算に1年 + バックテスト1年 = 約2年分のデータが必要
    start_date = end_date - timedelta(days=IV_LOOKBACK + 400)
    backtest_start = end_date - timedelta(days=365)

    print("=" * 80)
    print(f"  1年間バックテスト: 旧閾値 vs 新閾値（厳格化後）")
    print(f"  期間: {backtest_start.strftime('%Y-%m-%d')} ~ {end_date.strftime('%Y-%m-%d')}")
    print("=" * 80)

    # VIXデータ取得
    print("\nFetching VIX data...")
    vix_data = yf.Ticker("^VIX").history(start=start_date, end=end_date)
    vix_close = vix_data["Close"]
    print(f"  VIX data: {len(vix_close)} days loaded")

    for symbol in SYMBOLS:
        print(f"\n{'='*80}")
        print(f"  {symbol}")
        print(f"{'='*80}")

        ticker = yf.Ticker(symbol)
        hist = ticker.history(start=start_date, end=end_date)
        if hist.empty:
            print(f"  No data for {symbol}")
            continue

        prices = hist["Close"]
        rsi_series = calculate_rsi_series(prices, RSI_PERIOD)
        hv_series = calculate_hv_series(prices, 20)
        ma50_series = prices.rolling(window=MA_SHORT).mean()
        vix_aligned = vix_close.reindex(prices.index, method="ffill")

        old_signals = []
        new_signals = []

        backtest_dates = prices.index[prices.index >= pd.Timestamp(backtest_start)]

        for date in backtest_dates:
            if date not in vix_aligned.index:
                continue

            price = float(prices.loc[date])
            vix_val = float(vix_aligned.loc[date])

            iv_multiplier = {"SPY": 1.0, "IWM": 1.15, "QQQ": 1.05}.get(symbol, 1.0)
            iv_est = vix_val * iv_multiplier

            vix_hist_window = vix_aligned.loc[:date].tail(252)
            if len(vix_hist_window) < 50:
                continue
            iv_high = float(vix_hist_window.max())
            iv_low = float(vix_hist_window.min())
            ivr = (vix_val - iv_low) / (iv_high - iv_low) * 100 if iv_high != iv_low else 50.0

            hv_val = float(hv_series.loc[date]) if not np.isnan(hv_series.loc[date]) else 15.0
            iv_hv = iv_est / hv_val if hv_val > 0 else 1.0
            rsi_val = float(rsi_series.loc[date]) if not np.isnan(rsi_series.loc[date]) else 50.0

            ma50 = float(ma50_series.loc[date]) if not np.isnan(ma50_series.loc[date]) else price
            near_50ma = abs(price - ma50) / ma50 * 100 < MA_PROXIMITY_PCT

            vix_recent = vix_aligned.loc[:date].tail(5)
            vix_declining = float(vix_recent.iloc[-1]) < float(vix_recent.max()) * 0.95 if len(vix_recent) >= 5 else False

            base_data = {
                "date": date, "price": price, "vix": vix_val,
                "ivr": ivr, "rsi": rsi_val, "iv_hv": iv_hv,
                "near_50ma": near_50ma,
            }

            for strat_name, met, total, strength, conds in check_signals(
                date, vix_val, ivr, rsi_val, iv_hv, near_50ma, vix_declining, OLD_THRESHOLDS
            ):
                old_signals.append({**base_data, "strategy": strat_name, "strength": strength, "met": met, "total": total, "conds": conds})

            for strat_name, met, total, strength, conds in check_signals(
                date, vix_val, ivr, rsi_val, iv_hv, near_50ma, vix_declining, NEW_THRESHOLDS
            ):
                new_signals.append({**base_data, "strategy": strat_name, "strength": strength, "met": met, "total": total, "conds": conds})

        # --- 結果表示 ---

        # カレンダースプレッド以外のシグナル（売り系戦略）
        old_sell = [s for s in old_signals if not s["strategy"].startswith("D:")]
        new_sell = [s for s in new_signals if not s["strategy"].startswith("D:")]
        old_cal = [s for s in old_signals if s["strategy"].startswith("D:")]
        new_cal = [s for s in new_signals if s["strategy"].startswith("D:")]

        old_sell_days = sorted(set(s["date"] for s in old_sell))
        new_sell_days = sorted(set(s["date"] for s in new_sell))
        old_cal_days = sorted(set(s["date"] for s in old_cal))
        new_cal_days = sorted(set(s["date"] for s in new_cal))

        print(f"\n  --- 売り系戦略 (A/B/C) サマリー ---")
        print(f"  旧閾値: {len(old_sell_days)} 日間シグナル点灯")
        print(f"  新閾値: {len(new_sell_days)} 日間シグナル点灯")
        print(f"  削減率: {(1 - len(new_sell_days)/max(len(old_sell_days),1))*100:.0f}%")

        # 新閾値のシグナル詳細（売り系）
        if new_sell:
            print(f"\n  --- 新閾値で発火した売り系シグナル ---")
            print(f"  {'Date':<12} {'Strategy':<20} {'Price':>8} {'VIX':>6} {'IVR':>6} {'RSI':>6} {'IV/HV':>6} {'50MA':>5} {'Met':>5} {'Str':<8}")
            print(f"  {'-'*12} {'-'*20} {'-'*8} {'-'*6} {'-'*6} {'-'*6} {'-'*6} {'-'*5} {'-'*5} {'-'*8}")
            for sig in new_sell:
                date_str = sig["date"].strftime("%Y-%m-%d")
                near_ma = "Yes" if sig["near_50ma"] else "No"
                print(f"  {date_str:<12} {sig['strategy']:<20} ${sig['price']:>7.2f} {sig['vix']:>5.1f} {sig['ivr']:>5.1f}% {sig['rsi']:>5.1f} {sig['iv_hv']:>5.2f} {near_ma:>5} {sig['met']}/{sig['total']} {sig['strength']:<8}")

        # カレンダースプレッド
        print(f"\n  --- カレンダースプレッド (D) サマリー ---")
        print(f"  旧閾値: {len(old_cal_days)} 日間シグナル点灯")
        print(f"  新閾値: {len(new_cal_days)} 日間シグナル点灯")

        # 月別集計
        if new_sell:
            print(f"\n  --- 新閾値 月別シグナル日数（売り系） ---")
            months = {}
            for sig in new_sell:
                m = sig["date"].strftime("%Y-%m")
                if m not in months:
                    months[m] = set()
                months[m].add(sig["date"])
            for m in sorted(months.keys()):
                print(f"    {m}: {len(months[m])} 日")

    # 全体サマリー
    print(f"\n{'='*80}")
    print(f"  全体サマリー")
    print(f"{'='*80}")
    print(f"""
  新閾値のコンセプト:
  - IVR 65%+ / VIX 25-30+ / RSI 30以下 / IV/HV 1.3+
  - 「明確なパニック局面」のみでシグナル発火
  - 年に数回の高確率エントリーに特化
""")


if __name__ == "__main__":
    main()
