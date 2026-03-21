"""
オプション取引アラートシステム - 設定ファイル

レポートの分析に基づき、最も再現性の高い戦略（SPYブルプットスプレッド）を
中心に、全5戦略のエントリー条件を定義。
"""

from dataclasses import dataclass, field


@dataclass
class StrategyConditions:
    """各戦略のエントリー条件"""
    name: str
    name_jp: str
    description: str
    min_conditions_met: int  # GOに必要な最低条件数
    ivr_min: float | None = None
    ivr_max: float | None = None
    vix_min: float | None = None
    vix_declining: bool = False  # VIXがスパイクから低下中か
    rsi_max: float | None = None  # プット売り時のRSI上限
    rsi_min: float | None = None  # コール売り時のRSI下限
    iv_hv_ratio_min: float | None = None
    near_50ma: bool = False
    near_200ma: bool = False
    put_call_ratio_sma_min: float | None = None
    target_delta: int = 20
    dte_min: int = 30
    dte_max: int = 45
    profit_target_pct: float = 50.0  # 利確目標（%）
    stop_loss_multiplier: float = 2.0  # 損切り倍率
    exit_dte: int = 21  # 強制決済DTE
    win_rate: str = ""
    bpr_range: str = ""


# === 戦略A：SPYブルプットスプレッド（最推奨・最高再現性） ===
STRATEGY_A = StrategyConditions(
    name="SPY Bull Put Spread",
    name_jp="SPYブルプットスプレッド",
    description="OTMプット売り + さらにOTMプット買い（損失限定型）。最も高い勝率と再現性。",
    min_conditions_met=3,
    ivr_min=50.0,
    vix_min=20.0,
    rsi_max=35.0,
    iv_hv_ratio_min=1.2,
    near_50ma=True,
    target_delta=20,
    dte_min=30,
    dte_max=45,
    profit_target_pct=50.0,
    stop_loss_multiplier=2.0,
    exit_dte=21,
    win_rate="80-91%",
    bpr_range="$350-450",
)

# === 戦略B：SPY/IWMアイアンコンドル ===
STRATEGY_B = StrategyConditions(
    name="SPY/IWM Iron Condor",
    name_jp="SPY/IWMアイアンコンドル",
    description="プット側・コール側の両方にクレジットスプレッド。VIXスパイク低下局面で有効。",
    min_conditions_met=3,
    ivr_min=50.0,
    vix_min=25.0,
    vix_declining=True,
    put_call_ratio_sma_min=1.0,
    iv_hv_ratio_min=1.2,
    target_delta=16,
    dte_min=30,
    dte_max=45,
    profit_target_pct=50.0,
    stop_loss_multiplier=2.0,
    exit_dte=21,
    win_rate="68-75%",
    bpr_range="$320-400",
)

# === 戦略C：アイアンバタフライ ===
STRATEGY_C = StrategyConditions(
    name="Iron Butterfly",
    name_jp="アイアンバタフライ",
    description="ATMストラドル売り + ウイング買い。最も資金効率が高い。IVR>70%の高ボラ環境向け。",
    min_conditions_met=2,
    ivr_min=70.0,
    vix_min=20.0,
    target_delta=50,  # ATM
    dte_min=30,
    dte_max=45,
    profit_target_pct=25.0,
    stop_loss_multiplier=2.0,
    exit_dte=21,
    win_rate="68-85%",
    bpr_range="$50-150",
)

# === 戦略D：カレンダースプレッド（低IV時） ===
STRATEGY_D = StrategyConditions(
    name="Calendar Spread",
    name_jp="カレンダースプレッド",
    description="低IV環境での代替戦略。期近売り + 期先買い。IV上昇で利益。",
    min_conditions_met=2,
    ivr_max=20.0,
    dte_min=30,
    dte_max=60,
    profit_target_pct=35.0,
    stop_loss_multiplier=1.5,
    exit_dte=7,
    win_rate="55-65%",
    bpr_range="$200-400",
)

# === 戦略E：日経ミニプット売り ===
STRATEGY_E = StrategyConditions(
    name="Nikkei Mini Put Sell",
    name_jp="日経ミニプット売り",
    description="日経225ミニオプションのOTMプット売り。資金20万円以上推奨。",
    min_conditions_met=2,
    ivr_min=50.0,
    vix_min=28.0,  # 日経VI基準
    rsi_max=35.0,
    target_delta=20,
    dte_min=30,
    dte_max=45,
    profit_target_pct=50.0,
    stop_loss_multiplier=2.0,
    exit_dte=21,
    win_rate="70-80%",
    bpr_range="¥50,000+",
)

# 全戦略のリスト（優先度順）
ALL_STRATEGIES = [STRATEGY_A, STRATEGY_B, STRATEGY_C, STRATEGY_D, STRATEGY_E]

# === モニタリング対象銘柄 ===
WATCHLIST = {
    "us_etfs": ["SPY", "IWM", "QQQ"],
    "us_stocks_pmcc": ["F", "SOFI"],  # プアマンズ・カバードコール用
    "japan": ["^N225"],  # 日経225（日経VI参考用）
}

# === テクニカル設定 ===
RSI_PERIOD = 14
MA_SHORT = 50
MA_LONG = 200
MA_PROXIMITY_PCT = 2.0  # MA付近の判定（±2%）
IV_LOOKBACK_DAYS = 252  # IV Rank計算用（52週 = 252営業日）
PUT_CALL_RATIO_SMA_PERIOD = 10
VIX_DECLINE_LOOKBACK = 5  # VIX低下判定の日数
