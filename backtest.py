#!/usr/bin/env python3
"""
過去1ヶ月のバックテスト - エントリーシグナルが出たポイントを特定
"""

import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta

# 設定
SYMBOLS = ["SPY", "IWM", "QQQ"]
LOOKBACK_DAYS = 60  # バックテスト期間 + バッファ
BACKTEST_DAYS = 35  # 実際にチェックする日数（約1ヶ月）
RSI_PERIOD = 14
MA_SHORT = 50
MA_LONG = 200
MA_PROXIMITY_PCT = 2.0
IV_LOOKBACK = 252

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

def main():
    end_date = datetime.now()
    start_date = end_date - timedelta(days=IV_LOOKBACK + 30)  # IV Rank計算に1年必要
    backtest_start = end_date - timedelta(days=BACKTEST_DAYS)

    # VIXデータ取得
    print("Fetching VIX data...")
    vix_data = yf.Ticker("^VIX").history(start=start_date, end=end_date)
    vix_close = vix_data["Close"]

    for symbol in SYMBOLS:
        print(f"\n{'='*70}")
        print(f"  Backtest: {symbol} ({backtest_start.strftime('%Y-%m-%d')} ~ {end_date.strftime('%Y-%m-%d')})")
        print(f"{'='*70}")

        # 価格データ取得
        ticker = yf.Ticker(symbol)
        hist = ticker.history(start=start_date, end=end_date)
        if hist.empty:
            print(f"  No data for {symbol}")
            continue

        prices = hist["Close"]

        # 各指標をシリーズとして計算
        rsi_series = calculate_rsi_series(prices, RSI_PERIOD)
        hv_series = calculate_hv_series(prices, 20)
        ma50_series = prices.rolling(window=MA_SHORT).mean()
        ma200_series = prices.rolling(window=MA_LONG).mean()

        # IV Rank計算用のVIXローリング
        vix_aligned = vix_close.reindex(prices.index, method="ffill")

        signals_found = []

        # バックテスト期間の各営業日をチェック
        backtest_dates = prices.index[prices.index >= pd.Timestamp(backtest_start)]

        for date in backtest_dates:
            if date not in vix_aligned.index:
                continue

            price = float(prices.loc[date])
            vix_val = float(vix_aligned.loc[date])

            # IV推定
            iv_multiplier = {"SPY": 1.0, "IWM": 1.15, "QQQ": 1.05}.get(symbol, 1.0)
            iv_est = vix_val * iv_multiplier

            # IV Rank（VIXベース、過去252日）
            vix_hist_window = vix_aligned.loc[:date].tail(252)
            if len(vix_hist_window) < 50:
                continue
            iv_high = float(vix_hist_window.max())
            iv_low = float(vix_hist_window.min())
            if iv_high == iv_low:
                ivr = 50.0
            else:
                ivr = (vix_val - iv_low) / (iv_high - iv_low) * 100

            # HV
            hv_val = float(hv_series.loc[date]) if not np.isnan(hv_series.loc[date]) else 15.0

            # IV/HV比率
            iv_hv = iv_est / hv_val if hv_val > 0 else 1.0

            # RSI
            rsi_val = float(rsi_series.loc[date]) if not np.isnan(rsi_series.loc[date]) else 50.0

            # MA
            ma50 = float(ma50_series.loc[date]) if not np.isnan(ma50_series.loc[date]) else price
            ma200 = float(ma200_series.loc[date]) if not np.isnan(ma200_series.loc[date]) else price
            near_50ma = abs(price - ma50) / ma50 * 100 < MA_PROXIMITY_PCT
            near_200ma = abs(price - ma200) / ma200 * 100 < MA_PROXIMITY_PCT

            # VIX declining
            vix_recent = vix_aligned.loc[:date].tail(5)
            vix_declining = float(vix_recent.iloc[-1]) < float(vix_recent.max()) * 0.95 if len(vix_recent) >= 5 else False

            # === 戦略A: SPYブルプットスプレッド ===
            conds_a = {
                "IVR >= 50%": ivr >= 50,
                "VIX >= 20": vix_val >= 20,
                "RSI <= 35": rsi_val <= 35,
                "IV/HV >= 1.2": iv_hv >= 1.2,
                "Near 50MA": near_50ma,
            }
            met_a = sum(v for v in conds_a.values())

            # === 戦略B: アイアンコンドル ===
            conds_b = {
                "IVR >= 50%": ivr >= 50,
                "VIX >= 25": vix_val >= 25,
                "VIX declining": vix_declining,
                "IV/HV >= 1.2": iv_hv >= 1.2,
            }
            met_b = sum(v for v in conds_b.values())

            # === 戦略C: アイアンバタフライ ===
            conds_c = {
                "IVR >= 70%": ivr >= 70,
                "VIX >= 20": vix_val >= 20,
            }
            met_c = sum(v for v in conds_c.values())

            # === 戦略D: カレンダースプレッド ===
            conds_d = {
                "IVR <= 20%": ivr <= 20,
            }
            met_d = sum(v for v in conds_d.values())

            # シグナル判定
            triggered = []

            if met_a >= 3:
                strength = "STRONG" if met_a >= 4 else "MODERATE"
                triggered.append(("SPYブルプットスプレッド", met_a, 5, strength, conds_a))

            if met_b >= 3:
                strength = "STRONG" if met_b >= 3 else "MODERATE"
                triggered.append(("アイアンコンドル", met_b, 4, strength, conds_b))

            if met_c >= 2:
                strength = "STRONG" if met_c >= 2 else "MODERATE"
                triggered.append(("アイアンバタフライ", met_c, 2, strength, conds_c))

            if met_d >= 1:
                triggered.append(("カレンダースプレッド", met_d, 1, "MODERATE", conds_d))

            if triggered:
                for strat_name, met, total, strength, conds in triggered:
                    signals_found.append({
                        "date": date,
                        "strategy": strat_name,
                        "strength": strength,
                        "met": met,
                        "total": total,
                        "price": price,
                        "vix": vix_val,
                        "ivr": ivr,
                        "rsi": rsi_val,
                        "iv_hv": iv_hv,
                        "near_50ma": near_50ma,
                        "conds": conds,
                    })

        # 結果表示
        if not signals_found:
            print("\n  No entry signals found in the backtest period.")
            continue

        # 戦略ごとにグループ化して表示
        strategies_seen = {}
        for sig in signals_found:
            key = sig["strategy"]
            if key not in strategies_seen:
                strategies_seen[key] = []
            strategies_seen[key].append(sig)

        for strat_name, sigs in strategies_seen.items():
            print(f"\n  --- {strat_name} ---")
            print(f"  {'Date':<12} {'Price':>8} {'VIX':>6} {'IVR':>6} {'RSI':>6} {'IV/HV':>6} {'50MA':>5} {'Strength':<9} {'Conds'}")
            print(f"  {'-'*12} {'-'*8} {'-'*6} {'-'*6} {'-'*6} {'-'*6} {'-'*5} {'-'*9} {'-'*20}")

            for sig in sigs:
                date_str = sig["date"].strftime("%Y-%m-%d")
                near_ma = "Yes" if sig["near_50ma"] else "No"
                met_conds = [k for k, v in sig["conds"].items() if v]
                print(f"  {date_str:<12} ${sig['price']:>7.2f} {sig['vix']:>5.1f} {sig['ivr']:>5.1f}% {sig['rsi']:>5.1f} {sig['iv_hv']:>5.2f} {near_ma:>5} {sig['strength']:<9} {', '.join(met_conds)}")

        print(f"\n  Total signal days: {len(set(s['date'] for s in signals_found))}")

if __name__ == "__main__":
    main()
