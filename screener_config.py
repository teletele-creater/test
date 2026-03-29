"""
株式スクリーニングルール設定

投資哲学: 業績が成長しているのに株価が上がらず、
ある価格まで下がると配当利回りが高くなり、
高配当かつ高成長銘柄になるラインを待つ。

3条件すべて満たす = 異常値エントリーゾーン
"""

from dataclasses import dataclass, field


@dataclass
class ScreeningRules:
    """スクリーニングルールのパラメータ"""

    # === ルール①: 総合利回り（配当＋優待換算） ===
    # 過去5年の利回りレンジの上位N%以内なら合格
    yield_top_percentile: float = 10.0  # 上位10%
    yield_lookback_years: int = 5
    # 優待換算額（年間、円）: 銘柄ごとに手動設定
    # 恒常的制度のみ加算（記念優待等は除外）
    include_shareholder_benefits: bool = True

    # === ルール②: 営業利益成長 × 独自PEG ===
    # 営業利益成長率が業種平均以上
    op_growth_periods: int = 3  # 直近N期の平均成長率
    op_growth_min_periods: int = 2  # 最低N期のデータが必要
    # 独自PEG = PER ÷ 営業利益成長率(%)
    peg_threshold: float = 0.75  # PEG < 0.75 で合格
    # EPS乖離チェック: 営業利益成長率とEPS成長率の差がN%以上なら警告
    eps_divergence_warn_pct: float = 30.0

    # === ルール③: PERが過去5年レンジの下位25%以内 ===
    per_bottom_percentile: float = 25.0  # 下位25%
    per_lookback_years: int = 5
    # 異常値除外: PERがN以下またはN以上の年度は除外
    per_outlier_min: float = 0.0  # PER <= 0（赤字）は除外
    per_outlier_max: float = 100.0  # PER > 100は除外

    # === エントリー判定 ===
    min_rules_passed: int = 3  # 全3条件クリアで「異常値エントリーゾーン」


@dataclass
class SectorBenchmark:
    """業種別ベンチマーク（営業利益成長率の業種平均）"""
    sector: str
    avg_op_growth_rate: float  # 業種平均の営業利益成長率(%)


# 業種別の営業利益成長率ベンチマーク（日本市場・概算値）
# 実運用時はデータソースから動的更新推奨
SECTOR_BENCHMARKS: dict[str, float] = {
    "Technology": 12.0,
    "Healthcare": 8.0,
    "Financial Services": 6.0,
    "Consumer Cyclical": 7.0,
    "Consumer Defensive": 4.0,
    "Industrials": 6.0,
    "Basic Materials": 5.0,
    "Energy": 8.0,
    "Utilities": 3.0,
    "Real Estate": 4.0,
    "Communication Services": 7.0,
    # 日本語セクター名も対応
    "情報・通信業": 12.0,
    "医薬品": 8.0,
    "銀行業": 6.0,
    "小売業": 7.0,
    "食料品": 4.0,
    "機械": 6.0,
    "化学": 5.0,
    "電気機器": 10.0,
    "輸送用機器": 6.0,
    "サービス業": 8.0,
}

# デフォルトの業種平均（セクター不明時）
DEFAULT_SECTOR_GROWTH_RATE: float = 6.0

# 優待換算データ（銘柄コード -> 年間優待価値(円)、最低必要株数）
# 恒常的制度のみ。記念優待・一時的優待は除外
SHAREHOLDER_BENEFITS: dict[str, dict] = {
    # 例: "2914.T": {"value_yen": 6000, "min_shares": 100, "description": "JT 自社商品"},
    # ユーザーが手動で追加・管理
}

# スクリーニング対象銘柄リスト
SCREENING_WATCHLIST: list[str] = [
    # 日本株の例
    "7203.T",   # トヨタ自動車
    "8306.T",   # 三菱UFJ
    "9432.T",   # NTT
    "2914.T",   # JT
    "8058.T",   # 三菱商事
    "9433.T",   # KDDI
    "8766.T",   # 東京海上
    "4502.T",   # 武田薬品
    "6758.T",   # ソニー
    "7267.T",   # ホンダ
    # 米国株の例
    "AAPL",
    "MSFT",
    "JNJ",
    "PG",
    "KO",
]
