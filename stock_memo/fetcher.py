"""
X (Twitter) API フェッチャー
@shodousan のツイートを取得し、株関連ツイートをフィルタリングする
"""

import re
import tweepy
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
from config import (
    X_BEARER_TOKEN, X_API_KEY, X_API_SECRET,
    X_ACCESS_TOKEN, X_ACCESS_TOKEN_SECRET,
    TARGET_USERNAME, MAX_TWEETS
)


@dataclass
class Tweet:
    id: str
    text: str
    created_at: datetime
    stock_codes: list[str]  # ツイート内の銘柄コード (4桁数字)


def _extract_stock_codes(text: str) -> list[str]:
    """ツイートから日本株の銘柄コード（4桁数字）を抽出する"""
    # 単独の4桁数字を抽出（6桁や5桁などを除外）
    pattern = r'(?<!\d)(\d{4})(?!\d)'
    candidates = re.findall(pattern, text)

    # 1000-9999の範囲に絞る（日本株の銘柄コード範囲）
    codes = [c for c in candidates if 1000 <= int(c) <= 9999]
    return list(set(codes))  # 重複除去


def _is_stock_related(text: str, codes: list[str]) -> bool:
    """ツイートが株関連かどうかを判定する"""
    if codes:
        return True

    # 株関連キーワードが含まれているかチェック
    stock_keywords = [
        '株', '銘柄', '上昇', '急騰', '高騰', 'ストップ高', '初動',
        '決算', '上方修正', '買い', 'テーマ株', '材料',
        '増益', '増収', '利益', 'PER', 'PBR',
    ]
    return any(kw in text for kw in stock_keywords)


def get_user_id(client: tweepy.Client, username: str) -> Optional[str]:
    """ユーザー名からユーザーIDを取得する"""
    try:
        response = client.get_user(username=username)
        if response.data:
            return response.data.id
        return None
    except tweepy.errors.TweepyException as e:
        print(f"[ERROR] ユーザーID取得失敗: {e}")
        return None


def fetch_tweets(since_id: Optional[str] = None) -> list[Tweet]:
    """
    @shodousan の最新ツイートを取得する

    Args:
        since_id: このID以降のツイートのみ取得（差分取得用）

    Returns:
        株関連ツイートのリスト
    """
    if not X_BEARER_TOKEN:
        raise ValueError(
            "X_BEARER_TOKEN が設定されていません。\n"
            ".env ファイルを作成して BEARER_TOKEN を設定してください。\n"
            "詳細は .env.example を参照。"
        )

    client = tweepy.Client(
        bearer_token=X_BEARER_TOKEN,
        consumer_key=X_API_KEY,
        consumer_secret=X_API_SECRET,
        access_token=X_ACCESS_TOKEN,
        access_token_secret=X_ACCESS_TOKEN_SECRET,
        wait_on_rate_limit=True
    )

    user_id = get_user_id(client, TARGET_USERNAME)
    if not user_id:
        raise ValueError(f"ユーザー @{TARGET_USERNAME} が見つかりません")

    print(f"[INFO] @{TARGET_USERNAME} (ID: {user_id}) のツイートを取得中...")

    kwargs = {
        "max_results": MAX_TWEETS,
        "tweet_fields": ["created_at", "text"],
        "exclude": ["retweets", "replies"],  # RTと返信を除外
    }
    if since_id:
        kwargs["since_id"] = since_id

    try:
        response = client.get_users_tweets(user_id, **kwargs)
    except tweepy.errors.Forbidden as e:
        raise PermissionError(
            "ツイートの取得に失敗しました。X API の Basic 以上のプランが必要です。\n"
            f"詳細: {e}"
        )

    if not response.data:
        print("[INFO] 新しいツイートはありません")
        return []

    tweets = []
    for tw in response.data:
        codes = _extract_stock_codes(tw.text)
        if _is_stock_related(tw.text, codes):
            created_at = tw.created_at or datetime.now(timezone.utc)
            tweets.append(Tweet(
                id=str(tw.id),
                text=tw.text,
                created_at=created_at,
                stock_codes=codes
            ))

    print(f"[INFO] {len(response.data)} ツイート取得、うち株関連: {len(tweets)} 件")
    return tweets
