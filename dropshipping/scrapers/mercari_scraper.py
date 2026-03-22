"""メルカリ売切相場スクレイパー（Playwright使用）"""

import re
from dataclasses import dataclass

from playwright.async_api import Page, async_playwright

from ..utils.config import config
from ..utils.helpers import get_logger, scraping_delay

logger = get_logger(__name__)

MERCARI_SEARCH_URL = "https://jp.mercari.com/search"


@dataclass
class MercariSoldItem:
    """メルカリの売切商品データ"""
    title: str
    price: int
    url: str


@dataclass
class MercariMarketData:
    """メルカリの相場データ"""
    keyword: str
    sold_items: list[MercariSoldItem]
    avg_sold_price: int
    min_price: int
    max_price: int
    sold_count: int


async def scrape_mercari_sold_prices(
    keyword: str,
    count: int = 10,
    page: Page | None = None,
) -> MercariMarketData | None:
    """
    メルカリで売切れ商品の相場を取得

    Args:
        keyword: 検索キーワード
        count: 取得する売切れ件数
        page: 既存のPlaywrightページ
    """
    own_browser = page is None
    pw = None
    browser = None

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
        # メルカリで「売り切れ」フィルターをかけて検索
        # status=sold_out でフィルタリング
        search_params = f"?keyword={keyword}&status=sold_out&sort=created_time&order=desc"
        url = f"{MERCARI_SEARCH_URL}{search_params}"

        logger.info(f"メルカリ売切相場を検索中: {keyword}")
        await page.goto(url, timeout=config.scraping.page_timeout, wait_until="domcontentloaded")
        await scraping_delay(config.scraping.min_delay, config.scraping.max_delay)

        sold_items: list[MercariSoldItem] = []

        # 商品カード要素を取得
        # メルカリの検索結果ページの構造に合わせたセレクタ
        item_selectors = [
            "[data-testid='item-cell']",
            "li[data-testid='item-cell']",
            "div[data-testid='search-result'] li",
            "#item-grid li",
            "mer-item-thumbnail",
        ]

        items = []
        for selector in item_selectors:
            items = await page.locator(selector).all()
            if items:
                break

        if not items:
            # フォールバック: リンク要素から直接取得
            items = await page.locator("a[href*='/item/']").all()

        for item_elem in items[:count]:
            try:
                # 価格の取得
                price_text = None
                price_selectors = [
                    "[class*='price']",
                    "[class*='Price']",
                    "span[class*='number']",
                    "mer-price",
                ]
                for ps in price_selectors:
                    try:
                        price_elem = item_elem.locator(ps).first
                        if await price_elem.is_visible(timeout=1000):
                            price_text = await price_elem.text_content()
                            if price_text:
                                break
                    except Exception:
                        continue

                if not price_text:
                    # item_elem全体のテキストから価格を探す
                    full_text = await item_elem.text_content() or ""
                    price_match = re.search(r"[¥￥][\d,]+", full_text)
                    if price_match:
                        price_text = price_match.group()

                if not price_text:
                    continue

                numbers = re.findall(r"[\d,]+", price_text)
                if not numbers:
                    continue
                price = int(numbers[0].replace(",", ""))

                # タイトルの取得
                title = ""
                try:
                    title_elem = item_elem.locator("span, [class*='name'], [class*='title']").first
                    title = (await title_elem.text_content() or "").strip()
                except Exception:
                    pass

                # URLの取得
                item_url = ""
                try:
                    link = item_elem.locator("a[href*='/item/']").first
                    href = await link.get_attribute("href")
                    if href:
                        item_url = href if href.startswith("http") else f"https://jp.mercari.com{href}"
                except Exception:
                    try:
                        href = await item_elem.get_attribute("href")
                        if href:
                            item_url = href if href.startswith("http") else f"https://jp.mercari.com{href}"
                    except Exception:
                        pass

                sold_items.append(MercariSoldItem(title=title, price=price, url=item_url))

            except Exception as e:
                logger.debug(f"売切商品の解析をスキップ: {e}")
                continue

        if not sold_items:
            logger.warning(f"メルカリで売切データが見つかりませんでした: {keyword}")
            return None

        prices = [item.price for item in sold_items]
        avg_price = int(sum(prices) / len(prices))

        result = MercariMarketData(
            keyword=keyword,
            sold_items=sold_items,
            avg_sold_price=avg_price,
            min_price=min(prices),
            max_price=max(prices),
            sold_count=len(sold_items),
        )

        logger.info(
            f"メルカリ相場取得完了: {keyword} | "
            f"平均: ¥{avg_price:,} | "
            f"件数: {len(sold_items)} | "
            f"範囲: ¥{min(prices):,}～¥{max(prices):,}"
        )

        return result

    except Exception as e:
        logger.error(f"メルカリスクレイピング中にエラー: {e}")
        return None
    finally:
        if own_browser:
            if browser:
                await browser.close()
            if pw:
                await pw.stop()
