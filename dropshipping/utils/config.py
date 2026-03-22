"""設定管理モジュール"""

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "items.db"


@dataclass
class ScrapingConfig:
    """スクレイピング関連設定"""
    # リクエスト間の最小/最大待機時間（秒）
    min_delay: float = 2.0
    max_delay: float = 5.0
    # メルカリ検索時の直近売切件数
    mercari_sold_count: int = 10
    # Playwrightのタイムアウト（ミリ秒）
    page_timeout: int = 30000
    # ブラウザをヘッドレスで実行するか
    headless: bool = True


@dataclass
class ProfitConfig:
    """利益計算関連設定"""
    # メルカリ手数料率（10%）
    mercari_fee_rate: float = 0.10
    # デフォルト送料（円）
    default_shipping_cost: int = 700
    # 最低利益しきい値（円）
    min_profit_threshold: int = 3000


@dataclass
class MonitorConfig:
    """在庫監視関連設定"""
    # チェック間隔（秒）
    check_interval: int = 300  # 5分
    # Discord Webhook URL
    discord_webhook_url: str = field(
        default_factory=lambda: os.getenv("DISCORD_WEBHOOK_URL", "")
    )
    # LINE Notify トークン
    line_notify_token: str = field(
        default_factory=lambda: os.getenv("LINE_NOTIFY_TOKEN", "")
    )
    # 通知方法: "discord", "line", "both"
    notification_method: str = field(
        default_factory=lambda: os.getenv("NOTIFICATION_METHOD", "discord")
    )


@dataclass
class MercariConfig:
    """メルカリ自動操作関連設定"""
    # メルカリのログイン情報
    email: str = field(
        default_factory=lambda: os.getenv("MERCARI_EMAIL", "")
    )
    password: str = field(
        default_factory=lambda: os.getenv("MERCARI_PASSWORD", "")
    )
    # Cookie保存パス
    cookie_path: Path = field(
        default_factory=lambda: BASE_DIR / "mercari_cookies.json"
    )
    # 人間に近づけるための待機時間（秒）
    human_min_delay: float = 1.0
    human_max_delay: float = 3.0


@dataclass
class AppConfig:
    """アプリケーション全体設定"""
    scraping: ScrapingConfig = field(default_factory=ScrapingConfig)
    profit: ProfitConfig = field(default_factory=ProfitConfig)
    monitor: MonitorConfig = field(default_factory=MonitorConfig)
    mercari: MercariConfig = field(default_factory=MercariConfig)
    db_path: Path = DB_PATH


# グローバル設定インスタンス
config = AppConfig()
