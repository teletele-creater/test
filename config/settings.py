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
    # 基本パターン
    "ホールディングス",
    "HD",
    "インベストメント",
    "キャピタル",
    "パートナーズ",
    "アドバイザリー",
    "投資",
    "買収",
    "アクイジション",
    # 英語パターン
    "Acquisition",
    "Holdings",
    "Investment",
    "Capital",
    "Partners",
    "Advisory",
    # MBO実例で頻出するパターン
    "合同会社BCPE",      # ベインキャピタル系SPC
    "エスケーホールディングス",  # 典型的なSPC命名
    "グロース",
    "バリュー",
    "ストラテジック",
    "マージャー",
    "Merger",
    "Buyout",
    "バイアウト",
    "テンダー",
    "Tender",
    "オファー",
]

# SPC法人形態（合同会社が圧倒的に多い）
SPC_ENTITY_TYPES = [
    "合同会社",
    "株式会社",
]

# === 偽陽性除外パターン ===
# MBOとは無関係にSPCパターンに一致してしまう業種・用途
FALSE_POSITIVE_KEYWORDS = [
    # 不動産
    "不動産", "リアルエステート", "Real Estate", "プロパティ",
    "マンション", "レジデンス", "ビルディング", "アパート",
    # 太陽光・再エネ
    "太陽光", "ソーラー", "Solar", "再生可能エネルギー",
    "風力", "バイオマス", "発電",
    # 一般事業
    "飲食", "レストラン", "クリニック", "医療", "薬局",
    "美容", "サロン", "整骨", "介護", "福祉",
    "運送", "物流", "清掃", "建設", "工務",
    "農業", "漁業", "林業",
    # 暗号資産・FX
    "暗号資産", "仮想通貨", "FX", "バイナリー",
]

# 偽陽性の法人目的パターン（purposeフィールドで除外）
FALSE_POSITIVE_PURPOSE_KEYWORDS = [
    "不動産の売買", "不動産の賃貸", "不動産の管理",
    "太陽光発電", "再生可能エネルギー",
    "飲食店の経営", "飲食業",
]

# MBOに関連するPEファンド名
PE_FUND_KEYWORDS = [
    # グローバルPE
    "ベインキャピタル", "Bain Capital", "BCPE",
    "カーライル", "Carlyle",
    "KKR",
    "ブラックストーン", "Blackstone",
    "MBKパートナーズ", "MBK Partners",
    "アポロ", "Apollo",
    "EQT",
    "CVC", "CVCキャピタル",
    "ペルミラ", "Permira",
    "ウォーバーグ", "Warburg Pincus",
    # 日本国内PE
    "ユニゾン", "Unison",
    "ポラリス", "Polaris",
    "アドバンテッジ", "Advantage Partners",
    "日本産業パートナーズ", "JIP",
    "インテグラル", "Integral",
    "エンデバー", "Endeavour",
    "BCJ",
    "ロングリーチ", "Longreach",
    "J-STAR",
    "丸の内キャピタル",
    "日本産業推進機構", "NSSK",
    "ニューホライズンキャピタル",
    "アント・キャピタル", "Ant Capital",
    "東京海上キャピタル",
    "野村キャピタル",
    "大和PIパートナーズ",
    "みずほキャピタル",
    "SBIキャピタル",
    "ジャフコ", "JAFCO",
    "タイヨウファンド", "Taiyo",
    "オアシス", "Oasis",
    "エフィッシモ", "Effissimo",
    "ダルトン", "Dalton",
    "3Dインベストメント", "3D Investment",
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
