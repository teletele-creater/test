#!/usr/bin/env python3
"""
スクリーニングルールのバックテストエンジン

「このルールで検知した時に買っていたら儲かるか？」を検証する。

リアルな市場パターンをシミュレートして:
  1. 過去の各月でスクリーニングを実行
  2. エントリーシグナルが出た時に買い
  3. 一定期間後のリターンを計測
  4. パラメータを変えて最適値を探索

使い方:
    python backtest_screener.py                # デフォルトで実行
    python backtest_screener.py --optimize     # パラメータ最適化
"""

import argparse
import itertools
import sys
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np
import pandas as pd

from screener_config import (
    DEFAULT_SECTOR_GROWTH_RATE,
    SCREENING_WATCHLIST,
    SECTOR_BENCHMARKS,
    SHAREHOLDER_BENEFITS,
    ScreeningRules,
)
from stock_screener import (
    StockData,
    check_rule1_yield,
    check_rule2_growth_peg,
    check_rule3_per_range,
    screen_stock,
)

np.random.seed(42)


# ============================================================
# リアルな市場データシミュレーション
# ============================================================

@dataclass
class SimulatedStock:
    """シミュレート銘柄の定義"""
    symbol: str
    name: str
    sector: str
    # 基本パラメータ
    base_price: float          # 基準株価
    base_eps: float            # 基準EPS
    annual_dividend: float     # 年間配当
    benefit_value: float       # 優待年間価値(円)
    min_shares: int            # 最低株数
    # 成長パラメータ
    op_income_base: float      # 営業利益ベース
    op_growth_annual: float    # 年間営業利益成長率(%)
    eps_growth_annual: float   # 年間EPS成長率(%)
    # 株価の振る舞い
    price_trend: str           # "up", "flat", "down", "volatile", "crash_recover"
    fair_pe: float             # 適正PER


# 20銘柄: 多様なパターンでルールの有効性を検証
SIMULATED_STOCKS = [
    # ===== 理想エントリー群（成長×株価下落→回復）=====
    # ルールが拾うべきパターン。買ったら儲かるはず。
    SimulatedStock(
        symbol="IDEAL_A", name="JT型（高配当+優待+成長）", sector="Consumer Defensive",
        base_price=3000, base_eps=200, annual_dividend=150, benefit_value=4500,
        min_shares=100, op_income_base=15e9, op_growth_annual=10.0,
        eps_growth_annual=9.0, price_trend="crash_recover", fair_pe=13.0,
    ),
    SimulatedStock(
        symbol="IDEAL_B", name="KDDI型（安定成長+優待）", sector="Communication Services",
        base_price=4500, base_eps=300, annual_dividend=140, benefit_value=3000,
        min_shares=100, op_income_base=20e9, op_growth_annual=8.0,
        eps_growth_annual=7.0, price_trend="crash_recover", fair_pe=15.0,
    ),
    SimulatedStock(
        symbol="IDEAL_C", name="三菱商事型（高配当+資源成長）", sector="Industrials",
        base_price=2500, base_eps=250, annual_dividend=180, benefit_value=0,
        min_shares=100, op_income_base=25e9, op_growth_annual=14.0,
        eps_growth_annual=12.0, price_trend="crash_recover", fair_pe=10.0,
    ),
    SimulatedStock(
        symbol="IDEAL_D", name="東京海上型（保険成長+高配当）", sector="Financial Services",
        base_price=3500, base_eps=350, annual_dividend=150, benefit_value=0,
        min_shares=100, op_income_base=18e9, op_growth_annual=12.0,
        eps_growth_annual=11.0, price_trend="crash_recover", fair_pe=10.0,
    ),
    SimulatedStock(
        symbol="IDEAL_E", name="花王型（優待+じわ成長）", sector="Consumer Defensive",
        base_price=5000, base_eps=250, annual_dividend=150, benefit_value=5000,
        min_shares=100, op_income_base=12e9, op_growth_annual=7.0,
        eps_growth_annual=6.0, price_trend="crash_recover", fair_pe=20.0,
    ),

    # ===== バリュートラップ群（高配当だけど成長なし/悪化）=====
    # ルールが弾くべきパターン。買ったら損するやつ。
    SimulatedStock(
        symbol="TRAP_A", name="衰退高配当（電力型）", sector="Utilities",
        base_price=1800, base_eps=120, annual_dividend=90, benefit_value=2000,
        min_shares=100, op_income_base=8e9, op_growth_annual=1.0,
        eps_growth_annual=0.5, price_trend="down", fair_pe=15.0,
    ),
    SimulatedStock(
        symbol="TRAP_B", name="減配リスク型", sector="Energy",
        base_price=2000, base_eps=100, annual_dividend=80, benefit_value=0,
        min_shares=100, op_income_base=10e9, op_growth_annual=-5.0,
        eps_growth_annual=-8.0, price_trend="down", fair_pe=12.0,
    ),
    SimulatedStock(
        symbol="TRAP_C", name="優待廃止リスク型", sector="Consumer Cyclical",
        base_price=1500, base_eps=80, annual_dividend=30, benefit_value=3000,
        min_shares=100, op_income_base=5e9, op_growth_annual=-3.0,
        eps_growth_annual=-5.0, price_trend="down", fair_pe=15.0,
    ),

    # ===== 高成長割高群（成長はいいが常にPER高い）=====
    # ルールが拾わないはず（PER条件で弾く）
    SimulatedStock(
        symbol="GROWTH_A", name="テック高成長型", sector="Technology",
        base_price=8000, base_eps=200, annual_dividend=40, benefit_value=0,
        min_shares=100, op_income_base=20e9, op_growth_annual=20.0,
        eps_growth_annual=18.0, price_trend="up", fair_pe=35.0,
    ),
    SimulatedStock(
        symbol="GROWTH_B", name="SaaS型高成長", sector="Technology",
        base_price=12000, base_eps=300, annual_dividend=0, benefit_value=0,
        min_shares=100, op_income_base=8e9, op_growth_annual=25.0,
        eps_growth_annual=22.0, price_trend="up", fair_pe=40.0,
    ),

    # ===== 景気循環群（上下動大きい）=====
    SimulatedStock(
        symbol="CYCL_A", name="素材循環型", sector="Basic Materials",
        base_price=2000, base_eps=150, annual_dividend=60, benefit_value=0,
        min_shares=100, op_income_base=12e9, op_growth_annual=5.0,
        eps_growth_annual=4.0, price_trend="volatile", fair_pe=14.0,
    ),
    SimulatedStock(
        symbol="CYCL_B", name="自動車循環型", sector="Consumer Cyclical",
        base_price=3000, base_eps=200, annual_dividend=100, benefit_value=0,
        min_shares=100, op_income_base=30e9, op_growth_annual=7.0,
        eps_growth_annual=6.0, price_trend="volatile", fair_pe=12.0,
    ),

    # ===== 業績悪化群 =====
    SimulatedStock(
        symbol="DECL_A", name="構造的衰退型", sector="Consumer Cyclical",
        base_price=2500, base_eps=180, annual_dividend=50, benefit_value=0,
        min_shares=100, op_income_base=18e9, op_growth_annual=-10.0,
        eps_growth_annual=-12.0, price_trend="down", fair_pe=12.0,
    ),
    SimulatedStock(
        symbol="DECL_B", name="業界再編負け組型", sector="Real Estate",
        base_price=1200, base_eps=60, annual_dividend=30, benefit_value=0,
        min_shares=100, op_income_base=4e9, op_growth_annual=-8.0,
        eps_growth_annual=-10.0, price_trend="down", fair_pe=15.0,
    ),

    # ===== 安定配当群（配当は出すが大きな成長もない）=====
    SimulatedStock(
        symbol="STABLE_A", name="NTT型（安定+dポイント）", sector="Communication Services",
        base_price=4000, base_eps=250, annual_dividend=130, benefit_value=1500,
        min_shares=100, op_income_base=25e9, op_growth_annual=5.0,
        eps_growth_annual=4.5, price_trend="flat", fair_pe=16.0,
    ),
    SimulatedStock(
        symbol="STABLE_B", name="食品安定型", sector="Consumer Defensive",
        base_price=3000, base_eps=150, annual_dividend=60, benefit_value=3000,
        min_shares=100, op_income_base=8e9, op_growth_annual=3.5,
        eps_growth_annual=3.0, price_trend="flat", fair_pe=20.0,
    ),

    # ===== V字回復群（下落→急回復）=====
    SimulatedStock(
        symbol="RECOVER_A", name="コロナ回復型", sector="Industrials",
        base_price=3500, base_eps=220, annual_dividend=100, benefit_value=0,
        min_shares=100, op_income_base=20e9, op_growth_annual=15.0,
        eps_growth_annual=13.0, price_trend="crash_recover", fair_pe=16.0,
    ),
    SimulatedStock(
        symbol="RECOVER_B", name="外食回復型", sector="Consumer Cyclical",
        base_price=2800, base_eps=180, annual_dividend=70, benefit_value=6000,
        min_shares=100, op_income_base=8e9, op_growth_annual=12.0,
        eps_growth_annual=10.0, price_trend="crash_recover", fair_pe=15.0,
    ),

    # ===== 米国高配当型 =====
    SimulatedStock(
        symbol="US_DIV_A", name="JNJ型（連続増配）", sector="Healthcare",
        base_price=150, base_eps=10, annual_dividend=5, benefit_value=0,
        min_shares=100, op_income_base=25e9, op_growth_annual=6.0,
        eps_growth_annual=5.0, price_trend="crash_recover", fair_pe=16.0,
    ),
    SimulatedStock(
        symbol="US_DIV_B", name="MO型（超高配当）", sector="Consumer Defensive",
        base_price=45, base_eps=5, annual_dividend=4, benefit_value=0,
        min_shares=100, op_income_base=12e9, op_growth_annual=4.0,
        eps_growth_annual=3.0, price_trend="volatile", fair_pe=10.0,
    ),
]


# ============================================================
# 1489 ETF 構成銘柄シミュレーション（48銘柄）
# 実際の業種・配当水準・成長率を反映したパラメータ
# ============================================================

def _ben(sym: str) -> float:
    """SHAREHOLDER_BENEFITSから優待額を取得"""
    return SHAREHOLDER_BENEFITS.get(sym, {}).get("value_yen", 0)

SIMULATED_1489_STOCKS = [
    # === 鉱業・エネルギー ===
    SimulatedStock("1605.T", "INPEX", "Energy",
                   base_price=2200, base_eps=200, annual_dividend=86, benefit_value=_ben("1605.T"),
                   min_shares=100, op_income_base=500e9, op_growth_annual=8.0,
                   eps_growth_annual=7.0, price_trend="volatile", fair_pe=10.0),
    SimulatedStock("5020.T", "ENEOS HD", "Energy",
                   base_price=800, base_eps=60, annual_dividend=26, benefit_value=_ben("5020.T"),
                   min_shares=100, op_income_base=350e9, op_growth_annual=5.0,
                   eps_growth_annual=4.0, price_trend="volatile", fair_pe=12.0),
    SimulatedStock("5019.T", "出光興産", "Energy",
                   base_price=1100, base_eps=110, annual_dividend=40, benefit_value=_ben("5019.T"),
                   min_shares=100, op_income_base=250e9, op_growth_annual=4.0,
                   eps_growth_annual=3.0, price_trend="volatile", fair_pe=10.0),

    # === 建設 ===
    SimulatedStock("1928.T", "積水ハウス", "Real Estate",
                   base_price=3400, base_eps=230, annual_dividend=123, benefit_value=_ben("1928.T"),
                   min_shares=100, op_income_base=200e9, op_growth_annual=7.0,
                   eps_growth_annual=6.0, price_trend="crash_recover", fair_pe=13.0),
    SimulatedStock("1812.T", "鹿島建設", "Industrials",
                   base_price=2800, base_eps=260, annual_dividend=100, benefit_value=_ben("1812.T"),
                   min_shares=100, op_income_base=150e9, op_growth_annual=8.0,
                   eps_growth_annual=7.0, price_trend="crash_recover", fair_pe=11.0),
    SimulatedStock("1801.T", "大成建設", "Industrials",
                   base_price=5500, base_eps=350, annual_dividend=150, benefit_value=_ben("1801.T"),
                   min_shares=100, op_income_base=100e9, op_growth_annual=6.0,
                   eps_growth_annual=5.0, price_trend="crash_recover", fair_pe=14.0),

    # === 食品 ===
    SimulatedStock("2914.T", "JT", "Consumer Defensive",
                   base_price=4200, base_eps=250, annual_dividend=194, benefit_value=_ben("2914.T"),
                   min_shares=100, op_income_base=600e9, op_growth_annual=6.0,
                   eps_growth_annual=5.0, price_trend="crash_recover", fair_pe=15.0),

    # === 紙・パルプ ===
    SimulatedStock("3861.T", "王子HD", "Basic Materials",
                   base_price=600, base_eps=40, annual_dividend=22, benefit_value=_ben("3861.T"),
                   min_shares=100, op_income_base=80e9, op_growth_annual=5.0,
                   eps_growth_annual=4.0, price_trend="volatile", fair_pe=14.0),

    # === 化学 ===
    SimulatedStock("4188.T", "三菱ケミカルG", "Basic Materials",
                   base_price=900, base_eps=60, annual_dividend=32, benefit_value=_ben("4188.T"),
                   min_shares=100, op_income_base=200e9, op_growth_annual=6.0,
                   eps_growth_annual=5.0, price_trend="volatile", fair_pe=14.0),
    SimulatedStock("4183.T", "三井化学", "Basic Materials",
                   base_price=3800, base_eps=300, annual_dividend=130, benefit_value=_ben("4183.T"),
                   min_shares=100, op_income_base=150e9, op_growth_annual=7.0,
                   eps_growth_annual=6.0, price_trend="crash_recover", fair_pe=12.0),
    SimulatedStock("3407.T", "旭化成", "Basic Materials",
                   base_price=1100, base_eps=70, annual_dividend=36, benefit_value=_ben("3407.T"),
                   min_shares=100, op_income_base=180e9, op_growth_annual=4.0,
                   eps_growth_annual=3.0, price_trend="volatile", fair_pe=14.0),

    # === 医薬品 ===
    SimulatedStock("4502.T", "武田薬品", "Healthcare",
                   base_price=4200, base_eps=230, annual_dividend=188, benefit_value=_ben("4502.T"),
                   min_shares=100, op_income_base=500e9, op_growth_annual=7.0,
                   eps_growth_annual=6.0, price_trend="crash_recover", fair_pe=16.0),
    SimulatedStock("4503.T", "アステラス製薬", "Healthcare",
                   base_price=1600, base_eps=80, annual_dividend=70, benefit_value=_ben("4503.T"),
                   min_shares=100, op_income_base=200e9, op_growth_annual=5.0,
                   eps_growth_annual=4.0, price_trend="crash_recover", fair_pe=18.0),

    # === ゴム ===
    SimulatedStock("5108.T", "ブリヂストン", "Consumer Cyclical",
                   base_price=5800, base_eps=400, annual_dividend=200, benefit_value=_ben("5108.T"),
                   min_shares=100, op_income_base=450e9, op_growth_annual=6.0,
                   eps_growth_annual=5.0, price_trend="crash_recover", fair_pe=13.0),

    # === ガラス ===
    SimulatedStock("5201.T", "AGC", "Basic Materials",
                   base_price=5000, base_eps=350, annual_dividend=210, benefit_value=_ben("5201.T"),
                   min_shares=100, op_income_base=150e9, op_growth_annual=5.0,
                   eps_growth_annual=4.0, price_trend="volatile", fair_pe=13.0),

    # === 鉄鋼 ===
    SimulatedStock("5401.T", "日本製鉄", "Basic Materials",
                   base_price=3400, base_eps=400, annual_dividend=160, benefit_value=_ben("5401.T"),
                   min_shares=100, op_income_base=500e9, op_growth_annual=8.0,
                   eps_growth_annual=6.0, price_trend="volatile", fair_pe=8.0),
    SimulatedStock("5406.T", "神戸製鋼", "Basic Materials",
                   base_price=1800, base_eps=200, annual_dividend=70, benefit_value=_ben("5406.T"),
                   min_shares=100, op_income_base=120e9, op_growth_annual=7.0,
                   eps_growth_annual=5.0, price_trend="volatile", fair_pe=8.0),
    SimulatedStock("5411.T", "JFE HD", "Basic Materials",
                   base_price=2100, base_eps=250, annual_dividend=100, benefit_value=_ben("5411.T"),
                   min_shares=100, op_income_base=200e9, op_growth_annual=6.0,
                   eps_growth_annual=4.0, price_trend="volatile", fair_pe=8.0),

    # === 非鉄金属 ===
    SimulatedStock("5713.T", "住友金属鉱山", "Basic Materials",
                   base_price=4000, base_eps=250, annual_dividend=100, benefit_value=_ben("5713.T"),
                   min_shares=100, op_income_base=100e9, op_growth_annual=5.0,
                   eps_growth_annual=4.0, price_trend="volatile", fair_pe=15.0),

    # === 機械 ===
    SimulatedStock("6301.T", "コマツ", "Industrials",
                   base_price=4500, base_eps=300, annual_dividend=144, benefit_value=_ben("6301.T"),
                   min_shares=100, op_income_base=400e9, op_growth_annual=8.0,
                   eps_growth_annual=7.0, price_trend="crash_recover", fair_pe=14.0),
    SimulatedStock("6305.T", "日立建機", "Industrials",
                   base_price=3800, base_eps=300, annual_dividend=130, benefit_value=_ben("6305.T"),
                   min_shares=100, op_income_base=100e9, op_growth_annual=9.0,
                   eps_growth_annual=8.0, price_trend="crash_recover", fair_pe=12.0),
    SimulatedStock("6471.T", "日本精工", "Industrials",
                   base_price=800, base_eps=60, annual_dividend=30, benefit_value=_ben("6471.T"),
                   min_shares=100, op_income_base=60e9, op_growth_annual=6.0,
                   eps_growth_annual=5.0, price_trend="volatile", fair_pe=13.0),
    SimulatedStock("6472.T", "NTN", "Industrials",
                   base_price=300, base_eps=20, annual_dividend=12, benefit_value=_ben("6472.T"),
                   min_shares=100, op_income_base=30e9, op_growth_annual=8.0,
                   eps_growth_annual=6.0, price_trend="volatile", fair_pe=14.0),
    SimulatedStock("6473.T", "ジェイテクト", "Industrials",
                   base_price=1200, base_eps=100, annual_dividend=46, benefit_value=_ben("6473.T"),
                   min_shares=100, op_income_base=50e9, op_growth_annual=7.0,
                   eps_growth_annual=6.0, price_trend="crash_recover", fair_pe=12.0),

    # === 電気機器 ===
    SimulatedStock("7751.T", "キヤノン", "Technology",
                   base_price=5000, base_eps=300, annual_dividend=150, benefit_value=_ben("7751.T"),
                   min_shares=100, op_income_base=300e9, op_growth_annual=6.0,
                   eps_growth_annual=5.0, price_trend="crash_recover", fair_pe=16.0),

    # === 輸送用機器 ===
    SimulatedStock("7202.T", "いすゞ自動車", "Consumer Cyclical",
                   base_price=2000, base_eps=180, annual_dividend=86, benefit_value=_ben("7202.T"),
                   min_shares=100, op_income_base=250e9, op_growth_annual=7.0,
                   eps_growth_annual=6.0, price_trend="crash_recover", fair_pe=10.0),
    SimulatedStock("7261.T", "マツダ", "Consumer Cyclical",
                   base_price=1200, base_eps=130, annual_dividend=55, benefit_value=_ben("7261.T"),
                   min_shares=100, op_income_base=120e9, op_growth_annual=6.0,
                   eps_growth_annual=5.0, price_trend="volatile", fair_pe=8.0),
    SimulatedStock("7267.T", "本田技研", "Consumer Cyclical",
                   base_price=1600, base_eps=150, annual_dividend=68, benefit_value=_ben("7267.T"),
                   min_shares=100, op_income_base=800e9, op_growth_annual=7.0,
                   eps_growth_annual=6.0, price_trend="crash_recover", fair_pe=10.0),
    SimulatedStock("7272.T", "ヤマハ発動機", "Consumer Cyclical",
                   base_price=1400, base_eps=120, annual_dividend=50, benefit_value=_ben("7272.T"),
                   min_shares=100, op_income_base=150e9, op_growth_annual=8.0,
                   eps_growth_annual=7.0, price_trend="crash_recover", fair_pe=11.0),

    # === サービス ===
    SimulatedStock("4324.T", "電通グループ", "Communication Services",
                   base_price=4000, base_eps=200, annual_dividend=139, benefit_value=_ben("4324.T"),
                   min_shares=100, op_income_base=100e9, op_growth_annual=5.0,
                   eps_growth_annual=4.0, price_trend="volatile", fair_pe=18.0),

    # === 卸売（商社） ===
    SimulatedStock("8001.T", "伊藤忠商事", "Industrials",
                   base_price=7000, base_eps=500, annual_dividend=200, benefit_value=_ben("8001.T"),
                   min_shares=100, op_income_base=500e9, op_growth_annual=10.0,
                   eps_growth_annual=9.0, price_trend="crash_recover", fair_pe=12.0),
    SimulatedStock("8002.T", "丸紅", "Industrials",
                   base_price=2500, base_eps=250, annual_dividend=85, benefit_value=_ben("8002.T"),
                   min_shares=100, op_income_base=300e9, op_growth_annual=10.0,
                   eps_growth_annual=8.0, price_trend="crash_recover", fair_pe=9.0),
    SimulatedStock("8015.T", "豊田通商", "Industrials",
                   base_price=8500, base_eps=600, annual_dividend=280, benefit_value=_ben("8015.T"),
                   min_shares=100, op_income_base=200e9, op_growth_annual=9.0,
                   eps_growth_annual=8.0, price_trend="crash_recover", fair_pe=12.0),
    SimulatedStock("8053.T", "住友商事", "Industrials",
                   base_price=3500, base_eps=300, annual_dividend=130, benefit_value=_ben("8053.T"),
                   min_shares=100, op_income_base=350e9, op_growth_annual=9.0,
                   eps_growth_annual=8.0, price_trend="crash_recover", fair_pe=10.0),
    SimulatedStock("8058.T", "三菱商事", "Industrials",
                   base_price=2600, base_eps=270, annual_dividend=100, benefit_value=_ben("8058.T"),
                   min_shares=100, op_income_base=700e9, op_growth_annual=11.0,
                   eps_growth_annual=9.0, price_trend="crash_recover", fair_pe=10.0),

    # === 銀行 ===
    SimulatedStock("8304.T", "あおぞら銀行", "Financial Services",
                   base_price=2500, base_eps=200, annual_dividend=100, benefit_value=_ben("8304.T"),
                   min_shares=100, op_income_base=40e9, op_growth_annual=4.0,
                   eps_growth_annual=3.0, price_trend="volatile", fair_pe=12.0),
    SimulatedStock("8308.T", "りそなHD", "Financial Services",
                   base_price=1100, base_eps=80, annual_dividend=25, benefit_value=_ben("8308.T"),
                   min_shares=100, op_income_base=250e9, op_growth_annual=6.0,
                   eps_growth_annual=5.0, price_trend="crash_recover", fair_pe=12.0),
    SimulatedStock("8309.T", "三井住友トラストHD", "Financial Services",
                   base_price=3500, base_eps=300, annual_dividend=130, benefit_value=_ben("8309.T"),
                   min_shares=100, op_income_base=150e9, op_growth_annual=7.0,
                   eps_growth_annual=6.0, price_trend="crash_recover", fair_pe=11.0),
    SimulatedStock("8316.T", "三井住友FG", "Financial Services",
                   base_price=8500, base_eps=800, annual_dividend=330, benefit_value=_ben("8316.T"),
                   min_shares=100, op_income_base=1200e9, op_growth_annual=8.0,
                   eps_growth_annual=7.0, price_trend="crash_recover", fair_pe=11.0),
    SimulatedStock("8411.T", "みずほFG", "Financial Services",
                   base_price=2800, base_eps=250, annual_dividend=105, benefit_value=_ben("8411.T"),
                   min_shares=100, op_income_base=800e9, op_growth_annual=7.0,
                   eps_growth_annual=6.0, price_trend="crash_recover", fair_pe=11.0),

    # === 証券 ===
    SimulatedStock("8473.T", "SBI HD", "Financial Services",
                   base_price=3700, base_eps=300, annual_dividend=160, benefit_value=_ben("8473.T"),
                   min_shares=100, op_income_base=200e9, op_growth_annual=10.0,
                   eps_growth_annual=9.0, price_trend="volatile", fair_pe=12.0),
    SimulatedStock("8601.T", "大和証券G", "Financial Services",
                   base_price=1100, base_eps=80, annual_dividend=40, benefit_value=_ben("8601.T"),
                   min_shares=100, op_income_base=120e9, op_growth_annual=7.0,
                   eps_growth_annual=6.0, price_trend="volatile", fair_pe=13.0),
    SimulatedStock("8604.T", "野村HD", "Financial Services",
                   base_price=900, base_eps=60, annual_dividend=25, benefit_value=_ben("8604.T"),
                   min_shares=100, op_income_base=150e9, op_growth_annual=8.0,
                   eps_growth_annual=7.0, price_trend="volatile", fair_pe=14.0),

    # === 保険 ===
    SimulatedStock("8725.T", "MS&AD", "Financial Services",
                   base_price=6000, base_eps=500, annual_dividend=250, benefit_value=_ben("8725.T"),
                   min_shares=100, op_income_base=300e9, op_growth_annual=9.0,
                   eps_growth_annual=8.0, price_trend="crash_recover", fair_pe=12.0),

    # === 海運 ===
    SimulatedStock("9101.T", "日本郵船", "Industrials",
                   base_price=5000, base_eps=700, annual_dividend=260, benefit_value=_ben("9101.T"),
                   min_shares=100, op_income_base=200e9, op_growth_annual=5.0,
                   eps_growth_annual=3.0, price_trend="volatile", fair_pe=7.0),
    SimulatedStock("9107.T", "川崎汽船", "Industrials",
                   base_price=2200, base_eps=350, annual_dividend=120, benefit_value=_ben("9107.T"),
                   min_shares=100, op_income_base=100e9, op_growth_annual=5.0,
                   eps_growth_annual=3.0, price_trend="volatile", fair_pe=6.0),

    # === 通信 ===
    SimulatedStock("9433.T", "KDDI", "Communication Services",
                   base_price=4800, base_eps=310, annual_dividend=145, benefit_value=_ben("9433.T"),
                   min_shares=100, op_income_base=1100e9, op_growth_annual=6.0,
                   eps_growth_annual=5.0, price_trend="crash_recover", fair_pe=15.0),
    SimulatedStock("9434.T", "ソフトバンク", "Communication Services",
                   base_price=1900, base_eps=100, annual_dividend=86, benefit_value=_ben("9434.T"),
                   min_shares=100, op_income_base=900e9, op_growth_annual=5.0,
                   eps_growth_annual=4.0, price_trend="flat", fair_pe=18.0),
]


def generate_monthly_prices(stock: SimulatedStock, months: int = 120) -> pd.DataFrame:
    """
    月次株価データを生成（10年分 = 120ヶ月）
    5年のルックバック + 5年の検証期間
    """
    dates = pd.date_range(end="2025-12-31", periods=months, freq="ME")
    n = len(dates)

    noise = np.random.normal(0, 0.04, n)  # 月次ボラティリティ4%

    if stock.price_trend == "up":
        trend = np.linspace(0, 0.8, n)
        prices = stock.base_price * (1 + trend + np.cumsum(noise * 0.5))

    elif stock.price_trend == "down":
        trend = np.linspace(0, -0.5, n)
        prices = stock.base_price * (1 + trend + np.cumsum(noise * 0.5))

    elif stock.price_trend == "flat":
        prices = stock.base_price * (1 + np.cumsum(noise * 0.3))

    elif stock.price_trend == "volatile":
        # 2回の大きなサイクル
        cycle = 0.30 * np.sin(np.linspace(0, 4 * np.pi, n))
        prices = stock.base_price * (1 + cycle + np.cumsum(noise * 0.3))

    elif stock.price_trend == "crash_recover":
        # 複数回の下落→回復サイクルを作る（よりリアル）
        trend = np.zeros(n)
        # 1回目: 月30-50で底（lookback確保後に検出可能）
        phase1_bottom = 80  # ~6.7年目で底
        phase1_start = 50
        # 下落フェーズ（月50→80で-40%下落）
        trend[phase1_start:phase1_bottom] = np.linspace(0, -0.40, phase1_bottom - phase1_start)
        # 回復フェーズ（月80→120で回復）
        trend[phase1_bottom:] = np.linspace(-0.40, 0.05, n - phase1_bottom)
        # 前半は小さな調整も入れる
        trend[:phase1_start] += 0.08 * np.sin(np.linspace(0, 2 * np.pi, phase1_start))
        prices = stock.base_price * (1 + trend + np.cumsum(noise * 0.3))

    else:
        prices = stock.base_price * (1 + np.cumsum(noise))

    prices = np.maximum(prices, stock.base_price * 0.15)  # 下限

    return pd.DataFrame({"price": prices}, index=dates)


def generate_financials(stock: SimulatedStock, years: int = 10) -> dict:
    """年度別の財務データを生成"""
    base_year = 2025 - years + 1
    op_incomes = {}
    eps_values = {}

    op = stock.op_income_base * (1 + stock.op_growth_annual / 100) ** (-years // 2)
    eps = stock.base_eps * (1 + stock.eps_growth_annual / 100) ** (-years // 2)

    for i in range(years):
        year = str(base_year + i)
        # 成長にノイズを加える
        op_noise = np.random.normal(1.0, 0.05)
        eps_noise = np.random.normal(1.0, 0.08)

        op *= (1 + stock.op_growth_annual / 100) * op_noise
        eps *= (1 + stock.eps_growth_annual / 100) * eps_noise

        op_incomes[year] = max(op, 0)
        eps_values[year] = max(eps, 1)

    return {"op_incomes": op_incomes, "eps_values": eps_values}


# ============================================================
# バックテストエンジン
# ============================================================

@dataclass
class Trade:
    """個別トレード"""
    symbol: str
    name: str
    entry_date: pd.Timestamp
    entry_price: float
    rules_passed: int
    rule_details: list[str]
    # 結果（後で埋める）
    exit_date: pd.Timestamp | None = None
    exit_price: float | None = None
    return_pct: float | None = None
    holding_months: int = 0
    dividend_return_pct: float = 0.0
    benefit_return_pct: float = 0.0
    total_return_pct: float | None = None


@dataclass
class BacktestResult:
    """バックテスト結果"""
    rules: ScreeningRules
    trades: list[Trade]
    # 集計
    total_trades: int = 0
    win_count: int = 0
    loss_count: int = 0
    win_rate: float = 0.0
    avg_return: float = 0.0
    avg_total_return: float = 0.0  # 配当+優待込み
    median_return: float = 0.0
    max_return: float = 0.0
    max_loss: float = 0.0
    avg_holding_months: float = 0.0
    # シグナル精度
    true_positive_rate: float = 0.0  # エントリー→実際にプラス
    sharpe_like: float = 0.0  # リターン/リスク

    def summary(self) -> str:
        lines = [
            f"{'='*65}",
            f"  バックテスト結果",
            f"{'='*65}",
            f"  パラメータ:",
            f"    PEG閾値: {self.rules.peg_threshold}",
            f"    利回り上位: {self.rules.yield_top_percentile}%",
            f"    PER下位: {self.rules.per_bottom_percentile}%",
            f"    最低ルール数: {self.rules.min_rules_passed}",
            f"{'─'*65}",
            f"  トレード数:     {self.total_trades}",
            f"  勝率:           {self.win_rate:.1f}% ({self.win_count}勝 {self.loss_count}敗)",
            f"  平均リターン:    {self.avg_return:+.2f}% (値上がりのみ)",
            f"  平均総合リターン: {self.avg_total_return:+.2f}% (配当+優待込み)",
            f"  中央値リターン:  {self.median_return:+.2f}%",
            f"  最大利益:       {self.max_return:+.2f}%",
            f"  最大損失:       {self.max_loss:+.2f}%",
            f"  平均保有期間:    {self.avg_holding_months:.1f}ヶ月",
            f"  シャープ的指標:  {self.sharpe_like:.3f}",
            f"{'='*65}",
        ]
        return "\n".join(lines)


def run_backtest(
    stocks: list[SimulatedStock],
    rules: ScreeningRules,
    holding_months: int = 12,
    lookback_months: int = 60,
) -> BacktestResult:
    """
    バックテストを実行

    各月で全銘柄をスクリーニング → シグナルが出たら買い →
    holding_months後に売って損益を記録
    """
    trades: list[Trade] = []

    for stock in stocks:
        # データ生成
        price_df = generate_monthly_prices(stock, months=120)
        financials = generate_financials(stock, years=10)
        prices = price_df["price"]

        sector_avg = SECTOR_BENCHMARKS.get(stock.sector, DEFAULT_SECTOR_GROWTH_RATE)

        # 各月でスクリーニング（lookback開始後から、売却できる期間まで）
        check_start = lookback_months
        check_end = len(prices) - holding_months

        for i in range(check_start, check_end):
            current_date = prices.index[i]
            current_price = prices.iloc[i]

            # この時点での過去利回り推移を構築
            hist_prices = prices.iloc[i - lookback_months:i + 1]
            if stock.annual_dividend > 0:
                hist_yields = (stock.annual_dividend / hist_prices * 100)
            else:
                hist_yields = pd.Series([0.0] * len(hist_prices), index=hist_prices.index)

            # この時点での過去PER推移
            # EPSはその時点の最新年度を使用
            year_idx = min(i // 12, len(financials["eps_values"]) - 1)
            eps_keys = sorted(financials["eps_values"].keys())
            current_eps = financials["eps_values"][eps_keys[min(year_idx, len(eps_keys) - 1)]]
            hist_pes = hist_prices / current_eps

            # 営業利益データ（この時点で利用可能な年度のみ）
            available_years = [y for y in sorted(financials["op_incomes"].keys())
                               if int(y) <= current_date.year]
            op_incomes = {y: financials["op_incomes"][y] for y in available_years[-5:]}
            eps_vals = {y: financials["eps_values"].get(y, current_eps) for y in available_years[-5:]}

            current_pe = current_price / current_eps if current_eps > 0 else 999
            div_yield = stock.annual_dividend / current_price * 100 if current_price > 0 else 0

            # StockData構築
            stock_data = StockData(
                symbol=stock.symbol,
                name=stock.name,
                sector=stock.sector,
                current_price=current_price,
                market_cap=current_price * 1_000_000,
                annual_dividend_per_share=stock.annual_dividend,
                dividend_yield=div_yield,
                historical_dividend_yields=hist_yields,
                shareholder_benefit_value=stock.benefit_value,
                min_shares_for_benefit=stock.min_shares,
                operating_incomes=op_incomes,
                eps_values=eps_vals,
                sector_avg_op_growth=sector_avg,
                trailing_pe=current_pe,
                forward_pe=None,
                historical_pes=hist_pes,
                price_history=prices.iloc[max(0, i - 12):i + 1],
            )

            result = screen_stock(stock_data, rules)

            if result.is_entry_zone:
                # エントリー！ → holding_months後の結果を記録
                exit_idx = i + holding_months
                exit_date = prices.index[exit_idx]
                exit_price = prices.iloc[exit_idx]
                price_return = (exit_price - current_price) / current_price * 100

                # 保有期間中の配当リターン
                div_return = (stock.annual_dividend * holding_months / 12) / current_price * 100

                # 優待リターン（年1回として按分）
                if stock.benefit_value > 0 and current_price > 0:
                    investment = current_price * stock.min_shares
                    ben_return = (stock.benefit_value * holding_months / 12) / investment * 100
                else:
                    ben_return = 0.0

                total_return = price_return + div_return + ben_return

                rule_details = []
                for r in result.rules:
                    mark = "OK" if r.passed else "NG"
                    rule_details.append(f"[{mark}] {r.rule_name}: {r.current_value}")

                trade = Trade(
                    symbol=stock.symbol,
                    name=stock.name,
                    entry_date=current_date,
                    entry_price=current_price,
                    rules_passed=result.rules_passed,
                    rule_details=rule_details,
                    exit_date=exit_date,
                    exit_price=exit_price,
                    return_pct=price_return,
                    holding_months=holding_months,
                    dividend_return_pct=div_return,
                    benefit_return_pct=ben_return,
                    total_return_pct=total_return,
                )
                trades.append(trade)

                # 同じ銘柄で連続シグナルは避ける（holding期間スキップ）
                # → 次のiをholding_months先に
                # （forループなのでbreakせず、チェックで制御）

    # 同一銘柄の重複エントリーを除去（保有中に再シグナルが出た場合）
    filtered_trades: list[Trade] = []
    last_exit: dict[str, pd.Timestamp] = {}
    for t in sorted(trades, key=lambda x: x.entry_date):
        if t.symbol in last_exit and t.entry_date < last_exit[t.symbol]:
            continue
        filtered_trades.append(t)
        if t.exit_date:
            last_exit[t.symbol] = t.exit_date

    trades = filtered_trades

    # 集計
    bt = BacktestResult(rules=rules, trades=trades)
    bt.total_trades = len(trades)

    if trades:
        returns = [t.total_return_pct for t in trades if t.total_return_pct is not None]
        price_returns = [t.return_pct for t in trades if t.return_pct is not None]

        bt.win_count = sum(1 for r in returns if r > 0)
        bt.loss_count = sum(1 for r in returns if r <= 0)
        bt.win_rate = bt.win_count / len(returns) * 100 if returns else 0
        bt.avg_return = np.mean(price_returns) if price_returns else 0
        bt.avg_total_return = np.mean(returns) if returns else 0
        bt.median_return = float(np.median(returns)) if returns else 0
        bt.max_return = max(returns) if returns else 0
        bt.max_loss = min(returns) if returns else 0
        bt.avg_holding_months = np.mean([t.holding_months for t in trades])

        std = np.std(returns) if len(returns) > 1 else 1.0
        bt.sharpe_like = bt.avg_total_return / std if std > 0 else 0
    return bt


# ============================================================
# パラメータ最適化
# ============================================================

@dataclass
class OptimizationResult:
    """最適化結果"""
    best_params: ScreeningRules
    best_score: float
    best_bt: BacktestResult | None
    all_results: list[tuple[dict, BacktestResult]]


def optimize_parameters(
    stocks: list[SimulatedStock],
    holding_months: int = 12,
) -> OptimizationResult:
    """グリッドサーチでパラメータを最適化"""

    param_grid = {
        "peg_threshold": [0.5, 0.75, 1.0, 1.2],
        "yield_top_percentile": [10.0, 15.0, 20.0, 30.0],
        "per_bottom_percentile": [20.0, 25.0, 30.0, 40.0],
        "min_rules_passed": [2, 3],
        "use_momentum_filter": [True, False],
        "momentum_rebound_pct": [3.0, 5.0, 8.0],
    }

    all_results: list[tuple[dict, BacktestResult]] = []
    best_score = -999
    best_params = None
    best_bt = None

    keys = list(param_grid.keys())
    values = list(param_grid.values())
    total = 1
    for v in values:
        total *= len(v)

    print(f"\n  パラメータ組み合わせ: {total}通り")
    print(f"  探索中...\n")

    for combo in itertools.product(*values):
        params = dict(zip(keys, combo))
        rules = ScreeningRules(**params)

        bt = run_backtest(stocks, rules, holding_months=holding_months)

        # スコア: 勝率×平均リターンの複合指標（トレード数が少なすぎるとペナルティ）
        if bt.total_trades < 3:
            score = -100
        else:
            trade_bonus = min(bt.total_trades / 10, 1.0)  # トレード数のボーナス(最大1.0)
            score = (
                bt.win_rate * 0.3
                + bt.avg_total_return * 2.0
                + bt.sharpe_like * 10.0
                - max(0, -bt.max_loss) * 0.3  # 最大損失ペナルティ
            ) * trade_bonus

        all_results.append((params, bt))

        if score > best_score:
            best_score = score
            best_params = rules
            best_bt = bt

    # 上位10件を表示
    all_results.sort(key=lambda x: (
        x[1].win_rate * 0.3 + x[1].avg_total_return * 2.0 + x[1].sharpe_like * 10.0
        if x[1].total_trades >= 3 else -100
    ), reverse=True)

    print(f"{'─'*105}")
    print(f"{'PEG':>5} {'利回':>5} {'PER':>5} {'ルール':>4} {'底打':>4} {'反発%':>5} │"
          f"{'取引':>4} {'勝率':>7} {'平均R':>8} {'総合R':>8} {'最大損':>8} {'シャープ':>8}")
    print(f"{'─'*105}")

    for params, bt in all_results[:20]:
        mom = "ON" if params.get("use_momentum_filter", True) else "OFF"
        reb = params.get("momentum_rebound_pct", 5.0)
        print(
            f"{params['peg_threshold']:>5.2f} "
            f"{params['yield_top_percentile']:>5.0f} "
            f"{params['per_bottom_percentile']:>5.0f} "
            f"{params['min_rules_passed']:>4} "
            f"{mom:>4} "
            f"{reb:>5.0f} │"
            f"{bt.total_trades:>4} "
            f"{bt.win_rate:>6.1f}% "
            f"{bt.avg_return:>+7.2f}% "
            f"{bt.avg_total_return:>+7.2f}% "
            f"{bt.max_loss:>+7.2f}% "
            f"{bt.sharpe_like:>8.3f}"
        )

    print(f"{'─'*90}")

    return OptimizationResult(
        best_params=best_params,
        best_score=best_score,
        best_bt=best_bt,
        all_results=all_results,
    )


# ============================================================
# トレード詳細表示
# ============================================================

def print_trade_details(bt: BacktestResult) -> None:
    """全トレードの詳細を表示"""
    print(f"\n{'─'*80}")
    print(f"  トレード詳細 ({bt.total_trades}件)")
    print(f"{'─'*80}")

    for i, t in enumerate(bt.trades, 1):
        result_mark = "✅" if (t.total_return_pct or 0) > 0 else "❌"
        print(
            f"\n  {result_mark} #{i} {t.name} ({t.symbol})"
            f"  {t.entry_date.strftime('%Y-%m')}"
            f" → {t.exit_date.strftime('%Y-%m') if t.exit_date else '?'}"
        )
        print(
            f"     買値: ¥{t.entry_price:,.0f} → 売値: ¥{t.exit_price:,.0f}"
            f"  値上がり: {t.return_pct:+.2f}%"
        )
        print(
            f"     配当: +{t.dividend_return_pct:.2f}%"
            f"  優待: +{t.benefit_return_pct:.2f}%"
            f"  → 総合: {t.total_return_pct:+.2f}%"
        )

    # 銘柄別サマリー
    print(f"\n{'─'*80}")
    print(f"  銘柄別サマリー")
    print(f"{'─'*80}")

    by_symbol: dict[str, list[Trade]] = {}
    for t in bt.trades:
        by_symbol.setdefault(t.symbol, []).append(t)

    print(f"{'銘柄':<14} {'名称':<16} {'回数':>4} {'勝率':>7} {'平均総合R':>10} {'判定'}")
    print(f"{'─'*70}")
    for sym, ts in sorted(by_symbol.items()):
        returns = [t.total_return_pct for t in ts if t.total_return_pct is not None]
        wr = sum(1 for r in returns if r > 0) / len(returns) * 100 if returns else 0
        avg_r = np.mean(returns) if returns else 0
        verdict = "◎ 有効" if wr >= 60 and avg_r > 0 else "△ 微妙" if wr >= 40 else "✗ 無効"
        print(f"{sym:<14} {ts[0].name:<16} {len(ts):>4} {wr:>6.1f}% {avg_r:>+9.2f}% {verdict}")


# ============================================================
# メイン
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="スクリーニングルール バックテスト")
    parser.add_argument("--optimize", action="store_true", help="パラメータ最適化を実行")
    parser.add_argument("--holding", type=int, default=12, help="保有期間（月、default: 12）")
    parser.add_argument("--peg", type=float, default=0.75)
    parser.add_argument("--yield-pct", type=float, default=10.0)
    parser.add_argument("--per-pct", type=float, default=25.0)
    parser.add_argument("--min-rules", type=int, default=3)
    parser.add_argument("--mode", choices=["generic", "1489"], default="1489",
                        help="銘柄セット: generic=汎用20銘柄, 1489=ETF構成48銘柄")
    args = parser.parse_args()

    stocks = SIMULATED_1489_STOCKS if args.mode == "1489" else SIMULATED_STOCKS
    mode_label = "1489 ETF構成銘柄" if args.mode == "1489" else "汎用シミュレーション"

    if args.optimize:
        print("\n" + "#" * 65)
        print(f"  パラメータ最適化モード [{mode_label}] ({len(stocks)}銘柄)")
        print("#" * 65)

        for holding in [6, 12, 18]:
            print(f"\n{'='*65}")
            print(f"  保有期間: {holding}ヶ月")
            print(f"{'='*65}")

            opt = optimize_parameters(stocks, holding_months=holding)

            print(f"\n  ★ ベストパラメータ (保有{holding}ヶ月):")
            print(opt.best_bt.summary() if opt.best_bt else "  (結果なし)")

    else:
        rules = ScreeningRules(
            peg_threshold=args.peg,
            yield_top_percentile=args.yield_pct,
            per_bottom_percentile=args.per_pct,
            min_rules_passed=args.min_rules,
        )

        print("\n" + "#" * 65)
        print(f"  スクリーニングルール バックテスト [{mode_label}] ({len(stocks)}銘柄)")
        print("#" * 65)

        bt = run_backtest(stocks, rules, holding_months=args.holding)

        print(bt.summary())
        print_trade_details(bt)

        if bt.total_trades == 0:
            print("\n  ⚠️  エントリーシグナルが0件。条件が厳しすぎる可能性があります。")
            print("  → --min-rules 2 や --peg 1.0 で緩和してみてください。")

    return 0


if __name__ == "__main__":
    sys.exit(main())
