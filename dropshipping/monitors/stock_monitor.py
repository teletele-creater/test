"""
フェーズ2: 在庫監視スクリプト

DBに登録された「出品中（listed）」の商品について、
Amazonの在庫状況を定期的にチェックし、在庫切れ時に通知を送る。

改善点:
- 利益がしきい値未満の商品は通知をスキップ
- 同じ商品への重複通知を防止
- ページ読み込みエラー時のリトライ処理
"""

import asyncio

from playwright.async_api import async_playwright

from ..scrapers.amazon_scraper import _check_stock
from ..utils.config import config
from ..utils.database import (
    get_listed_items,
    init_db,
    is_already_notified,
    update_item_status,
    update_stock_status,
)
from ..utils.helpers import format_price, get_logger, scraping_delay
from .notifier import send_notification

logger = get_logger(__name__)

MAX_PAGE_RETRIES = 2


async def check_single_item(page, item: dict) -> bool | None:
    """
    単一商品の在庫をチェック（リトライ付き）

    Returns:
        True: 在庫あり, False: 在庫なし, None: チェック失敗
    """
    url = item["amazon_url"]
    title = item["amazon_title"] or "(タイトル不明)"

    for attempt in range(MAX_PAGE_RETRIES + 1):
        try:
            logger.info(f"在庫チェック中: {title}")
            await page.goto(url, timeout=config.scraping.page_timeout, wait_until="domcontentloaded")
            await scraping_delay(config.scraping.min_delay, config.scraping.max_delay)

            in_stock = await _check_stock(page)
            return in_stock

        except Exception as e:
            if attempt < MAX_PAGE_RETRIES:
                wait = 2 ** (attempt + 1)
                logger.warning(f"在庫チェック失敗（リトライ {attempt + 1}/{MAX_PAGE_RETRIES}）: {title} - {e}")
                await asyncio.sleep(wait)
            else:
                logger.error(f"在庫チェック失敗（リトライ上限）: {title} - {e}")
                return None


async def run_stock_check():
    """出品中の全商品の在庫を一括チェック"""
    init_db()
    items = get_listed_items()

    if not items:
        logger.info("出品中の商品はありません。")
        return

    logger.info(f"在庫チェック開始: {len(items)}件の商品を確認します")

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

    out_of_stock_count = 0

    try:
        for item in items:
            in_stock = await check_single_item(page, item)

            if in_stock is None:
                continue

            item_id = item["id"]
            title = item["amazon_title"] or "(タイトル不明)"
            url = item["amazon_url"]
            profit = item.get("estimated_profit") or 0

            # 在庫チェック履歴を記録
            update_stock_status(item_id, in_stock)

            if not in_stock:
                out_of_stock_count += 1
                logger.warning(f"在庫切れ検出: {title}")

                # ステータスを「在庫なし」に更新
                update_item_status(item_id, "out_of_stock")

                # 利益がしきい値未満の商品は通知しない
                if profit < config.profit.min_profit_threshold:
                    logger.info(
                        f"通知スキップ（利益基準未満: {format_price(profit)}）: {title}"
                    )
                    continue

                # 同じ商品への重複通知を防止
                if is_already_notified(item_id, "out_of_stock"):
                    logger.info(f"通知スキップ（通知済み）: {title}")
                    continue

                # 通知を送信
                message = (
                    f"【警告】在庫切れ：{title}\n"
                    f"URL: {url}\n"
                    f"推定利益: {format_price(profit)}\n"
                    f"メルカリでの出品停止を推奨します。"
                )
                await send_notification(item_id, message, notification_type="out_of_stock")
            else:
                logger.info(f"在庫あり: {title}")

            await scraping_delay(config.scraping.min_delay, config.scraping.max_delay)

    finally:
        await browser.close()
        await pw.stop()

    logger.info(
        f"在庫チェック完了: {len(items)}件中 {out_of_stock_count}件が在庫切れ"
    )


async def start_monitoring():
    """在庫監視ループを開始（設定間隔で繰り返し実行）"""
    interval = config.monitor.check_interval
    logger.info(
        f"在庫監視を開始します（チェック間隔: {interval}秒 = {interval // 60}分）"
    )

    while True:
        try:
            await run_stock_check()
        except Exception as e:
            logger.error(f"在庫チェックサイクルでエラー: {e}")

        logger.info(f"次のチェックまで{interval // 60}分待機中...")
        await asyncio.sleep(interval)
