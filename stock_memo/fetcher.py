"""
X (Twitter) スクレイパー (Playwright使用)
@shodousan のポストをブラウザで取得し、株関連ポストをフィルタリングする
X API 不要・無料で動作
"""

import re
import json
import time
import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Optional
from config import TARGET_USERNAME, MAX_TWEETS


@dataclass
class Tweet:
    id: str
    text: str
    created_at: datetime
    stock_codes: list[str]  # ポスト内の銘柄コード (4桁数字)


def _extract_stock_codes(text: str) -> list[str]:
    """ポストから日本株の銘柄コード（4桁数字）を抽出する"""
    pattern = r'(?<!\d)(\d{4})(?!\d)'
    candidates = re.findall(pattern, text)
    codes = [c for c in candidates if 1000 <= int(c) <= 9999]
    return list(set(codes))


def _is_shodou_alert(text: str) -> bool:
    """【初動検知】企業名（銘柄コード）形式のツイートかどうかを判定する"""
    return bool(re.match(r'【初動検知】.+[（(]\d{4}[）)]', text))


def _is_today_jst(dt: datetime) -> bool:
    """datetimeが日本時間で今日かどうかを判定する"""
    jst = timezone(timedelta(hours=9))
    today = datetime.now(jst).date()
    return dt.astimezone(jst).date() == today


def _parse_twitter_date(date_str: str) -> datetime:
    """Xの日時文字列をdatetimeに変換する"""
    try:
        # ISO 8601形式 (例: 2024-01-15T12:34:56.000Z)
        return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    except Exception:
        return datetime.now(timezone.utc)


def _make_id(text: str, timestamp: str) -> str:
    """テキストとタイムスタンプからユニークIDを生成する"""
    raw = f"{timestamp}:{text[:50]}"
    return hashlib.md5(raw.encode()).hexdigest()[:16]


def fetch_tweets(since_id: Optional[str] = None, max_count: Optional[int] = None) -> list[Tweet]:
    """
    @shodousan の最新ポストをPlaywrightでスクレイピングして取得する

    Args:
        since_id: このID以降のポストのみ取得（差分取得用、ハッシュIDベース）

    Returns:
        株関連ポストのリスト
    """
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
    except ImportError:
        raise ImportError(
            "playwright がインストールされていません。\n"
            "以下を実行してください:\n"
            "  pip install playwright\n"
            "  playwright install chromium"
        )

    url = f"https://x.com/{TARGET_USERNAME}"
    print(f"[INFO] {url} をスクレイピング中...")

    tweets: list[Tweet] = []
    seen_ids: set[str] = set()

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox"]
        )
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            locale="ja-JP",
        )

        # XHRレスポンスからツイートJSONを横取りする
        intercepted: list[dict] = []

        def _on_response(response):
            if "UserTweets" in response.url or "UserMedia" in response.url:
                try:
                    body = response.json()
                    intercepted.append(body)
                except Exception:
                    pass

        page = context.new_page()
        page.on("response", _on_response)

        try:
            page.goto(url, wait_until="networkidle", timeout=30000)
        except PlaywrightTimeout:
            print("[WARN] ページ読み込みタイムアウト。取得済みデータで続行します")

        # スクロールしてさらに読み込む
        for _ in range(3):
            page.keyboard.press("End")
            time.sleep(2)

        browser.close()

    # --- XHRから取得したJSONを解析 ---
    # 先に固定ツイートIDを収集してから除外しつつ抽出
    all_pinned_ids: set[str] = set()
    for body in intercepted:
        all_pinned_ids |= _collect_pinned_ids(body)
    if all_pinned_ids:
        print(f"  [INFO] 固定ツイート {len(all_pinned_ids)} 件をスキップ: {all_pinned_ids}")
    for body in intercepted:
        _extract_from_json(body, tweets, seen_ids, all_pinned_ids)

    # XHRが取れなかった場合はDOMから直接取得を再試行
    if not tweets:
        print("[INFO] XHRキャプチャなし。DOM解析にフォールバック...")
        tweets = _fetch_via_dom(url, since_id)
        return tweets

    # 差分フィルタ
    if since_id:
        new_tweets = []
        for tw in tweets:
            if tw.id == since_id:
                break
            new_tweets.append(tw)
        tweets = new_tweets

    # 件数制限
    limit = max_count if max_count is not None else MAX_TWEETS
    tweets = tweets[:limit]

    print(f"[INFO] 【初動検知】当日ツイート: {len(tweets)} 件取得")
    return tweets


def _collect_pinned_ids(body) -> set:
    """JSONからピン留めツイートのIDを収集する（TimelinePinEntryを検索）"""
    pinned_ids: set[str] = set()

    def _walk(obj, in_pinned: bool):
        if isinstance(obj, dict):
            is_pinned = in_pinned or obj.get("type") == "TimelinePinEntry"
            if is_pinned and "legacy" in obj and "id_str" in obj.get("legacy", {}):
                pinned_ids.add(obj["legacy"]["id_str"])
            for v in obj.values():
                _walk(v, is_pinned)
        elif isinstance(obj, list):
            for item in obj:
                _walk(item, in_pinned)

    _walk(body, False)
    return pinned_ids


def _extract_from_json(body: dict, tweets: list, seen_ids: set, pinned_ids: set | None = None) -> None:
    """XのAPIレスポンスJSONからツイートを再帰的に抽出する"""
    if pinned_ids is None:
        pinned_ids = set()
    if isinstance(body, dict):
        # tweet_results → result → legacy にツイートデータがある
        if "legacy" in body and "full_text" in body.get("legacy", {}):
            legacy = body["legacy"]
            text = legacy.get("full_text", "")
            tweet_id = legacy.get("id_str") or legacy.get("conversation_id_str", "")
            created_str = legacy.get("created_at", "")

            # RTを除外
            if text.startswith("RT @"):
                return
            # 返信を除外（in_reply_to_user_id が設定されているもの）
            if legacy.get("in_reply_to_user_id_str"):
                return
            # 固定ツイートを除外
            if tweet_id in pinned_ids:
                print(f"  [SKIP] 固定ツイート: {text[:40]}...")
                return

            if tweet_id and tweet_id not in seen_ids:
                seen_ids.add(tweet_id)
                try:
                    created_at = datetime.strptime(
                        created_str, "%a %b %d %H:%M:%S +0000 %Y"
                    ).replace(tzinfo=timezone.utc)
                except Exception:
                    created_at = datetime.now(timezone.utc)

                # 【初動検知】形式でないツイートをスキップ
                if not _is_shodou_alert(text):
                    return
                # 当日のツイートでなければスキップ
                if not _is_today_jst(created_at):
                    return

                codes = _extract_stock_codes(text)
                tweets.append(Tweet(
                    id=tweet_id,
                    text=text,
                    created_at=created_at,
                    stock_codes=codes
                ))

        for v in body.values():
            _extract_from_json(v, tweets, seen_ids, pinned_ids)

    elif isinstance(body, list):
        for item in body:
            _extract_from_json(item, tweets, seen_ids, pinned_ids)


def _fetch_via_dom(url: str, since_id: Optional[str]) -> list[Tweet]:
    """
    DOMからポストテキストを取得するフォールバック
    XHRキャプチャが失敗した場合に使用する
    """
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
    except ImportError:
        return []

    tweets: list[Tweet] = []
    seen_texts: set[str] = set()

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox"]
        )
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            locale="ja-JP",
        )
        page = context.new_page()

        try:
            page.goto(url, wait_until="networkidle", timeout=30000)
        except PlaywrightTimeout:
            pass

        # スクロールして追加ロード
        for _ in range(4):
            page.keyboard.press("End")
            time.sleep(2)

        # ツイート要素を取得
        # data-testid="tweet" の中の tweetText を探す
        article_els = page.query_selector_all('article[data-testid="tweet"]')
        print(f"  [DEBUG] article要素数: {len(article_els)}")

        for article in article_els[:MAX_TWEETS * 2]:
            try:
                # 固定ツイートを除外（「ピン留め」インジケータの有無で判定）
                pinned_el = article.query_selector('[data-testid="socialContext"]')
                if pinned_el:
                    ctx_text = pinned_el.inner_text()
                    if "ピン" in ctx_text or "Pin" in ctx_text:
                        print(f"  [SKIP] 固定ツイート（DOM）をスキップ")
                        continue

                # テキスト取得
                text_el = article.query_selector('[data-testid="tweetText"]')
                if not text_el:
                    print(f"  [DEBUG] tweetText要素なし → スキップ")
                    continue
                text = text_el.inner_text()
                print(f"  [DEBUG] 取得テキスト: {text[:60]!r}")

                # RT・返信除外
                if text.startswith("RT @"):
                    print(f"  [DEBUG] RT → スキップ")
                    continue

                if text in seen_texts:
                    continue
                seen_texts.add(text)

                # 日時取得
                time_el = article.query_selector("time")
                date_str = time_el.get_attribute("datetime") if time_el else ""
                created_at = _parse_twitter_date(date_str) if date_str else datetime.now(timezone.utc)

                # ツイートURLからID取得
                link_el = article.query_selector('a[href*="/status/"]')
                tweet_id = ""
                if link_el:
                    href = link_el.get_attribute("href") or ""
                    m = re.search(r'/status/(\d+)', href)
                    if m:
                        tweet_id = m.group(1)
                if not tweet_id:
                    tweet_id = _make_id(text, date_str)

                # 【初動検知】形式でないツイートをスキップ
                if not _is_shodou_alert(text):
                    print(f"  [DEBUG] 【初動検知】形式でない → スキップ: {text[:40]!r}")
                    continue
                # 当日のツイートでなければスキップ
                if not _is_today_jst(created_at):
                    print(f"  [DEBUG] 当日でない ({created_at.date()}) → スキップ: {text[:40]!r}")
                    continue

                codes = _extract_stock_codes(text)
                tweets.append(Tweet(
                    id=tweet_id,
                    text=text,
                    created_at=created_at,
                    stock_codes=codes
                ))

            except Exception as e:
                print(f"  [WARN] 要素解析エラー: {e}")
                continue

        browser.close()

    # 差分フィルタ
    if since_id:
        new_tweets = []
        for tw in tweets:
            if tw.id == since_id:
                break
            new_tweets.append(tw)
        tweets = new_tweets

    tweets = tweets[:MAX_TWEETS]
    print(f"[INFO] DOM解析: 株関連 {len(tweets)} 件取得")
    return tweets


def fetch_latest_tweet() -> Optional[Tweet]:
    """最新の株関連ツイートを1件だけ取得する"""
    tweets = fetch_tweets(max_count=5)  # 直近5件から株関連を探す
    return tweets[0] if tweets else None
