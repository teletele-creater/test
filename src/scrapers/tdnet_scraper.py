"""
TDnet（適時開示情報）スクレイパー
上場企業のMBO関連適時開示を取得
"""
import re
from bs4 import BeautifulSoup

from config.settings import TDNET_RSS_URL
from src.utils.http_client import HttpClient
from src.utils.logger import setup_logger

logger = setup_logger("tdnet_scraper")

MBO_DISCLOSURE_KEYWORDS = [
    "MBO", "公開買付", "マネジメント・バイアウト",
    "非公開化", "上場廃止", "完全子会社化",
    "経営陣による", "スクイーズアウト",
    "賛同の意見", "応募推奨",
]


class TdnetScraper:
    """TDnetから適時開示情報を取得"""

    def __init__(self, http_client: HttpClient = None):
        self.client = http_client or HttpClient()

    def fetch_recent_disclosures(self) -> list:
        """最新の適時開示一覧を取得"""
        try:
            html = self.client.get_text(TDNET_RSS_URL)
            return self._parse_disclosure_list(html)
        except Exception as e:
            logger.error(f"Failed to fetch TDnet disclosures: {e}")
            return []

    def fetch_mbo_related_disclosures(self) -> list:
        """MBO関連の適時開示のみ取得"""
        disclosures = self.fetch_recent_disclosures()
        mbo_related = [d for d in disclosures if self._is_mbo_related(d)]
        logger.info(f"Found {len(mbo_related)} MBO-related disclosures out of {len(disclosures)}")
        return mbo_related

    def _parse_disclosure_list(self, html: str) -> list:
        """TDnetのHTML一覧をパースする"""
        soup = BeautifulSoup(html, "html.parser")
        disclosures = []

        # TDnetの適時開示一覧テーブルをパース
        rows = soup.select("table tr")
        for row in rows:
            cells = row.find_all("td")
            if len(cells) < 4:
                continue

            try:
                disclosed_at = cells[0].get_text(strip=True)
                company_code = cells[1].get_text(strip=True)
                company_name = cells[2].get_text(strip=True)
                title_elem = cells[3].find("a")

                if not title_elem:
                    continue

                title = title_elem.get_text(strip=True)
                url = title_elem.get("href", "")
                if url and not url.startswith("http"):
                    url = f"https://www.release.tdnet.info/inbs/{url}"

                # 証券コードの正規化（4桁）
                code_match = re.match(r"(\d{4})", company_code)
                code = code_match.group(1) if code_match else company_code

                disclosure = {
                    "disclosure_id": self._generate_id(disclosed_at, code, title),
                    "company_code": code,
                    "company_name": company_name,
                    "title": title,
                    "disclosed_at": disclosed_at,
                    "is_mbo_related": 1 if self._is_mbo_related_text(title) else 0,
                    "url": url,
                }
                disclosures.append(disclosure)
            except (IndexError, AttributeError) as e:
                logger.debug(f"Failed to parse row: {e}")
                continue

        logger.info(f"Parsed {len(disclosures)} disclosures from TDnet")
        return disclosures

    @staticmethod
    def _is_mbo_related(disclosure: dict) -> bool:
        title = disclosure.get("title", "")
        return TdnetScraper._is_mbo_related_text(title)

    @staticmethod
    def _is_mbo_related_text(text: str) -> bool:
        return any(kw in text for kw in MBO_DISCLOSURE_KEYWORDS)

    @staticmethod
    def _generate_id(date: str, code: str, title: str) -> str:
        """一意なIDを生成"""
        import hashlib
        raw = f"{date}_{code}_{title}"
        return hashlib.md5(raw.encode()).hexdigest()[:16]
