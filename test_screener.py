#!/usr/bin/env python3
"""
スクリーニングルールのテスト

モックデータを使って各ルールの判定ロジックを検証する。
yfinanceに接続せず、ロジック単体をテストできる。

使い方:
    python test_screener.py           # 全テスト実行
    python test_screener.py --live    # yfinanceから実データで実行
"""

import argparse
import sys
from datetime import datetime

import numpy as np
import pandas as pd

from screener_config import ScreeningRules
from stock_screener import (
    RuleResult,
    ScreeningResult,
    StockData,
    check_rule1_yield,
    check_rule2_growth_peg,
    check_rule3_per_range,
    print_screening_report,
    screen_stock,
    screen_stocks,
)


# ============================================================
# テスト用モックデータ生成
# ============================================================

def make_historical_yields(
    base: float = 2.5,
    current: float = 4.5,
    months: int = 60,
) -> pd.Series:
    """過去N月の配当利回り推移をシミュレート"""
    dates = pd.date_range(end=datetime.now(), periods=months, freq="ME")
    n = len(dates)
    # 通常時は base 付近、直近で current に上昇するパターン
    values = np.random.normal(base, 0.3, n)
    # 直近6ヶ月を高利回りに
    values[-6:] = np.random.normal(current, 0.2, min(6, n))
    return pd.Series(values, index=dates).clip(lower=0.5)


def make_price_history(
    current_price: float = 2000,
    low_price: float = 1600,
    months: int = 12,
) -> pd.Series:
    """底値から反発する株価推移を生成"""
    dates = pd.date_range(end=datetime.now(), periods=months, freq="ME")
    n = len(dates)
    # 前半で下がって後半で回復するパターン
    bottom_idx = n // 2
    prices = np.zeros(n)
    prices[:bottom_idx] = np.linspace(current_price * 0.9, low_price, bottom_idx)
    prices[bottom_idx:] = np.linspace(low_price, current_price, n - bottom_idx)
    return pd.Series(prices, index=dates)


def make_declining_price_history(
    current_price: float = 800,
    months: int = 12,
) -> pd.Series:
    """下落し続ける株価推移"""
    dates = pd.date_range(end=datetime.now(), periods=months, freq="ME")
    n = len(dates)
    prices = np.linspace(current_price * 1.5, current_price, n)
    return pd.Series(prices, index=dates)


def make_historical_pes(
    base: float = 18.0,
    current_price: float = 2000,
    eps: float = 200,
    months: int = 60,
) -> pd.Series:
    """過去N月のPER推移をシミュレート"""
    dates = pd.date_range(end=datetime.now(), periods=months, freq="ME")
    n = len(dates)
    # 株価変動でPERが変動するパターン
    prices = np.random.normal(base * eps, eps * 3, n)
    prices[-1] = current_price
    pes = prices / eps
    return pd.Series(pes, index=dates).clip(lower=3, upper=80)


def create_entry_zone_stock() -> StockData:
    """★ 全条件クリアの理想的エントリー銘柄"""
    return StockData(
        symbol="9999.T",
        name="理想エントリー株",
        sector="Industrials",
        current_price=2000,
        market_cap=500_000_000_000,
        annual_dividend_per_share=100,
        dividend_yield=5.0,  # 高配当
        historical_dividend_yields=make_historical_yields(base=2.5, current=5.0),
        shareholder_benefit_value=3000,  # 優待あり
        min_shares_for_benefit=100,
        operating_incomes={
            "2021": 10_000_000_000,
            "2022": 11_500_000_000,  # +15%
            "2023": 13_200_000_000,  # +14.8%
            "2024": 15_000_000_000,  # +13.6%
        },
        eps_values={
            "2021": 150,
            "2022": 170,
            "2023": 195,
            "2024": 220,
        },
        sector_avg_op_growth=6.0,
        trailing_pe=9.1,  # 低PER（株価下落で）
        forward_pe=8.0,
        historical_pes=make_historical_pes(base=18.0, current_price=2000, eps=220),
        price_history=make_price_history(current_price=2000, low_price=1600),
    )


def create_growth_no_value_stock() -> StockData:
    """成長はしているが株価がまだ高い（エントリーまだ）"""
    return StockData(
        symbol="8888.T",
        name="高成長だけど割高株",
        sector="Technology",
        current_price=5000,
        market_cap=1_000_000_000_000,
        annual_dividend_per_share=50,
        dividend_yield=1.0,  # 低配当
        historical_dividend_yields=make_historical_yields(base=1.0, current=1.0),
        shareholder_benefit_value=0,
        min_shares_for_benefit=100,
        operating_incomes={
            "2021": 20_000_000_000,
            "2022": 24_000_000_000,  # +20%
            "2023": 30_000_000_000,  # +25%
            "2024": 37_000_000_000,  # +23.3%
        },
        eps_values={
            "2021": 200,
            "2022": 240,
            "2023": 300,
            "2024": 370,
        },
        sector_avg_op_growth=12.0,
        trailing_pe=25.0,  # 高PER
        forward_pe=20.0,
        historical_pes=make_historical_pes(base=25.0, current_price=5000, eps=200),
        price_history=make_price_history(current_price=5000, low_price=4500),
    )


def create_high_yield_no_growth_stock() -> StockData:
    """高配当だが成長なし（バリュートラップ）"""
    return StockData(
        symbol="7777.T",
        name="高配当だけど成長ゼロ",
        sector="Utilities",
        current_price=1500,
        market_cap=200_000_000_000,
        annual_dividend_per_share=75,
        dividend_yield=5.0,
        historical_dividend_yields=make_historical_yields(base=3.5, current=5.0),
        shareholder_benefit_value=2000,
        min_shares_for_benefit=100,
        operating_incomes={
            "2021": 5_000_000_000,
            "2022": 5_100_000_000,  # +2%
            "2023": 4_900_000_000,  # -3.9%
            "2024": 5_000_000_000,  # +2%
        },
        eps_values={
            "2021": 100,
            "2022": 102,
            "2023": 98,
            "2024": 100,
        },
        sector_avg_op_growth=3.0,
        trailing_pe=15.0,
        forward_pe=14.5,
        historical_pes=make_historical_pes(base=16.0, current_price=1500, eps=100),
        price_history=make_declining_price_history(current_price=1500),
    )


def create_declining_stock() -> StockData:
    """業績悪化中（全条件NG）"""
    return StockData(
        symbol="6666.T",
        name="業績悪化株",
        sector="Consumer Cyclical",
        current_price=800,
        market_cap=50_000_000_000,
        annual_dividend_per_share=10,
        dividend_yield=1.25,
        historical_dividend_yields=make_historical_yields(base=2.0, current=1.25),
        shareholder_benefit_value=0,
        min_shares_for_benefit=100,
        operating_incomes={
            "2021": 8_000_000_000,
            "2022": 6_000_000_000,  # -25%
            "2023": 4_000_000_000,  # -33%
            "2024": 3_000_000_000,  # -25%
        },
        eps_values={
            "2021": 80,
            "2022": 50,
            "2023": 30,
            "2024": 15,
        },
        sector_avg_op_growth=7.0,
        trailing_pe=53.3,
        forward_pe=40.0,
        historical_pes=make_historical_pes(base=15.0, current_price=800, eps=15),
        price_history=make_declining_price_history(current_price=800),
    )


def create_eps_divergence_stock() -> StockData:
    """営業利益は成長だがEPSは乖離（特別損失等）"""
    return StockData(
        symbol="5555.T",
        name="EPS乖離警告株",
        sector="Industrials",
        current_price=3000,
        market_cap=300_000_000_000,
        annual_dividend_per_share=120,
        dividend_yield=4.0,
        historical_dividend_yields=make_historical_yields(base=2.5, current=4.0),
        shareholder_benefit_value=5000,
        min_shares_for_benefit=100,
        operating_incomes={
            "2021": 10_000_000_000,
            "2022": 12_000_000_000,  # +20%
            "2023": 14_400_000_000,  # +20%
            "2024": 17_000_000_000,  # +18%
        },
        eps_values={
            "2021": 150,
            "2022": 80,  # 特別損失でEPS大幅減
            "2023": 90,
            "2024": 85,
        },
        sector_avg_op_growth=6.0,
        trailing_pe=23.1,
        forward_pe=18.0,
        historical_pes=make_historical_pes(base=20.0, current_price=3000, eps=130),
        price_history=make_price_history(current_price=3000, low_price=2400),
    )


# ============================================================
# テスト実行
# ============================================================

def test_rule1():
    """ルール①のテスト: 総合利回り"""
    print("\n" + "="*60)
    print("テスト: ルール① 総合利回り（配当＋優待）")
    print("="*60)

    rules = ScreeningRules()
    test_cases = [
        ("全条件クリア株", create_entry_zone_stock(), True),
        ("高成長だけど割高株", create_growth_no_value_stock(), False),
        ("高配当成長なし株", create_high_yield_no_growth_stock(), True),
        ("業績悪化株", create_declining_stock(), False),
    ]

    all_passed = True
    for label, data, expected in test_cases:
        result = check_rule1_yield(data, rules)
        status = "PASS" if result.passed == expected else "FAIL"
        if status == "FAIL":
            all_passed = False
        print(f"\n  [{status}] {label}")
        print(f"    結果: {'合格' if result.passed else '不合格'} (期待: {'合格' if expected else '不合格'})")
        print(f"    {result.detail}")

    return all_passed


def test_rule2():
    """ルール②のテスト: 営業利益成長 × PEG"""
    print("\n" + "="*60)
    print("テスト: ルール② 営業利益成長率 × 独自PEG")
    print("="*60)

    rules = ScreeningRules()
    test_cases = [
        ("全条件クリア株 (成長+低PER→低PEG)", create_entry_zone_stock(), True),
        ("高成長だけど割高株 (成長OK, PEG高い)", create_growth_no_value_stock(), False),
        ("高配当成長なし株 (成長率低い)", create_high_yield_no_growth_stock(), False),
        ("業績悪化株 (マイナス成長)", create_declining_stock(), False),
    ]

    all_passed = True
    for label, data, expected in test_cases:
        result = check_rule2_growth_peg(data, rules)
        status = "PASS" if result.passed == expected else "FAIL"
        if status == "FAIL":
            all_passed = False
        print(f"\n  [{status}] {label}")
        print(f"    結果: {'合格' if result.passed else '不合格'} (期待: {'合格' if expected else '不合格'})")
        print(f"    {result.detail}")
        for w in result.warnings:
            print(f"    ⚠️  {w}")

    # EPS乖離警告テスト
    print(f"\n  --- EPS乖離警告テスト ---")
    eps_data = create_eps_divergence_stock()
    result = check_rule2_growth_peg(eps_data, rules)
    has_warning = len(result.warnings) > 0
    status = "PASS" if has_warning else "FAIL"
    if not has_warning:
        all_passed = False
    print(f"  [{status}] EPS乖離検出: {'警告あり' if has_warning else '警告なし'}")
    for w in result.warnings:
        print(f"    ⚠️  {w}")

    return all_passed


def test_rule3():
    """ルール③のテスト: PER過去レンジ"""
    print("\n" + "="*60)
    print("テスト: ルール③ PER（過去5年下位25%）")
    print("="*60)

    rules = ScreeningRules()
    test_cases = [
        ("全条件クリア株 (低PER)", create_entry_zone_stock(), True),
        ("高成長だけど割高株 (高PER)", create_growth_no_value_stock(), False),
        ("業績悪化株 (異常PER)", create_declining_stock(), False),
    ]

    all_passed = True
    for label, data, expected in test_cases:
        result = check_rule3_per_range(data, rules)
        status = "PASS" if result.passed == expected else "FAIL"
        if status == "FAIL":
            all_passed = False
        print(f"\n  [{status}] {label}")
        print(f"    結果: {'合格' if result.passed else '不合格'} (期待: {'合格' if expected else '不合格'})")
        print(f"    {result.detail}")

    return all_passed


def test_full_screening():
    """統合スクリーニングテスト"""
    print("\n" + "="*60)
    print("テスト: 統合スクリーニング（全3ルール）")
    print("="*60)

    rules = ScreeningRules()
    stocks = [
        create_entry_zone_stock(),
        create_growth_no_value_stock(),
        create_high_yield_no_growth_stock(),
        create_declining_stock(),
        create_eps_divergence_stock(),
    ]

    results = []
    all_passed = True

    for data in stocks:
        result = screen_stock(data, rules)
        results.append(result)

    # エントリーゾーン判定の検証
    expected_entry = {"9999.T"}  # 全条件クリア株のみ
    actual_entry = {r.symbol for r in results if r.is_entry_zone}

    if actual_entry == expected_entry:
        print(f"\n  [PASS] エントリーゾーン判定: {actual_entry}")
    else:
        print(f"\n  [FAIL] エントリーゾーン判定")
        print(f"    期待: {expected_entry}")
        print(f"    実際: {actual_entry}")
        all_passed = False

    # 全結果レポート出力
    print_screening_report(results)

    return all_passed


def test_parameter_sensitivity():
    """パラメータ感度テスト: しきい値を変えた時の挙動"""
    print("\n" + "="*60)
    print("テスト: パラメータ感度分析")
    print("="*60)

    data = create_entry_zone_stock()

    param_sets = [
        ("デフォルト", ScreeningRules()),
        ("厳格（PEG<0.5, 利回り上位5%）", ScreeningRules(
            peg_threshold=0.5,
            yield_top_percentile=5.0,
        )),
        ("緩和（PEG<1.0, 利回り上位20%, PER下位40%）", ScreeningRules(
            peg_threshold=1.0,
            yield_top_percentile=20.0,
            per_bottom_percentile=40.0,
        )),
        ("成長重視（PEG<0.5, 最低3期平均）", ScreeningRules(
            peg_threshold=0.5,
            op_growth_periods=3,
        )),
    ]

    for label, rules in param_sets:
        result = screen_stock(data, rules)
        marks = " ".join(["✅" if r.passed else "❌" for r in result.rules])
        entry = "★ENTRY" if result.is_entry_zone else ""
        print(f"\n  {label}")
        print(f"    {marks} → {result.rules_passed}/{result.rules_total} {entry}")
        for r in result.rules:
            print(f"      {'✅' if r.passed else '❌'} {r.rule_name}: {r.current_value}")


def run_live_screening():
    """yfinanceからリアルデータでスクリーニング"""
    from screener_config import SCREENING_WATCHLIST

    print("\n" + "="*60)
    print("ライブスクリーニング（yfinance）")
    print("="*60 + "\n")

    rules = ScreeningRules()
    results = screen_stocks(SCREENING_WATCHLIST, rules)
    print_screening_report(results)


def main():
    parser = argparse.ArgumentParser(description="スクリーニングルールのテスト")
    parser.add_argument("--live", action="store_true", help="yfinanceから実データでスクリーニング")
    args = parser.parse_args()

    if args.live:
        run_live_screening()
        return

    print("\n" + "#"*60)
    print("  株式スクリーニングルール テスト")
    print("#"*60)

    results = {
        "ルール①": test_rule1(),
        "ルール②": test_rule2(),
        "ルール③": test_rule3(),
        "統合": test_full_screening(),
    }

    test_parameter_sensitivity()

    print("\n\n" + "="*60)
    print("  テスト結果サマリー")
    print("="*60)
    all_ok = True
    for name, passed in results.items():
        status = "PASS" if passed else "FAIL"
        if not passed:
            all_ok = False
        print(f"  [{status}] {name}")

    if all_ok:
        print(f"\n  全テスト合格 ✅")
    else:
        print(f"\n  一部テスト失敗 ❌")
        sys.exit(1)


if __name__ == "__main__":
    main()
