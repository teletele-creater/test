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
    # --- 1489構成銘柄（優待なし） ---
    "1605.T": {"value_yen": 0, "min_shares": 100,
               "description": "INPEX 優待なし"},
    "1801.T": {"value_yen": 0, "min_shares": 100,
               "description": "大成建設 優待なし"},
    "1812.T": {"value_yen": 0, "min_shares": 100,
               "description": "鹿島建設 優待なし"},
    "1928.T": {"value_yen": 0, "min_shares": 100,
               "description": "積水ハウス 優待なし"},
    "3407.T": {"value_yen": 0, "min_shares": 100,
               "description": "旭化成 優待なし"},
    "3861.T": {"value_yen": 0, "min_shares": 100,
               "description": "王子HD 優待なし"},
    "4183.T": {"value_yen": 0, "min_shares": 100,
               "description": "三井化学 優待なし"},
    "4188.T": {"value_yen": 0, "min_shares": 100,
               "description": "三菱ケミカルG 優待なし"},
    "4324.T": {"value_yen": 0, "min_shares": 100,
               "description": "電通グループ 優待なし"},
    "4502.T": {"value_yen": 0, "min_shares": 100,
               "description": "武田薬品 優待なし"},
    "4503.T": {"value_yen": 0, "min_shares": 100,
               "description": "アステラス製薬 優待なし"},
    "5019.T": {"value_yen": 0, "min_shares": 100,
               "description": "出光興産 優待なし"},
    "5020.T": {"value_yen": 0, "min_shares": 100,
               "description": "ENEOS HD 優待なし"},
    "5108.T": {"value_yen": 0, "min_shares": 100,
               "description": "ブリヂストン 優待なし"},
    "5201.T": {"value_yen": 0, "min_shares": 100,
               "description": "AGC 優待なし"},
    "5401.T": {"value_yen": 0, "min_shares": 100,
               "description": "日本製鉄 優待なし"},
    "5406.T": {"value_yen": 0, "min_shares": 100,
               "description": "神戸製鋼所 優待なし"},
    "5411.T": {"value_yen": 0, "min_shares": 100,
               "description": "JFE HD 優待なし"},
    "5713.T": {"value_yen": 0, "min_shares": 100,
               "description": "住友金属鉱山 優待なし"},
    "6301.T": {"value_yen": 0, "min_shares": 100,
               "description": "コマツ 優待なし"},
    "6305.T": {"value_yen": 0, "min_shares": 100,
               "description": "日立建機 優待なし"},
    "6471.T": {"value_yen": 0, "min_shares": 100,
               "description": "日本精工 優待なし"},
    "6472.T": {"value_yen": 0, "min_shares": 100,
               "description": "NTN 優待なし"},
    "6473.T": {"value_yen": 0, "min_shares": 100,
               "description": "ジェイテクト 優待なし"},
    "7202.T": {"value_yen": 0, "min_shares": 100,
               "description": "いすゞ自動車 優待なし"},
    "7261.T": {"value_yen": 0, "min_shares": 100,
               "description": "マツダ 優待なし"},
    "7267.T": {"value_yen": 0, "min_shares": 100,
               "description": "ホンダ 優待なし"},
    "7272.T": {"value_yen": 0, "min_shares": 100,
               "description": "ヤマハ発動機 優待なし"},
    "7751.T": {"value_yen": 0, "min_shares": 100,
               "description": "キヤノン 優待なし"},
    "8001.T": {"value_yen": 0, "min_shares": 100,
               "description": "伊藤忠商事 優待なし"},
    "8002.T": {"value_yen": 0, "min_shares": 100,
               "description": "丸紅 優待なし"},
    "8015.T": {"value_yen": 0, "min_shares": 100,
               "description": "豊田通商 優待なし"},
    "8053.T": {"value_yen": 0, "min_shares": 100,
               "description": "住友商事 優待なし"},
    "8058.T": {"value_yen": 0, "min_shares": 100,
               "description": "三菱商事 優待なし"},
    "8304.T": {"value_yen": 0, "min_shares": 100,
               "description": "あおぞら銀行 優待なし"},
    "8308.T": {"value_yen": 0, "min_shares": 100,
               "description": "りそなHD 優待なし"},
    "8309.T": {"value_yen": 0, "min_shares": 100,
               "description": "三井住友トラストHD 優待なし"},
    "8316.T": {"value_yen": 0, "min_shares": 100,
               "description": "三井住友FG 優待なし"},
    "8411.T": {"value_yen": 0, "min_shares": 100,
               "description": "みずほFG 優待なし"},
    "8473.T": {"value_yen": 0, "min_shares": 100,
               "description": "SBI HD 優待なし"},
    "8601.T": {"value_yen": 0, "min_shares": 100,
               "description": "大和証券グループ 優待なし"},
    "8604.T": {"value_yen": 0, "min_shares": 100,
               "description": "野村HD 優待なし"},
    "8725.T": {"value_yen": 0, "min_shares": 100,
               "description": "MS&AD 優待なし"},
    "9101.T": {"value_yen": 0, "min_shares": 100,
               "description": "日本郵船 優待なし"},
    "9107.T": {"value_yen": 0, "min_shares": 100,
               "description": "川崎汽船 優待なし"},
    "9434.T": {"value_yen": 0, "min_shares": 100,
               "description": "ソフトバンク 優待なし"},
}

# スクリーニング対象銘柄リスト
# ====================================================================
# 日経平均高配当株50指数（1489 ETF）構成銘柄ベース
# - 2025年6月定期見直し後の50銘柄から開始
# - 2025年9月: シチズン(7762)臨時除外
# - 2026年3月: カシオ(6952)臨時除外
# → 現在48銘柄で算出中。次回定期見直しは2026年6月末
#
# ※公式リスト: https://indexes.nikkei.co.jp/nkave/index/component?idx=nk225hdy
# ※検索結果・ファクトシート・入替ニュースから構築。要定期確認。
# ====================================================================
SCREENING_WATCHLIST: list[str] = [
    # === 鉱業・エネルギー ===
    "1605.T",   # INPEX（ウェート1位）
    "5020.T",   # ENEOS HD
    "5019.T",   # 出光興産
    # === 建設 ===
    "1928.T",   # 積水ハウス
    "1812.T",   # 鹿島建設
    "1801.T",   # 大成建設
    # === 食品 ===
    "2914.T",   # JT 日本たばこ産業（ウェート6位）
    # === 紙・パルプ ===
    "3861.T",   # 王子HD（2025年6月追加）
    # === 化学 ===
    "4188.T",   # 三菱ケミカルG
    "4183.T",   # 三井化学
    "3407.T",   # 旭化成
    # === 医薬品 ===
    "4502.T",   # 武田薬品工業（ウェート5位）
    "4503.T",   # アステラス製薬（ウェート3位）
    # === ゴム ===
    "5108.T",   # ブリヂストン
    # === ガラス・土石 ===
    "5201.T",   # AGC
    # === 鉄鋼 ===
    "5401.T",   # 日本製鉄
    "5406.T",   # 神戸製鋼所
    "5411.T",   # JFE HD
    # === 非鉄金属 ===
    "5713.T",   # 住友金属鉱山
    # === 機械 ===
    "6301.T",   # コマツ（小松製作所）
    "6305.T",   # 日立建機
    "6471.T",   # 日本精工
    "6472.T",   # NTN（2025年6月追加）
    "6473.T",   # ジェイテクト（2025年6月追加）
    # === 電気機器 ===
    "7751.T",   # キヤノン
    # === 輸送用機器 ===
    "7202.T",   # いすゞ自動車
    "7261.T",   # マツダ（2025年6月追加）
    "7267.T",   # 本田技研工業
    "7272.T",   # ヤマハ発動機（2025年6月追加）
    # === サービス ===
    "4324.T",   # 電通グループ（2025年6月追加）
    # === 卸売（商社） ===
    "8001.T",   # 伊藤忠商事
    "8002.T",   # 丸紅
    "8015.T",   # 豊田通商
    "8053.T",   # 住友商事（ウェート10位）
    "8058.T",   # 三菱商事（ウェート8位）
    # === 銀行 ===
    "8304.T",   # あおぞら銀行
    "8308.T",   # りそなHD
    "8309.T",   # 三井住友トラストHD
    "8316.T",   # 三井住友FG（ウェート7位）
    "8411.T",   # みずほFG（ウェート2位）
    # === 証券 ===
    "8473.T",   # SBI HD
    "8601.T",   # 大和証券グループ
    "8604.T",   # 野村HD（ウェート4位、2025年6月追加）
    # === 保険 ===
    "8725.T",   # MS&AD インシュアランスG
    # === 海運 ===
    "9101.T",   # 日本郵船
    "9107.T",   # 川崎汽船（ウェート9位）
    # === 通信 ===
    "9433.T",   # KDDI
    "9434.T",   # ソフトバンク
    # === 合計: 48銘柄 ===
]
