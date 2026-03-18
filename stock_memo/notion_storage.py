"""
Notion ストレージ
分析結果を Notion データベースに保存する
"""

from notion_client import Client
from analyzer import Analysis
from config import NOTION_TOKEN, NOTION_DATABASE_ID


def _rt(text: str) -> list[dict]:
    """rich_text ブロックを生成するヘルパー"""
    return [{"type": "rich_text", "rich_text": [{"type": "text", "text": {"content": text[:2000]}}]}]


def save_to_notion(analysis: Analysis) -> str | None:
    """
    分析結果を Notion DB に1行追加する

    Returns:
        作成したページのID。失敗時は None。
    """
    if not NOTION_TOKEN or not NOTION_DATABASE_ID:
        return None

    client = Client(auth=NOTION_TOKEN)
    tweet = analysis.tweet
    jst_datetime = tweet.created_at.strftime("%Y-%m-%dT%H:%M:%S+09:00")

    backgrounds_text = "\n".join(f"・{bg}" for bg in analysis.backgrounds) if analysis.backgrounds else ""

    properties = {
        "銘柄名": {
            "title": [{"type": "text", "text": {"content": analysis.stock_name or analysis.stock_code}}]
        },
        "銘柄コード": {
            "rich_text": [{"type": "text", "text": {"content": analysis.stock_code}}]
        },
        "日時": {
            "date": {"start": jst_datetime}
        },
        "上昇理由": {
            "rich_text": [{"type": "text", "text": {"content": analysis.reason}}]
        },
        "キーワード": {
            "multi_select": [{"name": kw.strip()} for kw in analysis.keywords.split("、") if kw.strip()]
        },
        "背景": {
            "rich_text": [{"type": "text", "text": {"content": backgrounds_text[:2000]}}]
        },
    }

    try:
        response = client.pages.create(
            parent={"database_id": NOTION_DATABASE_ID},
            properties=properties,
        )
        page_id = response["id"]
        print(f"  [Notion] 保存完了: {analysis.stock_code} {analysis.stock_name} (page_id={page_id})")
        return page_id
    except Exception as e:
        print(f"  [Notion] 保存失敗: {e}")
        return None
