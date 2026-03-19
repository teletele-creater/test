"""HTTP通信ユーティリティ"""
import time
import requests
from config.settings import REQUEST_TIMEOUT, REQUEST_DELAY, MAX_RETRIES, USER_AGENT
from src.utils.logger import setup_logger

logger = setup_logger("http_client")


class HttpClient:
    """レート制限付きHTTPクライアント"""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})
        self._last_request_time = 0

    def _wait_for_rate_limit(self):
        """リクエスト間隔を守る"""
        elapsed = time.time() - self._last_request_time
        if elapsed < REQUEST_DELAY:
            time.sleep(REQUEST_DELAY - elapsed)

    def get(self, url: str, params: dict = None, headers: dict = None,
            timeout: int = None) -> requests.Response:
        """GETリクエスト（リトライ付き）"""
        self._wait_for_rate_limit()

        for attempt in range(MAX_RETRIES):
            try:
                response = self.session.get(
                    url,
                    params=params,
                    headers=headers,
                    timeout=timeout or REQUEST_TIMEOUT,
                )
                self._last_request_time = time.time()
                response.raise_for_status()
                return response
            except requests.exceptions.RequestException as e:
                logger.warning(f"Request failed (attempt {attempt + 1}/{MAX_RETRIES}): {e}")
                if attempt < MAX_RETRIES - 1:
                    wait = 2 ** (attempt + 1)
                    logger.info(f"Retrying in {wait}s...")
                    time.sleep(wait)
                else:
                    raise

    def get_json(self, url: str, params: dict = None, headers: dict = None) -> dict:
        """JSONレスポンスを取得"""
        response = self.get(url, params=params, headers=headers)
        return response.json()

    def get_text(self, url: str, params: dict = None, headers: dict = None) -> str:
        """テキストレスポンスを取得"""
        response = self.get(url, params=params, headers=headers)
        return response.text

    def get_xml(self, url: str, params: dict = None):
        """XMLレスポンスを取得してパース"""
        from bs4 import BeautifulSoup
        text = self.get_text(url, params=params)
        return BeautifulSoup(text, "lxml-xml")
