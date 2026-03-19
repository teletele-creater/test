"""
MBO予測システム - 設定ファイル
"""
import os
from pathlib import Path

# プロジェクトルート
PROJECT_ROOT = Path(__file__).parent.parent

# データディレクトリ
DATA_DIR = PROJECT_ROOT / "data"
LOG_DIR = PROJECT_ROOT / "logs"
DB_PATH = DATA_DIR / "mbo_detector.db"

# === 国税庁 法人番号公表システム Web-API ===
# https://www.houjin-bangou.nta.go.jp/webapi/
# アプリケーションID（利用登録して取得する）
NTA_APP_ID = os.environ.get("NTA_APP_ID", "")
NTA_API_BASE = "https://api.houjin-bangou.nta.go.jp/4"

# === EDINET API ===
# https://disclosure.edinet-fsa.go.jp/
EDINET_API_BASE = "https://api.edinet-fsa.go.jp/api/v2"
EDINET_API_KEY = os.environ.get("EDINET_API_KEY", "")

# === gBizINFO API ===
# https://info.gbiz.go.jp/
GBIZ_API_BASE = "https://info.gbiz.go.jp/hojin/v1"
GBIZ_API_TOKEN = os.environ.get("GBIZ_API_TOKEN", "")

# === JPX 上場企業リスト ===
JPX_LISTED_COMPANIES_URL = "https://www.jpx.co.jp/markets/statistics-equities/misc/tvdivq0000001vg2-att/data_j.xls"

# === TDnet (適時開示情報) ===
TDNET_RSS_URL = "https://www.release.tdnet.info/inbs/I_list_001_00.html"

# === スクレイピング設定 ===
REQUEST_TIMEOUT = 30  # seconds
REQUEST_DELAY = 2.0  # リクエスト間隔（秒）- 礼儀的なクロール
MAX_RETRIES = 3
USER_AGENT = "MBO-Detector/1.0 (Research Purpose)"

# === SPC検出パターン ===
# MBO用SPCに多い法人名パターン
SPC_NAME_PATTERNS = [
    "ホールディングス",
    "HD",
    "インベストメント",
    "キャピタル",
    "パートナーズ",
    "アドバイザリー",
    "投資",
    "買収",
    "アクイジション",
    "Acquisition",
    "Holdings",
    "Investment",
    "Capital",
    "Partners",
]

# SPC法人形態（合同会社が圧倒的に多い）
SPC_ENTITY_TYPES = [
    "合同会社",
    "株式会社",
]

# MBOに関連するPEファンド名
PE_FUND_KEYWORDS = [
    "ベインキャピタル",
    "Bain Capital",
    "カーライル",
    "Carlyle",
    "KKR",
    "ブラックストーン",
    "Blackstone",
    "MBKパートナーズ",
    "MBK Partners",
    "ユニゾン",
    "Unison",
    "ポラリス",
    "Polaris",
    "アドバンテッジ",
    "Advantage",
    "日本産業パートナーズ",
    "JIP",
    "インテグラル",
    "Integral",
    "エンデバー",
    "BCJ",
    "ロングリーチ",
    "Longreach",
    "J-STAR",
    "丸の内キャピタル",
]

# === 監視スケジュール ===
# 法人番号APIの新規法人チェック間隔（分）
NTA_CHECK_INTERVAL_MINUTES = 60
# EDINET/TDnetチェック間隔（分）
EDINET_CHECK_INTERVAL_MINUTES = 30
# 分析実行間隔（分）
ANALYSIS_INTERVAL_MINUTES = 120

# === 通知設定 ===
NOTIFICATION_ENABLED = os.environ.get("NOTIFICATION_ENABLED", "false").lower() == "true"
SLACK_WEBHOOK_URL = os.environ.get("SLACK_WEBHOOK_URL", "")
EMAIL_SMTP_SERVER = os.environ.get("EMAIL_SMTP_SERVER", "")
EMAIL_FROM = os.environ.get("EMAIL_FROM", "")
EMAIL_TO = os.environ.get("EMAIL_TO", "")
