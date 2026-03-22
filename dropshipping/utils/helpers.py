"""共通ヘルパー関数"""

import asyncio
import logging
import random
import re
from urllib.parse import urlparse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


async def human_delay(min_sec: float = 1.0, max_sec: float = 3.0):
    """人間の操作速度に近づけるランダムな待機"""
    delay = random.uniform(min_sec, max_sec)
    await asyncio.sleep(delay)


async def scraping_delay(min_sec: float = 2.0, max_sec: float = 5.0):
    """スクレイピング時のサイト負荷軽減用待機"""
    delay = random.uniform(min_sec, max_sec)
    await asyncio.sleep(delay)


def extract_asin(url: str) -> str | None:
    """AmazonのURLからASINを抽出"""
    patterns = [
        r"/dp/([A-Z0-9]{10})",
        r"/gp/product/([A-Z0-9]{10})",
        r"/ASIN/([A-Z0-9]{10})",
        r"/product/([A-Z0-9]{10})",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def is_amazon_url(url: str) -> bool:
    """AmazonのURLかどうかを判定"""
    parsed = urlparse(url)
    return "amazon" in parsed.hostname if parsed.hostname else False


def format_price(price: int) -> str:
    """価格をフォーマット表示"""
    return f"¥{price:,}"


def calculate_profit(
    mercari_price: int,
    amazon_price: int,
    fee_rate: float = 0.10,
    shipping_cost: int = 700,
) -> int:
    """
    利益を計算
    利益 = (メルカリ売価 × (1 - 手数料率) - 送料) - Amazon仕入価格
    """
    net_mercari = mercari_price * (1 - fee_rate) - shipping_cost
    return int(net_mercari - amazon_price)
