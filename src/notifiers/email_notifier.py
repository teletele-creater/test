"""
メール通知モジュール
MBO候補検出時にメール通知を送信
"""
import json
import smtplib
from email.mime.text import MIMEText

from config.settings import (
    NOTIFICATION_ENABLED, EMAIL_SMTP_SERVER, EMAIL_FROM, EMAIL_TO,
)
from src.utils.logger import setup_logger

logger = setup_logger("email_notifier")


class EmailNotifier:
    """メール通知"""

    def __init__(self):
        self.enabled = (
            NOTIFICATION_ENABLED
            and bool(EMAIL_SMTP_SERVER)
            and bool(EMAIL_FROM)
            and bool(EMAIL_TO)
        )

    def notify_mbo_candidate(self, candidate: dict):
        """MBO候補検出をメール通知"""
        if not self.enabled:
            logger.debug("Email notification is disabled")
            return

        subject = f"[MBO検出] スコア {candidate.get('match_score', 0):.3f} - {candidate.get('notes', '')}"
        body = self._format_body(candidate)
        self._send(subject, body)

    def notify_daily_summary(self, summary: dict):
        """日次サマリーをメール通知"""
        if not self.enabled:
            return

        subject = f"[MBO監視] 日次レポート - {summary.get('date', 'N/A')}"
        body = (
            f"=== MBO監視 日次レポート ===\n\n"
            f"日付: {summary.get('date', 'N/A')}\n"
            f"新規法人取得数: {summary.get('new_corps', 0)}\n"
            f"SPC候補検出数: {summary.get('spc_candidates', 0)}\n"
            f"MBO候補マッチ数: {summary.get('mbo_matches', 0)}\n"
            f"EDINET MBO関連書類数: {summary.get('edinet_mbo_docs', 0)}\n"
            f"TDnet MBO関連開示数: {summary.get('tdnet_mbo_disclosures', 0)}\n"
        )
        self._send(subject, body)

    def _format_body(self, candidate: dict) -> str:
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
            f"MBO候補が検出されました。\n\n"
            f"マッチスコア: {candidate.get('match_score', 0):.3f}\n"
            f"SPC法人番号: {candidate.get('spc_corporate_number', 'N/A')}\n"
            f"上場企業コード: {candidate.get('listed_company_code', 'N/A')}\n"
            f"理由:\n{reasons_text}\n\n"
            f"備考: {candidate.get('notes', '')}"
        )

    def _send(self, subject: str, body: str):
        """メール送信"""
        try:
            msg = MIMEText(body, "plain", "utf-8")
            msg["Subject"] = subject
            msg["From"] = EMAIL_FROM
            msg["To"] = EMAIL_TO

            with smtplib.SMTP(EMAIL_SMTP_SERVER) as server:
                server.send_message(msg)

            logger.info(f"Email sent: {subject}")
        except Exception as e:
            logger.error(f"Failed to send email: {e}")
