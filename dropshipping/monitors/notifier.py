"""通知モジュール（Discord Webhook / LINE Notify）"""

import json

import httpx

from ..utils.config import config
from ..utils.database import record_notification
from ..utils.helpers import get_logger

logger = get_logger(__name__)


async def send_discord_notification(item_id: int, message: str) -> bool:
    """Discord Webhookで通知を送信"""
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
            response = await client.post(
                webhook_url,
                json=payload,
                timeout=10.0,
            )
            response.raise_for_status()

        logger.info(f"Discord通知送信成功: {message[:50]}...")
        record_notification(item_id, "discord", message, success=True)
        return True

    except Exception as e:
        logger.error(f"Discord通知送信失敗: {e}")
        record_notification(item_id, "discord", message, success=False)
        return False


async def send_line_notification(item_id: int, message: str) -> bool:
    """LINE Notifyで通知を送信"""
    token = config.monitor.line_notify_token
    if not token:
        logger.error("LINE Notifyトークンが設定されていません。.envファイルを確認してください。")
        return False

    headers = {"Authorization": f"Bearer {token}"}
    data = {"message": message}

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://notify-api.line.me/api/notify",
                headers=headers,
                data=data,
                timeout=10.0,
            )
            response.raise_for_status()

        logger.info(f"LINE通知送信成功: {message[:50]}...")
        record_notification(item_id, "line", message, success=True)
        return True

    except Exception as e:
        logger.error(f"LINE通知送信失敗: {e}")
        record_notification(item_id, "line", message, success=False)
        return False


async def send_notification(item_id: int, message: str) -> bool:
    """設定に基づいて通知を送信"""
    method = config.monitor.notification_method
    success = False

    if method in ("discord", "both"):
        result = await send_discord_notification(item_id, message)
        success = success or result

    if method in ("line", "both"):
        result = await send_line_notification(item_id, message)
        success = success or result

    if not success:
        logger.warning("通知の送信に失敗しました。設定を確認してください。")

    return success
