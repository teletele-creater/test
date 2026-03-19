"""
国税庁 法人番号公表システム Web-API スクレイパー
新規設立法人を取得し、SPC候補を検出する
"""
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta

from config.settings import NTA_APP_ID, NTA_API_BASE
from src.utils.http_client import HttpClient
from src.utils.logger import setup_logger

logger = setup_logger("nta_scraper")


class NtaScraper:
    """国税庁法人番号APIからの新規法人取得"""

    def __init__(self, http_client: HttpClient = None):
        self.client = http_client or HttpClient()
        self.api_base = NTA_API_BASE

    def fetch_new_corporations(self, from_date: str = None, to_date: str = None) -> list:
        """
        指定期間の新規設立法人を取得する

        Args:
            from_date: 開始日 (YYYY-MM-DD)、デフォルトは7日前
            to_date: 終了日 (YYYY-MM-DD)、デフォルトは今日

        Returns:
            法人情報のリスト
        """
        if not NTA_APP_ID:
            logger.warning("NTA_APP_ID is not set. Skipping NTA API fetch.")
            return []

        if not from_date:
            from_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
        if not to_date:
            to_date = datetime.now().strftime("%Y-%m-%d")

        logger.info(f"Fetching new corporations from {from_date} to {to_date}")
        corporations = []
        page = 1

        while True:
            params = {
                "id": NTA_APP_ID,
                "from": from_date,
                "to": to_date,
                "type": "02",  # 新規設立
                "divide": page,
            }

            try:
                response = self.client.get(f"{self.api_base}/num", params=params)
                corps, has_more = self._parse_response(response.text)
                corporations.extend(corps)
                logger.info(f"Page {page}: fetched {len(corps)} corporations")

                if not has_more:
                    break
                page += 1
            except Exception as e:
                logger.error(f"Failed to fetch page {page}: {e}")
                break

        logger.info(f"Total fetched: {len(corporations)} corporations")
        return corporations

    def fetch_corporation_by_number(self, corporate_number: str) -> dict:
        """法人番号で法人情報を取得"""
        if not NTA_APP_ID:
            logger.warning("NTA_APP_ID is not set.")
            return {}

        params = {
            "id": NTA_APP_ID,
            "number": corporate_number,
            "type": "02",
            "history": "0",
        }

        try:
            response = self.client.get(f"{self.api_base}/num", params=params)
            corps, _ = self._parse_response(response.text)
            return corps[0] if corps else {}
        except Exception as e:
            logger.error(f"Failed to fetch corporation {corporate_number}: {e}")
            return {}

    def _parse_response(self, xml_text: str) -> tuple:
        """APIレスポンスXMLをパースする"""
        corporations = []
        has_more = False

        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as e:
            logger.error(f"XML parse error: {e}")
            return corporations, has_more

        # divideNumberを確認（ページネーション）
        last_update = root.find(".//lastUpdateDate")
        divide_number = root.find(".//divideNumber")
        divide_size = root.find(".//divideSize")

        if divide_number is not None and divide_size is not None:
            try:
                current = int(divide_number.text)
                total = int(divide_size.text)
                has_more = current < total
            except (ValueError, TypeError):
                pass

        for corp_elem in root.findall(".//corporation"):
            corp = {
                "corporate_number": self._get_text(corp_elem, "corporateNumber"),
                "name": self._get_text(corp_elem, "name"),
                "name_kana": self._get_text(corp_elem, "furigana"),
                "entity_type": self._classify_entity_type(
                    self._get_text(corp_elem, "kind")
                ),
                "prefecture": self._get_text(corp_elem, "prefectureName"),
                "city": self._get_text(corp_elem, "cityName"),
                "address": self._get_text(corp_elem, "streetNumber"),
                "established_date": self._get_text(corp_elem, "updateDate"),
                "source": "nta_api",
            }
            if corp["corporate_number"]:
                corporations.append(corp)

        return corporations, has_more

    @staticmethod
    def _get_text(elem, tag: str) -> str:
        child = elem.find(tag)
        return child.text.strip() if child is not None and child.text else ""

    @staticmethod
    def _classify_entity_type(kind_code: str) -> str:
        """法人種別コードを名称に変換"""
        kind_map = {
            "101": "株式会社",
            "201": "有限会社",
            "301": "合名会社",
            "302": "合資会社",
            "303": "合同会社",
            "399": "その他の設立登記法人",
        }
        return kind_map.get(kind_code, kind_code)
