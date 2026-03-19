"""
Slack通知モジュール
MBO候補検出時にSlack Webhookで通知を送信
"""
import json

from config.settings import SLACK_WEBHOOK_URL, NOTIFICATION_ENABLED
from src.utils.http_client import HttpClient
from src.utils.logger import setup_logger

logger = setup_logger("slack_notifier")


class SlackNotifier:
    """Slack Webhook通知"""

    def __init__(self, http_client: HttpClient = None):
        self.client = http_client or HttpClient()
        self.webhook_url = SLACK_WEBHOOK_URL
        self.enabled = NOTIFICATION_ENABLED and bool(self.webhook_url)

    def notify_mbo_candidate(self, candidate: dict):
        """MBO候補検出を通知"""
        if not self.enabled:
            logger.debug("Slack notification is disabled")
            return

        text = self._format_mbo_message(candidate)
        self._send(text)

    def notify_new_spc(self, spc: dict):
        """新規SPC候補検出を通知"""
        if not self.enabled:
            return

        text = (
            f":mag: *新規SPC候補検出*\n"
            f"法人名: {spc.get('name', 'N/A')}\n"
            f"法人番号: {spc.get('corporate_number', 'N/A')}\n"
            f"法人形態: {spc.get('entity_type', 'N/A')}\n"
            f"SPCスコア: {spc.get('spc_score', 0):.3f}\n"
            f"所在地: {spc.get('prefecture', '')} {spc.get('city', '')}\n"
            f"備考: {spc.get('notes', '')}"
        )
        self._send(text)

    def notify_edinet_filing(self, doc: dict):
        """MBO関連EDINET書類を通知"""
        if not self.enabled:
            return

        text = (
            f":page_facing_up: *MBO関連書類 (EDINET)*\n"
            f"書類種別: {doc.get('doc_type', 'N/A')}\n"
            f"提出者: {doc.get('filer_name', 'N/A')}\n"
            f"タイトル: {doc.get('title', 'N/A')}\n"
            f"対象企業: {doc.get('target_company', 'N/A')}\n"
            f"提出日: {doc.get('filing_date', 'N/A')}"
        )
        self._send(text)

    def _format_mbo_message(self, candidate: dict) -> str:
        reasons = candidate.get("match_reasons", "")
        if isinstance(reasons, str):
            try:
                reasons = json.loads(reasons)
            except (json.JSONDecodeError, TypeError):
                pass

        if isinstance(reasons, list):
            reasons_text = "\n".join(f"  - {r}" for r in reasons)
        else:
            reasons_text = str(reasons)

        return (
            f":rotating_light: *MBO候補検出*\n"
            f"マッチスコア: {candidate.get('match_score', 0):.3f}\n"
            f"SPC法人番号: {candidate.get('spc_corporate_number', 'N/A')}\n"
            f"上場企業コード: {candidate.get('listed_company_code', 'N/A')}\n"
            f"理由:\n{reasons_text}\n"
            f"備考: {candidate.get('notes', '')}"
        )

    def _send(self, text: str):
        """Webhookにメッセージ送信"""
        try:
            import requests
            requests.post(
                self.webhook_url,
                json={"text": text},
                timeout=10,
            )
            logger.info("Slack notification sent")
        except Exception as e:
            logger.error(f"Failed to send Slack notification: {e}")
