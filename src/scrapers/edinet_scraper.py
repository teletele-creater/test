"""
EDINET API スクレイパー
公開買付届出書・大量保有報告書等のMBO関連書類を取得
"""
import re
from datetime import datetime, timedelta

from config.settings import EDINET_API_BASE, EDINET_API_KEY
from src.utils.http_client import HttpClient
from src.utils.logger import setup_logger

logger = setup_logger("edinet_scraper")

# MBO関連書類のキーワード
MBO_KEYWORDS = [
    "公開買付", "MBO", "マネジメント・バイアウト",
    "経営陣による買収", "非公開化", "上場廃止",
    "スクイーズアウト", "完全子会社化",
    "大量保有", "特別関係者",
]


class EdinetScraper:
    """EDINET APIからMBO関連書類を取得"""

    def __init__(self, http_client: HttpClient = None):
        self.client = http_client or HttpClient()
        self.api_base = EDINET_API_BASE

    def fetch_documents(self, date: str = None, doc_type: str = None) -> list:
        """
        指定日の書類一覧を取得

        Args:
            date: 対象日 (YYYY-MM-DD)、デフォルトは今日
            doc_type: 書類種別でフィルタ

        Returns:
            書類情報のリスト
        """
        if not EDINET_API_KEY:
            logger.warning("EDINET_API_KEY is not set. Skipping EDINET fetch.")
            return []

        if not date:
            date = datetime.now().strftime("%Y-%m-%d")

        params = {
            "date": date,
            "type": 2,  # メタデータ + 書類一覧
            "Subscription-Key": EDINET_API_KEY,
        }

        try:
            data = self.client.get_json(f"{self.api_base}/documents.json", params=params)
            results = data.get("results", [])
            logger.info(f"EDINET {date}: {len(results)} documents found")

            documents = []
            for doc in results:
                parsed = self._parse_document(doc)
                if doc_type and parsed.get("doc_type") != doc_type:
                    continue
                documents.append(parsed)

            return documents
        except Exception as e:
            logger.error(f"Failed to fetch EDINET documents for {date}: {e}")
            return []

    def fetch_mbo_related_documents(self, days: int = 7) -> list:
        """直近N日間のMBO関連書類を取得"""
        mbo_docs = []
        today = datetime.now()

        for i in range(days):
            date = (today - timedelta(days=i)).strftime("%Y-%m-%d")
            docs = self.fetch_documents(date)

            for doc in docs:
                if self._is_mbo_related(doc):
                    doc["is_mbo_related"] = 1
                    mbo_docs.append(doc)

        logger.info(f"Found {len(mbo_docs)} MBO-related documents in last {days} days")
        return mbo_docs

    def fetch_tender_offer_documents(self, days: int = 30) -> list:
        """公開買付届出書を取得"""
        tender_docs = []
        today = datetime.now()

        for i in range(days):
            date = (today - timedelta(days=i)).strftime("%Y-%m-%d")
            docs = self.fetch_documents(date)

            for doc in docs:
                if doc.get("doc_type") in ("公開買付届出書", "公開買付報告書"):
                    tender_docs.append(doc)

        logger.info(f"Found {len(tender_docs)} tender offer documents in last {days} days")
        return tender_docs

    def _parse_document(self, raw: dict) -> dict:
        """APIレスポンスから書類情報を抽出"""
        return {
            "doc_id": raw.get("docID", ""),
            "doc_type": raw.get("docTypeCode", ""),
            "filer_name": raw.get("filerName", ""),
            "title": raw.get("docDescription", ""),
            "filing_date": raw.get("submitDateTime", ""),
            "target_company": self._extract_target_company(raw),
            "is_mbo_related": 1 if self._is_mbo_related_raw(raw) else 0,
            "content_summary": "",
        }

    def _extract_target_company(self, raw: dict) -> str:
        """書類から対象企業名を抽出"""
        desc = raw.get("docDescription", "")
        # 「○○株式会社株券等に対する」パターンで抽出
        match = re.search(r"(.+?(?:株式会社|Inc\.|Corp\.)).*?(?:株券|株式).*?に対する", desc)
        if match:
            return match.group(1)
        return ""

    @staticmethod
    def _is_mbo_related(doc: dict) -> bool:
        """書類がMBO関連かどうか判定"""
        text = f"{doc.get('title', '')} {doc.get('filer_name', '')} {doc.get('target_company', '')}"
        return any(kw in text for kw in MBO_KEYWORDS)

    @staticmethod
    def _is_mbo_related_raw(raw: dict) -> bool:
        """生データからMBO関連か判定"""
        text = f"{raw.get('docDescription', '')} {raw.get('filerName', '')}"
        return any(kw in text for kw in MBO_KEYWORDS)
