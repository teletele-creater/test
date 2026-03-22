"""
フェーズ1: 価格差リサーチツール

Amazon vs メルカリの価格差を調べて、利益の出る商品を見つける。
"""

import asyncio
import sys
from pathlib import Path

from playwright.async_api import async_playwright

from ..utils.config import config
from ..utils.database import (
    init_db,
    record_price_history,
    upsert_item,
)
from ..utils.helpers import (
    calculate_profit,
    format_price,
    get_logger,
    is_amazon_url,
    scraping_delay,
)
from .amazon_scraper import AmazonProduct, scrape_amazon_product, search_amazon_by_keyword
from .mercari_scraper import scrape_mercari_sold_prices

logger = get_logger(__name__)


def _display_result(
    product: AmazonProduct,
    mercari_keyword: str,
    mercari_avg_price: int,
    profit: int,
    shipping_cost: int,
):
    """リサーチ結果をコンソールに表示"""
    separator = "=" * 60
    print(f"\n{separator}")
    print(f"  💰 利益のある商品を発見！")
    print(f"{separator}")
    print(f"  商品名     : {product.title}")
    print(f"  ASIN       : {product.asin or '不明'}")
    print(f"  Amazon URL : {product.url}")
    print(f"  Amazon価格 : {format_price(product.price)}")
    print(f"  在庫状況   : {'あり ✅' if product.in_stock else 'なし ❌'}")
    print(f"  ─────────────────────────────")
    print(f"  メルカリ検索: {mercari_keyword}")
    print(f"  メルカリ相場: {format_price(mercari_avg_price)}")
    print(f"  送料       : {format_price(shipping_cost)}")
    print(f"  手数料(10%): {format_price(int(mercari_avg_price * config.profit.mercari_fee_rate))}")
    print(f"  ─────────────────────────────")
    print(f"  📈 推定利益 : {format_price(profit)}")
    print(f"{separator}\n")


async def research_single(
    amazon_url: str,
    mercari_keyword: str | None = None,
    shipping_cost: int | None = None,
) -> dict | None:
    """
    単一商品のリサーチ

    Args:
        amazon_url: Amazon商品URL
        mercari_keyword: メルカリ検索キーワード（Noneの場合はAmazonの商品名を使用）
        shipping_cost: 送料（Noneの場合はデフォルト値を使用）

    Returns:
        利益がしきい値以上の場合は商品情報のdict、それ以下はNone
    """
    if shipping_cost is None:
        shipping_cost = config.profit.default_shipping_cost

    pw = await async_playwright().start()
    browser = await pw.chromium.launch(headless=config.scraping.headless)
    context = await browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        locale="ja-JP",
    )
    page = await context.new_page()

    try:
        # Amazon商品情報を取得
        product = await scrape_amazon_product(amazon_url, page)

        if not product.price:
            logger.warning(f"Amazon価格を取得できませんでした: {amazon_url}")
            return None

        # メルカリ検索キーワードの決定
        keyword = mercari_keyword or product.title
        if not keyword:
            logger.warning("メルカリ検索キーワードが不明です")
            return None

        await scraping_delay(config.scraping.min_delay, config.scraping.max_delay)

        # メルカリ売切相場を取得
        mercari_data = await scrape_mercari_sold_prices(
            keyword, count=config.scraping.mercari_sold_count, page=page
        )

        if not mercari_data:
            logger.warning(f"メルカリ相場データがありません: {keyword}")
            return None

        # 利益計算
        profit = calculate_profit(
            mercari_price=mercari_data.avg_sold_price,
            amazon_price=product.price,
            fee_rate=config.profit.mercari_fee_rate,
            shipping_cost=shipping_cost,
        )

        # DBに保存
        item_id = upsert_item(
            amazon_url=amazon_url,
            amazon_title=product.title,
            amazon_price=product.price,
            amazon_in_stock=product.in_stock,
            amazon_asin=product.asin,
            mercari_keyword=keyword,
            mercari_avg_sold_price=mercari_data.avg_sold_price,
            mercari_sold_count=mercari_data.sold_count,
            estimated_profit=profit,
            shipping_cost=shipping_cost,
        )

        # 価格履歴を記録
        record_price_history(
            item_id=item_id,
            amazon_price=product.price,
            mercari_avg=mercari_data.avg_sold_price,
            profit=profit,
        )

        # 利益がしきい値以上なら表示
        if profit >= config.profit.min_profit_threshold:
            _display_result(
                product=product,
                mercari_keyword=keyword,
                mercari_avg_price=mercari_data.avg_sold_price,
                profit=profit,
                shipping_cost=shipping_cost,
            )
            return {
                "amazon_url": amazon_url,
                "title": product.title,
                "amazon_price": product.price,
                "mercari_avg_price": mercari_data.avg_sold_price,
                "profit": profit,
                "in_stock": product.in_stock,
            }
        else:
            logger.info(
                f"利益が基準未満: {product.title} | "
                f"利益: {format_price(profit)} "
                f"(基準: {format_price(config.profit.min_profit_threshold)})"
            )
            return None

    finally:
        await browser.close()
        await pw.stop()


async def research_urls(
    urls: list[str],
    mercari_keywords: dict[str, str] | None = None,
    shipping_cost: int | None = None,
) -> list[dict]:
    """
    複数のAmazon URLをリサーチ

    Args:
        urls: Amazon URLリスト
        mercari_keywords: URL→メルカリ検索キーワードのマッピング
        shipping_cost: 送料
    """
    if mercari_keywords is None:
        mercari_keywords = {}
    if shipping_cost is None:
        shipping_cost = config.profit.default_shipping_cost

    init_db()
    profitable = []

    pw = await async_playwright().start()
    browser = await pw.chromium.launch(headless=config.scraping.headless)
    context = await browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        ),
        locale="ja-JP",
    )
    page = await context.new_page()

    try:
        for i, url in enumerate(urls, 1):
            logger.info(f"リサーチ中 [{i}/{len(urls)}]: {url}")

            try:
                product = await scrape_amazon_product(url, page)

                if not product.price:
                    logger.warning(f"Amazon価格を取得できませんでした: {url}")
                    continue

                keyword = mercari_keywords.get(url) or product.title
                if not keyword:
                    logger.warning(f"メルカリ検索キーワードが不明です: {url}")
                    continue

                await scraping_delay(config.scraping.min_delay, config.scraping.max_delay)

                mercari_data = await scrape_mercari_sold_prices(
                    keyword, count=config.scraping.mercari_sold_count, page=page
                )

                if not mercari_data:
                    logger.warning(f"メルカリ相場データなし: {keyword}")
                    continue

                profit = calculate_profit(
                    mercari_price=mercari_data.avg_sold_price,
                    amazon_price=product.price,
                    fee_rate=config.profit.mercari_fee_rate,
                    shipping_cost=shipping_cost,
                )

                item_id = upsert_item(
                    amazon_url=url,
                    amazon_title=product.title,
                    amazon_price=product.price,
                    amazon_in_stock=product.in_stock,
                    amazon_asin=product.asin,
                    mercari_keyword=keyword,
                    mercari_avg_sold_price=mercari_data.avg_sold_price,
                    mercari_sold_count=mercari_data.sold_count,
                    estimated_profit=profit,
                    shipping_cost=shipping_cost,
                )

                record_price_history(
                    item_id=item_id,
                    amazon_price=product.price,
                    mercari_avg=mercari_data.avg_sold_price,
                    profit=profit,
                )

                if profit >= config.profit.min_profit_threshold:
                    _display_result(
                        product=product,
                        mercari_keyword=keyword,
                        mercari_avg_price=mercari_data.avg_sold_price,
                        profit=profit,
                        shipping_cost=shipping_cost,
                    )
                    profitable.append({
                        "amazon_url": url,
                        "title": product.title,
                        "amazon_price": product.price,
                        "mercari_avg_price": mercari_data.avg_sold_price,
                        "profit": profit,
                        "in_stock": product.in_stock,
                    })
                else:
                    logger.info(
                        f"利益基準未満: {product.title} | 利益: {format_price(profit)}"
                    )

            except Exception as e:
                logger.error(f"リサーチ中にエラー: {url} - {e}")
                continue

            await scraping_delay(config.scraping.min_delay, config.scraping.max_delay)
    finally:
        await browser.close()
        await pw.stop()

    print(f"\n{'=' * 60}")
    print(f"  リサーチ完了: {len(urls)}件中 {len(profitable)}件が利益基準をクリア")
    print(f"{'=' * 60}")

    return profitable


async def research_keyword(
    keyword: str,
    max_products: int = 10,
    shipping_cost: int | None = None,
) -> list[dict]:
    """
    キーワードベースでリサーチ

    Args:
        keyword: 検索キーワード
        max_products: 最大検索件数
        shipping_cost: 送料
    """
    init_db()
    logger.info(f"キーワードリサーチ開始: {keyword}")

    urls = await search_amazon_by_keyword(keyword, max_results=max_products)
    if not urls:
        logger.warning("Amazonの検索結果が見つかりませんでした")
        return []

    return await research_urls(urls, shipping_cost=shipping_cost)
