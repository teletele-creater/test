"""
フェーズ3: メルカリ自動公開停止スクリプト

メルカリにログインし、在庫切れ商品の出品を自動停止する。
"""

import json
from pathlib import Path

from playwright.async_api import Page, async_playwright

from ..utils.config import config
from ..utils.database import (
    get_out_of_stock_listed_items,
    init_db,
    update_item_status,
)
from ..utils.helpers import get_logger, human_delay

logger = get_logger(__name__)

MERCARI_BASE_URL = "https://jp.mercari.com"
MERCARI_LOGIN_URL = f"{MERCARI_BASE_URL}/signin"
MERCARI_MYPAGE_URL = f"{MERCARI_BASE_URL}/mypage"
MERCARI_LISTINGS_URL = f"{MERCARI_BASE_URL}/mypage/listings"


async def _save_cookies(context, cookie_path: Path):
    """ブラウザのCookieをファイルに保存"""
    cookies = await context.cookies()
    cookie_path.write_text(json.dumps(cookies, ensure_ascii=False, indent=2))
    logger.info(f"Cookieを保存しました: {cookie_path}")


async def _load_cookies(context, cookie_path: Path) -> bool:
    """保存済みCookieを読み込んでセッション復元を試みる"""
    if not cookie_path.exists():
        return False

    try:
        cookies = json.loads(cookie_path.read_text())
        await context.add_cookies(cookies)
        logger.info("保存済みCookieを読み込みました")
        return True
    except Exception as e:
        logger.warning(f"Cookie読み込み失敗: {e}")
        return False


async def _is_logged_in(page: Page) -> bool:
    """メルカリにログイン済みかチェック"""
    try:
        await page.goto(MERCARI_MYPAGE_URL, timeout=config.scraping.page_timeout)
        await human_delay(config.mercari.human_min_delay, config.mercari.human_max_delay)

        # マイページのコンテンツが表示されるか確認
        # ログインしていない場合はサインインページにリダイレクトされる
        current_url = page.url
        if "signin" in current_url or "login" in current_url:
            return False

        # マイページ要素の確認
        mypage_selectors = [
            "[data-testid='mypage']",
            "text=出品した商品",
            "text=マイページ",
        ]
        for selector in mypage_selectors:
            try:
                elem = page.locator(selector).first
                if await elem.is_visible(timeout=3000):
                    return True
            except Exception:
                continue

        return True  # リダイレクトされていなければログイン済みと判断
    except Exception:
        return False


async def login_mercari(page: Page, context) -> bool:
    """
    メルカリにログイン

    二段階認証が必要な場合はコンソールで入力を待機する。
    """
    email = config.mercari.email
    password = config.mercari.password

    if not email or not password:
        logger.error(
            "メルカリのログイン情報が設定されていません。\n"
            ".envファイルにMERCARI_EMAILとMERCARI_PASSWORDを設定してください。"
        )
        return False

    # Cookie復元を試みる
    cookie_loaded = await _load_cookies(context, config.mercari.cookie_path)
    if cookie_loaded:
        if await _is_logged_in(page):
            logger.info("Cookieによるセッション復元成功")
            return True
        logger.info("Cookie期限切れ。再ログインします。")

    # ログインページへ
    logger.info("メルカリにログイン中...")
    await page.goto(MERCARI_LOGIN_URL, timeout=config.scraping.page_timeout)
    await human_delay(config.mercari.human_min_delay, config.mercari.human_max_delay)

    # メールアドレスでログインを選択
    try:
        email_login_btn = page.locator("text=メールアドレスでログイン").first
        if await email_login_btn.is_visible(timeout=3000):
            await email_login_btn.click()
            await human_delay()
    except Exception:
        pass

    # メールアドレス入力
    email_selectors = [
        "input[name='email']",
        "input[type='email']",
        "input[placeholder*='メール']",
        "#email",
    ]
    for selector in email_selectors:
        try:
            elem = page.locator(selector).first
            if await elem.is_visible(timeout=2000):
                await elem.fill(email)
                await human_delay(0.5, 1.0)
                break
        except Exception:
            continue

    # パスワード入力
    password_selectors = [
        "input[name='password']",
        "input[type='password']",
        "#password",
    ]
    for selector in password_selectors:
        try:
            elem = page.locator(selector).first
            if await elem.is_visible(timeout=2000):
                await elem.fill(password)
                await human_delay(0.5, 1.0)
                break
        except Exception:
            continue

    # ログインボタンをクリック
    login_btn_selectors = [
        "button[type='submit']",
        "button:has-text('ログイン')",
        "button:has-text('Sign in')",
    ]
    for selector in login_btn_selectors:
        try:
            btn = page.locator(selector).first
            if await btn.is_visible(timeout=2000):
                await btn.click()
                break
        except Exception:
            continue

    await human_delay(2.0, 4.0)

    # 二段階認証チェック
    two_fa_selectors = [
        "input[name='code']",
        "input[placeholder*='認証コード']",
        "input[placeholder*='verification']",
        "text=認証コード",
        "text=確認コード",
    ]

    for selector in two_fa_selectors:
        try:
            elem = page.locator(selector).first
            if await elem.is_visible(timeout=5000):
                logger.info("二段階認証が必要です。")
                code = input("📱 認証コードを入力してください: ").strip()

                code_input = page.locator(
                    "input[name='code'], input[type='tel'], input[type='number']"
                ).first
                await code_input.fill(code)
                await human_delay(0.5, 1.0)

                # 認証ボタンをクリック
                verify_btn = page.locator(
                    "button[type='submit'], button:has-text('認証'), button:has-text('確認')"
                ).first
                await verify_btn.click()
                await human_delay(2.0, 4.0)
                break
        except Exception:
            continue

    # ログイン成功確認
    if await _is_logged_in(page):
        logger.info("メルカリログイン成功")
        await _save_cookies(context, config.mercari.cookie_path)
        return True

    logger.error("メルカリログインに失敗しました")
    return False


async def _find_and_pause_listing(page: Page, item_name: str) -> bool:
    """
    出品一覧から商品を見つけて公開停止する

    Args:
        page: Playwrightページ
        item_name: 商品名（部分一致で検索）
    """
    logger.info(f"メルカリ出品一覧で商品を検索中: {item_name}")

    await page.goto(MERCARI_LISTINGS_URL, timeout=config.scraping.page_timeout)
    await human_delay(config.mercari.human_min_delay, config.mercari.human_max_delay)

    # 出品中タブを選択
    try:
        listing_tab = page.locator("text=出品中").first
        if await listing_tab.is_visible(timeout=3000):
            await listing_tab.click()
            await human_delay()
    except Exception:
        pass

    # 商品名で対象を探す
    # キーワードの一部で一致する商品を探す
    search_terms = item_name.split()[:3]  # 最初の3単語を使う

    found = False
    for term in search_terms:
        if len(term) < 2:
            continue
        try:
            items = await page.locator(f"a:has-text('{term}')").all()
            for item_elem in items:
                item_text = await item_elem.text_content() or ""
                # 部分一致チェック
                if any(t in item_text for t in search_terms if len(t) >= 2):
                    href = await item_elem.get_attribute("href")
                    if href and "/item/" in href:
                        # 商品の編集画面へ遷移
                        edit_url = href.replace("/item/", "/mypage/items/") + "/edit" \
                            if "/mypage/" not in href else href
                        if not edit_url.startswith("http"):
                            edit_url = f"{MERCARI_BASE_URL}{edit_url}"

                        logger.info(f"商品を発見: {item_text[:50]}...")
                        await page.goto(edit_url, timeout=config.scraping.page_timeout)
                        await human_delay(config.mercari.human_min_delay, config.mercari.human_max_delay)
                        found = True
                        break
            if found:
                break
        except Exception as e:
            logger.debug(f"商品検索中にエラー: {e}")
            continue

    if not found:
        # フォールバック: ページをスクロールしながら探す
        for _ in range(5):
            page_text = await page.text_content("body") or ""
            for term in search_terms:
                if len(term) >= 2 and term in page_text:
                    try:
                        link = page.locator(f"a:has-text('{term}')").first
                        await link.click()
                        await human_delay()
                        found = True
                        break
                    except Exception:
                        continue
            if found:
                break
            await page.evaluate("window.scrollBy(0, 500)")
            await human_delay(0.5, 1.0)

    if not found:
        logger.warning(f"商品が見つかりませんでした: {item_name}")
        return False

    # 公開停止ボタンを探してクリック
    pause_selectors = [
        "button:has-text('公開を停止する')",
        "button:has-text('出品を一時停止')",
        "button:has-text('公開停止')",
        "[data-testid='pause-button']",
        "text=公開を停止する",
    ]

    for selector in pause_selectors:
        try:
            btn = page.locator(selector).first
            if await btn.is_visible(timeout=3000):
                await btn.click()
                await human_delay(config.mercari.human_min_delay, config.mercari.human_max_delay)

                # 確認ダイアログがあれば承諾
                confirm_selectors = [
                    "button:has-text('はい')",
                    "button:has-text('OK')",
                    "button:has-text('停止する')",
                    "button:has-text('確認')",
                ]
                for cs in confirm_selectors:
                    try:
                        confirm_btn = page.locator(cs).first
                        if await confirm_btn.is_visible(timeout=2000):
                            await confirm_btn.click()
                            await human_delay()
                            break
                    except Exception:
                        continue

                logger.info(f"✅ 公開停止完了: {item_name[:50]}...")
                return True
        except Exception:
            continue

    logger.warning(f"公開停止ボタンが見つかりませんでした: {item_name}")
    return False


async def pause_out_of_stock_listings():
    """
    在庫切れ商品のメルカリ出品を自動停止

    items.dbで「out_of_stock」ステータスの商品を探し、
    メルカリで公開停止操作を行う。
    """
    init_db()
    items = get_out_of_stock_listed_items()

    if not items:
        logger.info("公開停止が必要な商品はありません。")
        return

    logger.info(f"公開停止対象: {len(items)}件")

    pw = await async_playwright().start()
    browser = await pw.chromium.launch(
        headless=False,  # メルカリ操作はヘッドフル推奨（CAPTCHA対策）
    )
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
        # ログイン
        if not await login_mercari(page, context):
            logger.error("メルカリログインに失敗したため、処理を中断します。")
            return

        paused_count = 0

        for item in items:
            title = item["amazon_title"] or item.get("mercari_keyword", "")
            if not title:
                logger.warning(f"商品名が不明なためスキップ: ID={item['id']}")
                continue

            success = await _find_and_pause_listing(page, title)

            if success:
                update_item_status(item["id"], "paused")
                paused_count += 1

            await human_delay(config.mercari.human_min_delay, config.mercari.human_max_delay)

        logger.info(f"公開停止完了: {len(items)}件中 {paused_count}件を停止")

        # Cookie更新保存
        await _save_cookies(context, config.mercari.cookie_path)

    finally:
        await browser.close()
        await pw.stop()
