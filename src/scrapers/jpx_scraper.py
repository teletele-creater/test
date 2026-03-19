"""
JPX（日本取引所グループ）上場企業リストスクレイパー
上場企業一覧をExcelファイルから取得
"""
import io

import pandas as pd

from config.settings import JPX_LISTED_COMPANIES_URL
from src.utils.http_client import HttpClient
from src.utils.logger import setup_logger

logger = setup_logger("jpx_scraper")


class JpxScraper:
    """JPXから上場企業一覧を取得"""

    def __init__(self, http_client: HttpClient = None):
        self.client = http_client or HttpClient()

    def fetch_listed_companies(self) -> list:
        """JPXの上場企業一覧をダウンロードしてパース"""
        try:
            response = self.client.get(JPX_LISTED_COMPANIES_URL, timeout=60)
            df = pd.read_excel(io.BytesIO(response.content), header=0)
            companies = self._parse_dataframe(df)
            logger.info(f"Fetched {len(companies)} listed companies from JPX")
            return companies
        except Exception as e:
            logger.error(f"Failed to fetch JPX listed companies: {e}")
            return []

    def _parse_dataframe(self, df: pd.DataFrame) -> list:
        """DataFrameから企業情報を抽出"""
        companies = []

        # カラム名の正規化（JPXのExcelファイル形式に対応）
        col_map = self._detect_columns(df)
        if not col_map:
            logger.error("Could not detect column mapping for JPX data")
            return []

        for _, row in df.iterrows():
            try:
                code = str(row[col_map["code"]]).strip()
                if not code or len(code) < 4:
                    continue

                company = {
                    "code": code[:4],
                    "name": str(row.get(col_map.get("name", ""), "")).strip(),
                    "market": str(row.get(col_map.get("market", ""), "")).strip(),
                    "sector": str(row.get(col_map.get("sector", ""), "")).strip(),
                }
                companies.append(company)
            except (KeyError, ValueError):
                continue

        return companies

    @staticmethod
    def _detect_columns(df: pd.DataFrame) -> dict:
        """カラム名を自動検出"""
        col_map = {}
        columns = list(df.columns)

        for col in columns:
            col_str = str(col)
            if "コード" in col_str or "銘柄コード" in col_str:
                col_map["code"] = col
            elif "銘柄名" in col_str or "会社名" in col_str:
                col_map["name"] = col
            elif "市場" in col_str:
                col_map["market"] = col
            elif "業種" in col_str or "33業種" in col_str:
                col_map["sector"] = col

        if "code" not in col_map and len(columns) >= 2:
            col_map["code"] = columns[1]
            col_map["name"] = columns[2] if len(columns) > 2 else columns[1]

        return col_map
