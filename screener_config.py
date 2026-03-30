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
    # バックテスト最適化結果: 15-30%が安定（厳しくしすぎるとシグナル減少）
    yield_top_percentile: float = 20.0  # 上位20%（最適化推奨レンジ: 15-30%）
    yield_lookback_years: int = 5
    # 優待換算額（年間、円）: 銘柄ごとに手動設定
    # 恒常的制度のみ加算（記念優待等は除外）
    include_shareholder_benefits: bool = True

    # === ルール②: 営業利益成長 × 独自PEG ===
    # 営業利益成長率が業種平均以上
    op_growth_periods: int = 3  # 直近N期の平均成長率
    op_growth_min_periods: int = 2  # 最低N期のデータが必要
    # 独自PEG = PER ÷ 営業利益成長率(%)
    # バックテスト最適化結果: 0.75-1.2が高勝率。1.0が勝率×リターンのバランス良
    peg_threshold: float = 1.0  # PEG < 1.0 で合格（最適化推奨レンジ: 0.75-1.2）
    # EPS乖離チェック: 営業利益成長率とEPS成長率の差がN%以上なら警告
    eps_divergence_warn_pct: float = 30.0

    # === ルール③: PERが過去5年レンジの下位25%以内 ===
    # バックテスト最適化結果: 25-40%が安定
    per_bottom_percentile: float = 30.0  # 下位30%（最適化推奨レンジ: 25-40%）
    per_lookback_years: int = 5
    # 異常値除外: PERがN以下またはN以上の年度は除外
    per_outlier_min: float = 0.0  # PER <= 0（赤字）は除外
    per_outlier_max: float = 100.0  # PER > 100は除外

    # === ルール④: 底打ち確認（モメンタムフィルター） ===
    # 落ちるナイフを掴まない。直近N月で最安値から反転を確認
    # バックテスト: ON時は勝率42%→100%に劇的改善。最重要フィルター。
    use_momentum_filter: bool = True
    momentum_lookback_months: int = 6  # 直近N月を確認
    momentum_rebound_pct: float = 5.0  # 安値からN%以上（推奨: 3-8%）

    # === エントリー判定 ===
    min_rules_passed: int = 3  # 基本3条件クリアで「異常値エントリーゾーン」
    # ※momentum_filterはボーナスルールとして独立判定（min_rules_passedに含めない）
    # バックテスト: min=3が高精度。min=2だとバリュートラップを拾いやすい


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
# ※金額は100株保有時の年間換算額（2024年時点の制度ベース）
SHAREHOLDER_BENEFITS: dict[str, dict] = {
    # --- 食品・飲料 ---
    "2914.T": {"value_yen": 4500, "min_shares": 100,
               "description": "JT 自社グループ商品（年2回）"},
    "2802.T": {"value_yen": 3000, "min_shares": 100,
               "description": "味の素 自社商品詰合せ"},
    "2801.T": {"value_yen": 3000, "min_shares": 100,
               "description": "キッコーマン 自社商品詰合せ"},
    "2269.T": {"value_yen": 3000, "min_shares": 100,
               "description": "明治HD 自社商品詰合せ"},
    "2503.T": {"value_yen": 3500, "min_shares": 100,
               "description": "キリンHD 自社商品詰合せ"},
    "2502.T": {"value_yen": 3000, "min_shares": 100,
               "description": "アサヒGHD 自社飲料詰合せ"},
    # --- 通信 ---
    "9433.T": {"value_yen": 3000, "min_shares": 100,
               "description": "KDDI カタログギフト（Pontaポイント）"},
    "9432.T": {"value_yen": 1500, "min_shares": 100,
               "description": "NTT dポイント付与"},
    # --- 小売・外食 ---
    "8267.T": {"value_yen": 3000, "min_shares": 100,
               "description": "イオン 買物優待カード（3%キャッシュバック換算）"},
    "3382.T": {"value_yen": 3000, "min_shares": 100,
               "description": "セブン&iHD 商品券"},
    "7550.T": {"value_yen": 3000, "min_shares": 100,
               "description": "ゼンショーHD 食事券"},
    "3543.T": {"value_yen": 6000, "min_shares": 100,
               "description": "コメダHD KOMECA電子マネー"},
    "7412.T": {"value_yen": 2000, "min_shares": 100,
               "description": "アトム 食事優待ポイント"},
    "3387.T": {"value_yen": 2000, "min_shares": 100,
               "description": "クリレスHD 食事券"},
    "2702.T": {"value_yen": 6000, "min_shares": 100,
               "description": "マクドナルド 食事優待券（年2回）"},
    "9861.T": {"value_yen": 3000, "min_shares": 100,
               "description": "吉野家HD 食事券"},
    # --- 日用品・ヘルスケア ---
    "4452.T": {"value_yen": 5000, "min_shares": 100,
               "description": "花王 自社商品詰合せ"},
    "4911.T": {"value_yen": 3000, "min_shares": 100,
               "description": "資生堂 自社商品"},
    "4967.T": {"value_yen": 5000, "min_shares": 100,
               "description": "小林製薬 自社商品詰合せ"},
    # --- 金融 ---
    "8591.T": {"value_yen": 3000, "min_shares": 100,
               "description": "オリックス カタログギフト（2024年廃止予定→廃止済なら0に）"},
    # --- エンタメ・レジャー ---
    "9202.T": {"value_yen": 5000, "min_shares": 100,
               "description": "ANA 株主優待割引券（片道50%OFF換算）"},
    "9201.T": {"value_yen": 5000, "min_shares": 100,
               "description": "JAL 株主優待割引券（片道50%OFF換算）"},
    "4661.T": {"value_yen": 8000, "min_shares": 100,
               "description": "OLC（ディズニー）1デーパスポート"},
    # --- その他 ---
    "8058.T": {"value_yen": 0, "min_shares": 100,
               "description": "三菱商事 優待なし"},
    "8306.T": {"value_yen": 0, "min_shares": 100,
               "description": "三菱UFJ 優待なし"},
    "7203.T": {"value_yen": 0, "min_shares": 100,
               "description": "トヨタ 優待なし"},
    "6758.T": {"value_yen": 0, "min_shares": 100,
               "description": "ソニー 優待なし"},
    "7267.T": {"value_yen": 0, "min_shares": 100,
               "description": "ホンダ 優待なし"},
    "8766.T": {"value_yen": 0, "min_shares": 100,
               "description": "東京海上 優待なし"},
    "4502.T": {"value_yen": 0, "min_shares": 100,
               "description": "武田薬品 優待なし"},
}

# スクリーニング対象銘柄リスト
SCREENING_WATCHLIST: list[str] = [
    # --- 高配当・優待銘柄 ---
    "2914.T",   # JT（高配当+優待）
    "9433.T",   # KDDI（配当+優待）
    "9432.T",   # NTT（配当+dポイント）
    "8058.T",   # 三菱商事（高配当）
    "8306.T",   # 三菱UFJ（高配当）
    "8766.T",   # 東京海上（高配当）
    # --- 成長+配当 ---
    "7203.T",   # トヨタ自動車
    "6758.T",   # ソニー
    "7267.T",   # ホンダ
    "4502.T",   # 武田薬品
    # --- 優待人気銘柄 ---
    "2702.T",   # マクドナルド
    "3543.T",   # コメダHD
    "7550.T",   # ゼンショーHD
    "8267.T",   # イオン
    "4452.T",   # 花王
    "2503.T",   # キリンHD
    # --- 米国高配当 ---
    "JNJ",
    "PG",
    "KO",
    "ABBV",
    "MO",
]
