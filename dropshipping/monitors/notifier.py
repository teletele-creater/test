"""通知モジュール（Discord Webhook / LINE Messaging API）

改善点:
- LINE Notify（2025年3月末廃止済み）→ LINE Messaging APIに移行
- Discord Webhook のレートリミット(429)対応 + リトライ
- 通知タイプの記録で重複通知防止に対応
"""

import asyncio

import httpx

from ..utils.config import config
from ..utils.database import record_notification
from ..utils.helpers import get_logger

logger = get_logger(__name__)

DISCORD_MAX_RETRIES = 3


async def send_discord_notification(item_id: int, message: str, notification_type: str = "general") -> bool:
    """Discord Webhookで通知を送信（レートリミット対応）"""
    webhook_url = config.monitor.discord_webhook_url
    if not webhook_url:
        logger.error("Discord Webhook URLが設定されていません。.envファイルを確認してください。")
        return False

    payload = {
        "content": message,
        "username": "在庫監視Bot",
    }

    try:
        async with httpx.AsyncClient() as client:
            for attempt in range(DISCORD_MAX_RETRIES):
                response = await client.post(
                    webhook_url,
                    json=payload,
                    timeout=10.0,
                )

                if response.status_code == 429:
                    # レートリミット: Retry-Afterヘッダーを尊重
                    retry_after = float(response.headers.get("Retry-After", 2))
                    logger.warning(
                        f"Discord レートリミット。{retry_after}秒後にリトライ "
                        f"({attempt + 1}/{DISCORD_MAX_RETRIES})"
                    )
                    await asyncio.sleep(retry_after)
                    continue

                response.raise_for_status()
                break
            else:
                logger.error("Discord通知: レートリミットによりリトライ上限に達しました")
                record_notification(item_id, notification_type, message, success=False)
                return False

        logger.info(f"Discord通知送信成功: {message[:50]}...")
        record_notification(item_id, notification_type, message, success=True)
        return True

    except Exception as e:
        logger.error(f"Discord通知送信失敗: {e}")
        record_notification(item_id, notification_type, message, success=False)
        return False


async def send_line_notification(item_id: int, message: str, notification_type: str = "general") -> bool:
    """LINE Messaging APIで通知を送信

    LINE Notifyは2025年3月末で廃止済みのため、
    LINE Messaging API (push message) を使用。
    必要な設定:
      - LINE_CHANNEL_ACCESS_TOKEN: チャネルアクセストークン
      - LINE_USER_ID: 送信先ユーザーID
    """
    token = config.monitor.line_channel_access_token
    user_id = config.monitor.line_user_id
    if not token or not user_id:
        logger.error(
            "LINE Messaging APIの設定が不足しています。\n"
            ".envファイルに LINE_CHANNEL_ACCESS_TOKEN と LINE_USER_ID を設定してください。\n"
            "※ LINE Notifyは2025年3月末で廃止されました。"
        )
        return False

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}",
    }
    payload = {
        "to": user_id,
        "messages": [
            {
                "type": "text",
                "text": message,
            }
        ],
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.line.me/v2/bot/message/push",
                headers=headers,
                json=payload,
                timeout=10.0,
            )

            if response.status_code == 429:
                logger.warning("LINE APIレートリミットに到達しました。しばらく待ってから再試行してください。")
                record_notification(item_id, notification_type, message, success=False)
                return False

            response.raise_for_status()

        logger.info(f"LINE通知送信成功: {message[:50]}...")
        record_notification(item_id, notification_type, message, success=True)
        return True

    except Exception as e:
        logger.error(f"LINE通知送信失敗: {e}")
        record_notification(item_id, notification_type, message, success=False)
        return False


async def send_notification(item_id: int, message: str, notification_type: str = "general") -> bool:
    """設定に基づいて通知を送信"""
    method = config.monitor.notification_method
    success = False

    if method in ("discord", "both"):
        result = await send_discord_notification(item_id, message, notification_type)
        success = success or result

    if method in ("line", "both"):
        result = await send_line_notification(item_id, message, notification_type)
        success = success or result

    if not success:
        logger.warning("通知の送信に失敗しました。設定を確認してください。")

    return success
