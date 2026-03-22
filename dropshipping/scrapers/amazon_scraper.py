"""Amazon商品情報スクレイパー（Playwright使用）"""

import asyncio
import re
from dataclasses import dataclass

from playwright.async_api import Page, async_playwright

from ..utils.config import config
from ..utils.helpers import extract_asin, get_logger, scraping_delay

MAX_PAGE_RETRIES = 2

logger = get_logger(__name__)


@dataclass
class AmazonProduct:
    """Amazon商品データ"""
    url: str
    title: str | None = None
    price: int | None = None
    in_stock: bool = False
    asin: str | None = None


async def _extract_price(page: Page) -> int | None:
    """ページから価格を抽出"""
    # 複数のセレクタを試行（Amazonはレイアウトが頻繁に変わるため）
    price_selectors = [
        "#priceblock_ourprice",
        "#priceblock_dealprice",
        "span.a-price span.a-offscreen",
        "#corePrice_feature_div span.a-price span.a-offscreen",
        "#apex_offerDisplay_desktop span.a-price span.a-offscreen",
        ".a-price .a-offscreen",
        "#price_inside_buybox",
        "#newBuyBoxPrice",
    ]

    for selector in price_selectors:
        try:
            elem = page.locator(selector).first
            if await elem.is_visible(timeout=1000):
                text = await elem.text_content()
                if text:
                    # 「￥1,234」「¥1,234」「1,234円」などから数値を抽出
                    numbers = re.findall(r"[\d,]+", text.replace(" ", ""))
                    if numbers:
                        return int(numbers[0].replace(",", ""))
        except Exception:
            continue

    return None


async def _check_stock(page: Page) -> bool:
    """在庫があるかチェック"""
    # 在庫切れの判定テキスト
    out_of_stock_texts = [
        "現在在庫切れです",
        "この商品は現在お取り扱いできません",
        "在庫切れ",
        "Currently unavailable",
        "Out of Stock",
    ]

    page_text = await page.text_content("body") or ""
    for text in out_of_stock_texts:
        if text in page_text:
            return False

    # 「カートに入れる」ボタンの存在チェック
    add_to_cart_selectors = [
        "#add-to-cart-button",
        "#addToCart input[type='submit']",
        "input[name='submit.add-to-cart']",
    ]
    for selector in add_to_cart_selectors:
        try:
            elem = page.locator(selector).first
            if await elem.is_visible(timeout=2000):
                return True
        except Exception:
            continue

    return False


async def scrape_amazon_product(url: str, page: Page | None = None) -> AmazonProduct:
    """
    Amazon商品ページをスクレイピングして情報を取得

    Args:
        url: Amazon商品URL
        page: 既存のPlaywrightページ（None時は新規作成）
    """
    product = AmazonProduct(url=url, asin=extract_asin(url))
    own_browser = page is None

    if own_browser:
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
        for attempt in range(MAX_PAGE_RETRIES + 1):
            try:
                logger.info(f"Amazon商品ページにアクセス中: {url}")
                await page.goto(url, timeout=config.scraping.page_timeout, wait_until="domcontentloaded")
                await scraping_delay(config.scraping.min_delay, config.scraping.max_delay)
                break  # 成功
            except Exception as e:
                if attempt < MAX_PAGE_RETRIES:
                    wait = 2 ** (attempt + 1)
                    logger.warning(f"ページ読み込み失敗（リトライ {attempt + 1}/{MAX_PAGE_RETRIES}）: {e}")
                    await asyncio.sleep(wait)
                else:
                    raise

        # 商品タイトルの取得
        title_selectors = ["#productTitle", "#title span"]
        for selector in title_selectors:
            try:
                elem = page.locator(selector).first
                if await elem.is_visible(timeout=2000):
                    product.title = (await elem.text_content() or "").strip()
                    if product.title:
                        break
            except Exception:
                continue

        # 価格の取得
        product.price = await _extract_price(page)

        # 在庫チェック
        product.in_stock = await _check_stock(page)

        logger.info(
            f"取得完了: {product.title or '(タイトル取得失敗)'} | "
            f"価格: {product.price or '取得失敗'} | "
            f"在庫: {'あり' if product.in_stock else 'なし'}"
        )

    except Exception as e:
        logger.error(f"Amazon商品のスクレイピング中にエラー: {e}")
    finally:
        if own_browser:
            await browser.close()
            await pw.stop()

    return product


async def scrape_amazon_products(urls: list[str]) -> list[AmazonProduct]:
    """複数のAmazon商品を順次スクレイピング"""
    products = []
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
        for url in urls:
            product = await scrape_amazon_product(url, page)
            products.append(product)
            await scraping_delay(config.scraping.min_delay, config.scraping.max_delay)
    finally:
        await browser.close()
        await pw.stop()

    return products


async def search_amazon_by_keyword(keyword: str, max_results: int = 10) -> list[str]:
    """キーワードでAmazon商品を検索し、URLリストを返す"""
    urls = []
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
        search_url = f"https://www.amazon.co.jp/s?k={keyword}"
        logger.info(f"Amazon検索中: {keyword}")
        await page.goto(search_url, timeout=config.scraping.page_timeout, wait_until="domcontentloaded")
        await scraping_delay()

        # 検索結果から商品リンクを取得
        links = await page.locator(
            "div[data-component-type='s-search-result'] h2 a"
        ).all()

        for link in links[:max_results]:
            href = await link.get_attribute("href")
            if href:
                if href.startswith("/"):
                    href = f"https://www.amazon.co.jp{href}"
                urls.append(href)

        logger.info(f"検索結果: {len(urls)}件の商品URLを取得")
    except Exception as e:
        logger.error(f"Amazon検索中にエラー: {e}")
    finally:
        await browser.close()
        await pw.stop()

    return urls
